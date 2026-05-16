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
	FailureThresholdsByTier           map[string]int `json:"failure_thresholds_by_tier"`
	GoldUpstreamDegradedExtraFailures int            `json:"gold_upstream_degraded_extra_failures"`
	RollingWindowDays                 int            `json:"rolling_window_days"`
	SilverSpikeExtraFailures          int            `json:"silver_spike_extra_failures"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type upstreamDoc struct {
	Degraded    bool   `json:"degraded"`
	UpstreamID string `json:"upstream_id"`
}

type serviceDoc struct {
	OutcomesByDay map[string]string `json:"outcomes_by_day"`
	ServiceID     string             `json:"service_id"`
	Tier          string             `json:"tier"`
	UpstreamID    string             `json:"upstream_id"`
}

func main() {
	dataDir := getenv("CBSA_DATA_DIR", "/app/breakers")
	auditDir := getenv("CBSA_AUDIT_DIR", "/app/audit")
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

	services, err := loadServices(filepath.Join(dataDir, "services"))
	if err != nil {
		return err
	}
	sort.Slice(services, func(i, j int) bool { return services[i].ServiceID < services[j].ServiceID })

	upPath := filepath.Join(dataDir, "upstreams")
	upstreams := map[string]upstreamDoc{}
	entries, err := os.ReadDir(upPath)
	if err == nil {
		for _, e := range entries {
			if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
				continue
			}
			stem := e.Name()[:len(e.Name())-5]
			b, err := os.ReadFile(filepath.Join(upPath, e.Name()))
			if err != nil {
				continue
			}
			var u upstreamDoc
			if json.Unmarshal(b, &u) != nil {
				upstreams[stem] = upstreamDoc{Degraded: false, UpstreamID: stem}
				continue
			}
			upstreams[stem] = u
		}
	}

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
		kind := strVal(ev["kind"])
		if !incidentWellFormed(kind, ev) {
			ignored++
			continue
		}
		applied = append(applied, ev)
	}

	deltaByTier := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	silverSpike := false
	forceOpen := map[string]bool{}

	for _, ev := range applied {
		kind := strVal(ev["kind"])
		switch kind {
		case "tier_threshold_delta":
			tt := strVal(ev["target_tier"])
			deltaByTier[tt] += intVal(ev["delta"])
		case "silver_spike":
			silverSpike = true
		case "force_open":
			forceOpen[strVal(ev["service_id"])] = true
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
	for _, tier := range []string{"bronze", "gold", "silver"} {
		base := pol.FailureThresholdsByTier[tier]
		ds := deltaByTier[tier]
		adj := base + ds
		if adj < 1 {
			adj = 1
		}
		tiersOut[tier] = map[string]any{
			"adjusted_threshold": adj,
			"base_threshold":     base,
			"delta_sum":          ds,
		}
	}

	winStart := ps.CurrentDay - (pol.RollingWindowDays - 1)
	goldPenaltyN := pol.GoldUpstreamDegradedExtraFailures
	if goldPenaltyN < 0 {
		goldPenaltyN = 0
	}
	silverExtra := pol.SilverSpikeExtraFailures
	if silverExtra < 0 {
		silverExtra = 0
	}

	svcOut := make([]map[string]any, 0, len(services))
	openN := 0
	trippedN := 0
	goldPenCount := 0
	for _, sv := range services {
		up := upstreams[sv.UpstreamID]
		if sv.Tier == "gold" && up.Degraded && goldPenaltyN > 0 {
			goldPenCount++
		}
	}

	for _, sv := range services {
		raw := countFails(sv.OutcomesByDay, winStart, ps.CurrentDay)
		rf := raw
		for _, ev := range applied {
			if strVal(ev["kind"]) != "fail_day_suppress" {
				continue
			}
			if strVal(ev["service_id"]) != sv.ServiceID {
				continue
			}
			for _, d := range daySlice(ev["days"]) {
				if d < winStart || d > ps.CurrentDay {
					continue
				}
				key := strconv.Itoa(d)
				if sv.OutcomesByDay[key] == "fail" && rf > 0 {
					rf--
				}
			}
		}
		if rf < 0 {
			rf = 0
		}

		up := upstreams[sv.UpstreamID]
		eff := rf
		if sv.Tier == "gold" && up.Degraded && goldPenaltyN > 0 {
			eff += goldPenaltyN
		}
		if sv.Tier == "silver" && silverSpike {
			eff += silverExtra
		}

		baseTh := pol.FailureThresholdsByTier[sv.Tier]
		adjTh := baseTh + deltaByTier[sv.Tier]
		if adjTh < 1 {
			adjTh = 1
		}

		forced := forceOpen[sv.ServiceID]
		numericTrip := eff >= adjTh
		state := "closed"
		tripped := false
		if forced {
			state = "open"
			tripped = true
		} else if numericTrip {
			state = "open"
			tripped = true
		}

		reasons := []string{}
		if forced {
			reasons = append(reasons, "force_open_incident")
		}
		if sv.Tier == "gold" && up.Degraded && goldPenaltyN > 0 {
			reasons = append(reasons, "gold_upstream_degraded_penalty")
		}
		if sv.Tier == "silver" && silverSpike && silverExtra > 0 {
			reasons = append(reasons, "silver_spike_active")
		}
		if numericTrip {
			reasons = append(reasons, "threshold_exceeded")
		}
		reasons = uniqSort(reasons)

		if state == "closed" {
			reasons = []string{}
		}

		if state == "open" {
			openN++
		}
		if tripped {
			trippedN++
		}

		svcOut = append(svcOut, map[string]any{
			"adjusted_threshold": adjTh,
			"computed_state":     state,
			"effective_failures": eff,
			"raw_failures":       raw,
			"reasons":            reasons,
			"service_id":         sv.ServiceID,
			"tier":               sv.Tier,
			"tripped":            tripped,
			"upstream_id":        sv.UpstreamID,
		})
	}

	touch := map[string][]string{}
	for _, sv := range services {
		touch[sv.UpstreamID] = append(touch[sv.UpstreamID], sv.ServiceID)
	}
	keys := make([]string, 0, len(touch))
	for k := range touch {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	upOut := map[string]any{}
	for _, k := range keys {
		ss := touch[k]
		sort.Strings(ss)
		u := upstreams[k]
		upOut[k] = map[string]any{
			"degraded":             u.Degraded,
			"referencing_services": ss,
		}
	}

	summary := map[string]any{
		"applied_incident_events":             len(journal),
		"gold_services_with_upstream_penalty": goldPenCount,
		"ignored_incident_events":             ignored,
		"open_services":                       openN,
		"services_total":                      len(services),
		"silver_spike_active":                 silverSpike,
		"tripped_services":                    trippedN,
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "service_verdicts.json"), map[string]any{"services": svcOut}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "tier_thresholds.json"), map[string]any{"tiers": tiersOut}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "incident_journal.json"), map[string]any{"applied_events": journal}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "upstream_touchpoints.json"), map[string]any{"upstreams": upOut}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "summary.json"), summary); err != nil {
		return err
	}
	return nil
}

func loadServices(dir string) ([]serviceDoc, error) {
	var out []serviceDoc
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })
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

func countFails(m map[string]string, start, end int) int {
	n := 0
	for d := start; d <= end; d++ {
		key := strconv.Itoa(d)
		if m[key] == "fail" {
			n++
		}
	}
	return n
}

func incidentWellFormed(kind string, ev map[string]any) bool {
	switch kind {
	case "tier_threshold_delta":
		tt := strVal(ev["target_tier"])
		if tt != "gold" && tt != "silver" && tt != "bronze" {
			return false
		}
		if _, ok := ev["delta"]; !ok {
			return false
		}
		return true
	case "fail_day_suppress":
		if strVal(ev["service_id"]) == "" {
			return false
		}
		if _, ok := ev["days"]; !ok {
			return false
		}
		return true
	case "silver_spike":
		return true
	case "force_open":
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
	case "tier_threshold_delta":
		m["delta"] = intVal(ev["delta"])
		m["target_tier"] = strVal(ev["target_tier"])
	case "fail_day_suppress":
		m["days"] = daySlice(ev["days"])
		m["service_id"] = strVal(ev["service_id"])
	case "force_open":
		m["service_id"] = strVal(ev["service_id"])
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
