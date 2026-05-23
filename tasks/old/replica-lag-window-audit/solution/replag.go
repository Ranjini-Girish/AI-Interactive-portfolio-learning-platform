package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type policyFile struct {
	GraceDaysAfterFailover int `json:"grace_days_after_failover"`
	MedianRejectRatio      float64 `json:"median_reject_ratio"`
	MedianWindowK          int `json:"median_window_k"`
	TierThresholds         map[string]struct {
		CriticalLagBytes int `json:"critical_lag_bytes"`
		WarnLagBytes     int `json:"warn_lag_bytes"`
	} `json:"tier_thresholds"`
	WitnessSkewBytes int `json:"witness_skew_bytes"`
}

type poolFile struct {
	CurrentDay int `json:"current_day"`
}

type depsFile struct {
	Edges []struct {
		Child  string `json:"child"`
		Parent string `json:"parent"`
	} `json:"edges"`
}

type incidentsFile struct {
	Events []map[string]any `json:"events"`
}

type sampleRow struct {
	Day              int `json:"day"`
	LagBytes         int `json:"lag_bytes"`
	WitnessLagBytes  int `json:"witness_lag_bytes"`
}

type shardFile struct {
	Samples []sampleRow `json:"samples"`
	ShardID string      `json:"shard_id"`
	Tier    string      `json:"tier"`
}

type profileRow struct {
	EffectiveLagBytes int    `json:"effective_lag_bytes"`
	Embargoed         bool   `json:"embargoed"`
	FinalVerdict      string `json:"final_verdict"`
	FlushStatus       string `json:"flush_status"`
	GraceActive       bool   `json:"grace_active"`
	ShardID           string `json:"shard_id"`
	Tier              string `json:"tier"`
	WitnessDesync     bool   `json:"witness_desync"`
}

func medianInt(vals []int) int {
	if len(vals) == 0 {
		return 0
	}
	s := append([]int(nil), vals...)
	sort.Ints(s)
	n := len(s)
	mid := n / 2
	if n%2 == 1 {
		return s[mid]
	}
	return (s[mid-1] + s[mid]) / 2
}

func effectiveLag(samples []sampleRow, k int, rejectRatio float64) int {
	ordered := append([]sampleRow(nil), samples...)
	sort.Slice(ordered, func(i, j int) bool {
		return ordered[i].Day < ordered[j].Day
	})
	window := ordered
	if len(window) > k {
		window = window[len(window)-k:]
	}
	lags := make([]int, len(window))
	for i, s := range window {
		lags[i] = s.LagBytes
	}
	med := medianInt(lags)
	var kept []int
	if med == 0 {
		kept = lags
	} else {
		thresh := rejectRatio * float64(med)
		for _, v := range lags {
			diff := v - med
			if diff < 0 {
				diff = -diff
			}
			if float64(diff) <= thresh {
				kept = append(kept, v)
			}
		}
	}
	if len(kept) == 0 {
		return 0
	}
	return medianInt(kept)
}

func lagVerdict(eff int, tier string, policy policyFile) string {
	t := policy.TierThresholds[tier]
	if eff < t.WarnLagBytes {
		return "lag_ok"
	}
	if eff < t.CriticalLagBytes {
		return "lag_warn"
	}
	return "lag_critical"
}

func writeJSON(path string, v any) error {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(path, data, 0o644)
}

func main() {
	dataDir := os.Getenv("RLA_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/replag"
	}
	auditDir := os.Getenv("RLA_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "mkdir audit: %v\n", err)
		os.Exit(1)
	}

	var policy policyFile
	mustReadJSON(filepath.Join(dataDir, "policy.json"), &policy)
	var pool poolFile
	mustReadJSON(filepath.Join(dataDir, "pool_state.json"), &pool)
	var deps depsFile
	mustReadJSON(filepath.Join(dataDir, "dependencies.json"), &deps)
	var incidents incidentsFile
	mustReadJSON(filepath.Join(dataDir, "incidents.json"), &incidents)

	currentDay := pool.CurrentDay
	shards := map[string]shardFile{}
	var shardIDs []string
	entries, _ := filepath.Glob(filepath.Join(dataDir, "shards", "*.json"))
	sort.Strings(entries)
	for _, p := range entries {
		var sh shardFile
		mustReadJSON(p, &sh)
		shardIDs = append(shardIDs, sh.ShardID)
		shards[sh.ShardID] = sh
	}
	sort.Strings(shardIDs)

	parents := map[string][]string{}
	children := map[string][]string{}
	for _, e := range deps.Edges {
		if _, okP := shards[e.Parent]; !okP {
			continue
		}
		if _, okC := shards[e.Child]; !okC {
			continue
		}
		parents[e.Child] = append(parents[e.Child], e.Parent)
		children[e.Parent] = append(children[e.Parent], e.Child)
	}
	for k := range parents {
		sort.Strings(parents[k])
	}
	for k := range children {
		sort.Strings(children[k])
	}

	embargoed := map[string]bool{}
	failoverDay := map[string]int{}
	forced := map[string]string{}
	frozen := map[string]bool{}
	var applied []map[string]any

	type evKey struct {
		day int
		sid string
	}
	var sortedEvents []map[string]any
	for _, ev := range incidents.Events {
		day := intFromAny(ev["day"])
		if day > currentDay {
			continue
		}
		sortedEvents = append(sortedEvents, ev)
	}
	sort.Slice(sortedEvents, func(i, j int) bool {
		di := intFromAny(sortedEvents[i]["day"])
		dj := intFromAny(sortedEvents[j]["day"])
		if di != dj {
			return di < dj
		}
		return fmt.Sprint(sortedEvents[i]["shard_id"]) < fmt.Sprint(sortedEvents[j]["shard_id"])
	})

	for _, ev := range sortedEvents {
		sid := fmt.Sprint(ev["shard_id"])
		kind := fmt.Sprint(ev["kind"])
		day := intFromAny(ev["day"])
		if _, ok := shards[sid]; !ok {
			continue
		}
		switch kind {
		case "embargo_downstream":
			queue := []string{sid}
			seen := map[string]bool{}
			for len(queue) > 0 {
				node := queue[0]
				queue = queue[1:]
				if seen[node] {
					continue
				}
				seen[node] = true
				embargoed[node] = true
				for _, ch := range children[node] {
					queue = append(queue, ch)
				}
			}
			applied = append(applied, map[string]any{
				"day": day, "effect": "embargo", "kind": kind, "shard_id": sid,
			})
		case "failover":
			failoverDay[sid] = day
			applied = append(applied, map[string]any{
				"day": day, "effect": "failover", "kind": kind, "shard_id": sid,
			})
		case "force_lag_verdict":
			forced[sid] = fmt.Sprint(ev["forced_verdict"])
			applied = append(applied, map[string]any{
				"day": day, "effect": "force", "kind": kind, "shard_id": sid,
			})
		case "freeze_shard":
			frozen[sid] = true
			applied = append(applied, map[string]any{
				"day": day, "effect": "freeze", "kind": kind, "shard_id": sid,
			})
		}
	}
	_ = evKey{}

	cycles := findCycles(shardIDs, children)
	cycleNodes := map[string]bool{}
	for _, c := range cycles {
		for _, id := range c {
			cycleNodes[id] = true
		}
	}

	profiles := map[string]profileRow{}
	for _, sid := range shardIDs {
		sh := shards[sid]
		eff := effectiveLag(sh.Samples, policy.MedianWindowK, policy.MedianRejectRatio)
		ordered := append([]sampleRow(nil), sh.Samples...)
		sort.Slice(ordered, func(i, j int) bool { return ordered[i].Day < ordered[j].Day })
		latest := ordered[len(ordered)-1]
		wdesync := latest.WitnessLagBytes-latest.LagBytes > policy.WitnessSkewBytes
		graceActive := false
		if f, ok := failoverDay[sid]; ok {
			graceActive = currentDay <= f+policy.GraceDaysAfterFailover-1
		}
		verdict := lagVerdict(eff, sh.Tier, policy)
		if graceActive && (verdict == "lag_warn" || verdict == "lag_critical") {
			verdict = "lag_ok"
		}
		if fv, ok := forced[sid]; ok {
			verdict = fv
		}
		if frozen[sid] {
			verdict = "frozen"
		}
		if embargoed[sid] {
			verdict = "embargoed"
		}
		if wdesync && verdict != "frozen" {
			verdict = "hold"
		}
		profiles[sid] = profileRow{
			EffectiveLagBytes: eff,
			Embargoed:         embargoed[sid],
			FinalVerdict:      verdict,
			GraceActive:       graceActive,
			ShardID:           sid,
			Tier:              sh.Tier,
			WitnessDesync:     wdesync,
		}
	}

	flushStatus := map[string]string{}
	for _, sid := range shardIDs {
		p := profiles[sid]
		switch {
		case frozen[sid]:
			flushStatus[sid] = "blocked_frozen"
		case embargoed[sid]:
			flushStatus[sid] = "blocked_embargo"
		case p.WitnessDesync:
			flushStatus[sid] = "blocked_witness"
		case cycleNodes[sid]:
			flushStatus[sid] = "blocked_cycle"
		case p.FinalVerdict == "lag_ok":
			flushStatus[sid] = "flush_ready"
		default:
			flushStatus[sid] = "not_due"
		}
	}
	changed := true
	for changed {
		changed = false
		for _, sid := range shardIDs {
			if flushStatus[sid] != "flush_ready" {
				continue
			}
			for _, par := range parents[sid] {
				if profiles[par].FinalVerdict != "lag_ok" || flushStatus[par] != "flush_ready" {
					flushStatus[sid] = "blocked_parent"
					changed = true
					break
				}
			}
		}
	}

	for sid := range profiles {
		p := profiles[sid]
		p.FlushStatus = flushStatus[sid]
		profiles[sid] = p
	}

	order := topoOrder(shardIDs, cycleNodes, parents, children)

	flushEntries := make([]map[string]any, 0, len(shardIDs))
	for _, sid := range shardIDs {
		flushEntries = append(flushEntries, map[string]any{
			"flush_status": flushStatus[sid],
			"reasons":      reasonsFor(sid, flushStatus, profiles, parents),
			"shard_id":     sid,
		})
	}

	profileList := make([]profileRow, 0, len(shardIDs))
	for _, sid := range shardIDs {
		profileList = append(profileList, profiles[sid])
	}

	tiers := map[string]map[string]int{}
	for tier := range policy.TierThresholds {
		tiers[tier] = map[string]int{"lag_critical": 0, "lag_ok": 0, "lag_warn": 0}
	}
	holdTotal := 0
	flushReady := 0
	for _, sid := range shardIDs {
		p := profiles[sid]
		if p.FinalVerdict == "hold" {
			holdTotal++
		}
		if flushStatus[sid] == "flush_ready" {
			flushReady++
		}
		if p.FinalVerdict == "lag_ok" || p.FinalVerdict == "lag_warn" || p.FinalVerdict == "lag_critical" {
			tiers[p.Tier][p.FinalVerdict]++
		}
	}

	mustWriteJSON(filepath.Join(auditDir, "shard_profiles.json"), map[string]any{
		"current_day": currentDay,
		"profiles":    profileList,
	})
	mustWriteJSON(filepath.Join(auditDir, "dependency_plan.json"), map[string]any{
		"cycles": cycles,
		"order":  order,
	})
	mustWriteJSON(filepath.Join(auditDir, "flush_plan.json"), map[string]any{"entries": flushEntries})
	mustWriteJSON(filepath.Join(auditDir, "incident_trace.json"), map[string]any{"applied": applied})
	mustWriteJSON(filepath.Join(auditDir, "summary.json"), map[string]any{
		"current_day":       currentDay,
		"flush_ready_total": flushReady,
		"hold_total":        holdTotal,
		"shards_total":      len(shardIDs),
		"tiers":             tiers,
	})
}

func reasonsFor(sid string, flush map[string]string, profiles map[string]profileRow, parents map[string][]string) []string {
	st := flush[sid]
	switch st {
	case "blocked_frozen":
		return []string{"frozen"}
	case "blocked_embargo":
		return []string{"embargo"}
	case "blocked_witness":
		return []string{"witness_desync"}
	case "blocked_cycle":
		return []string{"cycle"}
	case "blocked_parent":
		var rs []string
		for _, par := range parents[sid] {
			if profiles[par].FinalVerdict != "lag_ok" || flush[par] != "flush_ready" {
				rs = append(rs, "parent:"+par)
			}
		}
		sort.Strings(rs)
		return rs
	case "not_due":
		return []string{"lag"}
	default:
		return []string{}
	}
}

func topoOrder(shardIDs []string, cycleNodes map[string]bool, parents, children map[string][]string) []string {
	inDeg := map[string]int{}
	for _, sid := range shardIDs {
		if cycleNodes[sid] {
			continue
		}
		inDeg[sid] = 0
	}
	for sid := range inDeg {
		for _, par := range parents[sid] {
			if _, ok := inDeg[par]; ok {
				inDeg[sid]++
			}
		}
	}
	var order []string
	ready := make([]string, 0)
	for sid := range inDeg {
		if inDeg[sid] == 0 {
			ready = append(ready, sid)
		}
	}
	sort.Strings(ready)
	for len(ready) > 0 {
		n := ready[0]
		ready = ready[1:]
		order = append(order, n)
		var newly []string
		for _, ch := range children[n] {
			if _, ok := inDeg[ch]; !ok {
				continue
			}
			inDeg[ch]--
			if inDeg[ch] == 0 {
				newly = append(newly, ch)
			}
		}
		ready = append(ready, newly...)
		sort.Strings(ready)
	}
	return order
}

func findCycles(shardIDs []string, children map[string][]string) [][]string {
	index := 0
	stack := []string{}
	onStack := map[string]bool{}
	indices := map[string]int{}
	lowlink := map[string]int{}
	var sccs [][]string

	var strong func(v string)
	strong = func(v string) {
		indices[v] = index
		lowlink[v] = index
		index++
		stack = append(stack, v)
		onStack[v] = true
		for _, w := range children[v] {
			if _, ok := indices[w]; !ok {
				strong(w)
				if lowlink[w] < lowlink[v] {
					lowlink[v] = lowlink[w]
				}
			} else if onStack[w] {
				if indices[w] < lowlink[v] {
					lowlink[v] = indices[w]
				}
			}
		}
		if lowlink[v] == indices[v] {
			var comp []string
			for {
				w := stack[len(stack)-1]
				stack = stack[:len(stack)-1]
				delete(onStack, w)
				comp = append(comp, w)
				if w == v {
					break
				}
			}
			if len(comp) > 1 {
				sort.Strings(comp)
				sccs = append(sccs, comp)
			}
		}
	}
	for _, sid := range shardIDs {
		if _, ok := indices[sid]; !ok {
			strong(sid)
		}
	}
	sort.Slice(sccs, func(i, j int) bool { return sccs[i][0] < sccs[j][0] })
	return sccs
}

func intFromAny(v any) int {
	switch x := v.(type) {
	case float64:
		return int(x)
	case int:
		return x
	default:
		return 0
	}
}

func mustReadJSON(path string, v any) {
	data, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(data, v); err != nil {
		panic(err)
	}
}

func mustWriteJSON(path string, v any) {
	if err := writeJSON(path, v); err != nil {
		panic(err)
	}
}
