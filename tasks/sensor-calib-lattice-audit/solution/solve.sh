#!/bin/bash
set -euo pipefail

SRC_DIR="${SCLA_SRC_DIR:-/app/src}"
BIN_DIR="${SCLA_BIN_DIR:-/app/bin}"
mkdir -p "$SRC_DIR" "$BIN_DIR"

cat > "$SRC_DIR/main.go" <<'GOEOF'
package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
)

type TierRule struct {
	CapacityWeight   int `json:"capacity_weight"`
	MaxResidualPPM   int `json:"max_residual_ppm"`
	MaxUncertaintyPPM int `json:"max_uncertainty_ppm"`
	PriorityRank     int `json:"priority_rank"`
	RecallDays       int `json:"recall_days"`
}

type Policy struct {
	SupportedIncidentKinds []string            `json:"supported_incident_kinds"`
	TierRules              map[string]TierRule `json:"tier_rules"`
}

type PoolState struct {
	CurrentDay int `json:"current_day"`
}

type Lab struct {
	BiasPPM       int    `json:"bias_ppm"`
	DailyCapacity int    `json:"daily_capacity"`
	LabID         string `json:"lab_id"`
	Region        string `json:"region"`
}

type Batch struct {
	BatchID string `json:"batch_id"`
	Day     int    `json:"day"`
	LabID   string `json:"lab_id"`
	Method  string `json:"method"`
}

type Sensor struct {
	BatchID        string   `json:"batch_id"`
	DependsOn      []string `json:"depends_on"`
	MeasuredPPM    int      `json:"measured_ppm"`
	ReferencePPM   int      `json:"reference_ppm"`
	SensorID       string   `json:"sensor_id"`
	Tier           string   `json:"tier"`
	UncertaintyPPM int      `json:"uncertainty_ppm"`
}

type Incident struct {
	Accepted     bool   `json:"accepted"`
	BatchID      string `json:"batch_id"`
	Day          int    `json:"day"`
	DurationDays int    `json:"duration_days"`
	EventID      string `json:"event_id"`
	ExtraDays    int    `json:"extra_days"`
	Kind         string `json:"kind"`
	LabID        string `json:"lab_id"`
	SensorID     string `json:"sensor_id"`
	Tier         string `json:"tier"`
}

type LineageInfo struct {
	Status       string
	TaintSource *string
	TaintHops   *int
	CycleMembers []string
}

func mustReadJSON(path string, out any) {
	data, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(data, out); err != nil {
		panic(fmt.Errorf("%s: %w", path, err))
	}
}

func readDirJSON[T any](dir string, id func(T) string) map[string]T {
	entries, err := os.ReadDir(dir)
	if err != nil {
		panic(err)
	}
	result := map[string]T{}
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		var item T
		mustReadJSON(filepath.Join(dir, entry.Name()), &item)
		result[id(item)] = item
	}
	return result
}

func eventTarget(e Incident) string {
	switch e.Kind {
	case "batch_contamination":
		return e.Kind + ":" + e.BatchID
	case "lab_freeze":
		return e.Kind + ":" + e.LabID
	case "recall_extend":
		return e.Kind + ":" + e.Tier
	case "sensor_suppress":
		return e.Kind + ":" + e.SensorID
	default:
		return e.Kind + ":"
	}
}

func betterEvent(a, b Incident) bool {
	if a.Day != b.Day {
		return a.Day > b.Day
	}
	return a.EventID > b.EventID
}

func intPtr(v int) *int { return &v }
func strPtr(v string) *string { return &v }

func abs(v int) int {
	if v < 0 {
		return -v
	}
	return v
}

func sortedKeys[T any](m map[string]T) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func findCycles(sensors map[string]Sensor) map[string][]string {
	visited := map[string]bool{}
	stackIndex := map[string]int{}
	stack := []string{}
	cycles := map[string]map[string]bool{}

	var dfs func(string)
	dfs = func(id string) {
		if _, ok := stackIndex[id]; ok {
			return
		}
		visited[id] = true
		stackIndex[id] = len(stack)
		stack = append(stack, id)
		for _, dep := range sensors[id].DependsOn {
			if _, ok := sensors[dep]; !ok {
				continue
			}
			if idx, ok := stackIndex[dep]; ok {
				members := append([]string{}, stack[idx:]...)
				sort.Strings(members)
				for _, member := range members {
					if cycles[member] == nil {
						cycles[member] = map[string]bool{}
					}
					for _, other := range members {
						cycles[member][other] = true
					}
				}
			} else if !visited[dep] {
				dfs(dep)
			}
		}
		delete(stackIndex, id)
		stack = stack[:len(stack)-1]
	}

	for _, id := range sortedKeys(sensors) {
		if !visited[id] {
			dfs(id)
		}
	}
	out := map[string][]string{}
	for id, set := range cycles {
		out[id] = sortedKeys(set)
	}
	return out
}

func writeJSON(outDir, name string, payload any) {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		panic(err)
	}
	f, err := os.Create(filepath.Join(outDir, name))
	if err != nil {
		panic(err)
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(payload); err != nil {
		panic(err)
	}
}

func main() {
	dataDir := os.Getenv("SCLA_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/sensor_lattice"
	}
	outDir := os.Getenv("SCLA_AUDIT_DIR")
	if outDir == "" {
		outDir = "/app/audit"
	}

	var policy Policy
	mustReadJSON(filepath.Join(dataDir, "policy.json"), &policy)
	var pool PoolState
	mustReadJSON(filepath.Join(dataDir, "pool_state.json"), &pool)
	labs := readDirJSON(filepath.Join(dataDir, "labs"), func(v Lab) string { return v.LabID })
	batches := readDirJSON(filepath.Join(dataDir, "batches"), func(v Batch) string { return v.BatchID })
	sensors := readDirJSON(filepath.Join(dataDir, "sensors"), func(v Sensor) string { return v.SensorID })
	var events []Incident
	mustReadJSON(filepath.Join(dataDir, "incident_log.json"), &events)

	supported := map[string]bool{}
	for _, kind := range policy.SupportedIncidentKinds {
		supported[kind] = true
	}
	winners := map[string]Incident{}
	for _, e := range events {
		if !e.Accepted || e.Day > pool.CurrentDay || !supported[e.Kind] {
			continue
		}
		key := eventTarget(e)
		if old, ok := winners[key]; !ok || betterEvent(e, old) {
			winners[key] = e
		}
	}
	applied := make([]Incident, 0, len(winners))
	for _, e := range winners {
		applied = append(applied, e)
	}
	sort.Slice(applied, func(i, j int) bool {
		if applied[i].Day != applied[j].Day {
			return applied[i].Day < applied[j].Day
		}
		return applied[i].EventID < applied[j].EventID
	})
	ignoredEvents := len(events) - len(applied)

	contamBatches := map[string]bool{}
	suppressed := map[string]bool{}
	frozenLabs := map[string]bool{}
	recallExtra := map[string]int{}
	for _, e := range applied {
		switch e.Kind {
		case "batch_contamination":
			contamBatches[e.BatchID] = true
		case "sensor_suppress":
			suppressed[e.SensorID] = true
		case "lab_freeze":
			if e.Day <= pool.CurrentDay && pool.CurrentDay <= e.Day+e.DurationDays-1 {
				frozenLabs[e.LabID] = true
			}
		case "recall_extend":
			recallExtra[e.Tier] += e.ExtraDays
		}
	}

	cycleMembers := findCycles(sensors)
	children := map[string][]string{}
	for _, s := range sensors {
		for _, parent := range s.DependsOn {
			children[parent] = append(children[parent], s.SensorID)
		}
	}
	for k := range children {
		sort.Strings(children[k])
	}

	type taint struct{ source string; hops int }
	taints := map[string]taint{}
	seeds := []string{}
	for _, id := range sortedKeys(sensors) {
		if contamBatches[sensors[id].BatchID] {
			seeds = append(seeds, id)
		}
	}
	for _, seed := range seeds {
		type item struct{ id string; hop int }
		queue := []item{{seed, 0}}
		seen := map[string]bool{seed: true}
		for len(queue) > 0 {
			cur := queue[0]
			queue = queue[1:]
			old, ok := taints[cur.id]
			if !ok || cur.hop < old.hops || (cur.hop == old.hops && seed < old.source) {
				taints[cur.id] = taint{seed, cur.hop}
			}
			for _, child := range children[cur.id] {
				if !seen[child] {
					seen[child] = true
					queue = append(queue, item{child, cur.hop + 1})
				}
			}
		}
	}

	lineage := map[string]LineageInfo{}
	for _, id := range sortedKeys(sensors) {
		if suppressed[id] {
			lineage[id] = LineageInfo{Status: "suppressed", CycleMembers: []string{}}
		} else if members, ok := cycleMembers[id]; ok {
			lineage[id] = LineageInfo{Status: "cyclic", CycleMembers: members}
		} else if t, ok := taints[id]; ok {
			lineage[id] = LineageInfo{Status: "tainted", TaintSource: strPtr(t.source), TaintHops: intPtr(t.hops), CycleMembers: []string{}}
		} else {
			lineage[id] = LineageInfo{Status: "clean", CycleMembers: []string{}}
		}
	}

	type calc struct {
		id string
		labID string
		residual int
		adjusted int
		age int
		effRecall int
	}
	calcs := map[string]calc{}
	for _, id := range sortedKeys(sensors) {
		s := sensors[id]
		b := batches[s.BatchID]
		lab := labs[b.LabID]
		rule := policy.TierRules[s.Tier]
		calcs[id] = calc{
			id: id,
			labID: b.LabID,
			residual: abs(s.MeasuredPPM - s.ReferencePPM),
			adjusted: abs(s.MeasuredPPM + lab.BiasPPM - s.ReferencePPM),
			age: pool.CurrentDay - b.Day,
			effRecall: rule.RecallDays + recallExtra[s.Tier],
		}
	}

	candidates := []string{}
	status := map[string]string{}
	reason := map[string]string{}
	for _, id := range sortedKeys(sensors) {
		info := lineage[id]
		c := calcs[id]
		if info.Status == "suppressed" {
			status[id] = "suppressed"
			reason[id] = "suppressed_event"
		} else if info.Status == "tainted" {
			status[id] = "quarantined"
			reason[id] = "contamination_lineage"
		} else if info.Status == "cyclic" {
			status[id] = "quarantined"
			reason[id] = "dependency_cycle"
		} else if frozenLabs[c.labID] {
			status[id] = "lab_frozen"
			reason[id] = "lab_freeze"
		} else {
			candidates = append(candidates, id)
		}
	}

	sort.Slice(candidates, func(i, j int) bool {
		a, b := sensors[candidates[i]], sensors[candidates[j]]
		ar, br := policy.TierRules[a.Tier], policy.TierRules[b.Tier]
		if ar.PriorityRank != br.PriorityRank {
			return ar.PriorityRank < br.PriorityRank
		}
		ac, bc := calcs[a.SensorID], calcs[b.SensorID]
		if ac.adjusted != bc.adjusted {
			return ac.adjusted > bc.adjusted
		}
		if a.UncertaintyPPM != b.UncertaintyPPM {
			return a.UncertaintyPPM > b.UncertaintyPPM
		}
		return a.SensorID < b.SensorID
	})

	remaining := map[string]int{}
	used := map[string]int{}
	placed := map[string][]string{}
	deferred := map[string][]string{}
	rank := map[string]any{}
	for _, labID := range sortedKeys(labs) {
		remaining[labID] = labs[labID].DailyCapacity
	}
	placementRank := 1
	for _, id := range candidates {
		s := sensors[id]
		c := calcs[id]
		weight := policy.TierRules[s.Tier].CapacityWeight
		if remaining[c.labID] < weight {
			status[id] = "capacity_deferred"
			reason[id] = "capacity_exhausted"
			rank[id] = nil
			deferred[c.labID] = append(deferred[c.labID], id)
			continue
		}
		remaining[c.labID] -= weight
		used[c.labID] += weight
		placed[c.labID] = append(placed[c.labID], id)
		rank[id] = placementRank
		placementRank++
		rule := policy.TierRules[s.Tier]
		if c.age > c.effRecall {
			status[id] = "recall_due"
			reason[id] = "recall_window_expired"
		} else if c.adjusted > rule.MaxResidualPPM || s.UncertaintyPPM > rule.MaxUncertaintyPPM {
			status[id] = "needs_review"
			reason[id] = "residual_or_uncertainty"
		} else {
			status[id] = "accepted"
			reason[id] = "within_threshold"
		}
	}
	for _, id := range sortedKeys(sensors) {
		if _, ok := rank[id]; !ok {
			rank[id] = nil
		}
	}

	planRows := []map[string]any{}
	lineageRows := []map[string]any{}
	recallRows := []map[string]any{}
	summaryCounts := map[string]int{
		"accepted": 0, "needs_review": 0, "recall_due": 0, "capacity_deferred": 0,
		"lab_frozen": 0, "quarantined": 0, "suppressed": 0,
	}
	cyclicCount := 0
	for _, id := range sortedKeys(sensors) {
		s := sensors[id]
		c := calcs[id]
		info := lineage[id]
		planRows = append(planRows, map[string]any{
			"adjusted_residual_ppm": c.adjusted,
			"batch_id": s.BatchID,
			"capacity_rank": rank[id],
			"decision_reason": reason[id],
			"lab_id": c.labID,
			"residual_ppm": c.residual,
			"sensor_id": id,
			"status": status[id],
			"tier": s.Tier,
			"uncertainty_ppm": s.UncertaintyPPM,
		})
		lineageRows = append(lineageRows, map[string]any{
			"cycle_members": info.CycleMembers,
			"lineage_status": info.Status,
			"sensor_id": id,
			"taint_hops": info.TaintHops,
			"taint_source": info.TaintSource,
		})
		recallState := "current"
		if info.Status == "suppressed" {
			recallState = "suppressed"
		} else if info.Status == "tainted" || info.Status == "cyclic" {
			recallState = "quarantined"
		} else if c.age > c.effRecall {
			recallState = "due"
		}
		recallRows = append(recallRows, map[string]any{
			"age_days": c.age,
			"effective_recall_days": c.effRecall,
			"recall_state": recallState,
			"sensor_id": id,
		})
		summaryCounts[status[id]]++
		if info.Status == "cyclic" {
			cyclicCount++
		}
	}

	labLedger := map[string]any{}
	for _, labID := range sortedKeys(labs) {
		sort.Strings(placed[labID])
		sort.Strings(deferred[labID])
		labLedger[labID] = map[string]any{
			"base_capacity": labs[labID].DailyCapacity,
			"capacity_remaining": int(math.Max(0, float64(remaining[labID]))),
			"capacity_used": used[labID],
			"deferred_sensors": deferred[labID],
			"frozen": frozenLabs[labID],
			"placed_sensors": placed[labID],
		}
	}

	appliedRows := []map[string]any{}
	for _, e := range applied {
		appliedRows = append(appliedRows, map[string]any{
			"day": e.Day,
			"event_id": e.EventID,
			"kind": e.Kind,
			"target": eventTarget(e),
		})
	}

	writeJSON(outDir, "calibration_plan.json", map[string]any{"generated_day": pool.CurrentDay, "sensors": planRows})
	writeJSON(outDir, "lineage_risk.json", map[string]any{"sensors": lineageRows})
	writeJSON(outDir, "recall_windows.json", map[string]any{"sensors": recallRows})
	writeJSON(outDir, "lab_ledger.json", map[string]any{"labs": labLedger})
	writeJSON(outDir, "summary.json", map[string]any{
		"accepted_sensors": summaryCounts["accepted"],
		"applied_incident_events": len(applied),
		"capacity_deferred_sensors": summaryCounts["capacity_deferred"],
		"cyclic_sensors": cyclicCount,
		"ignored_incident_events": ignoredEvents,
		"lab_frozen_sensors": summaryCounts["lab_frozen"],
		"needs_review_sensors": summaryCounts["needs_review"],
		"quarantined_sensors": summaryCounts["quarantined"],
		"recall_due_sensors": summaryCounts["recall_due"],
		"sensors_total": len(sensors),
		"suppressed_sensors": summaryCounts["suppressed"],
	})
}
GOEOF

gofmt -w "$SRC_DIR/main.go"
go build -o "$BIN_DIR/sensor-auditor" "$SRC_DIR/main.go"
"$BIN_DIR/sensor-auditor"
