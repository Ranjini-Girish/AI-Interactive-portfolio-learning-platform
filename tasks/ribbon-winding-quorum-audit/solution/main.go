package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type policyDoc struct {
	QuorumBase          int    `json:"quorum_base"`
	WindingModulus      int    `json:"winding_modulus"`
	AnchorBlend         string `json:"anchor_blend"`
	CrisisMode          bool   `json:"crisis_mode"`
	CrisisSeverityFloor int    `json:"crisis_severity_floor"`
	CrisisQuorum        int    `json:"crisis_quorum"`
}

type domainLayout struct {
	RibbonBias map[string]int `json:"ribbon_bias"`
}

type poolState struct {
	Votes      map[string]int `json:"votes"`
	CurrentDay int            `json:"current_day"`
}

type indexDoc struct {
	Segments []string `json:"segments"`
}

type anchorMask struct {
	MaskHex string `json:"mask_hex"`
}

type incidentEvent struct {
	Day      int      `json:"day"`
	EventID  string   `json:"event_id"`
	Action   string   `json:"action"`
	Lanes    []string `json:"lanes"`
	Severity int      `json:"severity"`
	Bias     int      `json:"bias"`
}

type incidentLog struct {
	Events []incidentEvent `json:"events"`
}

type segmentFile struct {
	ID      string `json:"id"`
	Lane    string `json:"lane"`
	Winding int    `json:"winding"`
	Weight  int    `json:"weight"`
	Slot    string `json:"slot"`
}

type segOut struct {
	EffectiveVotes   int    `json:"effective_votes"`
	EffectiveWinding int    `json:"effective_winding"`
	ID               string `json:"id"`
	Lane             string `json:"lane"`
	LaneBonus        int    `json:"lane_bonus"`
	QuorumNeed       int    `json:"quorum_need"`
	Satisfied        bool   `json:"satisfied"`
	Status           string `json:"status"`
	VotesRaw         int    `json:"votes_raw"`
	Winding          int    `json:"winding"`
}

type laneAgg struct {
	Frozen       int    `json:"frozen"`
	Lane         string `json:"lane"`
	MissingSlot  int    `json:"missing_slot"`
	OK           int    `json:"ok"`
	SegmentCount int    `json:"segment_count"`
	Short        int    `json:"short"`
}

type appliedRow struct {
	Action  string   `json:"action"`
	Day     int      `json:"day"`
	EventID string   `json:"event_id"`
	Lanes   []string `json:"lanes"`
	Note    string   `json:"note"`
}

// summaryOut: struct field order equals lexicographic JSON key order.
type summaryOut struct {
	ActiveQuorumFloor  int    `json:"active_quorum_floor"`
	AnchorBlend        string `json:"anchor_blend"`
	AppliedIncidents   int    `json:"applied_incidents"`
	CrisisTriggerDay   *int   `json:"crisis_trigger_day"`
	CrisisTriggered    bool   `json:"crisis_triggered"`
	EligibleIncidents  int    `json:"eligible_incidents"`
	LaneFrozenCount    int    `json:"lane_frozen_count"`
	MissingSlotCount   int    `json:"missing_slot_count"`
	QuorumBase         int    `json:"quorum_base"`
	SatisfiedCount     int    `json:"satisfied_count"`
	SegmentsTotal      int    `json:"segments_total"`
	ShortCount         int    `json:"short_count"`
	WindingModulus     int    `json:"winding_modulus"`
}

type segmentEnvelope struct {
	Segments []segOut `json:"segments"`
}

type laneEnvelope struct {
	Lanes []laneAgg `json:"lanes"`
}

type incidentEnvelope struct {
	Applied []appliedRow `json:"applied"`
}

func must(err error) {
	if err != nil {
		panic(err)
	}
}

func readJSON(path string, out any) {
	b, err := os.ReadFile(path)
	must(err)
	must(json.Unmarshal(b, out))
}

func canonicalJSON(v any) []byte {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	must(enc.Encode(v))
	return buf.Bytes()
}

func parseHexU64(s string) (uint64, error) {
	s = strings.TrimSpace(s)
	s = strings.TrimPrefix(strings.ToLower(s), "0x")
	if len(s) == 0 {
		return 0, fmt.Errorf("empty mask")
	}
	if len(s)%2 == 1 {
		s = "0" + s
	}
	return strconv.ParseUint(s, 16, 64)
}

func effectiveWinding(blend string, hi, lo uint64, winding int, mod int) int {
	w := uint64(winding)
	var fused uint64
	switch blend {
	case "xor":
		fused = hi ^ lo ^ w
	case "or":
		fused = hi | lo | w
	default:
		panic("bad anchor_blend")
	}
	if mod <= 0 {
		panic("bad winding_modulus")
	}
	return int(fused % uint64(mod))
}

func main() {
	if len(os.Args) > 1 {
		fmt.Fprintln(os.Stderr, "rwqaudit: unexpected arguments")
		os.Exit(2)
	}
	dataRoot := strings.TrimSpace(os.Getenv("RWQ_DATA_DIR"))
	if dataRoot == "" {
		dataRoot = "/app/rwq_lab"
	}
	auditRoot := strings.TrimSpace(os.Getenv("RWQ_AUDIT_DIR"))
	if auditRoot == "" {
		auditRoot = "/app/rwq_audit"
	}
	must(os.MkdirAll(auditRoot, 0o755))

	var pol policyDoc
	readJSON(filepath.Join(dataRoot, "policy.json"), &pol)
	var layout domainLayout
	readJSON(filepath.Join(dataRoot, "domain_layout.json"), &layout)
	var pool poolState
	readJSON(filepath.Join(dataRoot, "pool_state.json"), &pool)
	var idx indexDoc
	readJSON(filepath.Join(dataRoot, "index.json"), &idx)
	var inc incidentLog
	readJSON(filepath.Join(dataRoot, "incident_log.json"), &inc)

	var hiA, loA anchorMask
	readJSON(filepath.Join(dataRoot, "anchors", "hi.json"), &hiA)
	readJSON(filepath.Join(dataRoot, "anchors", "lo.json"), &loA)
	hi, err := parseHexU64(hiA.MaskHex)
	must(err)
	lo, err := parseHexU64(loA.MaskHex)
	must(err)

	if layout.RibbonBias == nil {
		layout.RibbonBias = map[string]int{}
	}
	if pool.Votes == nil {
		pool.Votes = map[string]int{}
	}

	eligible := make([]incidentEvent, 0, len(inc.Events))
	for _, ev := range inc.Events {
		if ev.Day <= 0 {
			fmt.Fprintln(os.Stderr, "incident day must be positive")
			os.Exit(1)
		}
		if ev.Day <= pool.CurrentDay {
			eligible = append(eligible, ev)
		}
	}
	sort.Slice(eligible, func(i, j int) bool {
		if eligible[i].Day != eligible[j].Day {
			return eligible[i].Day < eligible[j].Day
		}
		return eligible[i].EventID < eligible[j].EventID
	})

	frozen := map[string]bool{}
	laneCarry := map[string]int{}
	applied := make([]appliedRow, 0, len(eligible))
	crisisOn := false
	var crisisDay *int

	for _, ev := range eligible {
		switch ev.Action {
		case "freeze_lane":
			for _, ln := range ev.Lanes {
				frozen[ln] = true
			}
			applied = append(applied, appliedRow{
				Day: ev.Day, EventID: ev.EventID, Action: ev.Action, Lanes: append([]string(nil), ev.Lanes...),
				Note: "lanes marked frozen",
			})
		case "thaw_lane":
			for _, ln := range ev.Lanes {
				delete(frozen, ln)
			}
			applied = append(applied, appliedRow{
				Day: ev.Day, EventID: ev.EventID, Action: ev.Action, Lanes: append([]string(nil), ev.Lanes...),
				Note: "lanes removed from frozen set",
			})
		case "pulse_carry":
			for _, ln := range ev.Lanes {
				laneCarry[ln] += ev.Bias
			}
			applied = append(applied, appliedRow{
				Day: ev.Day, EventID: ev.EventID, Action: ev.Action, Lanes: append([]string(nil), ev.Lanes...),
				Note: "lane carry updated",
			})
		default:
			fmt.Fprintf(os.Stderr, "unknown incident action %q\n", ev.Action)
			os.Exit(1)
		}
		if pol.CrisisMode && ev.Severity >= pol.CrisisSeverityFloor && !crisisOn {
			crisisOn = true
			d := ev.Day
			crisisDay = &d
		}
	}

	segments := make([]segmentFile, 0, len(idx.Segments))
	for _, rel := range idx.Segments {
		var sf segmentFile
		readJSON(filepath.Join(dataRoot, rel), &sf)
		segments = append(segments, sf)
	}
	sort.Slice(segments, func(i, j int) bool { return segments[i].ID < segments[j].ID })

	baseNeed := pol.QuorumBase
	if crisisOn {
		baseNeed = pol.CrisisQuorum
	}

	segOuts := make([]segOut, 0, len(segments))
	laneStats := map[string]*laneAgg{}

	for _, sg := range segments {
		effW := effectiveWinding(pol.AnchorBlend, hi, lo, sg.Winding, pol.WindingModulus)
		need := baseNeed + effW
		raw, ok := pool.Votes[sg.Slot]
		if !ok {
			raw = 0
		}
		bias := layout.RibbonBias[sg.Lane]
		carry := laneCarry[sg.Lane]
		evVotes := raw + bias + carry

		st := "ok"
		sat := false
		if frozen[sg.Lane] {
			st = "lane_frozen"
			sat = false
		} else if !ok && sg.Slot != "" {
			st = "slot_missing"
			sat = false
		} else if evVotes >= need {
			st = "ok"
			sat = true
		} else {
			st = "short"
			sat = false
		}

		segOuts = append(segOuts, segOut{
			EffectiveVotes: evVotes, EffectiveWinding: effW, ID: sg.ID, Lane: sg.Lane,
			LaneBonus: bias + carry, QuorumNeed: need, Satisfied: sat, Status: st,
			VotesRaw: raw, Winding: sg.Winding,
		})

		if _, exists := laneStats[sg.Lane]; !exists {
			laneStats[sg.Lane] = &laneAgg{Lane: sg.Lane}
		}
		ag := laneStats[sg.Lane]
		ag.SegmentCount++
		switch st {
		case "short":
			ag.Short++
		case "lane_frozen":
			ag.Frozen++
		case "ok":
			ag.OK++
		case "slot_missing":
			ag.MissingSlot++
		}
	}

	laneNames := make([]string, 0, len(laneStats))
	for ln := range laneStats {
		laneNames = append(laneNames, ln)
	}
	sort.Strings(laneNames)
	laneList := make([]laneAgg, 0, len(laneNames))
	for _, ln := range laneNames {
		laneList = append(laneList, *laneStats[ln])
	}

	satCount := 0
	shortCount := 0
	frozenCount := 0
	missingCount := 0
	for _, s := range segOuts {
		if s.Satisfied {
			satCount++
		}
		switch s.Status {
		case "short":
			shortCount++
		case "lane_frozen":
			frozenCount++
		case "slot_missing":
			missingCount++
		}
	}

	summary := summaryOut{
		SegmentsTotal:      len(segOuts),
		SatisfiedCount:     satCount,
		ShortCount:         shortCount,
		LaneFrozenCount:    frozenCount,
		MissingSlotCount:   missingCount,
		CrisisTriggered:    crisisOn,
		CrisisTriggerDay:   crisisDay,
		EligibleIncidents:  len(eligible),
		AppliedIncidents:   len(applied),
		AnchorBlend:        pol.AnchorBlend,
		WindingModulus:     pol.WindingModulus,
		QuorumBase:         pol.QuorumBase,
		ActiveQuorumFloor:  baseNeed,
	}

	outSeg := segmentEnvelope{Segments: segOuts}
	outLane := laneEnvelope{Lanes: laneList}
	outInc := incidentEnvelope{Applied: applied}

	must(os.WriteFile(filepath.Join(auditRoot, "segment_quorum.json"), canonicalJSON(outSeg), 0o644))
	must(os.WriteFile(filepath.Join(auditRoot, "lane_summary.json"), canonicalJSON(outLane), 0o644))
	must(os.WriteFile(filepath.Join(auditRoot, "incident_effects.json"), canonicalJSON(outInc), 0o644))
	must(os.WriteFile(filepath.Join(auditRoot, "summary.json"), canonicalJSON(summary), 0o644))
}
