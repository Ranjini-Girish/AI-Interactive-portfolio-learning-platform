package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type tierThreshold struct {
	WarnLagBytes     int64 `json:"warn_lag_bytes"`
	CriticalLagBytes int64 `json:"critical_lag_bytes"`
}

type policy struct {
	GraceDaysAfterFailover int                        `json:"grace_days_after_failover"`
	MedianRejectRatio      float64                    `json:"median_reject_ratio"`
	MedianWindowK          int                        `json:"median_window_k"`
	TierThresholds         map[string]tierThreshold `json:"tier_thresholds"`
	WitnessSkewBytes       int64                      `json:"witness_skew_bytes"`
}

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type dependencies struct {
	Edges []struct {
		Parent string `json:"parent"`
		Child  string `json:"child"`
	} `json:"edges"`
}

type incidentEvent struct {
	Day           int    `json:"day"`
	ForcedVerdict string `json:"forced_verdict"`
	Kind          string `json:"kind"`
	ShardID       string `json:"shard_id"`
}

type incidents struct {
	Events []incidentEvent `json:"events"`
}

type sample struct {
	Day             int   `json:"day"`
	LagBytes        int64 `json:"lag_bytes"`
	WitnessLagBytes int64 `json:"witness_lag_bytes"`
}

type shardDoc struct {
	Samples []sample `json:"samples"`
	ShardID string   `json:"shard_id"`
	Tier    string   `json:"tier"`
}

type profile struct {
	EffectiveLagBytes int64
	Embargoed         bool
	FinalVerdict      string
	FlushStatus       string
	GraceActive       bool
	ShardID           string
	Tier              string
	WitnessDesync     bool
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	data := getenv("RLA_DATA_DIR", "/app/replag")
	outd := getenv("RLA_AUDIT_DIR", "/app/audit")
	if err := run(data, outd); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func medianInt64(vals []int64) int64 {
	if len(vals) == 0 {
		return 0
	}
	cp := append([]int64(nil), vals...)
	sort.Slice(cp, func(i, j int) bool { return cp[i] < cp[j] })
	n := len(cp)
	mid := n / 2
	if n%2 == 1 {
		return cp[mid]
	}
	return (cp[mid-1] + cp[mid]) / 2
}

func effectiveLag(samples []sample, k int, rejectRatio float64) int64 {
	if len(samples) == 0 {
		return 0
	}
	sort.Slice(samples, func(i, j int) bool { return samples[i].Day < samples[j].Day })
	window := samples
	if len(window) > k {
		window = window[len(window)-k:]
	}
	lags := make([]int64, len(window))
	for i, s := range window {
		lags[i] = s.LagBytes
	}
	med := medianInt64(lags)
	kept := make([]int64, 0, len(lags))
	if med == 0 {
		kept = append(kept, lags...)
	} else {
		limit := int64(float64(med) * rejectRatio)
		for _, v := range lags {
			diff := v - med
			if diff < 0 {
				diff = -diff
			}
			if diff <= limit {
				kept = append(kept, v)
			}
		}
	}
	return medianInt64(kept)
}

func witnessDesync(samples []sample, skew int64) bool {
	if len(samples) == 0 {
		return false
	}
	sort.Slice(samples, func(i, j int) bool { return samples[i].Day < samples[j].Day })
	latest := samples[len(samples)-1]
	return latest.WitnessLagBytes-latest.LagBytes > skew
}

func lagVerdict(tier string, eff int64, th map[string]tierThreshold) string {
	t, ok := th[tier]
	if !ok {
		return "lag_ok"
	}
	if eff >= t.CriticalLagBytes {
		return "lag_critical"
	}
	if eff >= t.WarnLagBytes {
		return "lag_warn"
	}
	return "lag_ok"
}

func tarjanCycles(nodes map[string]bool, adj map[string][]string) [][]string {
	index := 0
	var stack []string
	onStack := map[string]bool{}
	indices := map[string]int{}
	lowlink := map[string]int{}
	var cycles [][]string

	var strong func(v string)
	strong = func(v string) {
		indices[v] = index
		lowlink[v] = index
		index++
		stack = append(stack, v)
		onStack[v] = true
		for _, w := range adj[v] {
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
			var scc []string
			for {
				w := stack[len(stack)-1]
				stack = stack[:len(stack)-1]
				onStack[w] = false
				scc = append(scc, w)
				if w == v {
					break
				}
			}
			if len(scc) > 1 {
				sort.Strings(scc)
				cycles = append(cycles, scc)
			}
		}
	}

	ids := make([]string, 0, len(nodes))
	for id := range nodes {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		if _, ok := indices[id]; !ok {
			strong(id)
		}
	}
	sort.Slice(cycles, func(i, j int) bool { return cycles[i][0] < cycles[j][0] })
	return cycles
}

func topoOrder(nodes map[string]bool, adj map[string][]string, inCycle map[string]bool) []string {
	inDeg := map[string]int{}
	for id := range nodes {
		if !inCycle[id] {
			inDeg[id] = 0
		}
	}
	for p, chs := range adj {
		if inCycle[p] {
			continue
		}
		for _, c := range chs {
			if inCycle[c] {
				continue
			}
			inDeg[c]++
		}
	}
	ready := []string{}
	for id := range nodes {
		if !inCycle[id] && inDeg[id] == 0 {
			ready = append(ready, id)
		}
	}
	var order []string
	sort.Strings(ready)
	for len(ready) > 0 {
		id := ready[0]
		ready = ready[1:]
		order = append(order, id)
		nxt := []string{}
		for _, c := range adj[id] {
			if inCycle[c] {
				continue
			}
			inDeg[c]--
			if inDeg[c] == 0 {
				nxt = append(nxt, c)
			}
		}
		ready = append(ready, nxt...)
		sort.Strings(ready)
	}
	return order
}

func markEmbargo(root string, adj map[string][]string, embargoed map[string]bool) {
	stack := []string{root}
	for len(stack) > 0 {
		id := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if embargoed[id] {
			continue
		}
		embargoed[id] = true
		stack = append(stack, adj[id]...)
	}
}

func loadShards(dir string) (map[string]shardDoc, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := map[string]shardDoc{}
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var doc shardDoc
		if err := json.Unmarshal(b, &doc); err != nil {
			return nil, err
		}
		out[doc.ShardID] = doc
	}
	return out, nil
}

func computeFlushStatus(
	id string,
	p *profile,
	parents map[string][]string,
	byID map[string]*profile,
	frozen, embargoed, inCycle map[string]bool,
) (string, []string) {
	reasons := []string{}
	switch {
	case frozen[id]:
		return "blocked_frozen", []string{"frozen"}
	case embargoed[id]:
		return "blocked_embargo", []string{"embargo"}
	case p.WitnessDesync:
		return "blocked_witness", []string{"witness_desync"}
	case inCycle[id]:
		return "blocked_cycle", []string{"cycle"}
	}
	for _, par := range parents[id] {
		pp := byID[par]
		if pp == nil {
			continue
		}
		if pp.FinalVerdict != "lag_ok" || pp.FlushStatus != "flush_ready" {
			reasons = append(reasons, "parent:"+par)
		}
	}
	if len(reasons) > 0 {
		sort.Strings(reasons)
		return "blocked_parent", reasons
	}
	if p.FinalVerdict == "lag_warn" || p.FinalVerdict == "lag_critical" {
		return "not_due", []string{"lag"}
	}
	if p.FinalVerdict != "lag_ok" {
		return "not_due", []string{p.FinalVerdict}
	}
	return "flush_ready", []string{}
}

func run(dataDir, auditDir string) error {
	polRaw, err := os.ReadFile(filepath.Join(dataDir, "policy.json"))
	if err != nil {
		return err
	}
	var pol policy
	if err := json.Unmarshal(polRaw, &pol); err != nil {
		return err
	}
	if pol.MedianWindowK <= 0 || pol.GraceDaysAfterFailover <= 0 {
		return fmt.Errorf("invalid policy")
	}

	psRaw, err := os.ReadFile(filepath.Join(dataDir, "pool_state.json"))
	if err != nil {
		return err
	}
	var ps poolState
	if err := json.Unmarshal(psRaw, &ps); err != nil {
		return err
	}

	shards, err := loadShards(filepath.Join(dataDir, "shards"))
	if err != nil {
		return err
	}

	adj := map[string][]string{}
	parents := map[string][]string{}
	if b, err := os.ReadFile(filepath.Join(dataDir, "dependencies.json")); err == nil {
		var dep dependencies
		if json.Unmarshal(b, &dep) == nil {
			known := map[string]bool{}
			for id := range shards {
				known[id] = true
			}
			for _, e := range dep.Edges {
				if !known[e.Parent] || !known[e.Child] {
					continue
				}
				adj[e.Parent] = append(adj[e.Parent], e.Child)
				parents[e.Child] = append(parents[e.Child], e.Parent)
			}
			for p := range adj {
				sort.Strings(adj[p])
			}
			for c := range parents {
				sort.Strings(parents[c])
			}
		}
	}

	nodes := map[string]bool{}
	for id := range shards {
		nodes[id] = true
	}
	cycles := tarjanCycles(nodes, adj)
	inCycle := map[string]bool{}
	for _, cyc := range cycles {
		for _, id := range cyc {
			inCycle[id] = true
		}
	}
	order := topoOrder(nodes, adj, inCycle)

	failoverDay := map[string]int{}
	frozen := map[string]bool{}
	forced := map[string]string{}
	embargoed := map[string]bool{}
	var applied []map[string]any

	if b, err := os.ReadFile(filepath.Join(dataDir, "incidents.json")); err == nil {
		var inc incidents
		if json.Unmarshal(b, &inc) == nil {
			sort.Slice(inc.Events, func(i, j int) bool {
				if inc.Events[i].Day != inc.Events[j].Day {
					return inc.Events[i].Day < inc.Events[j].Day
				}
				return inc.Events[i].ShardID < inc.Events[j].ShardID
			})
			for _, ev := range inc.Events {
				if ev.Day > ps.CurrentDay {
					continue
				}
				if _, ok := shards[ev.ShardID]; !ok {
					continue
				}
				row := map[string]any{
					"day":      ev.Day,
					"kind":     ev.Kind,
					"shard_id": ev.ShardID,
				}
				switch ev.Kind {
				case "failover":
					failoverDay[ev.ShardID] = ev.Day
					row["effect"] = "failover"
				case "freeze_shard":
					frozen[ev.ShardID] = true
					row["effect"] = "freeze"
				case "force_lag_verdict":
					if ev.ForcedVerdict == "lag_warn" || ev.ForcedVerdict == "lag_critical" {
						forced[ev.ShardID] = ev.ForcedVerdict
					}
					row["effect"] = "force"
				case "embargo_downstream":
					markEmbargo(ev.ShardID, adj, embargoed)
					row["effect"] = "embargo"
				default:
					continue
				}
				applied = append(applied, row)
			}
		}
	}

	ids := make([]string, 0, len(shards))
	for id := range shards {
		ids = append(ids, id)
	}
	sort.Strings(ids)

	profiles := make([]profile, 0, len(ids))
	byID := map[string]*profile{}
	for _, id := range ids {
		doc := shards[id]
		eff := effectiveLag(doc.Samples, pol.MedianWindowK, pol.MedianRejectRatio)
		wdesync := witnessDesync(doc.Samples, pol.WitnessSkewBytes)
		lv := lagVerdict(doc.Tier, eff, pol.TierThresholds)
		grace := false
		if fd, ok := failoverDay[id]; ok {
			if ps.CurrentDay <= fd+pol.GraceDaysAfterFailover-1 {
				grace = true
				if lv == "lag_warn" || lv == "lag_critical" {
					lv = "lag_ok"
				}
			}
		}
		if fv, ok := forced[id]; ok {
			lv = fv
		}
		fv := lv
		if frozen[id] {
			fv = "frozen"
		} else if embargoed[id] {
			fv = "embargoed"
		} else if wdesync {
			fv = "hold"
		}
		p := profile{
			EffectiveLagBytes: eff,
			Embargoed:         embargoed[id],
			FinalVerdict:      fv,
			GraceActive:       grace,
			ShardID:           id,
			Tier:              doc.Tier,
			WitnessDesync:     wdesync,
		}
		profiles = append(profiles, p)
		byID[id] = &profiles[len(profiles)-1]
	}

	for pass := 0; pass < len(profiles)+2; pass++ {
		changed := false
		for i := range profiles {
			p := &profiles[i]
			st, rs := computeFlushStatus(p.ShardID, p, parents, byID, frozen, embargoed, inCycle)
			if p.FlushStatus != st {
				changed = true
				p.FlushStatus = st
			}
			_ = rs
		}
		if !changed && pass > 0 {
			break
		}
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}

	profRows := make([]map[string]any, len(profiles))
	for i, p := range profiles {
		profRows[i] = map[string]any{
			"effective_lag_bytes": p.EffectiveLagBytes,
			"embargoed":           p.Embargoed,
			"final_verdict":       p.FinalVerdict,
			"flush_status":        p.FlushStatus,
			"grace_active":        p.GraceActive,
			"shard_id":            p.ShardID,
			"tier":                p.Tier,
			"witness_desync":      p.WitnessDesync,
		}
	}
	if err := writeJSON(filepath.Join(auditDir, "shard_profiles.json"), map[string]any{
		"current_day": ps.CurrentDay,
		"profiles":    profRows,
	}); err != nil {
		return err
	}

	if err := writeJSON(filepath.Join(auditDir, "dependency_plan.json"), map[string]any{
		"cycles": cycles,
		"order":  order,
	}); err != nil {
		return err
	}

	flushEntries := make([]map[string]any, len(profiles))
	for i, p := range profiles {
		_, rs := computeFlushStatus(p.ShardID, &profiles[i], parents, byID, frozen, embargoed, inCycle)
		flushEntries[i] = map[string]any{
			"flush_status": p.FlushStatus,
			"reasons":      rs,
			"shard_id":     p.ShardID,
		}
	}
	sort.Slice(flushEntries, func(i, j int) bool {
		return flushEntries[i]["shard_id"].(string) < flushEntries[j]["shard_id"].(string)
	})
	if err := writeJSON(filepath.Join(auditDir, "flush_plan.json"), map[string]any{
		"entries": flushEntries,
	}); err != nil {
		return err
	}

	if err := writeJSON(filepath.Join(auditDir, "incident_trace.json"), map[string]any{
		"applied": applied,
	}); err != nil {
		return err
	}

	tiers := map[string]map[string]int{
		"bronze": {"lag_critical": 0, "lag_ok": 0, "lag_warn": 0},
		"gold":   {"lag_critical": 0, "lag_ok": 0, "lag_warn": 0},
		"silver": {"lag_critical": 0, "lag_ok": 0, "lag_warn": 0},
	}
	flushReady := 0
	holdTotal := 0
	for _, p := range profiles {
		if p.FinalVerdict == "hold" {
			holdTotal++
		}
		if p.FlushStatus == "flush_ready" {
			flushReady++
		}
		if p.FinalVerdict == "lag_ok" || p.FinalVerdict == "lag_warn" || p.FinalVerdict == "lag_critical" {
			if tc, ok := tiers[p.Tier]; ok {
				tc[p.FinalVerdict]++
			}
		}
	}

	return writeJSON(filepath.Join(auditDir, "summary.json"), map[string]any{
		"current_day":       ps.CurrentDay,
		"flush_ready_total": flushReady,
		"hold_total":        holdTotal,
		"shards_total":      len(profiles),
		"tiers":             tiers,
	})
}

func writeJSON(path string, v any) error {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(true)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		return err
	}
	out := buf.Bytes()
	if len(out) > 0 && out[len(out)-1] == '\n' {
		out = out[:len(out)-1]
	}
	out = append(out, '\n')
	return os.WriteFile(path, out, 0o644)
}
