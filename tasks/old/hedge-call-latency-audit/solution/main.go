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
	HedgeDelayMsPerTier    map[string]int `json:"hedge_delay_ms_per_tier"`
	HedgeBudgetPerWindow   map[string]int `json:"hedge_budget_per_window"`
	SlaMaxMsPerTier        map[string]int `json:"sla_max_ms_per_tier"`
	SupportedIncidentKinds []string       `json:"supported_incident_kinds"`
	WindowMs               int64          `json:"window_ms"`
}

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type callRec struct {
	CallID           string `json:"call_id"`
	CorrelationRoot  string `json:"correlation_root"`
	ServiceTier      string `json:"service_tier"`
	PrimaryLatencyMs int    `json:"primary_latency_ms"`
	HedgeLatencyMs   *int   `json:"hedge_latency_ms"`
	Status           string `json:"status"`
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	data := getenv("HCL_DATA_DIR", "/app/hedgecalls")
	outd := getenv("HCL_AUDIT_DIR", "/app/audit")
	if err := run(data, outd); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
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

	psRaw, err := os.ReadFile(filepath.Join(dataDir, "pool_state.json"))
	if err != nil {
		return err
	}
	var ps poolState
	if err := json.Unmarshal(psRaw, &ps); err != nil {
		return err
	}

	bump, credit, err := loadOverrides(filepath.Join(dataDir, "overrides"))
	if err != nil {
		return err
	}

	disabledRoots, disabledCalls, accepted, ignored, err := processIncidents(
		dataDir, pol, ps.CurrentDay, bump, credit,
	)
	if err != nil {
		return err
	}

	if err := loadAnchors(filepath.Join(dataDir, "anchors"), disabledCalls); err != nil {
		return err
	}

	calls, err := loadCalls(filepath.Join(dataDir, "calls"))
	if err != nil {
		return err
	}

	tiers := []string{"bronze", "gold", "silver"}
	tierCap := map[string]int{}
	tierDelay := map[string]int{}
	tierUsed := map[string]int{}
	for _, t := range tiers {
		tierCap[t] = pol.HedgeBudgetPerWindow[t] + credit[t]
		tierDelay[t] = pol.HedgeDelayMsPerTier[t] + bump[t]
		tierUsed[t] = 0
	}

	verdictCounts := map[string]int{
		"error": 0, "hedge_budget_exhausted": 0, "hedge_disabled": 0,
		"met_sla": 0, "missed_sla": 0,
	}
	rows := make([]map[string]any, 0, len(calls))
	hedgeFiredTotal := 0

	for _, c := range calls {
		root := c.CorrelationRoot
		if root == "" {
			root = c.CallID
		}
		disabled := disabledCalls[c.CallID] || disabledRoots[root]

		row := map[string]any{
			"call_id":            c.CallID,
			"correlation_root":   root,
			"effective_latency_ms": nil,
			"hedge_fired":        false,
			"hedge_latency_ms":   c.HedgeLatencyMs,
			"latency_source":     nil,
			"primary_latency_ms": c.PrimaryLatencyMs,
			"service_tier":       c.ServiceTier,
		}

		if c.Status == "error" {
			row["verdict"] = "error"
			verdictCounts["error"]++
			rows = append(rows, row)
			continue
		}

		if disabled {
			row["verdict"] = "hedge_disabled"
			row["hedge_fired"] = false
			if c.Status == "success" {
				row["effective_latency_ms"] = c.PrimaryLatencyMs
				row["latency_source"] = "primary"
			}
			verdictCounts["hedge_disabled"]++
			rows = append(rows, row)
			continue
		}

		delay := tierDelay[c.ServiceTier]
		trigger := c.HedgeLatencyMs != nil && (
			(c.Status == "success" && c.PrimaryLatencyMs > delay) ||
				c.Status == "primary_timeout")

		if trigger && tierUsed[c.ServiceTier] >= tierCap[c.ServiceTier] {
			row["verdict"] = "hedge_budget_exhausted"
			row["hedge_fired"] = false
			if c.Status == "success" {
				row["effective_latency_ms"] = c.PrimaryLatencyMs
				row["latency_source"] = "primary"
			}
			verdictCounts["hedge_budget_exhausted"]++
			rows = append(rows, row)
			continue
		}

		if trigger {
			row["hedge_fired"] = true
			tierUsed[c.ServiceTier]++
			hedgeFiredTotal++
			h := *c.HedgeLatencyMs
			if c.Status == "success" {
				eff := c.PrimaryLatencyMs
				src := "primary"
				if h < eff {
					eff = h
					src = "hedge"
				}
				row["effective_latency_ms"] = eff
				row["latency_source"] = src
			} else {
				row["effective_latency_ms"] = h
				row["latency_source"] = "hedge"
			}
		} else {
			row["hedge_fired"] = false
			if c.Status == "success" {
				row["effective_latency_ms"] = c.PrimaryLatencyMs
				row["latency_source"] = "primary"
			}
		}

		eff, _ := row["effective_latency_ms"].(int)
		if row["effective_latency_ms"] == nil {
			row["verdict"] = "missed_sla"
			verdictCounts["missed_sla"]++
		} else if eff <= pol.SlaMaxMsPerTier[c.ServiceTier] {
			row["verdict"] = "met_sla"
			verdictCounts["met_sla"]++
		} else {
			row["verdict"] = "missed_sla"
			verdictCounts["missed_sla"]++
		}
		rows = append(rows, row)
	}

	tiersOut := map[string]any{}
	for _, t := range tiers {
		tiersOut[t] = map[string]any{
			"budget_cap":         tierCap[t],
			"budget_credit":      credit[t],
			"delay_bump_ms":      bump[t],
			"effective_delay_ms": tierDelay[t],
			"hedges_fired":       tierUsed[t],
		}
	}

	disCallList := make([]string, 0, len(disabledCalls))
	for id := range disabledCalls {
		disCallList = append(disCallList, id)
	}
	sort.Strings(disCallList)
	disRootList := make([]string, 0, len(disabledRoots))
	for r := range disabledRoots {
		disRootList = append(disRootList, r)
	}
	sort.Strings(disRootList)

	sort.Slice(accepted, func(i, j int) bool {
		di := intFromAny(accepted[i]["day"])
		dj := intFromAny(accepted[j]["day"])
		if di != dj {
			return di < dj
		}
		return fmt.Sprint(accepted[i]["event_id"]) < fmt.Sprint(accepted[j]["event_id"])
	})
	sort.Slice(ignored, func(i, j int) bool {
		di := intFromAny(ignored[i]["day"])
		dj := intFromAny(ignored[j]["day"])
		if di != dj {
			return di < dj
		}
		return fmt.Sprint(ignored[i]["event_id"]) < fmt.Sprint(ignored[j]["event_id"])
	})

	payloads := map[string]any{
		"call_verdicts.json": map[string]any{
			"calls": rows, "window_ms": pol.WindowMs,
		},
		"compromise_report.json": map[string]any{
			"disabled_call_ids":          disCallList,
			"disabled_correlation_roots": disRootList,
		},
		"hedge_budget.json": map[string]any{
			"tiers": tiersOut, "window_ms": pol.WindowMs,
		},
		"incident_journal.json": map[string]any{
			"accepted": accepted, "ignored": ignored,
		},
		"summary.json": map[string]any{
			"calls_total":      len(rows),
			"hedge_fired_total": hedgeFiredTotal,
			"service_tiers":    []string{"bronze", "gold", "silver"},
			"verdict_counts":   verdictCounts,
			"window_ms":        pol.WindowMs,
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

func loadOverrides(dir string) (map[string]int, map[string]int, error) {
	bump := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	credit := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	ents, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return bump, credit, nil
		}
		return nil, nil, err
	}
	names := make([]string, 0)
	for _, e := range ents {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".json") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		b, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			return nil, nil, err
		}
		var raw map[string]json.RawMessage
		if json.Unmarshal(b, &raw) != nil {
			continue
		}
		if rf, ok := raw["delay_bump_ms"]; ok {
			var m map[string]int
			if json.Unmarshal(rf, &m) == nil {
				for k, v := range m {
					bump[k] += v
				}
			}
		}
		if rf, ok := raw["budget_credit"]; ok {
			var m map[string]int
			if json.Unmarshal(rf, &m) == nil {
				for k, v := range m {
					credit[k] += v
				}
			}
		}
	}
	return bump, credit, nil
}

func processIncidents(
	dataDir string,
	pol policy,
	currentDay int,
	bump, credit map[string]int,
) (map[string]bool, map[string]bool, []map[string]any, []map[string]any, error) {
	disabledRoots := map[string]bool{}
	disabledCalls := map[string]bool{}
	accepted := make([]map[string]any, 0)
	ignored := make([]map[string]any, 0)

	supported := map[string]struct{}{}
	for _, k := range pol.SupportedIncidentKinds {
		supported[k] = struct{}{}
	}

	b, err := os.ReadFile(filepath.Join(dataDir, "incidents.json"))
	if err != nil {
		return nil, nil, nil, nil, err
	}
	var inc struct {
		Events []map[string]any `json:"events"`
	}
	if err := json.Unmarshal(b, &inc); err != nil {
		return nil, nil, nil, nil, err
	}

	for _, ev := range inc.Events {
		kind := fmt.Sprint(ev["kind"])
		day := intFromAny(ev["day"])
		eid := fmt.Sprint(ev["event_id"])
		acc := true
		if v, ok := ev["accepted"]; ok {
			acc = boolFromAny(v)
		}
		reason := ""
		if !acc {
			reason = "accepted_false"
		} else if day > currentDay {
			reason = "future_day"
		} else if _, ok := supported[kind]; !ok {
			reason = "unsupported_kind"
		}
		if reason != "" {
			ignored = append(ignored, map[string]any{
				"day": day, "event_id": eid, "kind": kind, "reason": reason,
			})
			continue
		}
		accepted = append(accepted, ev)
		scope, _ := ev["scope"].(map[string]any)
		if scope == nil {
			continue
		}
		switch kind {
		case "hedge_compromise":
			if r, ok := scope["correlation_root"]; ok {
				disabledRoots[fmt.Sprint(r)] = true
			}
			if id, ok := scope["call_id"]; ok {
				disabledCalls[fmt.Sprint(id)] = true
			}
		case "force_budget_credit":
			tier := fmt.Sprint(scope["service_tier"])
			credit[tier] += intFromAny(scope["credit"])
		case "hedge_delay_bump":
			tier := fmt.Sprint(scope["service_tier"])
			bump[tier] += intFromAny(scope["bump_ms"])
		}
	}
	return disabledRoots, disabledCalls, accepted, ignored, nil
}

func loadAnchors(dir string, disabledCalls map[string]bool) error {
	ents, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	names := make([]string, 0)
	for _, e := range ents {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".txt") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		b, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			return err
		}
		for _, line := range strings.Split(string(b), "\n") {
			line = strings.TrimSpace(line)
			if line == "" {
				continue
			}
			parts := strings.Fields(line)
			if len(parts) >= 2 && parts[1] == "hedge_disabled" {
				disabledCalls[parts[0]] = true
			}
		}
	}
	return nil
}

func loadCalls(dir string) ([]callRec, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make([]callRec, 0)
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var c callRec
		if err := json.Unmarshal(b, &c); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].CallID < out[j].CallID })
	return out, nil
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

func intFromAny(v any) int {
	switch x := v.(type) {
	case float64:
		return int(x)
	case int:
		return x
	case json.Number:
		i, _ := x.Int64()
		return int(i)
	default:
		return 0
	}
}

func boolFromAny(v any) bool {
	switch x := v.(type) {
	case bool:
		return x
	default:
		return false
	}
}
