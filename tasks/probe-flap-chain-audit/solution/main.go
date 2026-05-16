package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
)

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type policy struct {
	FailThresholdByTier map[string]int `json:"fail_threshold_by_tier"`
	FlapThresholdByTier map[string]int `json:"flap_threshold_by_tier"`
	RollingWindowDays   int            `json:"rolling_window_days"`
	SoakDaysByTier      map[string]int `json:"soak_days_by_tier"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type nodeDoc struct {
	NodeID      string            `json:"node_id"`
	ParentID    *string           `json:"parent_id"`
	ProbesByDay map[string]string `json:"probes_by_day"`
	Tier        string            `json:"tier"`
}

type nodeResult struct {
	ComputedStatus string
	Degraded       bool
	Reasons        []string
}

func main() {
	dataDir := getenv("PFCA_DATA_DIR", "/app/probeflaps")
	auditDir := getenv("PFCA_AUDIT_DIR", "/app/audit")
	if err := run(dataDir, auditDir); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func run(dataDir, auditDir string) error {
	psRaw, err := os.ReadFile(filepath.Join(dataDir, "pool_state.json"))
	if err != nil {
		return err
	}
	var ps poolState
	if err := json.Unmarshal(psRaw, &ps); err != nil {
		return err
	}
	polRaw, err := os.ReadFile(filepath.Join(dataDir, "policy.json"))
	if err != nil {
		return err
	}
	var pol policy
	if err := json.Unmarshal(polRaw, &pol); err != nil {
		return err
	}
	if pol.RollingWindowDays < 1 {
		pol.RollingWindowDays = 1
	}
	incRaw, err := os.ReadFile(filepath.Join(dataDir, "incident_log.json"))
	if err != nil {
		return err
	}
	var il incidentLog
	if err := json.Unmarshal(incRaw, &il); err != nil {
		return err
	}

	nodes, err := loadNodes(filepath.Join(dataDir, "nodes"))
	if err != nil {
		return err
	}
	sort.Slice(nodes, func(i, j int) bool { return nodes[i].NodeID < nodes[j].NodeID })

	candidates := make([]map[string]any, 0)
	ignored := 0
	for _, ev := range il.Events {
		if !boolVal(ev["accepted"]) {
			ignored++
			continue
		}
		if intVal(ev["day"]) > ps.CurrentDay {
			ignored++
			continue
		}
		candidates = append(candidates, ev)
	}
	sort.Slice(candidates, func(i, j int) bool {
		di := intVal(candidates[i]["day"])
		dj := intVal(candidates[j]["day"])
		if di != dj {
			return di < dj
		}
		return strVal(candidates[i]["event_id"]) < strVal(candidates[j]["event_id"])
	})

	applied := make([]map[string]any, 0)
	for _, ev := range candidates {
		if !incidentWellFormed(strVal(ev["kind"]), ev) {
			ignored++
			continue
		}
		applied = append(applied, ev)
	}

	failDelta := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	flapDelta := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	soakDelta := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	rollSpanDelta := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	isolate := map[string]bool{}
	forceUnhealthy := map[string]bool{}

	for _, ev := range applied {
		kind := strVal(ev["kind"])
		switch kind {
		case "extend_soak_delta":
			soakDelta[strVal(ev["target_tier"])] += intVal(ev["delta"])
		case "fail_threshold_delta":
			failDelta[strVal(ev["target_tier"])] += intVal(ev["delta"])
		case "flap_threshold_delta":
			flapDelta[strVal(ev["target_tier"])] += intVal(ev["delta"])
		case "rolling_span_delta":
			rollSpanDelta[strVal(ev["target_tier"])] += intVal(ev["delta"])
		case "isolate_node":
			isolate[strVal(ev["node_id"])] = true
		case "force_unhealthy":
			forceUnhealthy[strVal(ev["node_id"])] = true
		}
	}

	effectiveFailTh := map[string]int{}
	effectiveFlapTh := map[string]int{}
	effectiveSoak := map[string]int{}
	tierSpan := map[string]int{}
	baseW := pol.RollingWindowDays
	if baseW < 1 {
		baseW = 1
	}
	tiersOut := map[string]any{}
	for _, tier := range []string{"bronze", "gold", "silver"} {
		bf := pol.FailThresholdByTier[tier]
		bfl := pol.FlapThresholdByTier[tier]
		bs := pol.SoakDaysByTier[tier]
		fd := failDelta[tier]
		fld := flapDelta[tier]
		sd := soakDelta[tier]
		rsd := rollSpanDelta[tier]
		ef := bf + fd
		if ef < 1 {
			ef = 1
		}
		efl := bfl + fld
		if efl < 1 {
			efl = 1
		}
		es := bs + sd
		if es < 0 {
			es = 0
		}
		span := baseW + rsd
		if span < 1 {
			span = 1
		}
		effectiveFailTh[tier] = ef
		effectiveFlapTh[tier] = efl
		effectiveSoak[tier] = es
		tierSpan[tier] = span
		tiersOut[tier] = map[string]any{
			"base_fail_threshold":         bf,
			"base_flap_threshold":         bfl,
			"base_rolling_window_days":    baseW,
			"base_soak_days":              bs,
			"effective_fail_threshold":    ef,
			"effective_flap_threshold":    efl,
			"effective_rolling_span_days":   span,
			"effective_soak_days":         es,
			"fail_delta_sum":              fd,
			"flap_delta_sum":              fld,
			"rolling_span_delta_sum":      rsd,
			"soak_delta_sum":              sd,
		}
	}

	journal := make([]map[string]any, 0, len(applied))
	for _, ev := range applied {
		journal = append(journal, journalEntry(ev))
	}
	sort.Slice(journal, func(i, j int) bool {
		di := intVal(journal[i]["day"])
		dj := intVal(journal[j]["day"])
		if di != dj {
			return di < dj
		}
		return strVal(journal[i]["event_id"]) < strVal(journal[j]["event_id"])
	})

	byID := map[string]nodeDoc{}
	for _, n := range nodes {
		byID[n.NodeID] = n
	}

	order := topoOrder(nodes)
	results := map[string]nodeResult{}
	rows := make([]map[string]any, 0, len(nodes))

	for _, nid := range order {
		n := byID[nid]
		winStart := ps.CurrentDay - (tierSpan[n.Tier] - 1)
		rawFail := countFails(n.ProbesByDay, winStart, ps.CurrentDay)
		rawFlap := countFlaps(n.ProbesByDay, winStart, ps.CurrentDay)
		effFlap := rawFlap
		for _, ev := range applied {
			if strVal(ev["kind"]) != "flap_day_suppress" {
				continue
			}
			if strVal(ev["node_id"]) != nid {
				continue
			}
			for _, d := range daySlice(ev["days"]) {
				if d <= winStart || d > ps.CurrentDay {
					continue
				}
				if !probePairDiffers(n.ProbesByDay, d) {
					continue
				}
				if effFlap > 0 {
					effFlap--
				}
			}
		}
		if effFlap < 0 {
			effFlap = 0
		}

		effFail := rawFail
		for _, ev := range applied {
			if strVal(ev["kind"]) != "fail_day_suppress" {
				continue
			}
			if strVal(ev["node_id"]) != nid {
				continue
			}
			for _, d := range daySlice(ev["days"]) {
				if d < winStart || d > ps.CurrentDay {
					continue
				}
				if n.ProbesByDay[strconv.Itoa(d)] != "fail" {
					continue
				}
				if effFail > 0 {
					effFail--
				}
			}
		}
		if effFail < 0 {
			effFail = 0
		}

		lastFail := lastFailDay(n.ProbesByDay, winStart, ps.CurrentDay)
		effFailTh := effectiveFailTh[n.Tier]
		effFlapTh := effectiveFlapTh[n.Tier]
		effSoak := effectiveSoak[n.Tier]

		var parentDegraded bool
		if n.ParentID != nil && *n.ParentID != "" {
			if pr, ok := results[*n.ParentID]; ok {
				parentDegraded = pr.Degraded
			}
		}

		status := "healthy"
		degraded := false
		reasons := []string{}

		if isolate[nid] {
			status = "isolated"
			degraded = true
			reasons = append(reasons, "isolate_incident")
		} else if forceUnhealthy[nid] {
			status = "unhealthy"
			degraded = true
			reasons = append(reasons, "force_unhealthy_incident")
		} else if parentDegraded {
			status = "inherited_degraded"
			degraded = true
			reasons = append(reasons, "parent_degraded_inheritance")
		} else if effFail >= effFailTh {
			status = "unhealthy"
			degraded = true
			reasons = append(reasons, "threshold_exceeded")
		} else if lastFail != nil && (ps.CurrentDay-*lastFail) < effSoak {
			status = "soaking"
			reasons = append(reasons, "soaking_period")
		} else if effFlap >= effFlapTh {
			status = "flapping"
			reasons = append(reasons, "flap_threshold_exceeded")
		}

		if status == "healthy" {
			reasons = []string{}
		} else {
			reasons = uniqSort(reasons)
		}

		results[nid] = nodeResult{ComputedStatus: status, Degraded: degraded, Reasons: reasons}

		var lastFailOut any
		if lastFail != nil {
			lastFailOut = *lastFail
		}

		var parentOut any
		if n.ParentID != nil {
			parentOut = *n.ParentID
		}

		rows = append(rows, map[string]any{
			"node_id":                    nid,
			"tier":                       n.Tier,
			"parent_id":                  parentOut,
			"raw_failures":               rawFail,
			"raw_flap_transitions":       rawFlap,
			"effective_failures":         effFail,
			"effective_flap_transitions": effFlap,
			"effective_fail_threshold":   effFailTh,
			"effective_flap_threshold":   effFlapTh,
			"effective_soak_days":        effSoak,
			"last_fail_day":              lastFailOut,
			"computed_status":            status,
			"degraded":                   degraded,
			"reasons":                    reasons,
		})
	}

	sort.Slice(rows, func(i, j int) bool {
		return strVal(rows[i]["node_id"]) < strVal(rows[j]["node_id"])
	})

	children := map[string][]string{}
	for _, n := range nodes {
		if n.ParentID != nil && *n.ParentID != "" {
			children[*n.ParentID] = append(children[*n.ParentID], n.NodeID)
		}
	}
	parentKeys := make([]string, 0, len(children))
	for k := range children {
		parentKeys = append(parentKeys, k)
	}
	sort.Strings(parentKeys)
	parentsOut := map[string]any{}
	for _, pid := range parentKeys {
		ch := children[pid]
		sort.Strings(ch)
		pst := "healthy"
		if pr, ok := results[pid]; ok {
			pst = pr.ComputedStatus
		}
		parentsOut[pid] = map[string]any{
			"child_nodes":    ch,
			"parent_status":  pst,
		}
	}

	healthyN, soakingN, unhealthyN, flappingN, isolatedN, inheritedN, degradedN := 0, 0, 0, 0, 0, 0, 0
	for _, r := range results {
		switch r.ComputedStatus {
		case "healthy":
			healthyN++
		case "soaking":
			soakingN++
		case "unhealthy":
			unhealthyN++
		case "flapping":
			flappingN++
		case "isolated":
			isolatedN++
		case "inherited_degraded":
			inheritedN++
		}
		if r.Degraded {
			degradedN++
		}
	}

	summary := map[string]any{
		"applied_incident_events":   len(journal),
		"degraded_nodes":            degradedN,
		"flapping_nodes":            flappingN,
		"healthy_nodes":             healthyN,
		"ignored_incident_events":   ignored,
		"inherited_degraded_nodes":  inheritedN,
		"isolated_nodes":            isolatedN,
		"nodes_total":               len(nodes),
		"soaking_nodes":             soakingN,
		"unhealthy_nodes":           unhealthyN,
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "node_verdicts.json"), map[string]any{"nodes": rows}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "tier_policy.json"), map[string]any{"tiers": tiersOut}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "incident_journal.json"), map[string]any{"applied_events": journal}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "dependency_touchpoints.json"), map[string]any{"parents": parentsOut}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "summary.json"), summary); err != nil {
		return err
	}
	return nil
}

func topoOrder(nodes []nodeDoc) []string {
	byID := map[string]nodeDoc{}
	for _, n := range nodes {
		byID[n.NodeID] = n
	}
	depth := map[string]int{}
	var compute func(string) int
	compute = func(id string) int {
		if d, ok := depth[id]; ok {
			return d
		}
		n := byID[id]
		if n.ParentID == nil || *n.ParentID == "" {
			depth[id] = 0
			return 0
		}
		p := *n.ParentID
		if _, ok := byID[p]; !ok {
			depth[id] = 0
			return 0
		}
		depth[id] = compute(p) + 1
		return depth[id]
	}
	ids := make([]string, 0, len(nodes))
	for _, n := range nodes {
		ids = append(ids, n.NodeID)
	}
	sort.Slice(ids, func(i, j int) bool {
		di := compute(ids[i])
		dj := compute(ids[j])
		if di != dj {
			return di < dj
		}
		return ids[i] < ids[j]
	})
	return ids
}

func loadNodes(dir string) ([]nodeDoc, error) {
	var out []nodeDoc
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var n nodeDoc
		if err := json.Unmarshal(b, &n); err != nil {
			return nil, err
		}
		out = append(out, n)
	}
	return out, nil
}

func countFails(m map[string]string, start, end int) int {
	n := 0
	for d := start; d <= end; d++ {
		if m[strconv.Itoa(d)] == "fail" {
			n++
		}
	}
	return n
}

func countFlaps(m map[string]string, start, end int) int {
	n := 0
	for d := start + 1; d <= end; d++ {
		if probePairDiffers(m, d) {
			n++
		}
	}
	return n
}

func probePairDiffers(m map[string]string, d int) bool {
	prev := m[strconv.Itoa(d-1)]
	cur := m[strconv.Itoa(d)]
	if prev == "" || cur == "" {
		return false
	}
	return prev != cur
}

func lastFailDay(m map[string]string, start, end int) *int {
	last := -1
	for d := start; d <= end; d++ {
		if m[strconv.Itoa(d)] == "fail" {
			last = d
		}
	}
	if last < 0 {
		return nil
	}
	return &last
}

func incidentWellFormed(kind string, ev map[string]any) bool {
	switch kind {
	case "extend_soak_delta", "fail_threshold_delta", "flap_threshold_delta", "rolling_span_delta":
		tt := strVal(ev["target_tier"])
		if tt != "gold" && tt != "silver" && tt != "bronze" {
			return false
		}
		_, ok := ev["delta"]
		return ok
	case "flap_day_suppress", "fail_day_suppress":
		if strVal(ev["node_id"]) == "" {
			return false
		}
		_, ok := ev["days"]
		return ok
	case "isolate_node", "force_unhealthy":
		return strVal(ev["node_id"]) != ""
	default:
		return false
	}
}

func journalEntry(ev map[string]any) map[string]any {
	kind := strVal(ev["kind"])
	m := map[string]any{
		"day":      intVal(ev["day"]),
		"event_id": strVal(ev["event_id"]),
		"kind":     kind,
	}
	switch kind {
	case "extend_soak_delta", "fail_threshold_delta", "flap_threshold_delta", "rolling_span_delta":
		m["delta"] = intVal(ev["delta"])
		m["target_tier"] = strVal(ev["target_tier"])
	case "flap_day_suppress", "fail_day_suppress":
		m["days"] = daySlice(ev["days"])
		m["node_id"] = strVal(ev["node_id"])
	case "isolate_node", "force_unhealthy":
		m["node_id"] = strVal(ev["node_id"])
	}
	return m
}

func writeJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}

func boolVal(v any) bool {
	b, ok := v.(bool)
	return ok && b
}

func strVal(v any) string {
	if v == nil {
		return ""
	}
	s, ok := v.(string)
	if ok {
		return s
	}
	return fmt.Sprint(v)
}

func intVal(v any) int {
	switch t := v.(type) {
	case float64:
		return int(t)
	case int:
		return t
	case json.Number:
		i, _ := t.Int64()
		return int(i)
	default:
		return 0
	}
}

func daySlice(v any) []int {
	arr, ok := v.([]any)
	if !ok {
		return nil
	}
	out := make([]int, 0, len(arr))
	for _, x := range arr {
		out = append(out, intVal(x))
	}
	return out
}

func uniqSort(in []string) []string {
	sort.Strings(in)
	out := make([]string, 0, len(in))
	var prev string
	for _, s := range in {
		if s == prev {
			continue
		}
		out = append(out, s)
		prev = s
	}
	return out
}
