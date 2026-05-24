#!/bin/bash
set -euo pipefail

cd /app

export PATH="/usr/local/go/bin:${PATH}"

cat > /app/main.go <<'GOEOF'
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

const (
	baseDir = "/app/stream"
	outPath = "/app/audit/report.json"
)

type Vote struct {
	Stream   string
	Epoch    int
	Voter    string
	Tick     int
	Weight   int
	Phase    string
	Escrow   bool
	SliceIdx int
}

func toInt(v any) (int, bool) {
	switch n := v.(type) {
	case float64:
		if n != float64(int(n)) {
			return 0, false
		}
		return int(n), true
	default:
		return 0, false
	}
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	quorumBytes, err := os.ReadFile(filepath.Join(baseDir, "quorum.json"))
	if err != nil {
		return err
	}
	policyBytes, err := os.ReadFile(filepath.Join(baseDir, "policy.json"))
	if err != nil {
		return err
	}
	manifestBytes, err := os.ReadFile(filepath.Join(baseDir, "manifest.json"))
	if err != nil {
		return err
	}

	var quorumObj map[string]any
	var policyObj map[string]any
	var manifestObj map[string]any
	if err := json.Unmarshal(quorumBytes, &quorumObj); err != nil {
		return err
	}
	if err := json.Unmarshal(policyBytes, &policyObj); err != nil {
		return err
	}
	if err := json.Unmarshal(manifestBytes, &manifestObj); err != nil {
		return err
	}

	threshold, ok := toInt(quorumObj["threshold"])
	if !ok || threshold <= 0 {
		return fmt.Errorf("invalid quorum.json")
	}
	watermark, ok := toInt(policyObj["watermark"])
	if !ok || watermark < 0 {
		return fmt.Errorf("invalid policy.json watermark")
	}
	cutoff, ok := toInt(policyObj["cutoff"])
	if !ok || cutoff < 0 {
		return fmt.Errorf("invalid policy.json cutoff")
	}
	grace, ok := toInt(policyObj["grace"])
	if !ok || grace < 0 {
		return fmt.Errorf("invalid policy.json grace")
	}

	rawSlices, ok := manifestObj["slices"].([]any)
	if !ok {
		return fmt.Errorf("invalid manifest.json")
	}

	var votes []Vote
	rowsSeen := 0
	rowsDroppedWatermark := 0

	for sliceIdx, item := range rawSlices {
		name, ok := item.(string)
		if !ok {
			continue
		}
		path := filepath.Join(baseDir, "slices", name)
		bytes, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		var arr []any
		if err := json.Unmarshal(bytes, &arr); err != nil {
			continue
		}
		for _, elem := range arr {
			obj, ok := elem.(map[string]any)
			if !ok {
				continue
			}
			rowsSeen++
			stream, okStream := obj["stream"].(string)
			epoch, okEpoch := toInt(obj["epoch"])
			voter, okVoter := obj["voter"].(string)
			tick, okTick := toInt(obj["tick"])
			weight, okWeight := toInt(obj["weight"])
			phase, okPhase := obj["phase"].(string)
			if !okStream || stream == "" || !okEpoch || epoch < 0 || !okVoter || voter == "" ||
				!okTick || !okWeight || weight < 1 || !okPhase ||
				(phase != "prepare" && phase != "commit") {
				continue
			}
			late, _ := obj["late"].(bool)
			if tick < watermark && !late {
				rowsDroppedWatermark++
				continue
			}
			escrow, _ := obj["escrow"].(bool)
			votes = append(votes, Vote{
				Stream: stream, Epoch: epoch, Voter: voter, Tick: tick,
				Weight: weight, Phase: phase, Escrow: escrow, SliceIdx: sliceIdx,
			})
		}
	}

	type triple struct {
		stream, voter string
		epoch         int
	}
	dedup := map[triple]Vote{}
	rowsDeduped := 0
	for _, v := range votes {
		key := triple{stream: v.Stream, epoch: v.Epoch, voter: v.Voter}
		cur, exists := dedup[key]
		if !exists {
			dedup[key] = v
			continue
		}
		if v.Tick > cur.Tick || (v.Tick == cur.Tick && v.SliceIdx > cur.SliceIdx) {
			dedup[key] = v
		}
		rowsDeduped++
	}

	type groupKey struct {
		stream, phase string
		epoch         int
	}
	groups := map[groupKey][]Vote{}
	for _, v := range dedup {
		gk := groupKey{stream: v.Stream, epoch: v.Epoch, phase: v.Phase}
		groups[gk] = append(groups[gk], v)
	}

	countedWeight := func(members []Vote) int {
		sum := 0
		for _, m := range members {
			if m.Tick >= watermark {
				sum += m.Weight
			}
		}
		return sum
	}

	type pair struct {
		stream string
		epoch  int
	}
	prepareQuorate := map[pair]bool{}
	type groupMeta struct {
		key        groupKey
		status     string
		weightSum  int
		countedSum int
		voters     []string
		members    []Vote
	}
	groupMetaMap := map[groupKey]groupMeta{}

	var prepareKeys []groupKey
	for gk := range groups {
		if gk.phase == "prepare" {
			prepareKeys = append(prepareKeys, gk)
		}
	}
	sort.Slice(prepareKeys, func(i, j int) bool {
		a, b := prepareKeys[i], prepareKeys[j]
		if a.stream != b.stream {
			return a.stream < b.stream
		}
		return a.epoch < b.epoch
	})

	for _, gk := range prepareKeys {
		members := groups[gk]
		rawSum := 0
		voters := make([]string, 0, len(members))
		for _, m := range members {
			rawSum += m.Weight
			voters = append(voters, m.Voter)
		}
		sort.Strings(voters)
		counted := countedWeight(members)
		status := "open"
		if counted >= threshold {
			status = "quorum"
		}
		meta := groupMeta{
			key: gk, status: status, weightSum: rawSum, countedSum: counted,
			voters: voters, members: members,
		}
		groupMetaMap[gk] = meta
		if status == "quorum" {
			pk := pair{stream: gk.stream, epoch: gk.epoch}
			if gk.epoch == 0 || prepareQuorate[pair{stream: gk.stream, epoch: gk.epoch - 1}] {
				prepareQuorate[pk] = true
			}
		}
	}

	var commitKeys []groupKey
	for gk := range groups {
		if gk.phase == "commit" {
			commitKeys = append(commitKeys, gk)
		}
	}
	sort.Slice(commitKeys, func(i, j int) bool {
		a, b := commitKeys[i], commitKeys[j]
		if a.stream != b.stream {
			return a.stream < b.stream
		}
		return a.epoch < b.epoch
	})

	for _, gk := range commitKeys {
		members := groups[gk]
		rawSum := 0
		voters := make([]string, 0, len(members))
		for _, m := range members {
			rawSum += m.Weight
			voters = append(voters, m.Voter)
		}
		sort.Strings(voters)
		pk := pair{stream: gk.stream, epoch: gk.epoch}
		counted := countedWeight(members)
		if !prepareQuorate[pk] {
			counted = 0
			for _, m := range members {
				if m.Escrow && m.Tick >= watermark {
					counted += m.Weight
				}
			}
		}
		status := "open"
		if counted >= threshold {
			status = "quorum"
		}
		groupMetaMap[gk] = groupMeta{
			key: gk, status: status, weightSum: rawSum, countedSum: counted,
			voters: voters, members: members,
		}
	}

	var stale []map[string]any
	for _, meta := range groupMetaMap {
		if meta.status != "open" {
			continue
		}
		pk := pair{stream: meta.key.stream, epoch: meta.key.epoch}
		prepOK := prepareQuorate[pk]
		for _, m := range meta.members {
			if m.Tick+grace >= cutoff {
				continue
			}
			if meta.key.phase == "commit" && !prepOK && m.Escrow {
				continue
			}
			stale = append(stale, map[string]any{
				"code":   "LATE_TICK",
				"epoch":  meta.key.epoch,
				"phase":  meta.key.phase,
				"stream": meta.key.stream,
				"tick":   m.Tick,
				"voter":  m.Voter,
			})
		}
	}
	sort.Slice(stale, func(i, j int) bool {
		ai, aj := stale[i], stale[j]
		if ai["stream"].(string) != aj["stream"].(string) {
			return ai["stream"].(string) < aj["stream"].(string)
		}
		if ai["epoch"].(int) != aj["epoch"].(int) {
			return ai["epoch"].(int) < aj["epoch"].(int)
		}
		if ai["phase"].(string) != aj["phase"].(string) {
			return ai["phase"].(string) < aj["phase"].(string)
		}
		if ai["voter"].(string) != aj["voter"].(string) {
			return ai["voter"].(string) < aj["voter"].(string)
		}
		return ai["tick"].(int) < aj["tick"].(int)
	})

	type streamEpoch struct {
		stream string
		epoch  int
	}
	bySE := map[streamEpoch][]groupMeta{}
	for gk, meta := range groupMetaMap {
		se := streamEpoch{stream: gk.stream, epoch: gk.epoch}
		bySE[se] = append(bySE[se], meta)
	}

	var seKeys []streamEpoch
	for se := range bySE {
		seKeys = append(seKeys, se)
	}
	sort.Slice(seKeys, func(i, j int) bool {
		if seKeys[i].stream != seKeys[j].stream {
			return seKeys[i].stream < seKeys[j].stream
		}
		return seKeys[i].epoch < seKeys[j].epoch
	})

	var ballots []map[string]any
	for _, se := range seKeys {
		metas := bySE[se]
		sort.Slice(metas, func(i, j int) bool {
			return metas[i].key.phase < metas[j].key.phase
		})
		var phases []any
		for _, meta := range metas {
			phases = append(phases, []any{meta.key.phase, meta.status, meta.weightSum, meta.voters})
		}
		ballots = append(ballots, map[string]any{
			"epoch":  se.epoch,
			"phases": phases,
			"stream": se.stream,
		})
	}

	var decisions []map[string]any
	groupsQuorum := 0
	var metaList []groupMeta
	for _, meta := range groupMetaMap {
		metaList = append(metaList, meta)
	}
	sort.Slice(metaList, func(i, j int) bool {
		a, b := metaList[i].key, metaList[j].key
		if a.stream != b.stream {
			return a.stream < b.stream
		}
		if a.epoch != b.epoch {
			return a.epoch < b.epoch
		}
		return a.phase < b.phase
	})
	for _, meta := range metaList {
		if meta.status == "quorum" {
			groupsQuorum++
			decisions = append(decisions, map[string]any{
				"counted_sum": meta.countedSum,
				"epoch":       meta.key.epoch,
				"phase":       meta.key.phase,
				"stream":      meta.key.stream,
			})
		}
	}

	report := map[string]any{
		"ballots": ballots,
		"decisions": decisions,
		"stale": stale,
		"summary": map[string]any{
			"groups_quorum":          groupsQuorum,
			"groups_total":           len(groupMetaMap),
			"rows_deduped":           rowsDeduped,
			"rows_dropped_watermark": rowsDroppedWatermark,
			"rows_seen":              rowsSeen,
			"stale_logged":           len(stale),
		},
	}

	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		return err
	}
	buf, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(outPath, buf, 0o644)
}
GOEOF

mkdir -p /app/audit
go mod init streamquorum >/dev/null 2>&1 || true
go run /app/main.go
