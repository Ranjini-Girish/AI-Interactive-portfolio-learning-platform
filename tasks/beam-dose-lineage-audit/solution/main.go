package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type poolState struct {
	AsOfMinute  int `json:"as_of_minute"`
	RecentShotK int `json:"recent_shot_k"`
}

type tierRule struct {
	MaxDoseMgy     int `json:"max_dose_mgy"`
	MinQualityPct  int `json:"min_quality_pct"`
	WindowGrace    int `json:"window_grace_min"`
	CapacityWeight int `json:"capacity_weight"`
}

type profile struct {
	ProfileID        string `json:"profile_id"`
	DarkPulse        int    `json:"dark_pulse"`
	SaturationPulse  int    `json:"saturation_pulse"`
	GainUMgyPerPulse int    `json:"gain_umgy_per_pulse"`
}

type specimen struct {
	SpecimenID     string   `json:"specimen_id"`
	Tier           string   `json:"tier"`
	PlannedDoseMgy int      `json:"planned_dose_mgy"`
	ParentIDs      []string `json:"parent_ids"`
}

type windowRec struct {
	WindowID            string `json:"window_id"`
	StationID           string `json:"station_id"`
	StartMinute         int    `json:"start_minute"`
	EndMinute           int    `json:"end_minute"`
	CapacityWeightLimit int    `json:"capacity_weight_limit"`
}

type runRec struct {
	RunID           string `json:"run_id"`
	SpecimenID      string `json:"specimen_id"`
	ProfileID       string `json:"profile_id"`
	StationID       string `json:"station_id"`
	ScheduledMinute int    `json:"scheduled_minute"`
	QualityPct      int    `json:"quality_pct"`
	Pulses          []int  `json:"pulses"`
}

type eventLog struct {
	Events []event `json:"events"`
}

type event struct {
	Accepted          *bool  `json:"accepted,omitempty"`
	Kind              string `json:"kind"`
	Minute            int    `json:"minute"`
	ProfileID         string `json:"profile_id,omitempty"`
	DeltaUMgyPerPulse int    `json:"delta_umgy_per_pulse,omitempty"`
	SpecimenID        string `json:"specimen_id,omitempty"`
	WindowID          string `json:"window_id,omitempty"`
	RunID             string `json:"run_id,omitempty"`
	DoseMgy           int    `json:"dose_mgy,omitempty"`
}

type overridePick struct {
	Minute int
	Index  int
	Dose   int
}

type specimenImpact struct {
	Status string
	Depth  *int
}

func main() {
	dataDir := getenv("BDL_DATA_DIR", "/app/beamline")
	auditDir := getenv("BDL_AUDIT_DIR", "/app/audit")
	must(os.MkdirAll(auditDir, 0o755))

	var pool poolState
	readJSON(filepath.Join(dataDir, "pool_state.json"), &pool)

	var rules map[string]tierRule
	readJSON(filepath.Join(dataDir, "policy", "tier_rules.json"), &rules)

	profiles := map[string]profile{}
	for _, p := range glob(filepath.Join(dataDir, "profiles", "*.json")) {
		var rec profile
		readJSON(p, &rec)
		profiles[rec.ProfileID] = rec
	}

	specimens := map[string]specimen{}
	for _, p := range glob(filepath.Join(dataDir, "specimens", "*.json")) {
		var rec specimen
		readJSON(p, &rec)
		sort.Strings(rec.ParentIDs)
		specimens[rec.SpecimenID] = rec
	}

	windows := map[string]windowRec{}
	for _, p := range glob(filepath.Join(dataDir, "windows", "*.json")) {
		var rec windowRec
		readJSON(p, &rec)
		windows[rec.WindowID] = rec
	}

	runs := map[string]runRec{}
	for _, p := range glob(filepath.Join(dataDir, "runs", "*.json")) {
		var rec runRec
		readJSON(p, &rec)
		runs[rec.RunID] = rec
	}

	var logs eventLog
	readJSON(filepath.Join(dataDir, "incidents", "events.json"), &logs)

	gainShift := map[string]int{}
	shiftedProfiles := map[string]bool{}
	frozenWindows := map[string]bool{}
	heldSpecimens := map[string]bool{}
	contamSeeds := []string{}
	overrides := map[string]overridePick{}
	ignored := 0

	for idx, ev := range logs.Events {
		if ev.Accepted != nil && !*ev.Accepted {
			ignored++
			continue
		}
		if ev.Minute > pool.AsOfMinute {
			ignored++
			continue
		}
		switch ev.Kind {
		case "calibration_shift":
			if _, ok := profiles[ev.ProfileID]; !ok || ev.ProfileID == "" {
				ignored++
				continue
			}
			gainShift[ev.ProfileID] += ev.DeltaUMgyPerPulse
			shiftedProfiles[ev.ProfileID] = true
		case "lineage_contam":
			if _, ok := specimens[ev.SpecimenID]; !ok || ev.SpecimenID == "" {
				ignored++
				continue
			}
			contamSeeds = append(contamSeeds, ev.SpecimenID)
		case "specimen_hold":
			if _, ok := specimens[ev.SpecimenID]; !ok || ev.SpecimenID == "" {
				ignored++
				continue
			}
			heldSpecimens[ev.SpecimenID] = true
		case "window_freeze":
			if _, ok := windows[ev.WindowID]; !ok || ev.WindowID == "" {
				ignored++
				continue
			}
			frozenWindows[ev.WindowID] = true
		case "dose_override":
			if _, ok := runs[ev.RunID]; !ok || ev.RunID == "" {
				ignored++
				continue
			}
			prev, ok := overrides[ev.RunID]
			if !ok || ev.Minute > prev.Minute || (ev.Minute == prev.Minute && idx > prev.Index) {
				overrides[ev.RunID] = overridePick{Minute: ev.Minute, Index: idx, Dose: ev.DoseMgy}
			}
		default:
			ignored++
		}
	}

	cyclic := findCyclic(specimens)
	impact := lineageImpact(specimens, cyclic, contamSeeds)
	doseRows, assigned := buildDoseRows(pool, rules, profiles, specimens, windows, runs, gainShift, shiftedProfiles, frozenWindows, heldSpecimens, overrides, impact)
	lineageRows := buildLineageRows(specimens, impact)
	windowRows := buildWindowRows(rules, windows, runs, specimens, doseRows, assigned, frozenWindows)
	summary := buildSummary(pool, runs, specimens, doseRows, lineageRows, frozenWindows, ignored)

	writeJSON(filepath.Join(auditDir, "dose_assessment.json"), map[string]any{"runs": doseRows})
	writeJSON(filepath.Join(auditDir, "lineage_impact.json"), map[string]any{"specimens": lineageRows})
	writeJSON(filepath.Join(auditDir, "window_utilization.json"), map[string]any{"windows": windowRows})
	writeJSON(filepath.Join(auditDir, "summary.json"), summary)
}

func buildDoseRows(pool poolState, rules map[string]tierRule, profiles map[string]profile, specimens map[string]specimen, windows map[string]windowRec, runs map[string]runRec, gainShift map[string]int, shifted map[string]bool, frozen map[string]bool, holds map[string]bool, overrides map[string]overridePick, impact map[string]specimenImpact) ([]map[string]any, map[string]string) {
	ids := keys(runs)
	rows := []map[string]any{}
	assigned := map[string]string{}
	for _, id := range ids {
		r := runs[id]
		sp := specimens[r.SpecimenID]
		rule := rules[sp.Tier]
		prof := profiles[r.ProfileID]
		winID := chooseWindow(r, rule, windows)
		if winID != "" {
			assigned[r.RunID] = winID
		}
		median := medianAdjusted(r.Pulses, prof, pool.RecentShotK)
		var dose *int
		if median != nil {
			v := (*median * (prof.GainUMgyPerPulse + gainShift[prof.ProfileID])) / 1000
			dose = &v
		}
		if ov, ok := overrides[r.RunID]; ok {
			v := ov.Dose
			dose = &v
		}
		status := "ok"
		imp := impact[r.SpecimenID]
		if imp.Status == "cyclic" {
			status = "cyclic_lineage"
		} else if imp.Status == "direct_contam" || imp.Status == "inherited_contam" {
			status = "lineage_contaminated"
		} else if holds[r.SpecimenID] {
			status = "specimen_hold"
		} else if winID != "" && frozen[winID] {
			status = "window_frozen"
		} else if winID == "" {
			status = "no_window"
		} else if r.QualityPct < rule.MinQualityPct {
			status = "bad_quality"
		} else if dose != nil && *dose > rule.MaxDoseMgy {
			status = "over_dose"
		} else if dose == nil {
			status = "missing_shots"
		}
		reasons := map[string]bool{status: true}
		if shifted[prof.ProfileID] {
			reasons["calibration_shift:"+prof.ProfileID] = true
		}
		if _, ok := overrides[r.RunID]; ok {
			reasons["dose_override:"+r.RunID] = true
		}
		if imp.Depth != nil && imp.Status != "cyclic" {
			reasons[fmt.Sprintf("contam_depth:%d", *imp.Depth)] = true
		}
		if holds[r.SpecimenID] {
			reasons["hold:"+r.SpecimenID] = true
		}
		if winID != "" && frozen[winID] {
			reasons["window_freeze:"+winID] = true
		}
		row := map[string]any{
			"effective_dose_mgy":    nilPtr(dose),
			"median_adjusted_pulse": nilPtr(median),
			"profile_id":            r.ProfileID,
			"reasons":               sortedSet(reasons),
			"run_id":                r.RunID,
			"specimen_id":           r.SpecimenID,
			"status":                status,
			"window_id":             nilString(winID),
		}
		rows = append(rows, row)
	}
	return rows, assigned
}

func buildLineageRows(specimens map[string]specimen, impact map[string]specimenImpact) []map[string]any {
	rows := []map[string]any{}
	for _, id := range keys(specimens) {
		sp := specimens[id]
		imp := impact[id]
		rows = append(rows, map[string]any{
			"contam_depth":   nilPtr(imp.Depth),
			"lineage_status": imp.Status,
			"parents":        sp.ParentIDs,
			"specimen_id":    sp.SpecimenID,
			"tier":           sp.Tier,
		})
	}
	return rows
}

func buildWindowRows(rules map[string]tierRule, windows map[string]windowRec, runs map[string]runRec, specimens map[string]specimen, doseRows []map[string]any, assigned map[string]string, frozen map[string]bool) []map[string]any {
	statusByRun := map[string]string{}
	for _, row := range doseRows {
		statusByRun[row["run_id"].(string)] = row["status"].(string)
	}
	byWindow := map[string][]string{}
	for rid, wid := range assigned {
		byWindow[wid] = append(byWindow[wid], rid)
	}
	rows := []map[string]any{}
	for _, id := range keys(windows) {
		w := windows[id]
		runIDs := byWindow[id]
		sort.Strings(runIDs)
		charged := 0
		if !frozen[id] {
			for _, rid := range runIDs {
				st := statusByRun[rid]
				if st == "ok" || st == "bad_quality" || st == "over_dose" {
					sp := specimens[runs[rid].SpecimenID]
					charged += rules[sp.Tier].CapacityWeight
				}
			}
		}
		status := "within_capacity"
		if frozen[id] {
			status = "frozen"
		} else if charged > w.CapacityWeightLimit {
			status = "over_capacity"
		}
		rows = append(rows, map[string]any{
			"assigned_runs":  runIDs,
			"capacity_limit": w.CapacityWeightLimit,
			"charged_weight": charged,
			"station_id":     w.StationID,
			"status":         status,
			"window_id":      w.WindowID,
		})
	}
	return rows
}

func buildSummary(pool poolState, runs map[string]runRec, specimens map[string]specimen, doseRows []map[string]any, lineageRows []map[string]any, frozen map[string]bool, ignored int) map[string]any {
	statusCounts := map[string]int{}
	for _, row := range doseRows {
		statusCounts[row["status"].(string)]++
	}
	lineageCounts := map[string]int{}
	for _, row := range lineageRows {
		lineageCounts[row["lineage_status"].(string)]++
	}
	return map[string]any{
		"as_of_minute":            pool.AsOfMinute,
		"frozen_windows":          len(frozen),
		"ignored_incident_events": ignored,
		"lineage_status_counts":   lineageCounts,
		"run_count":               len(runs),
		"specimen_count":          len(specimens),
		"status_counts":           statusCounts,
	}
}

func medianAdjusted(pulses []int, prof profile, k int) *int {
	usable := []int{}
	for _, p := range pulses {
		adj := p - prof.DarkPulse
		if adj > 0 && p < prof.SaturationPulse {
			usable = append(usable, adj)
		}
	}
	if len(usable) == 0 {
		return nil
	}
	if len(usable) > k {
		usable = usable[len(usable)-k:]
	}
	sort.Ints(usable)
	n := len(usable)
	v := usable[n/2]
	if n%2 == 0 {
		v = (usable[n/2-1] + usable[n/2]) / 2
	}
	return &v
}

func chooseWindow(r runRec, rule tierRule, windows map[string]windowRec) string {
	best := ""
	for _, id := range keys(windows) {
		w := windows[id]
		if w.StationID != r.StationID {
			continue
		}
		if r.ScheduledMinute < w.StartMinute-rule.WindowGrace || r.ScheduledMinute > w.EndMinute+rule.WindowGrace {
			continue
		}
		if best == "" || w.EndMinute < windows[best].EndMinute || (w.EndMinute == windows[best].EndMinute && id < best) {
			best = id
		}
	}
	return best
}

func lineageImpact(specimens map[string]specimen, cyclic map[string]bool, seeds []string) map[string]specimenImpact {
	children := map[string][]string{}
	for _, sp := range specimens {
		for _, p := range sp.ParentIDs {
			if _, ok := specimens[p]; ok {
				children[p] = append(children[p], sp.SpecimenID)
			}
		}
	}
	impact := map[string]specimenImpact{}
	for id := range specimens {
		if cyclic[id] {
			impact[id] = specimenImpact{Status: "cyclic"}
		} else {
			impact[id] = specimenImpact{Status: "clean"}
		}
	}
	type item struct {
		ID    string
		Depth int
	}
	queue := []item{}
	for _, seed := range seeds {
		if cyclic[seed] {
			continue
		}
		d := 0
		impact[seed] = specimenImpact{Status: "direct_contam", Depth: &d}
		queue = append(queue, item{ID: seed, Depth: 0})
	}
	for len(queue) > 0 {
		cur := queue[0]
		queue = queue[1:]
		for _, child := range children[cur.ID] {
			if cyclic[child] {
				continue
			}
			nd := cur.Depth + 1
			prev := impact[child]
			if prev.Depth == nil || nd < *prev.Depth {
				status := "inherited_contam"
				impact[child] = specimenImpact{Status: status, Depth: &nd}
				queue = append(queue, item{ID: child, Depth: nd})
			}
		}
	}
	return impact
}

func findCyclic(specimens map[string]specimen) map[string]bool {
	state := map[string]int{}
	stack := []string{}
	cyclic := map[string]bool{}
	var dfs func(string)
	dfs = func(id string) {
		state[id] = 1
		stack = append(stack, id)
		for _, p := range specimens[id].ParentIDs {
			if _, ok := specimens[p]; !ok {
				continue
			}
			if state[p] == 0 {
				dfs(p)
			} else if state[p] == 1 {
				for i := len(stack) - 1; i >= 0; i-- {
					cyclic[stack[i]] = true
					if stack[i] == p {
						break
					}
				}
			}
		}
		stack = stack[:len(stack)-1]
		state[id] = 2
	}
	for _, id := range keys(specimens) {
		if state[id] == 0 {
			dfs(id)
		}
	}
	return cyclic
}

func readJSON(path string, dst any) {
	b, err := os.ReadFile(path)
	must(err)
	must(json.Unmarshal(b, dst))
}

func writeJSON(path string, obj any) {
	f, err := os.Create(path)
	must(err)
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	must(enc.Encode(obj))
}

func glob(pattern string) []string {
	matches, err := filepath.Glob(pattern)
	must(err)
	sort.Strings(matches)
	return matches
}

func keys[T any](m map[string]T) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func sortedSet(in map[string]bool) []string {
	out := make([]string, 0, len(in))
	for k := range in {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func nilPtr(v *int) any {
	if v == nil {
		return nil
	}
	return *v
}

func nilString(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func getenv(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func must(err error) {
	if err != nil {
		panic(err)
	}
}
