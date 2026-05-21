package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type incidentDoc struct {
	ForcedQuarantine         []string `json:"forced_quarantine"`
	IncidentID               string   `json:"incident_id"`
	ReleasedHoldIDs          []string `json:"released_hold_ids"`
	SkewSlack                int      `json:"skew_slack"`
	TransitiveExemptChildren []string `json:"transitive_exempt_children"`
	WaivedSkewChildIDs       []string `json:"waived_skew_child_ids"`
}

type segmentRec struct {
	BaseQuarantine    bool    `json:"base_quarantine"`
	CompactionHold    bool    `json:"compaction_hold"`
	HoldID            string  `json:"hold_id"`
	ParentSegmentID   *string `json:"parent_segment_id"`
	RecordEpochHigh   int     `json:"record_epoch_high"`
	RecordEpochLow    int     `json:"record_epoch_low"`
	SegmentID         string  `json:"segment_id"`
	WriterEpoch       int     `json:"writer_epoch"`
}

type finding struct {
	Code              string  `json:"code"`
	Detail            string  `json:"detail"`
	ParentSegmentID   *string `json:"parent_segment_id"`
	SegmentID         string  `json:"segment_id"`
	WriterEpoch       int     `json:"writer_epoch"`
}

type gateRow struct {
	GateActive  bool   `json:"gate_active"`
	HoldID      string `json:"hold_id"`
	SegmentID   string `json:"segment_id"`
}

type mergeOrderOut struct {
	OrderedSegmentIDs []string `json:"ordered_segment_ids"`
}

type epochSkewOut struct {
	Findings []finding `json:"findings"`
}

type compactionGatesOut struct {
	Gates []gateRow `json:"gates"`
}

type quarantineClosureOut struct {
	BaseIDs               []string `json:"base_ids"`
	ForcedIDs             []string `json:"forced_ids"`
	QuarantinedSegmentIDs []string `json:"quarantined_segment_ids"`
	TransitiveOnlyIDs     []string `json:"transitive_only_ids"`
}

type summaryOut struct {
	ActiveCompactionGates    int `json:"active_compaction_gates"`
	EpochSkewFindings        int `json:"epoch_skew_findings"`
	QuarantinedTotal         int `json:"quarantined_total"`
	SegmentsLoaded           int `json:"segments_loaded"`
	TransitiveQuarantineCount int `json:"transitive_quarantine_count"`
	WriterEpochSpan          int `json:"writer_epoch_span"`
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func readIncident(path string) (incidentDoc, error) {
	var inc incidentDoc
	b, err := os.ReadFile(path)
	if err != nil {
		return inc, err
	}
	if err := json.Unmarshal(b, &inc); err != nil {
		return inc, err
	}
	sort.Strings(inc.ForcedQuarantine)
	sort.Strings(inc.ReleasedHoldIDs)
	sort.Strings(inc.TransitiveExemptChildren)
	sort.Strings(inc.WaivedSkewChildIDs)
	return inc, nil
}

func loadSegments(dir string) (map[string]segmentRec, error) {
	out := map[string]segmentRec{}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		if filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var s segmentRec
		if err := json.Unmarshal(b, &s); err != nil {
			return nil, fmt.Errorf("parse %s: %w", e.Name(), err)
		}
		if s.SegmentID == "" {
			return nil, fmt.Errorf("empty segment_id in %s", e.Name())
		}
		if _, ok := out[s.SegmentID]; ok {
			return nil, fmt.Errorf("duplicate segment_id %s", s.SegmentID)
		}
		out[s.SegmentID] = s
	}
	return out, nil
}

func writeJSON(path string, v any) error {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		return err
	}
	b := buf.Bytes()
	if len(b) == 0 {
		return fmt.Errorf("empty json for %s", path)
	}
	if b[len(b)-1] == '\n' {
		b = b[:len(b)-1]
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}

func setFromSlice(xs []string) map[string]struct{} {
	m := map[string]struct{}{}
	for _, x := range xs {
		m[x] = struct{}{}
	}
	return m
}

func sortFindings(fs []finding) {
	sort.Slice(fs, func(i, j int) bool {
		a, b := fs[i], fs[j]
		if a.SegmentID != b.SegmentID {
			return a.SegmentID < b.SegmentID
		}
		if a.Code != b.Code {
			return a.Code < b.Code
		}
		if a.Detail != b.Detail {
			return a.Detail < b.Detail
		}
		ap, bp := a.ParentSegmentID, b.ParentSegmentID
		if ap == nil && bp == nil {
			return false
		}
		if ap == nil {
			return false
		}
		if bp == nil {
			return true
		}
		return *ap < *bp
	})
}

func run(dataDir, auditDir string) error {
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	inc, err := readIncident(filepath.Join(dataDir, "incidents", "active.json"))
	if err != nil {
		return err
	}
	segs, err := loadSegments(filepath.Join(dataDir, "segments"))
	if err != nil {
		return err
	}
	if len(segs) == 0 {
		return fmt.Errorf("no segments loaded")
	}

	ids := make([]string, 0, len(segs))
	for id := range segs {
		ids = append(ids, id)
	}
	sort.Slice(ids, func(i, j int) bool {
		si, sj := segs[ids[i]], segs[ids[j]]
		if si.WriterEpoch != sj.WriterEpoch {
			return si.WriterEpoch < sj.WriterEpoch
		}
		return ids[i] < ids[j]
	})
	if err := writeJSON(filepath.Join(auditDir, "merge_order.json"), mergeOrderOut{OrderedSegmentIDs: ids}); err != nil {
		return err
	}

	baseIDs := make([]string, 0)
	for id, s := range segs {
		if s.BaseQuarantine {
			baseIDs = append(baseIDs, id)
		}
	}
	sort.Strings(baseIDs)

	forced := append([]string(nil), inc.ForcedQuarantine...)
	sort.Strings(forced)

	B := map[string]struct{}{}
	for _, id := range baseIDs {
		B[id] = struct{}{}
	}
	for _, id := range forced {
		B[id] = struct{}{}
	}

	exempt := setFromSlice(inc.TransitiveExemptChildren)

	Q := map[string]struct{}{}
	for id := range B {
		Q[id] = struct{}{}
	}
	changed := true
	for changed {
		changed = false
		for cid, s := range segs {
			if _, ok := Q[cid]; ok {
				continue
			}
			p := s.ParentSegmentID
			if p == nil || *p == "" || *p == cid {
				continue
			}
			pid := *p
			if _, ok := segs[pid]; !ok {
				continue
			}
			if _, ok := Q[pid]; !ok {
				continue
			}
			if _, ok := exempt[cid]; ok {
				continue
			}
			Q[cid] = struct{}{}
			changed = true
		}
	}

	quarantined := make([]string, 0, len(Q))
	for id := range Q {
		quarantined = append(quarantined, id)
	}
	sort.Strings(quarantined)

	transitiveOnly := make([]string, 0)
	for _, id := range quarantined {
		if _, ok := B[id]; !ok {
			transitiveOnly = append(transitiveOnly, id)
		}
	}
	sort.Strings(transitiveOnly)

	qc := quarantineClosureOut{
		BaseIDs:               append([]string(nil), baseIDs...),
		ForcedIDs:             forced,
		QuarantinedSegmentIDs: quarantined,
		TransitiveOnlyIDs:     transitiveOnly,
	}
	if err := writeJSON(filepath.Join(auditDir, "quarantine_closure.json"), qc); err != nil {
		return err
	}

	waived := setFromSlice(inc.WaivedSkewChildIDs)
	released := setFromSlice(inc.ReleasedHoldIDs)

	var findings []finding
	for sid, s := range segs {
		if s.RecordEpochLow > s.RecordEpochHigh {
			findings = append(findings, finding{
				Code:            "internal_inversion",
				Detail:          "low_gt_high",
				ParentSegmentID: nil,
				SegmentID:       sid,
				WriterEpoch:     s.WriterEpoch,
			})
			continue
		}
		p := s.ParentSegmentID
		if p == nil || *p == "" || *p == sid {
			continue
		}
		pid := *p
		parent, ok := segs[pid]
		if !ok {
			pp := pid
			findings = append(findings, finding{
				Code:            "missing_parent_ref",
				Detail:          "unknown_parent",
				ParentSegmentID: &pp,
				SegmentID:       sid,
				WriterEpoch:     s.WriterEpoch,
			})
			continue
		}
		if _, ok := waived[sid]; ok {
			continue
		}
		expected := parent.RecordEpochHigh + 1
		lowOK := expected - inc.SkewSlack
		highOK := expected + inc.SkewSlack
		if s.RecordEpochLow < lowOK {
			pp := pid
			findings = append(findings, finding{
				Code:            "epoch_behind",
				Detail:          "low_below_window",
				ParentSegmentID: &pp,
				SegmentID:       sid,
				WriterEpoch:     s.WriterEpoch,
			})
		} else if s.RecordEpochLow > highOK {
			pp := pid
			findings = append(findings, finding{
				Code:            "epoch_ahead",
				Detail:          "low_above_window",
				ParentSegmentID: &pp,
				SegmentID:       sid,
				WriterEpoch:     s.WriterEpoch,
			})
		}
	}
	sortFindings(findings)
	if err := writeJSON(filepath.Join(auditDir, "epoch_skew.json"), epochSkewOut{Findings: findings}); err != nil {
		return err
	}

	var gates []gateRow
	for sid, s := range segs {
		if !s.CompactionHold {
			continue
		}
		active := true
		if s.HoldID != "" {
			_, ok := released[s.HoldID]
			active = !ok
		}
		gates = append(gates, gateRow{
			GateActive: active,
			HoldID:     s.HoldID,
			SegmentID:  sid,
		})
	}
	sort.Slice(gates, func(i, j int) bool { return gates[i].SegmentID < gates[j].SegmentID })
	if err := writeJSON(filepath.Join(auditDir, "compaction_gates.json"), compactionGatesOut{Gates: gates}); err != nil {
		return err
	}

	activeGates := 0
	for _, g := range gates {
		if g.GateActive {
			activeGates++
		}
	}

	minW, maxW := 0, 0
	if len(ids) > 0 {
		minW = segs[ids[0]].WriterEpoch
		maxW = minW
		for _, id := range ids {
			w := segs[id].WriterEpoch
			if w < minW {
				minW = w
			}
			if w > maxW {
				maxW = w
			}
		}
	}
	span := 0
	if len(ids) >= 2 {
		span = maxW - minW
	}

	sm := summaryOut{
		ActiveCompactionGates:     activeGates,
		EpochSkewFindings:         len(findings),
		QuarantinedTotal:          len(quarantined),
		SegmentsLoaded:            len(segs),
		TransitiveQuarantineCount: len(transitiveOnly),
		WriterEpochSpan:           span,
	}
	return writeJSON(filepath.Join(auditDir, "summary.json"), sm)
}

func main() {
	dataDir := getenv("LES_DATA_DIR", "/app/ledger_epoch")
	auditDir := getenv("LES_AUDIT_DIR", "/app/audit")
	if err := run(dataDir, auditDir); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}
