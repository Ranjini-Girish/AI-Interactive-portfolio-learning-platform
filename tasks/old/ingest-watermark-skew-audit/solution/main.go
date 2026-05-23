package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type policy struct {
	DedupWindowDays      int            `json:"dedup_window_days"`
	IngestWindowDays     int            `json:"ingest_window_days"`
	LatenessDaysByTier   map[string]int `json:"lateness_days_by_tier"`
	SkewGuardDays        int            `json:"skew_guard_days"`
	SkewPenaltyDays      int            `json:"skew_penalty_days"`
	WatermarkRetreatDays int            `json:"watermark_retreat_days"`
}

type sourceDoc struct {
	SourceID string `json:"source_id"`
	Tier     string `json:"tier"`
}

type partitionDoc struct {
	PartitionID string `json:"partition_id"`
	SourceID    string `json:"source_id"`
}

type batchDoc struct {
	BatchID     string           `json:"batch_id"`
	IngestDay   int              `json:"ingest_day"`
	PartitionID string           `json:"partition_id"`
	Events      []map[string]any `json:"events"`
}

type evtRow struct {
	PartitionID    string
	SourceID       string
	Tier           string
	IngestDay      int
	EventID        string
	EventDay       int
	IdempotencyKey string
	Sequence       int
}

type keptDedup struct {
	EventID  string
	EventDay int
	Sequence int
}

type partStats struct {
	PartitionID              string
	SourceID                   string
	AcceptedDays               []int
	AcceptedCount              int
	RejectedStaleCount         int
	RejectedQuarantineCount    int
	DuplicateSupersededCount   int
}

func main() {
	dataDir := getenv("IWSA_DATA_DIR", "/app/ingest_buffers")
	auditDir := getenv("IWSA_AUDIT_DIR", "/app/audit")
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
	if pol.IngestWindowDays < 1 {
		pol.IngestWindowDays = 1
	}

	incRaw, err := os.ReadFile(filepath.Join(dataDir, "incident_log.json"))
	if err != nil {
		return err
	}
	var il struct {
		Events []map[string]any `json:"events"`
	}
	if err := json.Unmarshal(incRaw, &il); err != nil {
		return err
	}

	sources, err := loadSources(filepath.Join(dataDir, "sources"))
	if err != nil {
		return err
	}
	partitions, err := loadPartitions(filepath.Join(dataDir, "partitions"))
	if err != nil {
		return err
	}

	ingestMin := ps.CurrentDay - (pol.IngestWindowDays - 1)

	applied, ignored := filterIncidents(il.Events, ps.CurrentDay)

	tierLatenessDelta := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	dedupDelta := 0
	graceByPart := map[string][]struct {
		FromDay   int
		ExtraDays int
	}{}
	compromiseSource := map[string]int{}

	for _, ev := range applied {
		kind := strVal(ev["kind"])
		switch kind {
		case "lateness_delta":
			tt := strVal(ev["target_tier"])
			tierLatenessDelta[tt] += intVal(ev["delta"])
		case "dedup_window_extend":
			dedupDelta += intVal(ev["delta"])
		case "grace_day":
			pid := strVal(ev["partition_id"])
			graceByPart[pid] = append(graceByPart[pid], struct {
				FromDay   int
				ExtraDays int
			}{intVal(ev["day"]), intVal(ev["extra_days"])})
		case "source_compromise":
			sid := strVal(ev["source_id"])
			day := intVal(ev["day"])
			if prev, ok := compromiseSource[sid]; !ok || day < prev {
				compromiseSource[sid] = day
			}
		}
	}

	effectiveDedup := pol.DedupWindowDays + dedupDelta

	rows, err := loadEvents(filepath.Join(dataDir, "batches"), partitions, sources, ingestMin, ps.CurrentDay)
	if err != nil {
		return err
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].PartitionID != rows[j].PartitionID {
			return rows[i].PartitionID < rows[j].PartitionID
		}
		if rows[i].IngestDay != rows[j].IngestDay {
			return rows[i].IngestDay < rows[j].IngestDay
		}
		return rows[i].Sequence < rows[j].Sequence
	})

	stats := map[string]*partStats{}
	for pid, p := range partitions {
		stats[pid] = &partStats{PartitionID: pid, SourceID: p.SourceID}
	}

	dedupKept := map[string]keptDedup{}
	var supersessions []map[string]any

	for _, row := range rows {
		st := stats[row.PartitionID]
		compDay, compromised := compromiseSource[row.SourceID]
		if compromised && row.IngestDay >= compDay {
			st.RejectedQuarantineCount++
			continue
		}

		lateness := pol.LatenessDaysByTier[row.Tier] + tierLatenessDelta[row.Tier]
		for _, g := range graceByPart[row.PartitionID] {
			if row.IngestDay >= g.FromDay {
				lateness += g.ExtraDays
			}
		}
		cutoff := ps.CurrentDay - lateness
		if row.EventDay < cutoff {
			st.RejectedStaleCount++
			continue
		}

		dk := row.SourceID + "\x00" + row.IdempotencyKey
		if prev, ok := dedupKept[dk]; ok {
			if abs(row.EventDay-prev.EventDay) <= effectiveDedup {
				newT := tuple{row.EventDay, row.Sequence}
				oldT := tuple{prev.EventDay, prev.Sequence}
				if less(newT, oldT) {
					st.DuplicateSupersededCount++
					continue
				}
				st.DuplicateSupersededCount++
				supersessions = append(supersessions, map[string]any{
					"idempotency_key":     row.IdempotencyKey,
					"kept_event_id":       row.EventID,
					"source_id":           row.SourceID,
					"superseded_event_id": prev.EventID,
				})
				removeAcceptedDay(st, prev.EventDay)
				st.AcceptedCount--
				dedupKept[dk] = keptDedup{row.EventID, row.EventDay, row.Sequence}
				st.AcceptedCount++
				st.AcceptedDays = append(st.AcceptedDays, row.EventDay)
				continue
			}
		}

		dedupKept[dk] = keptDedup{row.EventID, row.EventDay, row.Sequence}
		st.AcceptedCount++
		st.AcceptedDays = append(st.AcceptedDays, row.EventDay)
	}

	sort.Slice(supersessions, func(i, j int) bool {
		si := strVal(supersessions[i]["source_id"])
		sj := strVal(supersessions[j]["source_id"])
		if si != sj {
			return si < sj
		}
		ki := strVal(supersessions[i]["idempotency_key"])
		kj := strVal(supersessions[j]["idempotency_key"])
		if ki != kj {
			return ki < kj
		}
		return strVal(supersessions[i]["superseded_event_id"]) < strVal(supersessions[j]["superseded_event_id"])
	})

	partOut := make([]map[string]any, 0, len(stats))
	partIDs := sortedKeys(stats)
	skewParts := 0
	for _, pid := range partIDs {
		st := stats[pid]
		row := map[string]any{
			"accepted_count":              st.AcceptedCount,
			"duplicate_superseded_count":  st.DuplicateSupersededCount,
			"partition_id":                st.PartitionID,
			"rejected_quarantine_count":   st.RejectedQuarantineCount,
			"rejected_stale_count":        st.RejectedStaleCount,
			"reasons":                     []string{},
			"source_id":                   st.SourceID,
			"skew_exceeded":               false,
			"watermark_day":               nil,
		}
		reasons := []string{}
		if st.RejectedStaleCount > 0 {
			reasons = append(reasons, "stale_events_present")
		}
		if st.RejectedQuarantineCount > 0 {
			reasons = append(reasons, "source_quarantine")
		}
		if st.DuplicateSupersededCount > 0 {
			reasons = append(reasons, "dedup_superseded")
		}
		if len(st.AcceptedDays) > 0 {
			minD, maxD := st.AcceptedDays[0], st.AcceptedDays[0]
			for _, d := range st.AcceptedDays[1:] {
				if d < minD {
					minD = d
				}
				if d > maxD {
					maxD = d
				}
			}
			if maxD-minD > pol.SkewGuardDays {
				row["skew_exceeded"] = true
				reasons = append(reasons, "skew_exceeded")
				row["watermark_day"] = maxD - pol.SkewPenaltyDays
				skewParts++
			} else {
				row["watermark_day"] = maxD - pol.WatermarkRetreatDays
			}
		}
		sort.Strings(reasons)
		row["reasons"] = reasons
		partOut = append(partOut, row)
	}

	srcAccepted := map[string]int{}
	for _, st := range stats {
		srcAccepted[st.SourceID] += st.AcceptedCount
	}

	srcOut := make([]map[string]any, 0, len(sources))
	srcIDs := sortedKeys(sources)
	quarantined := 0
	for _, sid := range srcIDs {
		s := sources[sid]
		disposition := "active"
		reasons := []string{}
		if _, ok := compromiseSource[sid]; ok {
			disposition = "quarantined"
			reasons = []string{"source_compromise"}
			quarantined++
		}
		srcOut = append(srcOut, map[string]any{
			"accepted_events": srcAccepted[sid],
			"disposition":     disposition,
			"reasons":         reasons,
			"source_id":       sid,
			"tier":            s.Tier,
		})
	}

	journal := make([]map[string]any, 0, len(applied))
	for _, ev := range applied {
		journal = append(journal, compactIncident(ev))
	}

	totAcc, totDup, totStale, totQuar := 0, 0, 0, 0
	for _, st := range stats {
		totAcc += st.AcceptedCount
		totDup += st.DuplicateSupersededCount
		totStale += st.RejectedStaleCount
		totQuar += st.RejectedQuarantineCount
	}

	summary := map[string]any{
		"applied_incident_events":        len(applied),
		"ignored_incident_events":        ignored,
		"partitions_total":               len(partitions),
		"partitions_with_skew_exceeded":  skewParts,
		"quarantined_sources":            quarantined,
		"sources_total":                  len(sources),
		"total_accepted":                 totAcc,
		"total_duplicate_superseded":     totDup,
		"total_rejected_quarantine":      totQuar,
		"total_rejected_stale":           totStale,
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	files := map[string]any{
		"partition_ledger.json": map[string]any{"partitions": partOut},
		"source_verdicts.json":  map[string]any{"sources": srcOut},
		"dedup_journal.json":    map[string]any{"supersessions": supersessions},
		"incident_journal.json": map[string]any{"applied_events": journal},
		"summary.json":          summary,
	}
	for name, body := range files {
		if err := writeCanonical(filepath.Join(auditDir, name), body); err != nil {
			return err
		}
	}
	return nil
}

type tuple struct {
	day int
	seq int
}

func less(a, b tuple) bool {
	if a.day != b.day {
		return a.day < b.day
	}
	return a.seq < b.seq
}

func abs(x int) int {
	if x < 0 {
		return -x
	}
	return x
}

func removeAcceptedDay(st *partStats, day int) {
	for i, d := range st.AcceptedDays {
		if d == day {
			st.AcceptedDays = append(st.AcceptedDays[:i], st.AcceptedDays[i+1:]...)
			return
		}
	}
}

func filterIncidents(events []map[string]any, currentDay int) ([]map[string]any, int) {
	ignored := 0
	candidates := make([]map[string]any, 0)
	for _, ev := range events {
		if !boolVal(ev["accepted"]) {
			ignored++
			continue
		}
		if intVal(ev["day"]) > currentDay {
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
		if incidentWellFormed(strVal(ev["kind"]), ev) {
			applied = append(applied, ev)
		} else {
			ignored++
		}
	}
	return applied, ignored
}

func incidentWellFormed(kind string, ev map[string]any) bool {
	switch kind {
	case "lateness_delta":
		tt := strVal(ev["target_tier"])
		if tt != "gold" && tt != "silver" && tt != "bronze" {
			return false
		}
		_, ok := ev["delta"]
		return ok
	case "dedup_window_extend":
		_, ok := ev["delta"]
		return ok
	case "grace_day":
		if strVal(ev["partition_id"]) == "" {
			return false
		}
		_, ok := ev["extra_days"]
		return ok
	case "source_compromise":
		return strVal(ev["source_id"]) != ""
	default:
		return false
	}
}

func compactIncident(ev map[string]any) map[string]any {
	out := map[string]any{
		"day":      intVal(ev["day"]),
		"event_id": strVal(ev["event_id"]),
		"kind":     strVal(ev["kind"]),
	}
	switch strVal(ev["kind"]) {
	case "lateness_delta":
		out["delta"] = intVal(ev["delta"])
		out["target_tier"] = strVal(ev["target_tier"])
	case "dedup_window_extend":
		out["delta"] = intVal(ev["delta"])
	case "grace_day":
		out["extra_days"] = intVal(ev["extra_days"])
		out["partition_id"] = strVal(ev["partition_id"])
	case "source_compromise":
		out["source_id"] = strVal(ev["source_id"])
	}
	return out
}

func loadSources(dir string) (map[string]sourceDoc, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := map[string]sourceDoc{}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var s sourceDoc
		if err := json.Unmarshal(raw, &s); err != nil {
			return nil, err
		}
		out[s.SourceID] = s
	}
	return out, nil
}

func loadPartitions(dir string) (map[string]partitionDoc, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := map[string]partitionDoc{}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var p partitionDoc
		if err := json.Unmarshal(raw, &p); err != nil {
			return nil, err
		}
		out[p.PartitionID] = p
	}
	return out, nil
}

func loadEvents(
	batchDir string,
	partitions map[string]partitionDoc,
	sources map[string]sourceDoc,
	ingestMin, ingestMax int,
) ([]evtRow, error) {
	entries, err := os.ReadDir(batchDir)
	if err != nil {
		return nil, err
	}
	var rows []evtRow
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(batchDir, e.Name()))
		if err != nil {
			return nil, err
		}
		var b batchDoc
		if err := json.Unmarshal(raw, &b); err != nil {
			return nil, err
		}
		if b.IngestDay < ingestMin || b.IngestDay > ingestMax {
			continue
		}
		part, ok := partitions[b.PartitionID]
		if !ok {
			continue
		}
		src, ok := sources[part.SourceID]
		if !ok {
			continue
		}
		for _, ev := range b.Events {
			rows = append(rows, evtRow{
				PartitionID:    b.PartitionID,
				SourceID:       part.SourceID,
				Tier:           src.Tier,
				IngestDay:      b.IngestDay,
				EventID:        strVal(ev["event_id"]),
				EventDay:       intVal(ev["event_day"]),
				IdempotencyKey: strVal(ev["idempotency_key"]),
				Sequence:       intVal(ev["sequence"]),
			})
		}
	}
	return rows, nil
}

func writeCanonical(path string, v any) error {
	raw, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	raw = append(raw, '\n')
	return os.WriteFile(path, raw, 0o644)
}

func sortedKeys[T any](m map[string]T) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func strVal(v any) string {
	if v == nil {
		return ""
	}
	switch t := v.(type) {
	case string:
		return t
	default:
		return fmt.Sprint(t)
	}
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

func boolVal(v any) bool {
	switch t := v.(type) {
	case bool:
		return t
	default:
		return false
	}
}
