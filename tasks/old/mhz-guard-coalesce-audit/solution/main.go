package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type policyFile struct {
	MergeGapMHz  int  `json:"merge_gap_mhz"`
	HeatFloor    int  `json:"heat_floor"`
	HotOnlyMerge bool `json:"hot_only_merge"`
}

type poolFile struct {
	SnapshotDay int `json:"snapshot_day"`
}

type incident struct {
	EventID    string `json:"event_id"`
	Day        int    `json:"day"`
	Kind       string `json:"kind"`
	BinID      string `json:"bin_id,omitempty"`
	Delta      int    `json:"delta,omitempty"`
	FloorDelta int    `json:"floor_delta,omitempty"`
}

type bin struct {
	ID         string `json:"id"`
	LoMHz      int    `json:"lo_mhz"`
	HiMHz      int    `json:"hi_mhz"`
	Tier       string `json:"tier"`
	Occupancy  int    `json:"occupancy"`
}

func getenv(key, def string) string {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return def
	}
	return v
}

func readJSON(path string, out any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, out)
}

func writeFile(path string, data []byte) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func marshalCanonical(v any) ([]byte, error) {
	var buf strings.Builder
	if err := writeCanon(&buf, v); err != nil {
		return nil, err
	}
	s := buf.String()
	return []byte(s + "\n"), nil
}

func writeCanon(w *strings.Builder, v any) error {
	switch t := v.(type) {
	case nil:
		w.WriteString("null")
	case bool:
		if t {
			w.WriteString("true")
		} else {
			w.WriteString("false")
		}
	case float64:
		w.WriteString(strconv.FormatFloat(t, 'f', -1, 64))
	case int:
		w.WriteString(strconv.Itoa(t))
	case int64:
		w.WriteString(strconv.FormatInt(t, 10))
	case string:
		w.WriteString(jsonString(t))
	case []string:
		w.WriteByte('[')
		for i, e := range t {
			if i > 0 {
				w.WriteByte(',')
			}
			w.WriteString(jsonString(e))
		}
		w.WriteByte(']')
	case []map[string]any:
		w.WriteByte('[')
		for i, e := range t {
			if i > 0 {
				w.WriteByte(',')
			}
			mv := make(map[string]any, len(e))
			for k, v := range e {
				mv[k] = v
			}
			if err := writeCanon(w, mv); err != nil {
				return err
			}
		}
		w.WriteByte(']')
	case []any:
		w.WriteByte('[')
		for i, e := range t {
			if i > 0 {
				w.WriteByte(',')
			}
			if err := writeCanon(w, e); err != nil {
				return err
			}
		}
		w.WriteByte(']')
	case map[string]any:
		keys := make([]string, 0, len(t))
		for k := range t {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		w.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				w.WriteByte(',')
			}
			w.WriteString(jsonString(k))
			w.WriteByte(':')
			if err := writeCanon(w, t[k]); err != nil {
				return err
			}
		}
		w.WriteByte('}')
	default:
		return fmt.Errorf("unsupported type %T", v)
	}
	return nil
}

func jsonString(s string) string {
	b, err := json.Marshal(s)
	if err != nil {
		return "\"\""
	}
	return string(b)
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func gapBetween(left, right *bin) int {
	if right.LoMHz < left.HiMHz {
		return 0
	}
	return right.LoMHz - left.HiMHz
}

func canMerge(left, right *bin, gapMax int, hotOnly bool, heatFloor int) bool {
	if left.Tier != right.Tier {
		return false
	}
	g := gapBetween(left, right)
	if g > gapMax {
		return false
	}
	if hotOnly {
		if left.Occupancy < heatFloor || right.Occupancy < heatFloor {
			return false
		}
	}
	return true
}

func mergeBins(left, right bin) bin {
	parts := append(strings.Split(left.ID, "+"), strings.Split(right.ID, "+")...)
	sort.Strings(parts)
	joined := strings.Join(parts, "+")
	return bin{
		ID:        joined,
		LoMHz:     min(left.LoMHz, right.LoMHz),
		HiMHz:     max(left.HiMHz, right.HiMHz),
		Tier:      left.Tier,
		Occupancy: min(left.Occupancy, right.Occupancy),
	}
}

func main() {
	dataRoot := getenv("SGA_DATA_DIR", "/app/sga_data")
	outRoot := getenv("SGA_AUDIT_DIR", "/app/sga_audit")
	if err := os.MkdirAll(outRoot, 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "mkdir audit: %v\n", err)
		os.Exit(1)
	}

	var pol policyFile
	if err := readJSON(filepath.Join(dataRoot, "policy.json"), &pol); err != nil {
		fmt.Fprintf(os.Stderr, "policy: %v\n", err)
		os.Exit(1)
	}
	var pool poolFile
	if err := readJSON(filepath.Join(dataRoot, "pool_state.json"), &pool); err != nil {
		fmt.Fprintf(os.Stderr, "pool: %v\n", err)
		os.Exit(1)
	}
	var incidents []incident
	if err := readJSON(filepath.Join(dataRoot, "incident_log.json"), &incidents); err != nil {
		fmt.Fprintf(os.Stderr, "incidents: %v\n", err)
		os.Exit(1)
	}

	gapMax := pol.MergeGapMHz
	heatFloor := pol.HeatFloor
	hotOnly := pol.HotOnlyMerge

	binsDir := filepath.Join(dataRoot, "bins")
	ents, err := os.ReadDir(binsDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "bins: %v\n", err)
		os.Exit(1)
	}
	active := map[string]bin{}
	for _, e := range ents {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		var b bin
		if err := readJSON(filepath.Join(binsDir, e.Name()), &b); err != nil {
			fmt.Fprintf(os.Stderr, "bin %s: %v\n", e.Name(), err)
			os.Exit(1)
		}
		active[b.ID] = b
	}

	sort.Slice(incidents, func(i, j int) bool {
		if incidents[i].Day != incidents[j].Day {
			return incidents[i].Day < incidents[j].Day
		}
		return incidents[i].EventID < incidents[j].EventID
	})

	applied := []map[string]any{}
	ignored := 0
	for _, inc := range incidents {
		if inc.Day > pool.SnapshotDay {
			ignored++
			continue
		}
		switch inc.Kind {
		case "strip_bin":
			if _, ok := active[inc.BinID]; !ok {
				ignored++
				continue
			}
			delete(active, inc.BinID)
			applied = append(applied, map[string]any{
				"day":      inc.Day,
				"detail":   map[string]any{"bin_id": inc.BinID},
				"event_id": inc.EventID,
				"kind":     inc.Kind,
			})
		case "tighten_gap":
			gapMax = max(0, gapMax-inc.Delta)
			applied = append(applied, map[string]any{
				"day":      inc.Day,
				"detail":   map[string]any{"merge_gap_mhz": gapMax},
				"event_id": inc.EventID,
				"kind":     inc.Kind,
			})
		case "relax_heat":
			heatFloor = max(0, heatFloor-inc.FloorDelta)
			applied = append(applied, map[string]any{
				"day":      inc.Day,
				"detail":   map[string]any{"heat_floor": heatFloor},
				"event_id": inc.EventID,
				"kind":     inc.Kind,
			})
		default:
			ignored++
		}
	}

	list := make([]bin, 0, len(active))
	for _, b := range active {
		list = append(list, b)
	}
	sort.Slice(list, func(i, j int) bool {
		if list[i].LoMHz != list[j].LoMHz {
			return list[i].LoMHz < list[j].LoMHz
		}
		return list[i].ID < list[j].ID
	})

	changed := true
	for changed && len(list) > 0 {
		changed = false
		out := make([]bin, 0, len(list))
		i := 0
		for i < len(list) {
			cur := list[i]
			j := i + 1
			for j < len(list) {
				nxt := list[j]
				if canMerge(&cur, &nxt, gapMax, hotOnly, heatFloor) {
					cur = mergeBins(cur, nxt)
					j++
					changed = true
					continue
				}
				break
			}
			out = append(out, cur)
			i = j
		}
		list = out
	}

	segments := make([]map[string]any, 0, len(list))
	for _, s := range list {
		ids := strings.Split(s.ID, "+")
		sort.Strings(ids)
		width := s.HiMHz - s.LoMHz
		segments = append(segments, map[string]any{
			"bin_ids":   ids,
			"hi_mhz":    s.HiMHz,
			"lo_mhz":    s.LoMHz,
			"tier":      s.Tier,
			"width_mhz": width,
		})
	}

	sort.Slice(segments, func(i, j int) bool {
		li := segments[i]["lo_mhz"].(int)
		lj := segments[j]["lo_mhz"].(int)
		if li != lj {
			return li < lj
		}
		ti := segments[i]["tier"].(string)
		tj := segments[j]["tier"].(string)
		if ti != tj {
			return ti < tj
		}
		bi := strings.Join(segments[i]["bin_ids"].([]string), "+")
		bj := strings.Join(segments[j]["bin_ids"].([]string), "+")
		return bi < bj
	})

	tierMHz := map[string]int{}
	tierBins := map[string]int{}
	totalActive := 0
	for _, seg := range segments {
		t := seg["tier"].(string)
		w := seg["width_mhz"].(int)
		ids := seg["bin_ids"].([]string)
		tierMHz[t] += w
		tierBins[t] += len(ids)
		totalActive += len(ids)
	}

	tierNames := make([]string, 0, len(tierMHz))
	for k := range tierMHz {
		tierNames = append(tierNames, k)
	}
	sort.Strings(tierNames)
	tiers := make([]map[string]any, 0, len(tierNames))
	for _, t := range tierNames {
		tiers = append(tiers, map[string]any{
			"bins":     tierBins[t],
			"tier":     t,
			"width_mhz": tierMHz[t],
		})
	}

	summary := map[string]any{
		"applied_incidents": len(applied),
		"final_gap_mhz":     gapMax,
		"final_heat_floor":  heatFloor,
		"ignored_incidents": ignored,
		"segments":          len(segments),
		"snapshot_day":      pool.SnapshotDay,
		"total_active_bins": totalActive,
	}

	trail := map[string]any{
		"applied": applied,
		"ignored": ignored,
	}

	rootSeg := map[string]any{"segments": segments}

	files := map[string]any{
		"incident_trail.json": trail,
		"segments.json":     rootSeg,
		"summary.json":      summary,
		"tier_rollup.json":  map[string]any{"tiers": tiers},
	}

	for name, payload := range files {
		raw, err := marshalCanonical(payload)
		if err != nil {
			fmt.Fprintf(os.Stderr, "marshal %s: %v\n", name, err)
			os.Exit(1)
		}
		if err := writeFile(filepath.Join(outRoot, name), raw); err != nil {
			fmt.Fprintf(os.Stderr, "write %s: %v\n", name, err)
			os.Exit(1)
		}
	}
}
