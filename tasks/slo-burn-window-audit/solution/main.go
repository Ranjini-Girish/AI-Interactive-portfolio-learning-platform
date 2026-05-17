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

type tierThreshold struct {
	Critical int `json:"critical"`
	Warning  int `json:"warning"`
}

type policy struct {
	BurnThresholdMilliByTier     map[string]tierThreshold `json:"burn_threshold_milli_by_tier"`
	ErrorBudgetMinutesByTier     map[string]int           `json:"error_budget_minutes_by_tier"`
	FastWindowDays               int                      `json:"fast_window_days"`
	InheritedBurnMilliFactor     int                      `json:"inherited_burn_milli_factor"`
	MaxErrorBudgetMinutesByTier  map[string]int           `json:"max_error_budget_minutes_by_tier"`
	SlowWindowDays               int                      `json:"slow_window_days"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type serviceDoc struct {
	MinutesByDay map[string]map[string]int `json:"minutes_by_day"`
	ServiceID    string                    `json:"service_id"`
	Tier         string                    `json:"tier"`
}

type edgesDoc struct {
	Edges []map[string]any `json:"edges"`
}

func main() {
	dataDir := getenv("SBWA_DATA_DIR", "/app/slo-matrix")
	auditDir := getenv("SBWA_AUDIT_DIR", "/app/audit")
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
	var ps poolState
	if err := readJSON(filepath.Join(dataDir, "pool_state.json"), &ps); err != nil {
		return err
	}
	var pol policy
	if err := readJSON(filepath.Join(dataDir, "policy.json"), &pol); err != nil {
		return err
	}
	if pol.SlowWindowDays < 1 {
		pol.SlowWindowDays = 1
	}
	if pol.FastWindowDays < 1 {
		pol.FastWindowDays = 1
	}

	var il incidentLog
	if err := readJSON(filepath.Join(dataDir, "incident_log.json"), &il); err != nil {
		return err
	}

	services, err := loadServices(filepath.Join(dataDir, "services"))
	if err != nil {
		return err
	}
	sort.Slice(services, func(i, j int) bool { return services[i].ServiceID < services[j].ServiceID })

	var edges edgesDoc
	_ = readJSON(filepath.Join(dataDir, "consumers", "edges.json"), &edges)

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

	deltaByTier := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	freezeRanges := map[string][][2]int{}
	compromised := map[string]bool{}
	overrideStatus := map[string]string{}

	for _, ev := range applied {
		kind := strVal(ev["kind"])
		switch kind {
		case "tier_budget_delta":
			tt := strVal(ev["target_tier"])
			deltaByTier[tt] += intVal(ev["delta_minutes"])
		case "burn_freeze":
			sid := strVal(ev["service_id"])
			freezeRanges[sid] = append(freezeRanges[sid], [2]int{
				intVal(ev["freeze_start_day"]),
				intVal(ev["freeze_end_day"]),
			})
		case "service_compromise":
			compromised[strVal(ev["service_id"])] = true
		case "slo_review_override":
			overrideStatus[strVal(ev["service_id"])] = strVal(ev["target_status"])
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

	tiersOut := map[string]any{}
	adjustedByTier := map[string]int{}
	for _, tier := range []string{"bronze", "gold", "silver"} {
		base := pol.ErrorBudgetMinutesByTier[tier]
		ds := deltaByTier[tier]
		adj := base + ds
		if cap, ok := pol.MaxErrorBudgetMinutesByTier[tier]; ok && adj > cap {
			adj = cap
		}
		if adj < 1 {
			adj = 1
		}
		adjustedByTier[tier] = adj
		tiersOut[tier] = map[string]any{
			"adjusted_budget_minutes": adj,
			"base_budget_minutes":     base,
			"delta_sum_minutes":       ds,
		}
	}

	slowStart := ps.CurrentDay - (pol.SlowWindowDays - 1)
	fastStart := ps.CurrentDay - (pol.FastWindowDays - 1)

	adj := buildAdjacency(edges)
	consumerIDs := consumerSet(edges)
	inheritedConsumers := map[string]bool{}
	taintRows := make([]map[string]any, 0, len(consumerIDs))
	inheritedN := 0
	for _, cid := range consumerIDs {
		producers := reachableProducers(cid, compromised, adj)
		status := "clean"
		if len(producers) > 0 {
			status = "inherited_compromise"
			inheritedConsumers[cid] = true
			inheritedN++
		}
		taintRows = append(taintRows, map[string]any{
			"compromised_producers": producers,
			"consumer_id":           cid,
			"taint_status":          status,
		})
	}

	inheritedFactor := pol.InheritedBurnMilliFactor
	if inheritedFactor < 1 {
		inheritedFactor = 1000
	}

	burnRows := make([]map[string]any, 0, len(services))
	okN, warnN, breachN := 0, 0, 0

	for _, sv := range services {
		budget := adjustedByTier[sv.Tier]
		if budget < 1 {
			budget = 1
		}
		th := pol.BurnThresholdMilliByTier[sv.Tier]
		freezes := freezeRanges[sv.ServiceID]

		consumedSlow := sumBad(sv, slowStart, ps.CurrentDay, freezes, true)
		allowedSlow := (budget * pol.SlowWindowDays) / pol.SlowWindowDays
		burnSlow := burnMilli(consumedSlow, allowedSlow)

		consumedFast := sumBad(sv, fastStart, ps.CurrentDay, freezes, false)
		allowedFast := (budget * pol.FastWindowDays) / pol.SlowWindowDays
		burnFast := burnMilli(consumedFast, allowedFast)

		effective := burnSlow
		if burnFast > effective {
			effective = burnFast
		}
		if inheritedConsumers[sv.ServiceID] {
			effective = (effective * inheritedFactor) / 1000
		}

		status := numericStatus(effective, th.Warning, th.Critical)
		remaining := allowedSlow - consumedSlow
		if remaining < 0 {
			remaining = 0
		}

		reasons := []string{}
		if compromised[sv.ServiceID] {
			status = "breached"
			remaining = 0
			reasons = append(reasons, "service_compromise")
		}
		if tgt, ok := overrideStatus[sv.ServiceID]; ok {
			if compromised[sv.ServiceID] && tgt == "ok" {
				tgt = "warning"
			}
			status = tgt
			reasons = append(reasons, "slo_review_override")
		}
		reasons = uniqSort(reasons)

		switch status {
		case "ok":
			okN++
		case "warning":
			warnN++
		case "breached":
			breachN++
		}

		burnRows = append(burnRows, map[string]any{
			"allowed_bad_minutes_slow":   allowedSlow,
			"burn_rate_milli_fast":       burnFast,
			"burn_rate_milli_slow":       burnSlow,
			"consumed_bad_minutes_slow":  consumedSlow,
			"effective_burn_rate_milli":  effective,
			"reasons":                    reasons,
			"remaining_budget_minutes":   remaining,
			"service_id":                 sv.ServiceID,
			"slo_status":                 status,
			"tier":                       sv.Tier,
		})
	}

	compromiseN := len(compromised)
	summary := map[string]any{
		"applied_incident_events":        len(journal),
		"breached_services":              breachN,
		"compromise_services":            compromiseN,
		"ignored_incident_events":        ignored,
		"inherited_compromise_consumers": inheritedN,
		"ok_services":                    okN,
		"services_total":                 len(services),
		"warning_services":               warnN,
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "burn_report.json"), map[string]any{"services": burnRows}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "tier_budgets.json"), map[string]any{"tiers": tiersOut}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "dependency_taint.json"), map[string]any{"consumers": taintRows}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "incident_journal.json"), map[string]any{"applied_events": journal}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "summary.json"), summary); err != nil {
		return err
	}
	return nil
}

func sumBad(sv serviceDoc, start, end int, freezes [][2]int, applyFreeze bool) int {
	total := 0
	for d := start; d <= end; d++ {
		if applyFreeze && frozen(d, freezes) {
			continue
		}
		key := strconv.Itoa(d)
		if day, ok := sv.MinutesByDay[key]; ok {
			total += day["bad_minutes"]
		}
	}
	return total
}

func frozen(d int, ranges [][2]int) bool {
	for _, r := range ranges {
		if r[0] <= d && d <= r[1] {
			return true
		}
	}
	return false
}

func burnMilli(consumed, allowed int) int {
	if allowed < 1 {
		allowed = 1
	}
	return (consumed * 1000) / allowed
}

func numericStatus(effective, warning, critical int) string {
	if effective >= critical {
		return "breached"
	}
	if effective >= warning {
		return "warning"
	}
	return "ok"
}

func buildAdjacency(edges edgesDoc) map[string][]string {
	adj := map[string][]string{}
	for _, e := range edges.Edges {
		c := strVal(e["consumer_id"])
		p := strVal(e["producer_id"])
		if c == "" || p == "" {
			continue
		}
		adj[p] = append(adj[p], c)
	}
	return adj
}

func consumerSet(edges edgesDoc) []string {
	set := map[string]bool{}
	for _, e := range edges.Edges {
		c := strVal(e["consumer_id"])
		p := strVal(e["producer_id"])
		if c == "" || p == "" {
			continue
		}
		set[c] = true
	}
	out := make([]string, 0, len(set))
	for k := range set {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func reachableProducers(consumer string, compromised map[string]bool, adj map[string][]string) []string {
	out := make([]string, 0)
	for prod, ok := range compromised {
		if !ok {
			continue
		}
		if producerReachConsumer(prod, consumer, adj) {
			out = append(out, prod)
		}
	}
	sort.Strings(out)
	return out
}

func producerReachConsumer(producer, consumer string, adj map[string][]string) bool {
	if producer == consumer {
		return true
	}
	visited := map[string]bool{producer: true}
	queue := []string{producer}
	for len(queue) > 0 {
		cur := queue[0]
		queue = queue[1:]
		if cur == consumer {
			return true
		}
		for _, nxt := range adj[cur] {
			if visited[nxt] {
				continue
			}
			visited[nxt] = true
			queue = append(queue, nxt)
		}
	}
	return false
}

func incidentWellFormed(kind string, ev map[string]any) bool {
	switch kind {
	case "tier_budget_delta":
		tt := strVal(ev["target_tier"])
		if tt != "gold" && tt != "silver" && tt != "bronze" {
			return false
		}
		_, ok := ev["delta_minutes"]
		return ok
	case "burn_freeze":
		if strVal(ev["service_id"]) == "" {
			return false
		}
		_, okS := ev["freeze_start_day"]
		_, okE := ev["freeze_end_day"]
		return okS && okE
	case "service_compromise":
		return strVal(ev["service_id"]) != ""
	case "slo_review_override":
		tgt := strVal(ev["target_status"])
		if tgt != "ok" && tgt != "warning" && tgt != "breached" {
			return false
		}
		return strVal(ev["service_id"]) != ""
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
	case "tier_budget_delta":
		m["delta_minutes"] = intVal(ev["delta_minutes"])
		m["target_tier"] = strVal(ev["target_tier"])
	case "burn_freeze":
		m["freeze_end_day"] = intVal(ev["freeze_end_day"])
		m["freeze_start_day"] = intVal(ev["freeze_start_day"])
		m["service_id"] = strVal(ev["service_id"])
	case "service_compromise":
		m["service_id"] = strVal(ev["service_id"])
	case "slo_review_override":
		m["service_id"] = strVal(ev["service_id"])
		m["target_status"] = strVal(ev["target_status"])
	}
	return m
}

func loadServices(dir string) ([]serviceDoc, error) {
	var out []serviceDoc
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
		var s serviceDoc
		if err := json.Unmarshal(b, &s); err != nil {
			return nil, err
		}
		out = append(out, s)
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
