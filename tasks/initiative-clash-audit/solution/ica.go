package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
)

type policyFile struct {
	BandRules    []struct {
		Band        int `json:"band"`
		MinPriority int `json:"min_priority"`
	} `json:"band_rules"`
	CurrentDay   int            `json:"current_day"`
	FactionFavor map[string]int `json:"faction_favor"`
	StanceDelta  map[string]int `json:"stance_delta"`
	StimDelta    int            `json:"stim_delta"`
}

type incidentFile struct {
	Events []struct {
		Day    int    `json:"day"`
		Kind   string `json:"kind"`
		UnitID string `json:"unit_id"`
	} `json:"events"`
}

type overclockFile struct {
	Units []string `json:"units"`
}

type unitFile struct {
	BasePriority int    `json:"base_priority"`
	Escort       string `json:"escort"`
	Faction      string `json:"faction"`
	Stance       string `json:"stance"`
	UnitID       string `json:"unit_id"`
}

type loadoutFile struct {
	TieToken int `json:"tie_token"`
}

type unitState struct {
	UnitID      string
	BaseScore   int
	Priority    int
	Intrinsic   int
	Final       int
	Tie         int
	Faction     string
	Escort      string
	Jammed      bool
	EchoSunk    bool
	Throttled   bool
	Overclocked bool
}

func readJSON(path string, dst any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, dst); err != nil {
		panic(fmt.Sprintf("%s: %v", path, err))
	}
}

func maxBand(rules []struct {
	Band        int `json:"band"`
	MinPriority int `json:"min_priority"`
}) int {
	m := 0
	for _, r := range rules {
		if r.Band > m {
			m = r.Band
		}
	}
	return m
}

func intrinsicBand(score int, rules []struct {
	Band        int `json:"band"`
	MinPriority int `json:"min_priority"`
}) int {
	cp := append([]struct {
		Band        int `json:"band"`
		MinPriority int `json:"min_priority"`
	}{}, rules...)
	sort.Slice(cp, func(i, j int) bool {
		return cp[i].MinPriority > cp[j].MinPriority
	})
	for _, r := range cp {
		if score >= r.MinPriority {
			return r.Band
		}
	}
	return cp[len(cp)-1].Band
}

func stanceDelta(m map[string]int, stance string) int {
	if m == nil {
		return 0
	}
	if v, ok := m[stance]; ok {
		return v
	}
	return m["neutral"]
}

func applyEscortAnchoring(states []unitState) {
	byID := map[string]*unitState{}
	for i := range states {
		byID[states[i].UnitID] = &states[i]
	}
	for {
		changed := false
		for i := range states {
			escort := states[i].Escort
			if escort == "" {
				continue
			}
			target, ok := byID[escort]
			if !ok {
				continue
			}
			if states[i].Final < target.Final {
				states[i].Final = target.Final
				changed = true
			}
		}
		if !changed {
			break
		}
	}
	// Close directed cycles: every member adopts the component maximum.
	visited := map[string]bool{}
	for start := range byID {
		if visited[start] {
			continue
		}
		path := []string{}
		index := map[string]int{}
		cur := start
		for {
			if pos, onPath := index[cur]; onPath {
				cycle := path[pos:]
				maxF := 0
				for _, id := range cycle {
					if byID[id].Final > maxF {
						maxF = byID[id].Final
					}
				}
				for _, id := range cycle {
					if byID[id].Final < maxF {
						byID[id].Final = maxF
					}
				}
				break
			}
			if visited[cur] {
				break
			}
			index[cur] = len(path)
			path = append(path, cur)
			next := byID[cur].Escort
			if next == "" || byID[next] == nil {
				break
			}
			cur = next
		}
		for _, id := range path {
			visited[id] = true
		}
	}
}

func computeEchoSunk(states []unitState) {
	for i := range states {
		if states[i].Jammed {
			continue
		}
		for _, other := range states {
			if other.UnitID == states[i].UnitID {
				continue
			}
			if other.Jammed && other.Faction == states[i].Faction && other.Intrinsic == states[i].Intrinsic {
				states[i].EchoSunk = true
				break
			}
		}
	}
}

func writeCanonical(w *bytes.Buffer, v any, indent int) {
	sp := bytes.Repeat([]byte(" "), indent)
	switch t := v.(type) {
	case nil:
		w.WriteString("null")
	case bool:
		if t {
			w.WriteString("true")
		} else {
			w.WriteString("false")
		}
	case int:
		w.WriteString(strconv.Itoa(t))
	case string:
		w.WriteString(jsonString(t))
	case []any:
		if len(t) == 0 {
			w.WriteString("[]")
			return
		}
		w.WriteString("[\n")
		for i, it := range t {
			w.Write(sp)
			w.WriteString("  ")
			writeCanonical(w, it, indent+2)
			if i+1 < len(t) {
				w.WriteString(",\n")
			} else {
				w.WriteByte('\n')
			}
		}
		w.Write(sp)
		w.WriteByte(']')
	case map[string]any:
		if len(t) == 0 {
			w.WriteString("{}")
			return
		}
		keys := make([]string, 0, len(t))
		for k := range t {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		w.WriteString("{\n")
		for i, k := range keys {
			w.Write(sp)
			w.WriteString("  ")
			w.WriteString(jsonString(k))
			w.WriteString(": ")
			writeCanonical(w, t[k], indent+2)
			if i+1 < len(keys) {
				w.WriteString(",\n")
			} else {
				w.WriteByte('\n')
			}
		}
		w.Write(sp)
		w.WriteByte('}')
	default:
		panic(fmt.Sprintf("unsupported type %T", v))
	}
}

func jsonString(s string) string {
	var b bytes.Buffer
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		default:
			if r < 0x20 {
				b.WriteString(fmt.Sprintf(`\u%04x`, r))
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
	return b.String()
}

func writeJSONFile(path string, root map[string]any) {
	var buf bytes.Buffer
	writeCanonical(&buf, root, 0)
	buf.WriteByte('\n')
	if err := os.WriteFile(path, buf.Bytes(), 0o644); err != nil {
		panic(err)
	}
}

func main() {
	dataDir := os.Getenv("ICA_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/init_clash"
	}
	auditDir := os.Getenv("ICA_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		panic(err)
	}

	var pol policyFile
	readJSON(filepath.Join(dataDir, "policy.json"), &pol)

	var inc incidentFile
	readJSON(filepath.Join(dataDir, "incidents.json"), &inc)

	var oc overclockFile
	readJSON(filepath.Join(dataDir, "overclock.json"), &oc)
	ocSet := map[string]struct{}{}
	for _, id := range oc.Units {
		ocSet[id] = struct{}{}
	}

	unitPaths, err := filepath.Glob(filepath.Join(dataDir, "units", "*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(unitPaths)

	worst := maxBand(pol.BandRules)

	states := make([]unitState, 0, len(unitPaths))
	for _, p := range unitPaths {
		var uf unitFile
		readJSON(p, &uf)
		var lf loadoutFile
		readJSON(filepath.Join(dataDir, "loadouts", uf.UnitID+".json"), &lf)

		bonus := 0
		if pol.FactionFavor != nil {
			if v, ok := pol.FactionFavor[uf.Faction]; ok {
				bonus = v
			}
		}
		base := uf.BasePriority + stanceDelta(pol.StanceDelta, uf.Stance) + bonus

		stimmed := false
		th := false
		jm := false
		for _, ev := range inc.Events {
			if ev.UnitID != uf.UnitID || ev.Day != pol.CurrentDay {
				continue
			}
			switch ev.Kind {
			case "stim":
				stimmed = true
			case "thermal_throttle":
				th = true
			case "jam":
				jm = true
			}
		}

		score := base
		if stimmed {
			score += pol.StimDelta
		}
		intr := intrinsicBand(score, pol.BandRules)

		_, over := ocSet[uf.UnitID]

		final := intr
		if th {
			final = intr + 1
			if final > worst {
				final = worst
			}
		} else if over {
			final = intr - 1
			if final < 0 {
				final = 0
			}
		}

		overclocked := over && !th && final != intr

		escort := uf.Escort
		if escort == uf.UnitID {
			escort = ""
		}

		states = append(states, unitState{
			UnitID:      uf.UnitID,
			BaseScore:   base,
			Priority:    score,
			Intrinsic:   intr,
			Final:       final,
			Tie:         lf.TieToken,
			Faction:     uf.Faction,
			Escort:      escort,
			Jammed:      jm,
			Throttled:   th,
			Overclocked: overclocked,
		})
	}

	applyEscortAnchoring(states)
	computeEchoSunk(states)

	rosterMaxFinal := 0
	for _, s := range states {
		if s.Final > rosterMaxFinal {
			rosterMaxFinal = s.Final
		}
	}

	sort.SliceStable(states, func(i, j int) bool {
		a, b := states[i], states[j]
		if a.Final != b.Final {
			return a.Final < b.Final
		}
		if a.Final == rosterMaxFinal {
			if a.Priority != b.Priority {
				return a.Priority < b.Priority
			}
		} else if a.Priority != b.Priority {
			return a.Priority > b.Priority
		}
		if a.UnitID != b.UnitID {
			return a.UnitID < b.UnitID
		}
		return a.Tie < b.Tie
	})

	bandOrder := make([]int, 0)
	seenBand := map[int]struct{}{}
	for _, s := range states {
		if _, ok := seenBand[s.Final]; ok {
			continue
		}
		seenBand[s.Final] = struct{}{}
		bandOrder = append(bandOrder, s.Final)
	}

	var ordered []unitState
	for _, fb := range bandOrder {
		var chunk []unitState
		for _, s := range states {
			if s.Final == fb {
				chunk = append(chunk, s)
			}
		}
		var lead, echo, jam []unitState
		for _, s := range chunk {
			switch {
			case s.Jammed:
				jam = append(jam, s)
			case s.EchoSunk:
				echo = append(echo, s)
			default:
				lead = append(lead, s)
			}
		}
		ordered = append(ordered, append(append(lead, echo...), jam...)...)
	}

	type clash struct {
		Intrinsic int
		A         string
		B         string
		Score     int
	}
	var clashes []clash
	byID := map[string]unitState{}
	for _, s := range states {
		byID[s.UnitID] = s
	}
	ids := make([]string, 0, len(byID))
	for id := range byID {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for i := 0; i < len(ids); i++ {
		for j := i + 1; j < len(ids); j++ {
			a := byID[ids[i]]
			b := byID[ids[j]]
			if a.Throttled || b.Throttled {
				continue
			}
			if a.BaseScore == b.BaseScore && a.Intrinsic == b.Intrinsic {
				clashes = append(clashes, clash{
					Intrinsic: a.Intrinsic,
					A:         a.UnitID,
					B:         b.UnitID,
					Score:     a.BaseScore,
				})
			}
		}
	}
	sort.Slice(clashes, func(i, j int) bool {
		ci, cj := clashes[i], clashes[j]
		if ci.A != cj.A {
			return ci.A < cj.A
		}
		if ci.B != cj.B {
			return ci.B < cj.B
		}
		if ci.Score != cj.Score {
			return ci.Score < cj.Score
		}
		return ci.Intrinsic < cj.Intrinsic
	})

	clashObjs := make([]any, 0, len(clashes))
	for _, c := range clashes {
		clashObjs = append(clashObjs, map[string]any{
			"intrinsic_band":        c.Intrinsic,
			"members":               []any{c.A, c.B},
			"shared_priority_score": c.Score,
		})
	}

	orderedIDs := make([]any, 0, len(ordered))
	perUnit := map[string]any{}
	echoCount := 0
	for _, s := range ordered {
		orderedIDs = append(orderedIDs, s.UnitID)
		if s.EchoSunk {
			echoCount++
		}
		perUnit[s.UnitID] = map[string]any{
			"echo_sunk":      s.EchoSunk,
			"final_band":     s.Final,
			"intrinsic_band": s.Intrinsic,
			"jammed":         s.Jammed,
			"overclocked":    s.Overclocked,
			"priority_score": s.Priority,
			"throttled":      s.Throttled,
		}
	}

	turnRoot := map[string]any{
		"ordered_unit_ids": orderedIDs,
		"per_unit":         perUnit,
	}

	clashesRoot := map[string]any{
		"clashes": clashObjs,
	}

	bandCounts := map[string]int{}
	delayed := 0
	degraded := 0
	ready := 0
	for _, s := range ordered {
		key := strconv.Itoa(s.Final)
		bandCounts[key]++
		if s.Throttled {
			degraded++
		} else if s.Jammed {
			delayed++
		} else {
			ready++
		}
	}
	bcAny := map[string]any{}
	for k, v := range bandCounts {
		bcAny[k] = v
	}

	summaryRoot := map[string]any{
		"band_counts":     bcAny,
		"clash_count":     len(clashes),
		"current_day":     pol.CurrentDay,
		"echo_sink_count": echoCount,
		"status_counts":   map[string]any{"degraded": degraded, "delayed": delayed, "ready": ready},
		"total_units":     len(ordered),
	}

	writeJSONFile(filepath.Join(auditDir, "turn_order.json"), turnRoot)
	writeJSONFile(filepath.Join(auditDir, "clashes.json"), clashesRoot)
	writeJSONFile(filepath.Join(auditDir, "summary.json"), summaryRoot)
}
