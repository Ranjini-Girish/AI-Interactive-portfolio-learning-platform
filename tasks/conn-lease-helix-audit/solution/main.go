package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type policy struct {
	IdleTimeoutMs int            `json:"idle_timeout_ms"`
	MaxLeaseMs    int            `json:"max_lease_ms"`
	MaxSize       int            `json:"max_size"`
	MinSize       int            `json:"min_size"`
	SegmentFloors map[string]int `json:"segment_floors"`
}

type poolState struct {
	EvalTickMs int64 `json:"eval_tick_ms"`
}

type freezeFile struct {
	Windows []rawWindow `json:"windows"`
}

type rawWindow struct {
	EndTickMs   int64   `json:"end_tick_ms"`
	Scope       string  `json:"scope"`
	Segment     *string `json:"segment"`
	StartTickMs int64   `json:"start_tick_ms"`
	WrapperID   *string `json:"wrapper_id"`
}

type wrapperDoc struct {
	CheckoutTickMs    any     `json:"checkout_tick_ms"`
	EnteredIdleTickMs any     `json:"entered_idle_tick_ms"`
	ParentWrapperID   *string `json:"parent_wrapper_id"`
	Phase             string  `json:"phase"`
	Segment           string  `json:"segment"`
	WrapperID         string  `json:"wrapper_id"`
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	dataDir := getenv("CLA_DATA_DIR", "/app/connhelix")
	auditDir := getenv("CLA_AUDIT_DIR", "/app/audit")
	if err := run(dataDir, auditDir); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
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
	if pol.MaxLeaseMs <= 0 || pol.MaxSize <= 0 || pol.IdleTimeoutMs < 0 || pol.MinSize < 0 {
		return fmt.Errorf("invalid policy bounds")
	}
	for seg, floor := range pol.SegmentFloors {
		if floor < 0 {
			return fmt.Errorf("invalid segment floor for %s", seg)
		}
	}

	frRaw, err := os.ReadFile(filepath.Join(dataDir, "freeze_windows.json"))
	if err != nil {
		return err
	}
	var fr freezeFile
	if err := json.Unmarshal(frRaw, &fr); err != nil {
		return err
	}

	wrappers, err := loadWrappers(filepath.Join(dataDir, "wrappers"))
	if err != nil {
		return err
	}
	sort.Slice(wrappers, func(i, j int) bool { return wrappers[i].WrapperID < wrappers[j].WrapperID })

	idIndex := map[string]int{}
	for i, w := range wrappers {
		if w.WrapperID == "" {
			return fmt.Errorf("empty wrapper_id")
		}
		if _, dup := idIndex[w.WrapperID]; dup {
			return fmt.Errorf("duplicate wrapper_id %s", w.WrapperID)
		}
		idIndex[w.WrapperID] = i
	}

	for _, w := range wrappers {
		switch w.Phase {
		case "leased":
			if _, ok := asInt64(w.CheckoutTickMs); !ok {
				return fmt.Errorf("wrapper %s leased without checkout_tick_ms", w.WrapperID)
			}
		case "idle":
			if _, ok := asInt64(w.EnteredIdleTickMs); !ok {
				return fmt.Errorf("wrapper %s idle without entered_idle_tick_ms", w.WrapperID)
			}
		default:
			return fmt.Errorf("unknown phase for %s", w.WrapperID)
		}
		if w.ParentWrapperID != nil {
			if _, ok := idIndex[*w.ParentWrapperID]; !ok {
				return fmt.Errorf("wrapper %s has unknown parent %s", w.WrapperID, *w.ParentWrapperID)
			}
		}
	}

	if err := detectParentCycles(wrappers, idIndex); err != nil {
		return err
	}

	renewals, ignoredRenewalIDs, err := loadAnchors(filepath.Join(dataDir, "anchors"), idIndex, wrappers)
	if err != nil {
		return err
	}

	T := ps.EvalTickMs
	verdict := make(map[string]string, len(wrappers))

	type leakInfo struct {
		id    string
		lease int64
	}
	var leaks []leakInfo
	leakSet := map[string]bool{}
	for _, w := range wrappers {
		if w.Phase != "leased" {
			continue
		}
		co, _ := asInt64(w.CheckoutTickMs)
		eff := co
		if r, ok := renewals[w.WrapperID]; ok && r > eff {
			eff = r
		}
		lease := T - eff
		if lease > int64(pol.MaxLeaseMs) {
			verdict[w.WrapperID] = "reclaimed_leak"
			leakSet[w.WrapperID] = true
			leaks = append(leaks, leakInfo{id: w.WrapperID, lease: lease})
		}
	}

	sort.Slice(leaks, func(i, j int) bool {
		if leaks[i].lease != leaks[j].lease {
			return leaks[i].lease > leaks[j].lease
		}
		return leaks[i].id < leaks[j].id
	})
	leakRank := map[string]int{}
	for i, lk := range leaks {
		leakRank[lk.id] = i
	}

	leakEvents := make([]map[string]any, 0, len(leaks))
	for _, lk := range leaks {
		leakEvents = append(leakEvents, map[string]any{
			"kind":       "leak_reclaim",
			"lease_ms":   lk.lease,
			"reason":     "lease_exceeded",
			"wrapper_id": lk.id,
		})
	}

	type cascadeInfo struct {
		id           string
		parentLeakID string
		depth        int
	}
	var cascades []cascadeInfo
	for _, w := range wrappers {
		if leakSet[w.WrapperID] {
			continue
		}
		anc := w.ParentWrapperID
		depth := 1
		for anc != nil {
			if leakSet[*anc] {
				cascades = append(cascades, cascadeInfo{id: w.WrapperID, parentLeakID: *anc, depth: depth})
				verdict[w.WrapperID] = "reclaimed_cascade"
				break
			}
			next := wrappers[idIndex[*anc]].ParentWrapperID
			if next == nil {
				break
			}
			anc = next
			depth++
		}
	}

	sort.Slice(cascades, func(i, j int) bool {
		ri, rj := leakRank[cascades[i].parentLeakID], leakRank[cascades[j].parentLeakID]
		if ri != rj {
			return ri < rj
		}
		if cascades[i].depth != cascades[j].depth {
			return cascades[i].depth < cascades[j].depth
		}
		return cascades[i].id < cascades[j].id
	})

	cascadeEvents := make([]map[string]any, 0, len(cascades))
	for _, c := range cascades {
		cascadeEvents = append(cascadeEvents, map[string]any{
			"depth":          c.depth,
			"kind":           "cascade_reclaim",
			"parent_leak_id": c.parentLeakID,
			"reason":         "parent_leaked",
			"wrapper_id":     c.id,
		})
	}

	leasedLive := 0
	idleLive := 0
	segmentLive := map[string]int{}
	for _, w := range wrappers {
		if verdict[w.WrapperID] == "reclaimed_leak" || verdict[w.WrapperID] == "reclaimed_cascade" {
			continue
		}
		segmentLive[w.Segment]++
		switch w.Phase {
		case "leased":
			leasedLive++
		case "idle":
			idleLive++
		}
	}

	type idleCand struct {
		w wrapperDoc
	}
	var cands []idleCand
	for _, w := range wrappers {
		if w.Phase != "idle" {
			continue
		}
		if v := verdict[w.WrapperID]; v == "reclaimed_leak" || v == "reclaimed_cascade" {
			continue
		}
		enter, _ := asInt64(w.EnteredIdleTickMs)
		idleMs := T - enter
		if idleMs > int64(pol.IdleTimeoutMs) {
			cands = append(cands, idleCand{w: w})
		}
	}
	sort.Slice(cands, func(i, j int) bool {
		ei, _ := asInt64(cands[i].w.EnteredIdleTickMs)
		ej, _ := asInt64(cands[j].w.EnteredIdleTickMs)
		if ei != ej {
			return ei < ej
		}
		return cands[i].w.WrapperID < cands[j].w.WrapperID
	})

	retainedGlobal := 0
	retainedSegment := 0
	idleEvents := make([]map[string]any, 0)
	for _, c := range cands {
		w := c.w
		enter, _ := asInt64(w.EnteredIdleTickMs)
		idleMs := T - enter
		if frozen(fr.Windows, w, T) {
			verdict[w.WrapperID] = "idle_preserved_freeze"
			continue
		}
		floor := pol.SegmentFloors[w.Segment]
		globalOK := int64(leasedLive+idleLive-1) >= int64(pol.MinSize)
		segmentOK := int64(segmentLive[w.Segment]-1) >= int64(floor)
		if globalOK && segmentOK {
			verdict[w.WrapperID] = "reclaimed_idle"
			idleLive--
			segmentLive[w.Segment]--
			idleEvents = append(idleEvents, map[string]any{
				"idle_ms":    idleMs,
				"kind":       "idle_reclaim",
				"reason":     "idle_timeout",
				"wrapper_id": w.WrapperID,
			})
			continue
		}
		verdict[w.WrapperID] = "idle_retained_cap"
		if !segmentOK {
			retainedSegment++
		} else {
			retainedGlobal++
		}
	}

	for _, w := range wrappers {
		if verdict[w.WrapperID] != "" {
			continue
		}
		if w.Phase == "leased" {
			verdict[w.WrapperID] = "healthy_leased"
		} else {
			verdict[w.WrapperID] = "healthy_idle"
		}
	}

	allEvents := make([]map[string]any, 0, len(leakEvents)+len(cascadeEvents)+len(idleEvents))
	allEvents = append(allEvents, leakEvents...)
	allEvents = append(allEvents, cascadeEvents...)
	allEvents = append(allEvents, idleEvents...)

	wv := make([]map[string]any, 0, len(wrappers))
	for _, w := range wrappers {
		wv = append(wv, map[string]any{
			"segment":    w.Segment,
			"verdict":    verdict[w.WrapperID],
			"wrapper_id": w.WrapperID,
		})
	}

	count := func(v string) int {
		n := 0
		for _, w := range wrappers {
			if verdict[w.WrapperID] == v {
				n++
			}
		}
		return n
	}

	segSet := map[string]struct{}{}
	for _, w := range wrappers {
		segSet[w.Segment] = struct{}{}
	}
	segList := make([]string, 0, len(segSet))
	for s := range segSet {
		segList = append(segList, s)
	}
	sort.Strings(segList)

	uniqSet := map[string]struct{}{}
	for _, w := range wrappers {
		uniqSet[verdict[w.WrapperID]] = struct{}{}
	}
	uniqList := make([]string, 0, len(uniqSet))
	for s := range uniqSet {
		uniqList = append(uniqList, s)
	}
	sort.Strings(uniqList)

	type echoWindow struct {
		end       int64
		scope     string
		segment   *string
		start     int64
		wrapperID *string
	}
	echo := make([]echoWindow, 0, len(fr.Windows))
	for _, w := range fr.Windows {
		ew := echoWindow{end: w.EndTickMs, scope: w.Scope, start: w.StartTickMs}
		if w.Scope == "segment" {
			ew.segment = w.Segment
		}
		if w.Scope == "wrapper" {
			ew.wrapperID = w.WrapperID
		}
		echo = append(echo, ew)
	}
	printStr := func(p *string) string {
		if p == nil {
			return "null"
		}
		return *p
	}
	sort.Slice(echo, func(i, j int) bool {
		if echo[i].start != echo[j].start {
			return echo[i].start < echo[j].start
		}
		if echo[i].end != echo[j].end {
			return echo[i].end < echo[j].end
		}
		if echo[i].scope != echo[j].scope {
			return echo[i].scope < echo[j].scope
		}
		si, sj := printStr(echo[i].segment), printStr(echo[j].segment)
		if si != sj {
			return si < sj
		}
		return printStr(echo[i].wrapperID) < printStr(echo[j].wrapperID)
	})
	echoOut := make([]map[string]any, 0, len(echo))
	for _, ew := range echo {
		row := map[string]any{
			"end_tick_ms":   ew.end,
			"scope":         ew.scope,
			"segment":       any(nil),
			"start_tick_ms": ew.start,
			"wrapper_id":    any(nil),
		}
		if ew.segment != nil {
			row["segment"] = *ew.segment
		}
		if ew.wrapperID != nil {
			row["wrapper_id"] = *ew.wrapperID
		}
		echoOut = append(echoOut, row)
	}

	counters := map[string]any{
		"cascade_reclaims":          count("reclaimed_cascade"),
		"eval_tick_ms":              T,
		"healthy_idle_remaining":    count("healthy_idle"),
		"healthy_leased_remaining":  count("healthy_leased"),
		"idle_evictions":            count("reclaimed_idle"),
		"idle_preserved_freeze":     count("idle_preserved_freeze"),
		"idle_retained_cap":         count("idle_retained_cap"),
		"idle_retained_cap_global":  retainedGlobal,
		"idle_retained_cap_segment": retainedSegment,
		"leak_reclaims":             count("reclaimed_leak"),
		"max_size":                  pol.MaxSize,
		"min_size":                  pol.MinSize,
		"wrappers_total":            len(wrappers),
	}

	summary := map[string]any{
		"eval_tick_ms":     T,
		"ignored_renewals": ignoredRenewalIDs,
		"segments":         segList,
		"unique_verdicts":  uniqList,
	}

	out := map[string]any{
		"freeze_echo.json":    map[string]any{"windows": echoOut},
		"pool_counters.json":  counters,
		"reclaim_events.json": map[string]any{"events": allEvents},
		"summary.json":        summary,
		"wrapper_verdicts.json": map[string]any{
			"eval_tick_ms": T,
			"wrappers":     wv,
		},
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	for name, payload := range out {
		if err := writeJSON(filepath.Join(auditDir, name), payload); err != nil {
			return err
		}
	}
	return nil
}

func writeJSON(path string, v any) error {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		return err
	}
	return os.WriteFile(path, buf.Bytes(), 0o644)
}

func loadWrappers(dir string) ([]wrapperDoc, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make([]wrapperDoc, 0)
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var w wrapperDoc
		if err := json.Unmarshal(b, &w); err != nil {
			return nil, err
		}
		out = append(out, w)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no wrappers")
	}
	return out, nil
}

func detectParentCycles(wrappers []wrapperDoc, idx map[string]int) error {
	color := map[string]int{}
	var visit func(id string) error
	visit = func(id string) error {
		switch color[id] {
		case 1:
			return fmt.Errorf("parent cycle through %s", id)
		case 2:
			return nil
		}
		color[id] = 1
		p := wrappers[idx[id]].ParentWrapperID
		if p != nil {
			if err := visit(*p); err != nil {
				return err
			}
		}
		color[id] = 2
		return nil
	}
	for _, w := range wrappers {
		if err := visit(w.WrapperID); err != nil {
			return err
		}
	}
	return nil
}

func loadAnchors(dir string, idIndex map[string]int, wrappers []wrapperDoc) (map[string]int64, []string, error) {
	renewals := map[string]int64{}
	ignored := map[string]struct{}{}
	ents, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return renewals, []string{}, nil
		}
		return nil, nil, err
	}
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".txt" {
			continue
		}
		f, err := os.Open(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, nil, err
		}
		sc := bufio.NewScanner(f)
		for sc.Scan() {
			line := sc.Text()
			trimmed := strings.TrimSpace(line)
			if trimmed == "" {
				continue
			}
			if strings.HasPrefix(trimmed, "#") {
				continue
			}
			parts := strings.Fields(trimmed)
			if len(parts) != 2 {
				f.Close()
				return nil, nil, fmt.Errorf("malformed anchor record %q in %s", line, e.Name())
			}
			id := parts[0]
			tick, err := strconv.ParseInt(parts[1], 10, 64)
			if err != nil {
				f.Close()
				return nil, nil, fmt.Errorf("malformed anchor tick %q in %s", parts[1], e.Name())
			}
			idx, known := idIndex[id]
			if !known {
				ignored[id] = struct{}{}
				continue
			}
			if wrappers[idx].Phase != "leased" {
				ignored[id] = struct{}{}
				continue
			}
			if existing, ok := renewals[id]; !ok || tick > existing {
				renewals[id] = tick
			}
		}
		f.Close()
		if err := sc.Err(); err != nil {
			return nil, nil, err
		}
	}
	out := make([]string, 0, len(ignored))
	for id := range ignored {
		out = append(out, id)
	}
	sort.Strings(out)
	return renewals, out, nil
}

func asInt64(v any) (int64, bool) {
	switch t := v.(type) {
	case nil:
		return 0, false
	case float64:
		return int64(t), true
	case int64:
		return t, true
	case json.Number:
		i, err := t.Int64()
		return i, err == nil
	default:
		return 0, false
	}
}

func frozen(wins []rawWindow, w wrapperDoc, T int64) bool {
	for _, win := range wins {
		if win.StartTickMs <= T && T <= win.EndTickMs {
			if win.Scope == "segment" && win.Segment != nil && *win.Segment == w.Segment {
				return true
			}
			if win.Scope == "wrapper" && win.WrapperID != nil && *win.WrapperID == w.WrapperID {
				return true
			}
		}
	}
	return false
}
