package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type policyDoc struct {
	GuardCooldownDays            int                       `json:"guard_cooldown_days"`
	HazardDecayByTier            map[string]int            `json:"hazard_decay_by_tier"`
	RiskThresholdsByTier         map[string]map[string]int `json:"risk_thresholds_by_tier"`
	SupportedIncidentKinds       []string                  `json:"supported_incident_kinds"`
	UncoveredMultiplierPctByTier map[string]int            `json:"uncovered_multiplier_pct_by_tier"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type routeDoc struct {
	DepotIDs []string `json:"depot_ids"`
	RouteID  string   `json:"route_id"`
	Segments []struct {
		BaseHazard int    `json:"base_hazard"`
		SegmentID  string `json:"segment_id"`
	} `json:"segments"`
}

type depotDoc struct {
	ActiveUntil int    `json:"active_until"`
	DepotID     string `json:"depot_id"`
}

type guardDoc struct {
	GuardID string `json:"guard_id"`
	Skill   int    `json:"skill"`
}

type convoyDoc struct {
	ConvoyID       string `json:"convoy_id"`
	DepartureDay   int    `json:"departure_day"`
	RequiredGuards int    `json:"required_guards"`
	RouteID        string `json:"route_id"`
	Tier           string `json:"tier"`
}

func main() {
	dataDir := getenv("WESA_DATA_DIR", "/app/escort")
	auditDir := getenv("WESA_AUDIT_DIR", "/app/schedule")
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
	var pol policyDoc
	if err := readJSON(filepath.Join(dataDir, "policy.json"), &pol); err != nil {
		return err
	}
	var il incidentLog
	if err := readJSON(filepath.Join(dataDir, "incident_log.json"), &il); err != nil {
		return err
	}
	supported := map[string]bool{}
	for _, k := range pol.SupportedIncidentKinds {
		supported[k] = true
	}

	routes, err := loadRoutes(filepath.Join(dataDir, "routes"))
	if err != nil {
		return err
	}
	depots, err := loadDepots(filepath.Join(dataDir, "depots"))
	if err != nil {
		return err
	}
	guards, err := loadGuards(filepath.Join(dataDir, "guards"))
	if err != nil {
		return err
	}
	convoys, err := loadConvoys(filepath.Join(dataDir, "convoys"))
	if err != nil {
		return err
	}

	currentDay := ps.CurrentDay
	cooldown := pol.GuardCooldownDays
	routeDelta := map[string]int{}
	for id := range routes {
		routeDelta[id] = 0
	}
	depotLimit := map[string]int{}
	for id, d := range depots {
		depotLimit[id] = d.ActiveUntil
	}
	benched := map[string]bool{}
	spikeRoutes := map[string]bool{}
	embargoRoutes := map[string]bool{}
	var applied []map[string]any

	var kept []map[string]any
	for _, ev := range il.Events {
		if eventOK(ev, currentDay, supported) {
			kept = append(kept, ev)
		}
	}
	sort.Slice(kept, func(i, j int) bool {
		di, _ := asInt(kept[i]["day"])
		dj, _ := asInt(kept[j]["day"])
		if di != dj {
			return di < dj
		}
		return fmt.Sprint(kept[i]["event_id"]) < fmt.Sprint(kept[j]["event_id"])
	})
	ignored := len(il.Events) - len(kept)

	for _, ev := range kept {
		kind := fmt.Sprint(ev["kind"])
		row := map[string]any{
			"day":      ev["day"],
			"event_id": ev["event_id"],
			"kind":     kind,
		}
		switch kind {
		case "hazard_spike":
			rid := fmt.Sprint(ev["route_id"])
			delta, _ := asInt(ev["delta"])
			routeDelta[rid] += delta
			spikeRoutes[rid] = true
			row["delta"] = delta
			row["route_id"] = rid
		case "depot_closure":
			did := fmt.Sprint(ev["depot_id"])
			effDay, _ := asInt(ev["effective_day"])
			limit := effDay - 1
			if cur, ok := depotLimit[did]; ok {
				if limit < cur {
					depotLimit[did] = limit
				}
			} else {
				depotLimit[did] = limit
			}
			row["depot_id"] = did
			row["effective_day"] = effDay
		case "guard_bench":
			gid := fmt.Sprint(ev["guard_id"])
			benched[gid] = true
			row["guard_id"] = gid
		case "route_embargo":
			ridsAny := ev["route_ids"].([]any)
			var rids []string
			for _, r := range ridsAny {
				rid := fmt.Sprint(r)
				embargoRoutes[rid] = true
				rids = append(rids, rid)
			}
			sort.Strings(rids)
			row["route_ids"] = rids
		}
		applied = append(applied, row)
	}

	classify := func(raw int, tier string) string {
		th := pol.RiskThresholdsByTier[tier]
		if raw < th["medium"] {
			return "low"
		}
		if raw < th["high"] {
			return "medium"
		}
		if raw < th["critical"] {
			return "high"
		}
		return "critical"
	}
	rank := map[string]int{"low": 0, "medium": 1, "high": 2, "critical": 3}
	covered := func(routeID string, depDay int) bool {
		r := routes[routeID]
		for _, did := range r.DepotIDs {
			if depotLimit[did] >= depDay {
				return true
			}
		}
		return false
	}

	var riskRows []map[string]any
	coveredCount := 0
	for _, c := range convoys {
		raw := 0
		delta := routeDelta[c.RouteID]
		for _, seg := range routes[c.RouteID].Segments {
			raw += seg.BaseHazard + delta
		}
		decay := pol.HazardDecayByTier[c.Tier]
		if raw > decay {
			raw -= decay
		} else {
			raw = 0
		}
		isCov := covered(c.RouteID, c.DepartureDay)
		if isCov {
			coveredCount++
		}
		reasons := []string{}
		if !isCov {
			mult := pol.UncoveredMultiplierPctByTier[c.Tier]
			raw = (raw * mult) / 100
			reasons = append(reasons, "uncovered_route")
		}
		if spikeRoutes[c.RouteID] {
			reasons = append(reasons, "hazard_spike_active")
		}
		level := classify(raw, c.Tier)
		if embargoRoutes[c.RouteID] {
			if rank[level] < rank["high"] {
				level = "high"
			}
			reasons = append(reasons, "route_embargo")
		}
		sort.Strings(reasons)
		reasons = uniqueStrings(reasons)
		riskRows = append(riskRows, map[string]any{
			"convoy_id":     c.ConvoyID,
			"departure_day": c.DepartureDay,
			"raw_hazard":    raw,
			"risk_level":    level,
			"reasons":       reasons,
			"route_id":      c.RouteID,
			"tier":          c.Tier,
		})
	}
	sort.Slice(riskRows, func(i, j int) bool {
		return fmt.Sprint(riskRows[i]["convoy_id"]) < fmt.Sprint(riskRows[j]["convoy_id"])
	})

	var eligible []guardDoc
	for _, g := range guards {
		if !benched[g.GuardID] {
			eligible = append(eligible, g)
		}
	}
	sort.Slice(eligible, func(i, j int) bool {
		if eligible[i].Skill != eligible[j].Skill {
			return eligible[i].Skill > eligible[j].Skill
		}
		return eligible[i].GuardID < eligible[j].GuardID
	})

	sched := append([]convoyDoc(nil), convoys...)
	sort.Slice(sched, func(i, j int) bool {
		if sched[i].DepartureDay != sched[j].DepartureDay {
			return sched[i].DepartureDay < sched[j].DepartureDay
		}
		return sched[i].ConvoyID < sched[j].ConvoyID
	})

	guardLastDay := map[string]int{}
	guardLastConvoy := map[string]string{}
	var assignRows []map[string]any
	fullyAssigned := 0
	for _, c := range sched {
		if embargoRoutes[c.RouteID] {
			assignRows = append(assignRows, map[string]any{
				"assigned_guard_ids": []string{},
				"assignment_status":  "blocked_escort",
				"convoy_id":          c.ConvoyID,
				"required_guards":    c.RequiredGuards,
			})
			continue
		}
		var picked []string = []string{}
		for _, g := range eligible {
			if len(picked) >= c.RequiredGuards {
				break
			}
			if d0, ok := guardLastDay[g.GuardID]; ok {
				if guardLastConvoy[g.GuardID] != c.ConvoyID && abs(c.DepartureDay-d0) <= cooldown {
					continue
				}
			}
			picked = append(picked, g.GuardID)
		}
		sort.Strings(picked)
		status := "unassigned"
		if c.RequiredGuards == 0 {
			status = "unassigned"
		} else if len(picked) == c.RequiredGuards {
			status = "assigned"
			fullyAssigned++
		} else if len(picked) > 0 {
			status = "partial"
		}
		for _, gid := range picked {
			guardLastDay[gid] = c.DepartureDay
			guardLastConvoy[gid] = c.ConvoyID
		}
		assignRows = append(assignRows, map[string]any{
			"assigned_guard_ids": picked,
			"assignment_status":  status,
			"convoy_id":          c.ConvoyID,
			"required_guards":    c.RequiredGuards,
		})
	}
	sort.Slice(assignRows, func(i, j int) bool {
		return fmt.Sprint(assignRows[i]["convoy_id"]) < fmt.Sprint(assignRows[j]["convoy_id"])
	})

	routeSet := map[string]bool{}
	for _, c := range convoys {
		routeSet[c.RouteID] = true
	}
	var routeIDs []string
	for rid := range routeSet {
		routeIDs = append(routeIDs, rid)
	}
	sort.Strings(routeIDs)

	var verdictRows []map[string]any
	blockedRoutes := 0
	for _, rid := range routeIDs {
		maxRisk := "low"
		maxRank := 0
		for _, r := range riskRows {
			if fmt.Sprint(r["route_id"]) != rid {
				continue
			}
			depDay, _ := asInt(r["departure_day"])
			if depDay > currentDay {
				continue
			}
			rl := fmt.Sprint(r["risk_level"])
			if rank[rl] > maxRank {
				maxRank = rank[rl]
				maxRisk = rl
			}
		}
		verdict := "cleared"
		reasons := []string{}
		if embargoRoutes[rid] {
			verdict = "blocked"
			reasons = []string{"route_embargo"}
		} else if maxRisk == "critical" {
			verdict = "blocked"
			reasons = []string{"critical_risk"}
		} else if maxRisk == "high" {
			verdict = "diverted"
			reasons = []string{"high_risk"}
		}
		if verdict == "blocked" {
			blockedRoutes++
		}
		verdictRows = append(verdictRows, map[string]any{
			"reasons":  reasons,
			"route_id": rid,
			"verdict":  verdict,
		})
	}

	journal := append([]map[string]any(nil), applied...)
	sort.Slice(journal, func(i, j int) bool {
		di, _ := asInt(journal[i]["day"])
		dj, _ := asInt(journal[j]["day"])
		if di != dj {
			return di < dj
		}
		return fmt.Sprint(journal[i]["event_id"]) < fmt.Sprint(journal[j]["event_id"])
	})

	summary := map[string]any{
		"applied_incident_events": len(journal),
		"blocked_routes":          blockedRoutes,
		"convoys_total":           len(convoys),
		"covered_convoys":         coveredCount,
		"embargo_routes":          len(embargoRoutes),
		"fully_assigned_convoys":  fullyAssigned,
		"ignored_incident_events": ignored,
		"route_embargo_active":    len(embargoRoutes) > 0,
		"uncovered_convoys":       len(convoys) - coveredCount,
	}

	outputs := map[string]any{
		"convoy_risk.json":      map[string]any{"convoys": riskRows},
		"guard_assignments.json": map[string]any{"convoys": assignRows},
		"route_verdict.json":    map[string]any{"routes": verdictRows},
		"incident_journal.json": map[string]any{"applied_events": journal},
		"summary.json":          summary,
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	for name, obj := range outputs {
		if err := writeCanonical(filepath.Join(auditDir, name), obj); err != nil {
			return err
		}
	}
	return nil
}

func readJSON(path string, dest any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, dest)
}

func loadRoutes(dir string) (map[string]routeDoc, error) {
	out := map[string]routeDoc{}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var r routeDoc
		if err := readJSON(filepath.Join(dir, e.Name()), &r); err != nil {
			return nil, err
		}
		out[r.RouteID] = r
	}
	return out, nil
}

func loadDepots(dir string) (map[string]depotDoc, error) {
	out := map[string]depotDoc{}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var d depotDoc
		if err := readJSON(filepath.Join(dir, e.Name()), &d); err != nil {
			return nil, err
		}
		out[d.DepotID] = d
	}
	return out, nil
}

func loadGuards(dir string) (map[string]guardDoc, error) {
	out := map[string]guardDoc{}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var g guardDoc
		if err := readJSON(filepath.Join(dir, e.Name()), &g); err != nil {
			return nil, err
		}
		out[g.GuardID] = g
	}
	return out, nil
}

func loadConvoys(dir string) ([]convoyDoc, error) {
	var out []convoyDoc
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var c convoyDoc
		if err := readJSON(filepath.Join(dir, e.Name()), &c); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ConvoyID < out[j].ConvoyID })
	return out, nil
}

func eventOK(ev map[string]any, currentDay int, supported map[string]bool) bool {
	if ev["accepted"] != true {
		return false
	}
	day, ok := asInt(ev["day"])
	if !ok || day > currentDay {
		return false
	}
	kind := fmt.Sprint(ev["kind"])
	if !supported[kind] {
		return false
	}
	switch kind {
	case "hazard_spike":
		_, ok1 := asInt(ev["delta"])
		_, ok2 := ev["route_id"].(string)
		return ok1 && ok2
	case "depot_closure":
		_, ok1 := asInt(ev["effective_day"])
		_, ok2 := ev["depot_id"].(string)
		return ok1 && ok2
	case "guard_bench":
		_, ok := ev["guard_id"].(string)
		return ok
		case "route_embargo":
			rids, ok := ev["route_ids"].([]any)
			if !ok {
				return false
			}
			for _, r := range rids {
				if _, ok := r.(string); !ok {
					return false
				}
			}
			return true
	}
	return false
}

func asInt(v any) (int, bool) {
	switch x := v.(type) {
	case float64:
		return int(x), true
	case int:
		return x, true
	case json.Number:
		i, err := x.Int64()
		return int(i), err == nil
	default:
		return 0, false
	}
}

func abs(n int) int {
	if n < 0 {
		return -n
	}
	return n
}

func uniqueStrings(in []string) []string {
	if len(in) == 0 {
		return []string{}
	}
	sort.Strings(in)
	out := []string{in[0]}
	for i := 1; i < len(in); i++ {
		if in[i] != in[i-1] {
			out = append(out, in[i])
		}
	}
	return out
}

func writeCanonical(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(b, '\n'), 0o644)
}
