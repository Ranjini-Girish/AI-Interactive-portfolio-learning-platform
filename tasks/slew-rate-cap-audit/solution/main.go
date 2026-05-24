package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
)

type policy struct {
	SlewCapMilli   int    `json:"slew_cap_milli"`
	MergeByTag     bool   `json:"merge_by_tag"`
	TieBreakDupT   string `json:"tie_break_dup_t"`
}

type poolState struct {
	CurrentT int `json:"current_t"`
}

type incidentEvent map[string]any

type incidentLog struct {
	Events []incidentEvent `json:"events"`
}

type channelFile struct {
	ChannelID string `json:"channel_id"`
	Tag       string `json:"tag"`
	Points    []struct {
		T int `json:"t"`
		V int `json:"v"`
	} `json:"points"`
}

type pt struct {
	T         int
	V         int
	ChannelID string
	Base      string
}

type seriesOut struct {
	Breach       bool   `json:"breach"`
	ID           string `json:"id"`
	MaxSlewMilli int    `json:"max_slew_milli"`
	Points       int    `json:"points"`
}

type report struct {
	Channels []seriesOut    `json:"channels"`
	Summary  map[string]int `json:"summary"`
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
		ai, _ := intFromAny(out[i]["apply_t"])
		aj, _ := intFromAny(out[j]["apply_t"])
		if ai != aj {
			return ai < aj
		}
		si, _ := strFromAny(out[i]["event_id"])
		sj, _ := strFromAny(out[j]["event_id"])
		return si < sj
	})
	return out
}

var chFileRe = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]*\.json$`)

func main() {
	dataRoot := os.Getenv("SRL_DATA_DIR")
	if dataRoot == "" {
		dataRoot = "/app/srl_lab"
	}
	auditRoot := os.Getenv("SRL_AUDIT_DIR")
	if auditRoot == "" {
		auditRoot = "/app/srl_audit"
	}

	var pol policy
	mustReadJSON(filepath.Join(dataRoot, "policy.json"), &pol)
	var pool poolState
	mustReadJSON(filepath.Join(dataRoot, "pool_state.json"), &pool)
	var log incidentLog
	mustReadJSON(filepath.Join(dataRoot, "incident_log.json"), &log)

	matches, err := filepath.Glob(filepath.Join(dataRoot, "channels", "*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(matches)
	var paths []string
	for _, p := range matches {
		base := filepath.Base(p)
		if chFileRe.MatchString(base) {
			paths = append(paths, p)
		}
	}

	type loadedCh struct {
		Path string
		Data channelFile
	}
	var loaded []loadedCh
	for _, p := range paths {
		var cf channelFile
		mustReadJSON(p, &cf)
		loaded = append(loaded, loadedCh{Path: p, Data: cf})
	}

	byID := map[string][]pt{}
	for _, lc := range loaded {
		cid := lc.Data.ChannelID
		base := filepath.Base(lc.Path)
		for _, q := range lc.Data.Points {
			byID[cid] = append(byID[cid], pt{T: q.T, V: q.V, ChannelID: cid, Base: base})
		}
	}

	eventsSeen := 0
	unknownKinds := 0
	sorted := sortEvents(log.Events)
	for _, ev := range sorted {
		eventsSeen++
		at, ok := intFromAny(ev["apply_t"])
		if !ok || at > pool.CurrentT {
			continue
		}
		kind, _ := strFromAny(ev["kind"])
		switch kind {
		case "zero_window":
			cid, ok := strFromAny(ev["channel_id"])
			if !ok {
				continue
			}
			st, ok1 := intFromAny(ev["start_t"])
			en, ok2 := intFromAny(ev["end_t"])
			if !ok1 || !ok2 || st > en {
				continue
			}
			arr := byID[cid]
			for i := range arr {
				if arr[i].T >= st && arr[i].T <= en {
					arr[i].V = 0
				}
			}
			byID[cid] = arr
		case "noop":
		default:
			unknownKinds++
		}
	}

	type tagGroup struct {
		Tag string
		Pts []pt
		IDs []string
	}
	tagTo := map[string]*tagGroup{}
	var orderedTags []string
	addTag := func(tag string) *tagGroup {
		g := tagTo[tag]
		if g == nil {
			g = &tagGroup{Tag: tag}
			tagTo[tag] = g
			orderedTags = append(orderedTags, tag)
		}
		return g
	}
	for _, lc := range loaded {
		cid := lc.Data.ChannelID
		tag := lc.Data.Tag
		g := addTag(tag)
		g.Pts = append(g.Pts, byID[cid]...)
		g.IDs = append(g.IDs, cid)
	}
	sort.Strings(orderedTags)

	uniqSorted := func(ids []string) []string {
		m := map[string]struct{}{}
		for _, id := range ids {
			m[id] = struct{}{}
		}
		out := make([]string, 0, len(m))
		for id := range m {
			out = append(out, id)
		}
		sort.Strings(out)
		return out
	}

	mergeID := func(ids []string) string {
		u := uniqSorted(ids)
		if len(u) == 1 {
			return u[0]
		}
		out := ""
		for i, id := range u {
			if i > 0 {
				out += "+"
			}
			out += id
		}
		return out
	}

	var series []seriesOut
	if !pol.MergeByTag {
		for _, lc := range loaded {
			cid := lc.Data.ChannelID
			pts := byID[cid]
			series = append(series, buildSeries(cid, pts, pol))
		}
		sort.Slice(series, func(i, j int) bool { return series[i].ID < series[j].ID })
	} else {
		for _, tag := range orderedTags {
			g := tagTo[tag]
			id := mergeID(g.IDs)
			series = append(series, buildSeries(id, collapseMerged(g.Pts, pol), pol))
		}
		sort.Slice(series, func(i, j int) bool { return series[i].ID < series[j].ID })
	}

	breach := 0
	maxAll := 0
	for _, s := range series {
		if s.Breach {
			breach++
		}
		if s.MaxSlewMilli > maxAll {
			maxAll = s.MaxSlewMilli
		}
	}

	rep := report{
		Summary: map[string]int{
			"breach_count":          breach,
			"channels_considered":   len(series),
			"events_seen":           eventsSeen,
			"max_overall_milli":     maxAll,
			"unknown_event_kinds":   unknownKinds,
		},
		Channels: series,
	}
	writeFile(filepath.Join(auditRoot, "report.json"), canonicalJSON(rep))
}

func collapseMerged(in []pt, pol policy) []pt {
	sort.SliceStable(in, func(i, j int) bool {
		if in[i].T != in[j].T {
			return in[i].T < in[j].T
		}
		if in[i].ChannelID != in[j].ChannelID {
			return in[i].ChannelID < in[j].ChannelID
		}
		return in[i].Base < in[j].Base
	})
	if len(in) == 0 {
		return nil
	}
	out := []pt{in[0]}
	for k := 1; k < len(in); k++ {
		prev := &out[len(out)-1]
		cur := in[k]
		if cur.T == prev.T {
			if pol.TieBreakDupT == "max_v" {
				if cur.V > prev.V {
					prev.V = cur.V
				}
			} else {
				if cur.V < prev.V {
					prev.V = cur.V
				}
			}
			continue
		}
		out = append(out, cur)
	}
	return out
}

func buildSeries(id string, pts []pt, pol policy) seriesOut {
	if len(pts) == 0 {
		return seriesOut{ID: id, MaxSlewMilli: 0, Points: 0, Breach: false}
	}
	sort.SliceStable(pts, func(i, j int) bool { return pts[i].T < pts[j].T })
	maxS := 0
	for i := 1; i < len(pts); i++ {
		dt := pts[i].T - pts[i-1].T
		if dt <= 0 {
			panic(fmt.Sprintf("non-increasing t in series %s", id))
		}
		num := absInt(pts[i].V-pts[i-1].V) * 1000
		slew := num / dt
		if slew > maxS {
			maxS = slew
		}
	}
	breach := maxS > pol.SlewCapMilli
	return seriesOut{ID: id, MaxSlewMilli: maxS, Points: len(pts), Breach: breach}
}

func absInt(v int) int {
	if v < 0 {
		return -v
	}
	return v
}
