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
	SoakDays   map[string]int    `json:"soak_days"`
	StageOrder []string          `json:"stage_order"`
	TierRank   map[string]int    `json:"tier_rank"`
}

type artifactDoc struct {
	ArtifactID      string   `json:"artifact_id"`
	CurrentStage    string   `json:"current_stage"`
	DependsOn       []string `json:"depends_on"`
	Pool            string   `json:"pool"`
	PromotePriority int      `json:"promote_priority"`
	StageEnteredDay int      `json:"stage_entered_day"`
}

type poolDoc struct {
	MaxPromotionsPerDay int    `json:"max_promotions_per_day"`
	PoolID              string `json:"pool_id"`
	Tier                string `json:"tier"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type blockedRow struct {
	Reason      string `json:"reason"`
	TargetStage string `json:"target_stage"`
}

type artifactRow struct {
	ArtifactID        string       `json:"artifact_id"`
	ArtifactStatus    string       `json:"artifact_status"`
	BlockedPromotions []blockedRow `json:"blocked_promotions"`
	CurrentStage      string       `json:"current_stage"`
	Pool              string       `json:"pool"`
	PromotedTo        any          `json:"promoted_to"`
}

var stageRank = map[string]int{"dev": 0, "staging": 1, "prod": 2}

func main() {
	dataDir := getenv("APLA_DATA_DIR", "/app/promote_lattice")
	auditDir := getenv("APLA_AUDIT_DIR", "/app/audit")
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

	artifacts, err := loadArtifacts(filepath.Join(dataDir, "artifacts"))
	if err != nil {
		return err
	}
	pools, err := loadPools(filepath.Join(dataDir, "pools"))
	if err != nil {
		return err
	}

	day := ps.CurrentDay
	_, kept, ignored := processIncidents(il.Events, day)
	embargoed := embargoSet(kept, day)
	compromise := compromiseSet(kept, day)
	frozen := freezeSet(kept, day)
	effectiveCap := poolCaps(pools, kept)

	poolByID := map[string]poolDoc{}
	for _, p := range pools {
		poolByID[p.PoolID] = p
	}
	stageByID := map[string]string{}
	for _, a := range artifacts {
		stageByID[a.ArtifactID] = a.CurrentStage
	}

	type contender struct {
		art       artifactDoc
		nextStage string
	}
	var contenders []contender

	artBlocked := map[string][]blockedRow{}
	artStatus := map[string]string{}
	artPromoted := map[string]any{}

	for _, a := range artifacts {
		quarantined := compromise[a.ArtifactID]
		frozenPool := frozen[a.Pool]
		next := nextStage(a.CurrentStage, pol.StageOrder)

		var blocked []blockedRow
		if next != "" {
			reason := blockReason(a, next, stageByID, embargoed, quarantined, frozenPool, pol, day)
			if reason != "" {
				blocked = append(blocked, blockedRow{TargetStage: next, Reason: reason})
			}
		}
		if blocked == nil {
			blocked = []blockedRow{}
		}
		artBlocked[a.ArtifactID] = blocked

		switch {
		case quarantined:
			artStatus[a.ArtifactID] = "quarantined"
			artPromoted[a.ArtifactID] = nil
		case frozenPool:
			artStatus[a.ArtifactID] = "pool_frozen"
			artPromoted[a.ArtifactID] = nil
		default:
			if next == "" {
				artStatus[a.ArtifactID] = "idle"
				artPromoted[a.ArtifactID] = nil
			} else if depsMet(a, next, stageByID) && !embargoed[a.ArtifactID] && soakMet(a, pol, day) {
				contenders = append(contenders, contender{art: a, nextStage: next})
			} else if !soakMet(a, pol, day) && next != "" && !embargoed[a.ArtifactID] && depsMet(a, next, stageByID) {
				artStatus[a.ArtifactID] = "soak_waiting"
				artPromoted[a.ArtifactID] = nil
			} else {
				artStatus[a.ArtifactID] = "idle"
				artPromoted[a.ArtifactID] = nil
			}
		}
	}

	sort.Slice(contenders, func(i, j int) bool {
		ti := pol.TierRank[poolByID[contenders[i].art.Pool].Tier]
		tj := pol.TierRank[poolByID[contenders[j].art.Pool].Tier]
		if ti != tj {
			return ti < tj
		}
		if contenders[i].art.PromotePriority != contenders[j].art.PromotePriority {
			return contenders[i].art.PromotePriority < contenders[j].art.PromotePriority
		}
		return contenders[i].art.ArtifactID < contenders[j].art.ArtifactID
	})

	poolPromoted := map[string]int{}
	for _, c := range contenders {
		cap := effectiveCap[c.art.Pool]
		if poolPromoted[c.art.Pool] < cap {
			poolPromoted[c.art.Pool]++
			artStatus[c.art.ArtifactID] = "promoted"
			artPromoted[c.art.ArtifactID] = c.nextStage
			artBlocked[c.art.ArtifactID] = []blockedRow{}
		} else {
			artStatus[c.art.ArtifactID] = "deferred_capacity"
			artPromoted[c.art.ArtifactID] = nil
			updated := false
			for i := range artBlocked[c.art.ArtifactID] {
				if artBlocked[c.art.ArtifactID][i].TargetStage == c.nextStage {
					artBlocked[c.art.ArtifactID][i].Reason = "capacity_deferred"
					updated = true
				}
			}
			if !updated {
				artBlocked[c.art.ArtifactID] = append(
					artBlocked[c.art.ArtifactID],
					blockedRow{TargetStage: c.nextStage, Reason: "capacity_deferred"},
				)
			}
			sort.Slice(artBlocked[c.art.ArtifactID], func(i, j int) bool {
				return artBlocked[c.art.ArtifactID][i].TargetStage < artBlocked[c.art.ArtifactID][j].TargetStage
			})
		}
	}

	var artRows []artifactRow
	sort.Slice(artifacts, func(i, j int) bool { return artifacts[i].ArtifactID < artifacts[j].ArtifactID })
	for _, a := range artifacts {
		st := artStatus[a.ArtifactID]
		if st == "" {
			st = "idle"
		}
		blocked := artBlocked[a.ArtifactID]
		if blocked == nil {
			blocked = []blockedRow{}
		}
		artRows = append(artRows, artifactRow{
			ArtifactID:        a.ArtifactID,
			Pool:              a.Pool,
			CurrentStage:      a.CurrentStage,
			ArtifactStatus:    st,
			PromotedTo:        artPromoted[a.ArtifactID],
			BlockedPromotions: blocked,
		})
	}

	poolLedger := buildPoolLedger(pools, effectiveCap, artRows)
	stageMatrix := buildStageMatrix(artRows, pol.StageOrder)
	journal := buildJournal(kept)
	summary := buildSummary(artRows, kept, ignored, il.Events)

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "artifact_plan.json"), map[string]any{"artifacts": artRows}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "pool_ledger.json"), map[string]any{"pools": poolLedger}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "stage_matrix.json"), map[string]any{"stages": stageMatrix}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "incident_journal.json"), map[string]any{"applied_events": journal}); err != nil {
		return err
	}
	return writeJSON(filepath.Join(auditDir, "summary.json"), summary)
}

func buildSummary(artRows []artifactRow, kept []map[string]any, ignored int, all []map[string]any) map[string]any {
	counts := map[string]int{
		"quarantined": 0, "pool_frozen": 0, "deferred_capacity": 0,
		"promoted": 0, "idle": 0, "soak_waiting": 0,
	}
	promotions := 0
	for _, r := range artRows {
		counts[r.ArtifactStatus]++
		if r.PromotedTo != nil {
			promotions++
		}
	}
	return map[string]any{
		"applied_incident_events": len(kept),
		"artifacts_total":         len(artRows),
		"deferred_artifacts":      counts["deferred_capacity"],
		"frozen_artifacts":        counts["pool_frozen"],
		"idle_artifacts":          counts["idle"],
		"ignored_incident_events": ignored,
		"promoted_artifacts":      counts["promoted"],
		"promotions_today":        promotions,
		"quarantined_artifacts":   counts["quarantined"],
		"soak_waiting_artifacts":  counts["soak_waiting"],
	}
}

func buildJournal(kept []map[string]any) []map[string]any {
	out := make([]map[string]any, 0, len(kept))
	for _, ev := range kept {
		row := map[string]any{
			"day":      ev["day"],
			"event_id": ev["event_id"],
			"kind":     ev["kind"],
		}
		for _, k := range []string{"artifact_id", "pool_id", "delta", "start_day", "end_day"} {
			if v, ok := ev[k]; ok {
				row[k] = v
			}
		}
		out = append(out, sortedKeys(row))
	}
	return out
}

func buildStageMatrix(artRows []artifactRow, stageOrder []string) []map[string]any {
	sched := map[string]int{}
	blocked := map[string]int{}
	for _, r := range artRows {
		if r.PromotedTo != nil {
			sched[r.PromotedTo.(string)]++
		}
		for _, br := range r.BlockedPromotions {
			blocked[br.TargetStage]++
		}
	}
	targets := append([]string(nil), stageOrder...)
	sort.Strings(targets)
	var out []map[string]any
	for _, st := range targets {
		out = append(out, map[string]any{
			"artifacts_blocked":  blocked[st],
			"artifacts_promoted": sched[st],
			"target_stage":       st,
		})
	}
	return out
}

func buildPoolLedger(pools []poolDoc, effectiveCap map[string]int, artRows []artifactRow) map[string]any {
	ledger := map[string]any{}
	for _, p := range pools {
		ledger[p.PoolID] = map[string]any{
			"artifacts_deferred":    0,
			"artifacts_promoted":    0,
			"effective_cap":         effectiveCap[p.PoolID],
			"max_promotions_per_day": p.MaxPromotionsPerDay,
		}
	}
	for _, r := range artRows {
		body := ledger[r.Pool].(map[string]any)
		switch r.ArtifactStatus {
		case "promoted":
			body["artifacts_promoted"] = body["artifacts_promoted"].(int) + 1
		case "deferred_capacity":
			body["artifacts_deferred"] = body["artifacts_deferred"].(int) + 1
		}
	}
	return ledger
}

func blockReason(a artifactDoc, next string, stages map[string]string, embargoed map[string]bool, quarantined, frozenPool bool, pol policyDoc, day int) string {
	if quarantined {
		return "quarantine"
	}
	if frozenPool {
		return "pool_frozen"
	}
	if a.CurrentStage == "prod" {
		return "at_terminal"
	}
	if embargoed[a.ArtifactID] {
		return "embargoed"
	}
	if !soakMet(a, pol, day) {
		return "soak_not_met"
	}
	if !depsMet(a, next, stages) {
		return "missing_dependency"
	}
	return ""
}

func depsMet(a artifactDoc, next string, stages map[string]string) bool {
	need := stageRank[next]
	for _, dep := range a.DependsOn {
		if stageRank[stages[dep]] < need {
			return false
		}
	}
	return true
}

func soakMet(a artifactDoc, pol policyDoc, day int) bool {
	if a.CurrentStage == "prod" {
		return false
	}
	need, ok := pol.SoakDays[a.CurrentStage]
	if !ok {
		need = 0
	}
	return day-a.StageEnteredDay >= need
}

func nextStage(current string, order []string) string {
	for i, s := range order {
		if s == current && i+1 < len(order) {
			return order[i+1]
		}
	}
	return ""
}

func processIncidents(events []map[string]any, day int) (applied map[string][]map[string]any, kept []map[string]any, ignored int) {
	applied = map[string][]map[string]any{
		"cap_bump": {}, "artifact_compromise": {}, "freeze_pool": {}, "promote_embargo": {},
	}
	var candidates []map[string]any
	for _, ev := range events {
		if !eventAccepted(ev) {
			ignored++
			continue
		}
		evDay := intNum(ev["day"])
		if evDay > day {
			ignored++
			continue
		}
		kind, _ := ev["kind"].(string)
		if !validIncident(ev, kind) {
			ignored++
			continue
		}
		candidates = append(candidates, ev)
	}
	sort.Slice(candidates, func(i, j int) bool {
		di, dj := intNum(candidates[i]["day"]), intNum(candidates[j]["day"])
		if di != dj {
			return di < dj
		}
		return fmt.Sprint(candidates[i]["event_id"]) < fmt.Sprint(candidates[j]["event_id"])
	})
	kept = candidates
	for _, ev := range kept {
		kind := ev["kind"].(string)
		applied[kind] = append(applied[kind], ev)
	}
	return applied, kept, len(events) - len(kept)
}

func validIncident(ev map[string]any, kind string) bool {
	switch kind {
	case "artifact_compromise":
		_, ok := ev["artifact_id"].(string)
		return ok
	case "freeze_pool":
		_, ok := ev["pool_id"].(string)
		return ok
	case "promote_embargo":
		_, ok := ev["artifact_id"].(string)
		_, hasEnd := ev["end_day"]
		return ok && hasEnd
	case "cap_bump":
		_, ok := ev["pool_id"].(string)
		return ok && ev["delta"] != nil
	default:
		return false
	}
}

func embargoSet(kept []map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range kept {
		if ev["kind"] != "promote_embargo" {
			continue
		}
		aid := ev["artifact_id"].(string)
		start := intNum(ev["day"])
		if v, ok := ev["start_day"]; ok {
			start = intNum(v)
		}
		end := intNum(ev["end_day"])
		if day >= start && day <= end {
			out[aid] = true
		}
	}
	return out
}

func compromiseSet(kept []map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range kept {
		if ev["kind"] != "artifact_compromise" {
			continue
		}
		if intNum(ev["day"]) <= day {
			out[ev["artifact_id"].(string)] = true
		}
	}
	return out
}

func freezeSet(kept []map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range kept {
		if ev["kind"] != "freeze_pool" {
			continue
		}
		if intNum(ev["day"]) <= day {
			out[ev["pool_id"].(string)] = true
		}
	}
	return out
}

func poolCaps(pools []poolDoc, kept []map[string]any) map[string]int {
	out := map[string]int{}
	for _, p := range pools {
		out[p.PoolID] = p.MaxPromotionsPerDay
	}
	for _, ev := range kept {
		if ev["kind"] != "cap_bump" {
			continue
		}
		pid := ev["pool_id"].(string)
		out[pid] += intNum(ev["delta"])
	}
	return out
}

func eventAccepted(ev map[string]any) bool {
	v, ok := ev["accepted"]
	if !ok {
		return false
	}
	switch t := v.(type) {
	case bool:
		return t
	default:
		return false
	}
}

func intNum(v any) int {
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

func sortedKeys(m map[string]any) map[string]any {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := map[string]any{}
	for _, k := range keys {
		out[k] = m[k]
	}
	return out
}

func readJSON(path string, out any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, &out)
}

func writeJSON(path string, v any) error {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(path, data, 0o644)
}

func loadArtifacts(dir string) ([]artifactDoc, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var out []artifactDoc
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var a artifactDoc
		if err := json.Unmarshal(b, &a); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ArtifactID < out[j].ArtifactID })
	return out, nil
}

func loadPools(dir string) ([]poolDoc, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var out []poolDoc
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var p poolDoc
		if err := json.Unmarshal(b, &p); err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].PoolID < out[j].PoolID })
	return out, nil
}
