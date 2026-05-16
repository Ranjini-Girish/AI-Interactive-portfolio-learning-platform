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
	MaxCreditCostPerSource map[string]int    `json:"max_credit_cost_per_source"`
	TierCalendar           map[string][][]int `json:"tier_calendar"`
	TierRank               map[string]int    `json:"tier_rank"`
}

type sourceDoc struct {
	ExportedBatches []string `json:"exported_batches"`
	SourceID        string   `json:"source_id"`
	SyncWindows     [][]int  `json:"sync_windows"`
	Tier            string   `json:"tier"`
	WarehouseID     string   `json:"warehouse_id"`
}

type batchDoc struct {
	BatchID    string   `json:"batch_id"`
	CreditCost int      `json:"credit_cost"`
	DependsOn  []string `json:"depends_on"`
	Priority   int      `json:"priority"`
}

type warehouseDoc struct {
	ExportCredits    int    `json:"export_credits"`
	MaxExportsPerDay int    `json:"max_exports_per_day"`
	WarehouseID      string `json:"warehouse_id"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type blockedRow struct {
	BatchID string `json:"batch_id"`
	Reason  string `json:"reason"`
}

type sourceRow struct {
	BlockedCandidates []blockedRow `json:"blocked_candidates"`
	ScheduledBatch    any          `json:"scheduled_batch"`
	SourceID          string       `json:"source_id"`
	SourceStatus      string       `json:"source_status"`
	Tier              string       `json:"tier"`
	WarehouseID       string       `json:"warehouse_id"`
}

func main() {
	dataDir := getenv("EBWA_DATA_DIR", "/app/export_batches")
	auditDir := getenv("EBWA_AUDIT_DIR", "/app/audit")
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

	batches, err := loadBatches(filepath.Join(dataDir, "batches"))
	if err != nil {
		return err
	}
	batchByID := map[string]batchDoc{}
	for _, b := range batches {
		batchByID[b.BatchID] = b
	}
	sources, err := loadSources(filepath.Join(dataDir, "sources"))
	if err != nil {
		return err
	}
	warehouses, err := loadWarehouses(filepath.Join(dataDir, "warehouses"))
	if err != nil {
		return err
	}

	day := ps.CurrentDay
	applied, kept, ignored := processIncidents(il.Events, day)
	embargoed := embargoSet(applied, day)
	compromise := compromiseSet(applied, day)
	frozen := freezeSet(applied, day)
	effectiveCap := warehouseCaps(warehouses, applied)
	creditsStart := warehouseCredits(warehouses, applied)
	creditsRemaining := map[string]int{}
	for k, v := range creditsStart {
		creditsRemaining[k] = v
	}

	type pick struct {
		batch  string
		source sourceDoc
	}
	var contenders []pick

	sourceBlocked := map[string][]blockedRow{}
	sourceStatus := map[string]string{}
	sourceScheduled := map[string]any{}

	for _, s := range sources {
		exportedSet := stringSet(s.ExportedBatches)
		inWindow := dayInEffectiveWindow(s, pol, day)
		quarantined := compromise[s.SourceID]
		frozenSrc := frozen[s.WarehouseID]
		maxCost := pol.MaxCreditCostPerSource[s.Tier]

		var blocked []blockedRow
		var candidates []batchDoc

		for _, b := range batches {
			if exportedSet[b.BatchID] {
				continue
			}
			reason := blockReason(b, inWindow, embargoed, quarantined, frozenSrc, exportedSet, maxCost)
			if reason == "" {
				candidates = append(candidates, b)
				continue
			}
			blocked = append(blocked, blockedRow{BatchID: b.BatchID, Reason: reason})
		}

		sort.Slice(blocked, func(i, j int) bool { return blocked[i].BatchID < blocked[j].BatchID })
		if blocked == nil {
			blocked = []blockedRow{}
		}
		sourceBlocked[s.SourceID] = blocked

		switch {
		case quarantined:
			sourceStatus[s.SourceID] = "quarantined"
			sourceScheduled[s.SourceID] = nil
		case frozenSrc:
			sourceStatus[s.SourceID] = "warehouse_frozen"
			sourceScheduled[s.SourceID] = nil
		default:
			chosen := chooseBatch(candidates)
			if chosen == "" {
				sourceStatus[s.SourceID] = "idle"
				sourceScheduled[s.SourceID] = nil
			} else {
				contenders = append(contenders, pick{source: s, batch: chosen})
			}
		}
	}

	sort.Slice(contenders, func(i, j int) bool {
		ri := pol.TierRank[contenders[i].source.Tier]
		rj := pol.TierRank[contenders[j].source.Tier]
		if ri != rj {
			return ri < rj
		}
		return contenders[i].source.SourceID < contenders[j].source.SourceID
	})

	whScheduled := map[string]int{}
	whDeferredCap := map[string]int{}
	whDeferredCredit := map[string]int{}

	for _, c := range contenders {
		wh := c.source.WarehouseID
		cap := effectiveCap[wh]
		b := batchByID[c.batch]
		if whScheduled[wh] >= cap {
			sourceStatus[c.source.SourceID] = "deferred_capacity"
			sourceScheduled[c.source.SourceID] = nil
			whDeferredCap[wh]++
			updateBlockedReason(sourceBlocked, c.source.SourceID, c.batch, "capacity_deferred")
			continue
		}
		if creditsRemaining[wh] < b.CreditCost {
			sourceStatus[c.source.SourceID] = "credit_deferred"
			sourceScheduled[c.source.SourceID] = nil
			whDeferredCredit[wh]++
			updateBlockedReason(sourceBlocked, c.source.SourceID, c.batch, "credit_deferred")
			continue
		}
		whScheduled[wh]++
		creditsRemaining[wh] -= b.CreditCost
		sourceStatus[c.source.SourceID] = "scheduled"
		sourceScheduled[c.source.SourceID] = c.batch
	}

	var sourceRows []sourceRow
	sort.Slice(sources, func(i, j int) bool { return sources[i].SourceID < sources[j].SourceID })
	for _, s := range sources {
		st := sourceStatus[s.SourceID]
		if st == "" {
			st = "idle"
		}
		sourceRows = append(sourceRows, sourceRow{
			SourceID:          s.SourceID,
			WarehouseID:       s.WarehouseID,
			Tier:              s.Tier,
			SourceStatus:      st,
			ScheduledBatch:    sourceScheduled[s.SourceID],
			BlockedCandidates: sourceBlocked[s.SourceID],
		})
	}

	warehouseLedger := buildWarehouseLedger(
		warehouses, effectiveCap, creditsStart, creditsRemaining,
		whScheduled, whDeferredCap, whDeferredCredit, sourceRows,
	)
	batchMatrix := buildBatchMatrix(batches, sourceRows)
	journal := buildJournal(kept)
	summary := buildSummary(sourceRows, batches, kept, ignored, il.Events)

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "source_plan.json"), map[string]any{"sources": sourceRows}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "warehouse_ledger.json"), map[string]any{"warehouses": warehouseLedger}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "batch_matrix.json"), map[string]any{"batches": batchMatrix}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "incident_journal.json"), map[string]any{"applied_events": journal}); err != nil {
		return err
	}
	return writeJSON(filepath.Join(auditDir, "summary.json"), summary)
}

func updateBlockedReason(blocked map[string][]blockedRow, sourceID, batchID, reason string) {
	updated := false
	for i := range blocked[sourceID] {
		if blocked[sourceID][i].BatchID == batchID {
			blocked[sourceID][i].Reason = reason
			updated = true
		}
	}
	if !updated {
		blocked[sourceID] = append(blocked[sourceID], blockedRow{BatchID: batchID, Reason: reason})
		sort.Slice(blocked[sourceID], func(i, j int) bool {
			return blocked[sourceID][i].BatchID < blocked[sourceID][j].BatchID
		})
	}
}

func buildSummary(sourceRows []sourceRow, batches []batchDoc, kept []map[string]any, ignored int, all []map[string]any) map[string]any {
	counts := map[string]int{
		"quarantined": 0, "warehouse_frozen": 0, "deferred_capacity": 0,
		"credit_deferred": 0, "scheduled": 0, "idle": 0,
	}
	scheduledBatches := 0
	for _, r := range sourceRows {
		counts[r.SourceStatus]++
		if r.ScheduledBatch != nil {
			scheduledBatches++
		}
	}
	return map[string]any{
		"applied_incident_events": len(kept),
		"batches_total":           len(batches),
		"credit_deferred_sources": counts["credit_deferred"],
		"deferred_sources":        counts["deferred_capacity"],
		"frozen_sources":          counts["warehouse_frozen"],
		"ignored_incident_events": ignored,
		"quarantined_sources":     counts["quarantined"],
		"scheduled_batches_today": scheduledBatches,
		"scheduled_sources":       counts["scheduled"],
		"sources_total":           len(sourceRows),
		"idle_sources":            counts["idle"],
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
		for _, k := range []string{"source_id", "warehouse_id", "batch_id", "delta", "start_day", "end_day"} {
			if v, ok := ev[k]; ok {
				row[k] = v
			}
		}
		out = append(out, sortedKeys(row))
	}
	return out
}

func buildBatchMatrix(batches []batchDoc, sourceRows []sourceRow) []map[string]any {
	sched := map[string]int{}
	blocked := map[string]int{}
	for _, r := range sourceRows {
		if r.ScheduledBatch != nil {
			sched[r.ScheduledBatch.(string)]++
		}
		for _, br := range r.BlockedCandidates {
			blocked[br.BatchID]++
		}
	}
	var out []map[string]any
	for _, b := range batches {
		out = append(out, map[string]any{
			"batch_id":          b.BatchID,
			"sources_blocked":   blocked[b.BatchID],
			"sources_scheduled": sched[b.BatchID],
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i]["batch_id"].(string) < out[j]["batch_id"].(string) })
	return out
}

func buildWarehouseLedger(
	warehouses []warehouseDoc,
	effectiveCap map[string]int,
	creditsStart map[string]int,
	creditsRemaining map[string]int,
	whScheduled map[string]int,
	whDeferredCap map[string]int,
	whDeferredCredit map[string]int,
	sourceRows []sourceRow,
) map[string]any {
	ledger := map[string]any{}
	for _, wh := range warehouses {
		wid := wh.WarehouseID
		ledger[wid] = map[string]any{
			"effective_cap":              effectiveCap[wid],
			"export_credits_remaining":   creditsRemaining[wid],
			"export_credits_start":       creditsStart[wid],
			"max_exports_per_day":        wh.MaxExportsPerDay,
			"sources_deferred_capacity":  whDeferredCap[wid],
			"sources_deferred_credit":      whDeferredCredit[wid],
			"sources_scheduled":          whScheduled[wid],
		}
	}
	return ledger
}

func chooseBatch(candidates []batchDoc) string {
	if len(candidates) == 0 {
		return ""
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].Priority != candidates[j].Priority {
			return candidates[i].Priority < candidates[j].Priority
		}
		return candidates[i].BatchID < candidates[j].BatchID
	})
	return candidates[0].BatchID
}

func blockReason(
	b batchDoc,
	inWindow bool,
	embargoed map[string]bool,
	quarantined, frozenSrc bool,
	exported map[string]bool,
	maxCost int,
) string {
	if quarantined {
		return "quarantine"
	}
	if frozenSrc {
		return "warehouse_frozen"
	}
	if embargoed[b.BatchID] {
		return "embargoed"
	}
	if !inWindow {
		return "outside_window"
	}
	for _, dep := range b.DependsOn {
		if !exported[dep] {
			return "missing_dependency"
		}
	}
	if b.CreditCost > maxCost {
		return "credit_over_budget"
	}
	return ""
}

func dayInEffectiveWindow(s sourceDoc, pol policyDoc, day int) bool {
	cal := pol.TierCalendar[s.Tier]
	for _, sw := range s.SyncWindows {
		if len(sw) < 2 {
			continue
		}
		for _, tc := range cal {
			if len(tc) < 2 {
				continue
			}
			start := sw[0]
			if tc[0] > start {
				start = tc[0]
			}
			end := sw[1]
			if tc[1] < end {
				end = tc[1]
			}
			if start <= end && day >= start && day <= end {
				return true
			}
		}
	}
	return false
}

func processIncidents(events []map[string]any, day int) (applied map[string][]map[string]any, kept []map[string]any, ignored int) {
	applied = map[string][]map[string]any{
		"cap_bump": {}, "credit_grant": {}, "source_compromise": {},
		"freeze_warehouse": {}, "batch_embargo": {},
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
	case "source_compromise":
		_, ok := ev["source_id"].(string)
		return ok
	case "freeze_warehouse":
		_, ok := ev["warehouse_id"].(string)
		return ok
	case "batch_embargo":
		_, ok := ev["batch_id"].(string)
		_, hasEnd := ev["end_day"]
		return ok && hasEnd
	case "cap_bump", "credit_grant":
		_, ok := ev["warehouse_id"].(string)
		return ok && ev["delta"] != nil
	default:
		return false
	}
}

func embargoSet(applied map[string][]map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range applied["batch_embargo"] {
		bid := ev["batch_id"].(string)
		start := intNum(ev["day"])
		if v, ok := ev["start_day"]; ok {
			start = intNum(v)
		}
		end := intNum(ev["end_day"])
		if day >= start && day <= end {
			out[bid] = true
		}
	}
	return out
}

func compromiseSet(applied map[string][]map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range applied["source_compromise"] {
		if intNum(ev["day"]) <= day {
			out[ev["source_id"].(string)] = true
		}
	}
	return out
}

func freezeSet(applied map[string][]map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range applied["freeze_warehouse"] {
		if intNum(ev["day"]) <= day {
			out[ev["warehouse_id"].(string)] = true
		}
	}
	return out
}

func warehouseCaps(warehouses []warehouseDoc, applied map[string][]map[string]any) map[string]int {
	out := map[string]int{}
	for _, w := range warehouses {
		out[w.WarehouseID] = w.MaxExportsPerDay
	}
	for _, ev := range applied["cap_bump"] {
		wid := ev["warehouse_id"].(string)
		out[wid] += intNum(ev["delta"])
	}
	return out
}

func warehouseCredits(warehouses []warehouseDoc, applied map[string][]map[string]any) map[string]int {
	out := map[string]int{}
	for _, w := range warehouses {
		out[w.WarehouseID] = w.ExportCredits
	}
	for _, ev := range applied["credit_grant"] {
		wid := ev["warehouse_id"].(string)
		out[wid] += intNum(ev["delta"])
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

func stringSet(xs []string) map[string]bool {
	m := map[string]bool{}
	for _, x := range xs {
		m[x] = true
	}
	return m
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

func loadSources(dir string) ([]sourceDoc, error) {
	return loadDir(dir, func(b []byte) (sourceDoc, error) {
		var s sourceDoc
		err := json.Unmarshal(b, &s)
		return s, err
	})
}

func loadBatches(dir string) ([]batchDoc, error) {
	return loadDir(dir, func(b []byte) (batchDoc, error) {
		var x batchDoc
		err := json.Unmarshal(b, &x)
		return x, err
	})
}

func loadWarehouses(dir string) ([]warehouseDoc, error) {
	return loadDir(dir, func(b []byte) (warehouseDoc, error) {
		var x warehouseDoc
		err := json.Unmarshal(b, &x)
		return x, err
	})
}

func loadDir[T any](dir string, parse func([]byte) (T, error)) ([]T, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var out []T
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		x, err := parse(b)
		if err != nil {
			return nil, err
		}
		out = append(out, x)
	}
	return out, nil
}
