package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type policy struct {
	EpochSpan    int `json:"epoch_span"`
	GraceEpochs  int `json:"grace_epochs"`
	WeightFloor  int `json:"weight_floor"`
}

type poolState struct {
	CurrentEpoch int `json:"current_epoch"`
	EpochEnd     int `json:"epoch_end"`
	EpochStart   int `json:"epoch_start"`
}

type keyRec struct {
	ClaimEpoch int    `json:"claim_epoch"`
	KeyHash    string `json:"key_hash"`
	OwnerNode  string `json:"owner_node"`
	Weight     int    `json:"weight"`
}

type nodeRec struct {
	LastSeenEpoch int    `json:"last_seen_epoch"`
	NodeID        string `json:"node_id"`
	Tier          string `json:"tier"`
	Weight        int    `json:"weight"`
}

type migrationRec struct {
	Epoch        int    `json:"epoch"`
	FromNode     string `json:"from_node"`
	KeyHash      string `json:"key_hash"`
	MigrationID  string `json:"migration_id"`
	ToNode       string `json:"to_node"`
}

type incidentEvent struct {
	Accepted bool   `json:"accepted"`
	Epoch    int    `json:"epoch"`
	Kind     string `json:"kind"`
	NodeID   string `json:"node_id"`
}

type overlayState struct {
	MinMigrationsPerBucket int
	BucketCap              int
	ExcludeNodes           map[string]struct{}
}

type anchorNote struct {
	NodeID       string
	ForcedStatus string
	Order        int
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	data := getenv("KME_DATA_DIR", "/app/keymigrate")
	outd := getenv("KME_AUDIT_DIR", "/app/audit")
	if err := run(data, outd); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func run(dataDir, auditDir string) error {
	var pol policy
	if err := readJSON(filepath.Join(dataDir, "policy.json"), &pol); err != nil {
		return err
	}
	var ps poolState
	if err := readJSON(filepath.Join(dataDir, "pool_state.json"), &ps); err != nil {
		return err
	}
	if pol.EpochSpan <= 0 {
		return fmt.Errorf("invalid epoch_span")
	}

	ov, err := loadOverlays(filepath.Join(dataDir, "overlays"))
	if err != nil {
		return err
	}
	compromised, err := loadCompromisedNodes(filepath.Join(dataDir, "incidents.json"))
	if err != nil {
		return err
	}
	anchors, err := loadAnchors(dataDir)
	if err != nil {
		return err
	}

	nodes, err := loadNodes(filepath.Join(dataDir, "nodes"))
	if err != nil {
		return err
	}
	keys, err := loadKeys(filepath.Join(dataDir, "keys"))
	if err != nil {
		return err
	}
	migrations, err := loadMigrations(filepath.Join(dataDir, "migrations"))
	if err != nil {
		return err
	}

	sort.Slice(nodes, func(i, j int) bool { return nodes[i].NodeID < nodes[j].NodeID })
	sort.Slice(keys, func(i, j int) bool { return keys[i].KeyHash < keys[j].KeyHash })

	nodeSet := map[string]struct{}{}
	for _, n := range nodes {
		nodeSet[n.NodeID] = struct{}{}
	}

	forced := map[string]string{}
	sort.Slice(anchors, func(i, j int) bool {
		if anchors[i].NodeID != anchors[j].NodeID {
			return anchors[i].NodeID < anchors[j].NodeID
		}
		return anchors[i].Order < anchors[j].Order
	})
	for _, a := range anchors {
		if _, ok := nodeSet[a.NodeID]; ok {
			forced[a.NodeID] = a.ForcedStatus
		}
	}

	migsByKey := map[string][]migrationRec{}
	for _, m := range migrations {
		if m.Epoch < ps.EpochStart || m.Epoch > ps.EpochEnd {
			continue
		}
		migsByKey[m.KeyHash] = append(migsByKey[m.KeyHash], m)
	}
	for k := range migsByKey {
		sort.Slice(migsByKey[k], func(i, j int) bool {
			a, b := migsByKey[k][i], migsByKey[k][j]
			if a.Epoch != b.Epoch {
				return a.Epoch < b.Epoch
			}
			return a.MigrationID < b.MigrationID
		})
	}

	complete := completeBuckets(ps.EpochStart, ps.EpochEnd, pol.EpochSpan)

	type keyOutcome struct {
		initialOwner    string
		finalOwner      string
		status          string
		migrationCount  int
		dropped         bool
		quarantined     bool
		appliedMigs     []migrationRec
	}

	outcomes := make([]keyOutcome, 0, len(keys))
	heldByNode := map[string][]string{}
	quarantinedTotal := 0
	droppedTotal := 0

	for _, k := range keys {
		owner := k.OwnerNode
		applied := make([]migrationRec, 0)
		for _, m := range migsByKey[k.KeyHash] {
			if m.FromNode == owner {
				owner = m.ToNode
				applied = append(applied, m)
			}
		}

		dropped := k.Weight < pol.WeightFloor
		_, touchesCompromise := compromised[k.OwnerNode]
		if !touchesCompromise {
			_, touchesCompromise = compromised[owner]
		}
		for _, m := range applied {
			if _, ok := compromised[m.FromNode]; ok {
				touchesCompromise = true
			}
			if _, ok := compromised[m.ToNode]; ok {
				touchesCompromise = true
			}
		}

		status := "ok"
		switch {
		case touchesCompromise:
			status = "quarantined"
			quarantinedTotal++
		case forced[owner] == "hold":
			status = "hold"
		case dropped:
			status = "dropped"
			droppedTotal++
		}

		outcomes = append(outcomes, keyOutcome{
			initialOwner:   k.OwnerNode,
			finalOwner:     owner,
			status:         status,
			migrationCount: len(applied),
			dropped:        dropped,
			quarantined:    touchesCompromise,
			appliedMigs:    applied,
		})

		if status != "quarantined" && status != "dropped" {
			heldByNode[owner] = append(heldByNode[owner], k.KeyHash)
		}
	}

	keyProfiles := make([]map[string]any, 0, len(keys))
	for i, k := range keys {
		o := outcomes[i]
		keyProfiles = append(keyProfiles, map[string]any{
			"final_owner":      o.finalOwner,
			"initial_owner":    o.initialOwner,
			"key_hash":         k.KeyHash,
			"migration_count":  o.migrationCount,
			"status":           o.status,
		})
	}

	for nid := range heldByNode {
		sort.Strings(heldByNode[nid])
	}

	nodeProfiles := make([]map[string]any, 0, len(nodes))
	staleRows := make([]map[string]any, 0)
	staleTotal := 0

	for _, n := range nodes {
		_, quar := compromised[n.NodeID]
		stale := ps.CurrentEpoch-n.LastSeenEpoch > pol.GraceEpochs
		if stale {
			staleTotal++
		}

		status := "ok"
		switch {
		case quar:
			status = "quarantined"
		case forced[n.NodeID] == "hold":
			status = "hold"
		case stale:
			status = "stale"
		}

		var weightAny any = n.Weight
		if quar {
			weightAny = nil
		}

		held := heldByNode[n.NodeID]
		if held == nil {
			held = []string{}
		}

		nodeProfiles = append(nodeProfiles, map[string]any{
			"effective_weight": weightAny,
			"keys_held":        held,
			"last_seen_epoch":  n.LastSeenEpoch,
			"node_id":          n.NodeID,
			"stale_flag":       stale,
			"status":           status,
			"tier":             n.Tier,
		})

		if stale && !quar {
			staleRows = append(staleRows, map[string]any{
				"last_seen_epoch": n.LastSeenEpoch,
				"node_id":         n.NodeID,
			})
		}
	}

	bucketsOut := make([]map[string]any, 0, len(complete))
	for _, bStart := range complete {
		bEnd := bStart + pol.EpochSpan - 1
		candidates := make([]migrationRec, 0)
		for i := range keys {
			o := outcomes[i]
			if o.status == "quarantined" || o.status == "dropped" {
				continue
			}
			for _, m := range o.appliedMigs {
				if m.Epoch < bStart || m.Epoch > bEnd {
					continue
				}
				if _, ex := ov.ExcludeNodes[m.FromNode]; ex {
					continue
				}
				if _, ex := ov.ExcludeNodes[m.ToNode]; ex {
					continue
				}
				candidates = append(candidates, m)
			}
		}
		sort.Slice(candidates, func(i, j int) bool {
			return candidates[i].MigrationID < candidates[j].MigrationID
		})
		if len(candidates) < ov.MinMigrationsPerBucket {
			continue
		}
		if len(candidates) > ov.BucketCap {
			candidates = candidates[:ov.BucketCap]
		}
		rows := make([]map[string]any, 0, len(candidates))
		for _, m := range candidates {
			rows = append(rows, map[string]any{
				"epoch":         m.Epoch,
				"from_node":     m.FromNode,
				"key_hash":      m.KeyHash,
				"migration_id":  m.MigrationID,
				"to_node":       m.ToNode,
			})
		}
		bucketsOut = append(bucketsOut, map[string]any{
			"epoch_start": bStart,
			"migrations":  rows,
		})
	}

	compromiseKeys := make([]map[string]any, 0)
	for i, k := range keys {
		if outcomes[i].status == "quarantined" {
			compromiseKeys = append(compromiseKeys, map[string]any{
				"final_owner":   outcomes[i].finalOwner,
				"initial_owner": outcomes[i].initialOwner,
				"key_hash":      k.KeyHash,
			})
		}
	}
	sort.Slice(compromiseKeys, func(i, j int) bool {
		return fmt.Sprint(compromiseKeys[i]["key_hash"]) < fmt.Sprint(compromiseKeys[j]["key_hash"])
	})

	nodeList := make([]string, 0, len(compromised))
	for nid := range compromised {
		nodeList = append(nodeList, nid)
	}
	sort.Strings(nodeList)

	sort.Slice(staleRows, func(i, j int) bool {
		return fmt.Sprint(staleRows[i]["node_id"]) < fmt.Sprint(staleRows[j]["node_id"])
	})

	payloads := map[string]any{
		"compromise_report.json": map[string]any{
			"keys":  compromiseKeys,
			"nodes": nodeList,
		},
		"key_profiles.json": map[string]any{
			"epoch_end":   ps.EpochEnd,
			"epoch_start": ps.EpochStart,
			"keys":        keyProfiles,
		},
		"migration_rollups.json": map[string]any{
			"buckets":     bucketsOut,
			"epoch_end":   ps.EpochEnd,
			"epoch_start": ps.EpochStart,
		},
		"stale_report.json": map[string]any{"nodes": staleRows},
		"summary.json": map[string]any{
			"complete_epoch_starts": complete,
			"current_epoch":         ps.CurrentEpoch,
			"dropped_total":         droppedTotal,
			"epoch_count":           len(complete),
			"epoch_end":             ps.EpochEnd,
			"epoch_start":           ps.EpochStart,
			"keys_total":            len(keys),
			"quarantined_total":     quarantinedTotal,
			"stale_total":           staleTotal,
		},
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	for name, payload := range payloads {
		if err := writeJSON(filepath.Join(auditDir, name), payload); err != nil {
			return err
		}
	}
	return nil
}

func completeBuckets(es, ee, span int) []int {
	out := make([]int, 0)
	for b := es; b+span-1 <= ee; b += span {
		out = append(out, b)
	}
	return out
}

func loadOverlays(dir string) (overlayState, error) {
	st := overlayState{
		MinMigrationsPerBucket: 1,
		BucketCap:              1 << 30,
		ExcludeNodes:           map[string]struct{}{},
	}
	ents, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return st, nil
		}
		return st, err
	}
	names := make([]string, 0)
	for _, e := range ents {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".json") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		var raw map[string]json.RawMessage
		if err := readJSON(filepath.Join(dir, name), &raw); err != nil {
			return st, err
		}
		if v, ok := raw["min_migrations_per_bucket"]; ok {
			var n int
			if json.Unmarshal(v, &n) == nil && n > 0 {
				st.MinMigrationsPerBucket = n
			}
		}
		if v, ok := raw["bucket_cap"]; ok {
			var n int
			if json.Unmarshal(v, &n) == nil && n > 0 {
				st.BucketCap = n
			}
		}
		if v, ok := raw["exclude_nodes"]; ok {
			var ids []string
			if json.Unmarshal(v, &ids) == nil {
				for _, id := range ids {
					st.ExcludeNodes[id] = struct{}{}
				}
			}
		}
	}
	return st, nil
}

func loadCompromisedNodes(path string) (map[string]struct{}, error) {
	out := map[string]struct{}{}
	var raw struct {
		Events []incidentEvent `json:"events"`
	}
	if err := readJSON(path, &raw); err != nil {
		return out, err
	}
	for _, ev := range raw.Events {
		if ev.Accepted && ev.Kind == "node_compromise" {
			out[ev.NodeID] = struct{}{}
		}
	}
	return out, nil
}

func loadAnchors(dataDir string) ([]anchorNote, error) {
	var notes []anchorNote
	order := 0
	anchorDir := filepath.Join(dataDir, "anchors")
	ents, err := os.ReadDir(anchorDir)
	if err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	names := make([]string, 0)
	for _, e := range ents {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".txt") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		b, err := os.ReadFile(filepath.Join(anchorDir, name))
		if err != nil {
			return nil, err
		}
		for _, line := range strings.Split(string(b), "\n") {
			line = strings.TrimSpace(line)
			if line == "" {
				continue
			}
			parts := strings.Fields(line)
			if len(parts) < 2 {
				continue
			}
			notes = append(notes, anchorNote{
				NodeID:       parts[0],
				ForcedStatus: parts[1],
				Order:        order,
			})
			order++
		}
	}
	return notes, nil
}

func loadNodes(dir string) ([]nodeRec, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make([]nodeRec, 0)
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var n nodeRec
		if err := readJSON(filepath.Join(dir, e.Name()), &n); err != nil {
			return nil, err
		}
		out = append(out, n)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no nodes")
	}
	return out, nil
}

func loadKeys(dir string) ([]keyRec, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make([]keyRec, 0)
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var k keyRec
		if err := readJSON(filepath.Join(dir, e.Name()), &k); err != nil {
			return nil, err
		}
		out = append(out, k)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no keys")
	}
	return out, nil
}

func loadMigrations(dir string) ([]migrationRec, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	out := make([]migrationRec, 0)
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var m migrationRec
		if err := readJSON(filepath.Join(dir, e.Name()), &m); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, nil
}

func readJSON(path string, v any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, v)
}

func writeJSON(path string, v any) error {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(true)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		return err
	}
	return os.WriteFile(path, buf.Bytes(), 0o644)
}
