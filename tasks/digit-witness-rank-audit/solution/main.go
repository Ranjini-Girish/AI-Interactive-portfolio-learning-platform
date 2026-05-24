package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type domainLayout struct {
	Lanes []string `json:"lanes"`
}

type policy struct {
	RadixBase int `json:"radix_base"`
	WitnessK  int `json:"witness_k"`
}

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type laneFile struct {
	LaneID   string `json:"lane_id"`
	Readings []int  `json:"readings"`
}

type witnessRow struct {
	DigitSum int    `json:"digit_sum"`
	Index    int    `json:"index"`
	LaneID   string `json:"lane_id"`
	Reading  int    `json:"reading"`
}

type laneWitnessBlock struct {
	LaneID    string         `json:"lane_id"`
	Witnesses []witnessRow `json:"witnesses"`
}

type laneWitnessOut struct {
	Lanes []laneWitnessBlock `json:"lanes"`
}

type mergedRankOut struct {
	Witnesses []witnessRow `json:"witnesses"`
}

type incidentTrail struct {
	Applied []map[string]any `json:"applied"`
	Ignored int              `json:"ignored"`
}

type summaryOut struct {
	AppliedIncidents       int `json:"applied_incidents"`
	CurrentDayUsed         int `json:"current_day_used"`
	IgnoredIncidents       int `json:"ignored_incidents"`
	IncidentDayFloorUsed  int `json:"incident_day_floor_used"`
	MergedWitnessCount    int `json:"merged_witness_count"`
	RadixFinal             int `json:"radix_final"`
	SuppressedLaneCount    int `json:"suppressed_lane_count"`
	TotalReadings          int `json:"total_readings"`
}

func mustReadJSON(path string, out any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, out); err != nil {
		panic(err)
	}
}

func canonicalMarshal(v any) []byte {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		panic(err)
	}
	out := buf.Bytes()
	for len(out) > 0 && out[len(out)-1] == '\n' {
		out = out[:len(out)-1]
	}
	out = append(out, '\n')
	return out
}

func writeFile(path string, data []byte) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		panic(err)
	}
	if err := os.WriteFile(path, data, 0o644); err != nil {
		panic(err)
	}
}

func sortKeysDeep(v any) any {
	switch t := v.(type) {
	case map[string]any:
		keys := make([]string, 0, len(t))
		for k := range t {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		out := map[string]any{}
		for _, k := range keys {
			out[k] = sortKeysDeep(t[k])
		}
		return out
	case []any:
		out := make([]any, len(t))
		for i, x := range t {
			out[i] = sortKeysDeep(x)
		}
		return out
	default:
		return v
	}
}

func sortEvents(events []map[string]any) []map[string]any {
	out := append([]map[string]any(nil), events...)
	sort.SliceStable(out, func(i, j int) bool {
		di := int(out[i]["day"].(float64))
		dj := int(out[j]["day"].(float64))
		if di != dj {
			return di < dj
		}
		ei := out[i]["event_id"].(string)
		ej := out[j]["event_id"].(string)
		return ei < ej
	})
	return out
}

func digitSum(n, base int) int {
	if n < 0 {
		n = -n
	}
	if n == 0 {
		return 0
	}
	sum := 0
	for n > 0 {
		sum += n % base
		n /= base
	}
	return sum
}

func main() {
	dataRoot := os.Getenv("DWR_DATA_DIR")
	if dataRoot == "" {
		dataRoot = "/app/dwr_lab"
	}
	auditRoot := os.Getenv("DWR_AUDIT_DIR")
	if auditRoot == "" {
		auditRoot = "/app/dwr_audit"
	}

	var layout domainLayout
	mustReadJSON(filepath.Join(dataRoot, "domain_layout.json"), &layout)
	laneSet := map[string]struct{}{}
	for _, l := range layout.Lanes {
		laneSet[l] = struct{}{}
	}

	var pol policy
	mustReadJSON(filepath.Join(dataRoot, "policy.json"), &pol)

	var pool poolState
	mustReadJSON(filepath.Join(dataRoot, "pool_state.json"), &pool)

	var dayFloor struct {
		StartDay int `json:"start_day"`
	}
	mustReadJSON(filepath.Join(dataRoot, "anchors", "day_floor.json"), &dayFloor)

	floorDay := dayFloor.StartDay

	var log incidentLog
	mustReadJSON(filepath.Join(dataRoot, "incident_log.json"), &log)

	radix := pol.RadixBase
	if radix < 2 {
		radix = 2
	}
	suppressed := map[string]struct{}{}
	applied := []map[string]any{}
	ignored := 0

	for _, ev := range sortEvents(log.Events) {
		kind, _ := ev["kind"].(string)
		_, eidOK := ev["event_id"].(string)
		dayF, dayOK := ev["day"].(float64)
		day := int(dayF)
		if !eidOK || !dayOK || kind == "" {
			ignored++
			continue
		}
		if day < floorDay || day > pool.CurrentDay {
			ignored++
			continue
		}
		switch kind {
		case "bump_radix":
			nb, ok := ev["new_base"].(float64)
			if !ok {
				ignored++
				continue
			}
			v := int(nb)
			if v < 2 {
				ignored++
				continue
			}
			if v > radix {
				radix = v
			}
			if sm, ok := sortKeysDeep(ev).(map[string]any); ok {
				applied = append(applied, sm)
			}
		case "suppress_lane":
			lid, ok := ev["lane_id"].(string)
			if !ok {
				ignored++
				continue
			}
			if _, ok := laneSet[lid]; !ok {
				ignored++
				continue
			}
			suppressed[lid] = struct{}{}
			if sm, ok := sortKeysDeep(ev).(map[string]any); ok {
				applied = append(applied, sm)
			}
		default:
			ignored++
		}
	}

	totalReadings := 0
	blocks := []laneWitnessBlock{}
	for _, lid := range layout.Lanes {
		if _, bad := suppressed[lid]; bad {
			continue
		}
		var lf laneFile
		mustReadJSON(filepath.Join(dataRoot, "lanes", lid+".json"), &lf)
		totalReadings += len(lf.Readings)
		type scored struct {
			idx int
			val int
			ds  int
		}
		sc := make([]scored, 0, len(lf.Readings))
		for i, r := range lf.Readings {
			sc = append(sc, scored{idx: i, val: r, ds: digitSum(r, radix)})
		}
		sort.SliceStable(sc, func(i, j int) bool {
			if sc[i].ds != sc[j].ds {
				return sc[i].ds > sc[j].ds
			}
			if sc[i].val != sc[j].val {
				return sc[i].val > sc[j].val
			}
			return sc[i].idx < sc[j].idx
		})
		k := pol.WitnessK
		if k < 0 {
			k = 0
		}
		if k > len(sc) {
			k = len(sc)
		}
		rows := make([]witnessRow, 0, k)
		for i := 0; i < k; i++ {
			rows = append(rows, witnessRow{
				DigitSum: sc[i].ds,
				Index:    sc[i].idx,
				LaneID:   lid,
				Reading:  sc[i].val,
			})
		}
		blocks = append(blocks, laneWitnessBlock{LaneID: lid, Witnesses: rows})
	}

	merged := []witnessRow{}
	for _, b := range blocks {
		merged = append(merged, b.Witnesses...)
	}
	sort.SliceStable(merged, func(i, j int) bool {
		if merged[i].DigitSum != merged[j].DigitSum {
			return merged[i].DigitSum > merged[j].DigitSum
		}
		if merged[i].Reading != merged[j].Reading {
			return merged[i].Reading > merged[j].Reading
		}
		if merged[i].LaneID != merged[j].LaneID {
			return merged[i].LaneID < merged[j].LaneID
		}
		return merged[i].Index < merged[j].Index
	})

	trail := incidentTrail{Applied: applied, Ignored: ignored}
	summary := summaryOut{
		AppliedIncidents:       len(applied),
		CurrentDayUsed:         pool.CurrentDay,
		IgnoredIncidents:       ignored,
		IncidentDayFloorUsed:   floorDay,
		MergedWitnessCount:     len(merged),
		RadixFinal:             radix,
		SuppressedLaneCount:    len(suppressed),
		TotalReadings:          totalReadings,
	}

	writeFile(filepath.Join(auditRoot, "lane_witnesses.json"), canonicalMarshal(laneWitnessOut{Lanes: blocks}))
	writeFile(filepath.Join(auditRoot, "merged_rank.json"), canonicalMarshal(mergedRankOut{Witnesses: merged}))
	writeFile(filepath.Join(auditRoot, "incident_trail.json"), canonicalMarshal(trail))
	writeFile(filepath.Join(auditRoot, "summary.json"), canonicalMarshal(summary))

	fmt.Fprintln(os.Stderr, "digit-witness-rank audit complete")
}
