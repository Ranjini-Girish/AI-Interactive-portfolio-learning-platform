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
	GraceDays   int `json:"grace_days"`
	MetricFloor int `json:"metric_floor"`
}

type poolState struct {
	CurrentDay     int `json:"current_day"`
	WindowEndDay   int `json:"window_end_day"`
	WindowStartDay int `json:"window_start_day"`
}

type observation struct {
	Day   int `json:"day"`
	Value int `json:"value"`
}

type armDef struct {
	ArmID         string        `json:"arm_id"`
	Observations  []observation `json:"observations"`
}

type experiment struct {
	Arms               []armDef `json:"arms"`
	ExperimentID       string   `json:"experiment_id"`
	HoldoutPct         int      `json:"holdout_pct"`
	LastObservationDay int      `json:"last_observation_day"`
	ParentID           string   `json:"parent_id"`
	Tier               string   `json:"tier"`
}

type tierDef struct {
	ExposureCap int    `json:"exposure_cap"`
	TierID      string `json:"tier_id"`
}

type incidentEvent struct {
	Accepted     bool   `json:"accepted"`
	Day          int    `json:"day"`
	ExperimentID string `json:"experiment_id"`
	Kind         string `json:"kind"`
}

type overlayState struct {
	MinObservations int
	ArmCap          int
	ExcludeArms     map[string]struct{}
}

type anchorNote struct {
	ExperimentID string
	ForcedStatus string
	Order        int
}

type profile struct {
	experimentID     string
	tier             string
	status           string
	effectiveHoldout int
	staleFlag        bool
	arms             []map[string]any
	eligibleTotal    *int
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	data := getenv("AAA_DATA_DIR", "/app/abarmalloc")
	outd := getenv("AAA_AUDIT_DIR", "/app/audit")
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

	tiers, err := loadTiers(filepath.Join(dataDir, "tiers"))
	if err != nil {
		return err
	}
	ov, err := loadOverlays(filepath.Join(dataDir, "overlays"))
	if err != nil {
		return err
	}
	compromised, frozen, err := loadIncidents(filepath.Join(dataDir, "incidents.json"))
	if err != nil {
		return err
	}
	anchors, err := loadAnchors(dataDir)
	if err != nil {
		return err
	}

	experiments, err := loadExperiments(filepath.Join(dataDir, "experiments"))
	if err != nil {
		return err
	}
	sort.Slice(experiments, func(i, j int) bool {
		return experiments[i].ExperimentID < experiments[j].ExperimentID
	})

	expSet := map[string]struct{}{}
	for _, e := range experiments {
		expSet[e.ExperimentID] = struct{}{}
	}

	forced := map[string]string{}
	sort.Slice(anchors, func(i, j int) bool {
		if anchors[i].ExperimentID != anchors[j].ExperimentID {
			return anchors[i].ExperimentID < anchors[j].ExperimentID
		}
		return anchors[i].Order < anchors[j].Order
	})
	for _, a := range anchors {
		if _, ok := expSet[a.ExperimentID]; ok {
			forced[a.ExperimentID] = a.ForcedStatus
		}
	}

	effectiveHoldout := map[string]int{}
	profiles := make([]profile, 0, len(experiments))

	for _, e := range experiments {
		eh := e.HoldoutPct
		if e.ParentID != "" {
			if _, ok := expSet[e.ParentID]; ok && e.ParentID < e.ExperimentID {
				if p, ok := effectiveHoldout[e.ParentID]; ok && p > eh {
					eh = p
				}
			}
		}
		effectiveHoldout[e.ExperimentID] = eh

		stale := ps.CurrentDay-e.LastObservationDay > pol.GraceDays
		_, quar := compromised[e.ExperimentID]
		_, frz := frozen[e.ExperimentID]

		status := "ok"
		switch {
		case quar:
			status = "quarantined"
		case frz:
			status = "frozen"
		case forced[e.ExperimentID] == "pause":
			status = "hold"
		}

		armRows := make([]map[string]any, 0, len(e.Arms))
		eligibleIDs := make([]string, 0)

		for _, a := range e.Arms {
			cnt, sum := countObs(a.Observations, ps, pol)
			armStatus := "eligible"
			if _, ex := ov.ExcludeArms[a.ArmID]; ex {
				armStatus = "excluded"
			} else if cnt < ov.MinObservations {
				armStatus = "underpowered"
			} else {
				eligibleIDs = append(eligibleIDs, a.ArmID)
			}
			armRows = append(armRows, map[string]any{
				"arm_id":            a.ArmID,
				"arm_status":        armStatus,
				"observation_count": cnt,
				"observation_sum":   sum,
			})
		}

		if status != "quarantined" && status != "frozen" && status != "hold" && len(eligibleIDs) == 0 {
			status = "underpowered"
		} else if status != "quarantined" && status != "frozen" && status != "hold" && stale {
			status = "stale"
		}

		sort.Strings(eligibleIDs)
		var eligibleTotal *int

		if status == "quarantined" || status == "frozen" || status == "underpowered" {
			for i := range armRows {
				armRows[i]["allocation_pct"] = nil
			}
		} else {
			budget := 100 - eh
			n := len(eligibleIDs)
			base := 0
			rem := budget
			if n > 0 {
				base = budget / n
				rem = budget % n
			}
			smallest := ""
			if n > 0 {
				smallest = eligibleIDs[0]
			}
			total := 0
			for i := range armRows {
				id := fmt.Sprint(armRows[i]["arm_id"])
				st := fmt.Sprint(armRows[i]["arm_status"])
				switch st {
				case "excluded", "underpowered":
					armRows[i]["allocation_pct"] = 0
				default:
					alloc := base
					if id == smallest {
						alloc += rem
					}
					armRows[i]["allocation_pct"] = alloc
					total += alloc
				}
			}
			eligibleTotal = &total
		}

		sort.Slice(armRows, func(i, j int) bool {
			return fmt.Sprint(armRows[i]["arm_id"]) < fmt.Sprint(armRows[j]["arm_id"])
		})

		profiles = append(profiles, profile{
			experimentID:     e.ExperimentID,
			tier:             e.Tier,
			status:           status,
			effectiveHoldout: eh,
			staleFlag:        stale,
			arms:             armRows,
			eligibleTotal:    eligibleTotal,
		})
	}

	tierRunning := map[string]int{}
	for i := range profiles {
		p := &profiles[i]
		if p.eligibleTotal == nil {
			continue
		}
		capVal, ok := tiers[p.tier]
		if !ok {
			continue
		}
		sum := tierRunning[p.tier] + *p.eligibleTotal
		if sum > capVal.ExposureCap {
			for j := range p.arms {
				p.arms[j]["allocation_pct"] = 0
			}
			zero := 0
			p.eligibleTotal = &zero
		} else {
			tierRunning[p.tier] = sum
		}
	}

	eligibleArms := make([]map[string]any, 0)
	experimentsOut := make([]map[string]any, 0, len(profiles))
	compromiseRows := make([]map[string]any, 0)
	counts := map[string]int{
		"frozen": 0, "hold": 0, "quarantined": 0, "stale": 0, "underpowered": 0,
	}

	for _, p := range profiles {
		counts[p.status]++
		armOut := make([]map[string]any, 0, len(p.arms))
		for _, a := range p.arms {
			row := map[string]any{
				"allocation_pct":    a["allocation_pct"],
				"arm_id":            a["arm_id"],
				"arm_status":        a["arm_status"],
				"observation_count": a["observation_count"],
				"observation_sum":   a["observation_sum"],
			}
			armOut = append(armOut, row)
			if fmt.Sprint(a["arm_status"]) == "eligible" {
				eligibleArms = append(eligibleArms, map[string]any{
					"arm_id":        a["arm_id"],
					"experiment_id": p.experimentID,
				})
			}
		}
		var totalAny any
		if p.eligibleTotal == nil {
			totalAny = nil
		} else {
			totalAny = *p.eligibleTotal
		}
		experimentsOut = append(experimentsOut, map[string]any{
			"arms":              armOut,
			"effective_holdout": p.effectiveHoldout,
			"experiment_id":     p.experimentID,
			"stale_flag":        p.staleFlag,
			"status":            p.status,
			"tier":              p.tier,
			"eligible_total":    totalAny,
		})
		if p.status == "quarantined" {
			compromiseRows = append(compromiseRows, map[string]any{
				"experiment_id": p.experimentID,
				"tier":          p.tier,
			})
		}
	}

	sort.Slice(eligibleArms, func(i, j int) bool {
		a, b := eligibleArms[i], eligibleArms[j]
		if fmt.Sprint(a["experiment_id"]) != fmt.Sprint(b["experiment_id"]) {
			return fmt.Sprint(a["experiment_id"]) < fmt.Sprint(b["experiment_id"])
		}
		return fmt.Sprint(a["arm_id"]) < fmt.Sprint(b["arm_id"])
	})

	tierRollups := buildTierRollups(profiles, tiers, ov.ArmCap)

	compromiseIDs := make([]string, 0, len(compromised))
	for id := range compromised {
		compromiseIDs = append(compromiseIDs, id)
	}
	sort.Strings(compromiseIDs)
	sort.Slice(compromiseRows, func(i, j int) bool {
		return fmt.Sprint(compromiseRows[i]["experiment_id"]) < fmt.Sprint(compromiseRows[j]["experiment_id"])
	})

	payloads := map[string]any{
		"arm_eligibility.json": map[string]any{"arms": eligibleArms},
		"compromise_report.json": map[string]any{
			"experiment_ids": compromiseIDs,
			"experiments":    compromiseRows,
		},
		"experiment_profiles.json": map[string]any{
			"experiments":      experimentsOut,
			"window_end_day":   ps.WindowEndDay,
			"window_start_day": ps.WindowStartDay,
		},
		"tier_rollups.json": map[string]any{"tiers": tierRollups},
		"summary.json": map[string]any{
			"current_day":       ps.CurrentDay,
			"experiment_total":  len(profiles),
			"frozen_total":      counts["frozen"],
			"hold_total":        counts["hold"],
			"quarantined_total": counts["quarantined"],
			"stale_total":       counts["stale"],
			"underpowered_total": counts["underpowered"],
			"window_end_day":    ps.WindowEndDay,
			"window_start_day":  ps.WindowStartDay,
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

func buildTierRollups(profiles []profile, tiers map[string]tierDef, armCap int) []map[string]any {
	byTier := map[string][]profile{}
	for _, p := range profiles {
		byTier[p.tier] = append(byTier[p.tier], p)
	}
	tierIDs := make([]string, 0, len(byTier))
	for id := range byTier {
		tierIDs = append(tierIDs, id)
	}
	sort.Strings(tierIDs)
	out := make([]map[string]any, 0, len(tierIDs))
	for _, tid := range tierIDs {
		rows := make([]map[string]any, 0)
		for _, p := range byTier[tid] {
			if p.eligibleTotal == nil || *p.eligibleTotal <= 0 {
				continue
			}
			if p.status != "ok" && p.status != "hold" && p.status != "stale" {
				continue
			}
			rows = append(rows, map[string]any{
				"eligible_total": *p.eligibleTotal,
				"experiment_id":  p.experimentID,
			})
		}
		sort.Slice(rows, func(i, j int) bool {
			return fmt.Sprint(rows[i]["experiment_id"]) < fmt.Sprint(rows[j]["experiment_id"])
		})
		if len(rows) > armCap {
			rows = rows[:armCap]
		}
		out = append(out, map[string]any{
			"experiments": rows,
			"tier_id":     tid,
		})
	}
	return out
}

func countObs(obs []observation, ps poolState, pol policy) (count, sum int) {
	for _, o := range obs {
		if o.Day < ps.WindowStartDay || o.Day > ps.WindowEndDay {
			continue
		}
		if o.Value < pol.MetricFloor {
			continue
		}
		count++
		sum += o.Value
	}
	return count, sum
}

func loadTiers(dir string) (map[string]tierDef, error) {
	out := map[string]tierDef{}
	ents, err := os.ReadDir(dir)
	if err != nil {
		return out, err
	}
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var t tierDef
		if err := readJSON(filepath.Join(dir, e.Name()), &t); err != nil {
			return out, err
		}
		out[t.TierID] = t
	}
	return out, nil
}

func loadOverlays(dir string) (overlayState, error) {
	st := overlayState{
		MinObservations: 1,
		ArmCap:          1 << 30,
		ExcludeArms:     map[string]struct{}{},
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
		if v, ok := raw["min_observations"]; ok {
			var n int
			if json.Unmarshal(v, &n) == nil && n > 0 {
				st.MinObservations = n
			}
		}
		if v, ok := raw["arm_cap"]; ok {
			var n int
			if json.Unmarshal(v, &n) == nil && n > 0 {
				st.ArmCap = n
			}
		}
		if v, ok := raw["exclude_arms"]; ok {
			var ids []string
			if json.Unmarshal(v, &ids) == nil {
				for _, id := range ids {
					st.ExcludeArms[id] = struct{}{}
				}
			}
		}
	}
	return st, nil
}

func loadIncidents(path string) (compromised, frozen map[string]struct{}, err error) {
	compromised = map[string]struct{}{}
	frozen = map[string]struct{}{}
	var raw struct {
		Events []incidentEvent `json:"events"`
	}
	if err = readJSON(path, &raw); err != nil {
		return compromised, frozen, err
	}
	for _, ev := range raw.Events {
		if !ev.Accepted {
			continue
		}
		switch ev.Kind {
		case "experiment_compromise":
			compromised[ev.ExperimentID] = struct{}{}
		case "freeze_rollout":
			frozen[ev.ExperimentID] = struct{}{}
		}
	}
	return compromised, frozen, nil
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
				ExperimentID: parts[0],
				ForcedStatus: parts[1],
				Order:        order,
			})
			order++
		}
	}
	return notes, nil
}

func loadExperiments(dir string) ([]experiment, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make([]experiment, 0)
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var ex experiment
		if err := readJSON(filepath.Join(dir, e.Name()), &ex); err != nil {
			return nil, err
		}
		out = append(out, ex)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no experiments")
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
