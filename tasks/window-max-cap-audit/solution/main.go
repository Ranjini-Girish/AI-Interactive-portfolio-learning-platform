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
	Parts []string `json:"parts"`
}

type policy struct {
	Cap    int `json:"cap"`
	Window int `json:"window"`
}

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type partFile struct {
	PartID string `json:"part_id"`
	Values []int  `json:"values"`
}

type traceRow struct {
	Capped int `json:"capped"`
	RawMax int `json:"raw_max"`
	Start  int `json:"start"`
}

type traceOut struct {
	Windows []traceRow `json:"windows"`
}

type dilatedSeries struct {
	Values []int `json:"values"`
}

type incidentTrail struct {
	Applied []map[string]any `json:"applied"`
	Ignored int              `json:"ignored"`
}

type summaryOut struct {
	AppliedIncidents      int `json:"applied_incidents"`
	CapFinal              int `json:"cap_final"`
	CurrentDayUsed        int `json:"current_day_used"`
	IgnoredIncidents      int `json:"ignored_incidents"`
	IncidentDayFloorUsed  int `json:"incident_day_floor_used"`
	OutputLen             int `json:"output_len"`
	TotalInputLen         int `json:"total_input_len"`
	WindowUsed            int `json:"window_used"`
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

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func main() {
	dataRoot := os.Getenv("WMC_DATA_DIR")
	if dataRoot == "" {
		dataRoot = "/app/wmc_lab"
	}
	auditRoot := os.Getenv("WMC_AUDIT_DIR")
	if auditRoot == "" {
		auditRoot = "/app/wmc_audit"
	}

	var layout domainLayout
	mustReadJSON(filepath.Join(dataRoot, "domain_layout.json"), &layout)

	var pol policy
	mustReadJSON(filepath.Join(dataRoot, "policy.json"), &pol)
	cap := pol.Cap
	win := pol.Window
	if win < 1 {
		win = 1
	}

	var pool poolState
	mustReadJSON(filepath.Join(dataRoot, "pool_state.json"), &pool)

	var dayFloor struct {
		StartDay int `json:"start_day"`
	}
	mustReadJSON(filepath.Join(dataRoot, "anchors", "day_floor.json"), &dayFloor)
	floorDay := dayFloor.StartDay

	var log incidentLog
	mustReadJSON(filepath.Join(dataRoot, "incident_log.json"), &log)

	vals := []int{}
	for _, pid := range layout.Parts {
		var pf partFile
		mustReadJSON(filepath.Join(dataRoot, "parts", pid+".json"), &pf)
		vals = append(vals, pf.Values...)
	}

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
		case "bump_cap":
			vf, ok := ev["new_cap"].(float64)
			if !ok {
				ignored++
				continue
			}
			v := int(vf)
			if v < 0 {
				ignored++
				continue
			}
			cap = maxInt(cap, v)
			if sm, ok := sortKeysDeep(ev).(map[string]any); ok {
				applied = append(applied, sm)
			}
		case "zero_index":
			ixf, ok := ev["index"].(float64)
			if !ok {
				ignored++
				continue
			}
			ix := int(ixf)
			if ix < 0 || ix >= len(vals) {
				ignored++
				continue
			}
			vals[ix] = 0
			if sm, ok := sortKeysDeep(ev).(map[string]any); ok {
				applied = append(applied, sm)
			}
		default:
			ignored++
		}
	}

	outVals := []int{}
	windows := []traceRow{}
	n := len(vals)
	if n >= win {
		for start := 0; start <= n-win; start++ {
			raw := vals[start]
			for j := 1; j < win; j++ {
				raw = maxInt(raw, vals[start+j])
			}
			capped := raw
			if capped > cap {
				capped = cap
			}
			outVals = append(outVals, capped)
			windows = append(windows, traceRow{Start: start, RawMax: raw, Capped: capped})
		}
	}

	trail := incidentTrail{Applied: applied, Ignored: ignored}
	summary := summaryOut{
		AppliedIncidents:      len(applied),
		CapFinal:              cap,
		CurrentDayUsed:        pool.CurrentDay,
		IgnoredIncidents:      ignored,
		IncidentDayFloorUsed:  floorDay,
		OutputLen:             len(outVals),
		TotalInputLen:         n,
		WindowUsed:            win,
	}

	writeFile(filepath.Join(auditRoot, "dilated_series.json"), canonicalMarshal(dilatedSeries{Values: outVals}))
	writeFile(filepath.Join(auditRoot, "window_trace.json"), canonicalMarshal(traceOut{Windows: windows}))
	writeFile(filepath.Join(auditRoot, "incident_trail.json"), canonicalMarshal(trail))
	writeFile(filepath.Join(auditRoot, "summary.json"), canonicalMarshal(summary))

	fmt.Fprintln(os.Stderr, "window-max-cap audit complete")
}
