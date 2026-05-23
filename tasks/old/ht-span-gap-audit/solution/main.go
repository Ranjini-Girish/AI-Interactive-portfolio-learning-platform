package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
)

type policy struct {
	MergeGap int `json:"merge_gap"`
}

type poolState struct {
	CurrentTick int `json:"current_tick"`
}

type incidentEvent map[string]any

type incidentLog struct {
	Events []incidentEvent `json:"events"`
}

type laneFile struct {
	LaneID    string `json:"lane_id"`
	Intervals []struct {
		Lo int `json:"lo"`
		Hi int `json:"hi"`
	} `json:"intervals"`
}

type laneOut struct {
	CoveredTicks int    `json:"covered_ticks"`
	ID             string `json:"id"`
	MergedCount    int    `json:"merged_count"`
}

type report struct {
	Lanes   []laneOut      `json:"lanes"`
	Summary map[string]int `json:"summary"`
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

func canonicalJSON(v any) []byte {
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

func intFromAny(v any) (int, bool) {
	switch x := v.(type) {
	case float64:
		return int(x), true
	case json.Number:
		i, err := strconv.Atoi(string(x))
		return i, err == nil
	case string:
		i, err := strconv.Atoi(x)
		return i, err == nil
	default:
		return 0, false
	}
}

func strFromAny(v any) (string, bool) {
	s, ok := v.(string)
	return s, ok
}

func sortEvents(ev []incidentEvent) []incidentEvent {
	out := append([]incidentEvent(nil), ev...)
	sort.SliceStable(out, func(i, j int) bool {
		ai, _ := intFromAny(out[i]["apply_tick"])
		aj, _ := intFromAny(out[j]["apply_tick"])
		if ai != aj {
			return ai < aj
		}
		si, _ := strFromAny(out[i]["event_id"])
		sj, _ := strFromAny(out[j]["event_id"])
		return si < sj
	})
	return out
}

var laneFileRe = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]*\.json$`)

func mergeIntervals(raw [][2]int, gap int) [][2]int {
	if len(raw) == 0 {
		return nil
	}
	sort.SliceStable(raw, func(i, j int) bool {
		if raw[i][0] != raw[j][0] {
			return raw[i][0] < raw[j][0]
		}
		return raw[i][1] < raw[j][1]
	})
	out := [][2]int{raw[0]}
	for k := 1; k < len(raw); k++ {
		top := &out[len(out)-1]
		cur := raw[k]
		if cur[0]-(*top)[1] <= gap {
			if cur[1] > (*top)[1] {
				(*top)[1] = cur[1]
			}
		} else {
			out = append(out, cur)
		}
	}
	return out
}

func main() {
	dataRoot := os.Getenv("HSG_DATA_DIR")
	if dataRoot == "" {
		dataRoot = "/app/hsg_lab"
	}
	auditRoot := os.Getenv("HSG_AUDIT_DIR")
	if auditRoot == "" {
		auditRoot = "/app/hsg_audit"
	}

	var pol policy
	mustReadJSON(filepath.Join(dataRoot, "policy.json"), &pol)
	var pool poolState
	mustReadJSON(filepath.Join(dataRoot, "pool_state.json"), &pool)
	var log incidentLog
	mustReadJSON(filepath.Join(dataRoot, "incident_log.json"), &log)

	matches, err := filepath.Glob(filepath.Join(dataRoot, "lanes", "*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(matches)
	var paths []string
	for _, p := range matches {
		if laneFileRe.MatchString(filepath.Base(p)) {
			paths = append(paths, p)
		}
	}

	type loadedLane struct {
		Path string
		Data laneFile
	}
	var loaded []loadedLane
	for _, p := range paths {
		var lf laneFile
		mustReadJSON(p, &lf)
		loaded = append(loaded, loadedLane{Path: p, Data: lf})
	}

	intervalsByLane := map[string][][2]int{}
	for _, lc := range loaded {
		id := lc.Data.LaneID
		for _, it := range lc.Data.Intervals {
			intervalsByLane[id] = append(intervalsByLane[id], [2]int{it.Lo, it.Hi})
		}
	}

	sorted := sortEvents(log.Events)
	eventsSeen := len(sorted)
	unknown := 0
	for _, ev := range sorted {
		at, ok := intFromAny(ev["apply_tick"])
		if !ok || at > pool.CurrentTick {
			continue
		}
		kind, _ := strFromAny(ev["kind"])
		switch kind {
		case "noop":
		case "drop_tick":
			lid, ok := strFromAny(ev["lane_id"])
			if !ok {
				continue
			}
			tk, ok := intFromAny(ev["tick"])
			if !ok {
				continue
			}
			arr := intervalsByLane[lid]
			if len(arr) == 0 {
				continue
			}
			nw := make([][2]int, 0, len(arr))
			for _, seg := range arr {
				if seg[0] <= tk && tk < seg[1] {
					continue
				}
				nw = append(nw, seg)
			}
			intervalsByLane[lid] = nw
		default:
			unknown++
		}
	}

	var lanes []laneOut
	for _, lc := range loaded {
		id := lc.Data.LaneID
		raw := intervalsByLane[id]
		merged := mergeIntervals(raw, pol.MergeGap)
		covered := 0
		for _, m := range merged {
			covered += m[1] - m[0]
		}
		lanes = append(lanes, laneOut{
			CoveredTicks: covered,
			ID:             id,
			MergedCount:    len(merged),
		})
	}
	sort.Slice(lanes, func(i, j int) bool { return lanes[i].ID < lanes[j].ID })

	total := 0
	for _, ln := range lanes {
		total += ln.CoveredTicks
	}

	rep := report{
		Lanes: lanes,
		Summary: map[string]int{
			"covered_ticks_total":   total,
			"events_seen":           eventsSeen,
			"lanes_considered":      len(lanes),
			"unknown_event_kinds":   unknown,
		},
	}
	writeFile(filepath.Join(auditRoot, "report.json"), canonicalJSON(rep))
}
