package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type policy struct {
	IdleTimeoutMs int `json:"idle_timeout_ms"`
	MaxLeaseMs    int `json:"max_lease_ms"`
	MaxSize       int `json:"max_size"`
	MinSize       int `json:"min_size"`
}

type poolState struct {
	EvalTickMs int64 `json:"eval_tick_ms"`
}

type freezeFile struct {
	Windows []freezeWindow `json:"windows"`
}

type freezeWindow struct {
	EndTickMs   int64  `json:"end_tick_ms"`
	Scope       string `json:"scope"`
	Segment     string `json:"segment"`
	StartTickMs int64  `json:"start_tick_ms"`
}

type wrapperDoc struct {
	CheckoutTickMs    any    `json:"checkout_tick_ms"`
	EnteredIdleTickMs any    `json:"entered_idle_tick_ms"`
	Phase             string `json:"phase"`
	Segment           string `json:"segment"`
	WrapperID         string `json:"wrapper_id"`
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

	seen := map[string]bool{}
	for _, w := range wrappers {
		if w.WrapperID == "" {
			return fmt.Errorf("empty wrapper_id")
		}
		if seen[w.WrapperID] {
			return fmt.Errorf("duplicate wrapper_id")
		}
		seen[w.WrapperID] = true
	}

	T := ps.EvalTickMs
	verdict := make(map[string]string, len(wrappers))
	leakInfos := make([]struct {
		id    string
		lease int64
	}, 0)

	for _, w := range wrappers {
		switch w.Phase {
		case "leased":
			co, ok := asInt64(w.CheckoutTickMs)
			if !ok {
				return fmt.Errorf("wrapper %s missing checkout", w.WrapperID)
			}
			lease := T - co
			if lease > int64(pol.MaxLeaseMs) {
				verdict[w.WrapperID] = "reclaimed_leak"
				leakInfos = append(leakInfos, struct {
					id    string
					lease int64
				}{id: w.WrapperID, lease: lease})
			}
		case "idle":
			// defer
		default:
			return fmt.Errorf("unknown phase for %s", w.WrapperID)
		}
	}

	sort.Slice(leakInfos, func(i, j int) bool {
		if leakInfos[i].lease != leakInfos[j].lease {
			return leakInfos[i].lease > leakInfos[j].lease
		}
		return leakInfos[i].id < leakInfos[j].id
	})
	leakEvents := make([]map[string]any, 0, len(leakInfos))
	for _, lk := range leakInfos {
		leakEvents = append(leakEvents, map[string]any{
			"kind":       "leak_reclaim",
			"lease_ms":   lk.lease,
			"reason":     "lease_exceeded",
			"wrapper_id": lk.id,
		})
	}

	leasedLive := 0
	for _, w := range wrappers {
		if w.Phase != "leased" {
			continue
		}
		if verdict[w.WrapperID] == "reclaimed_leak" {
			continue
		}
		leasedLive++
		if verdict[w.WrapperID] == "" {
			verdict[w.WrapperID] = "healthy_leased"
		}
	}

	idleLive := 0
	for _, w := range wrappers {
		if w.Phase != "idle" {
			continue
		}
		if verdict[w.WrapperID] == "reclaimed_leak" {
			continue
		}
		if _, ok := asInt64(w.EnteredIdleTickMs); !ok {
			return fmt.Errorf("wrapper %s missing entered_idle_tick", w.WrapperID)
		}
		idleLive++
	}

	type idleCand struct {
		w wrapperDoc
	}
	cands := make([]idleCand, 0)
	for _, w := range wrappers {
		if w.Phase != "idle" {
			continue
		}
		if verdict[w.WrapperID] == "reclaimed_leak" {
			continue
		}
		enter, ok := asInt64(w.EnteredIdleTickMs)
		if !ok {
			return fmt.Errorf("wrapper %s idle tick", w.WrapperID)
		}
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

	curIdle := idleLive
	idleEvents := make([]map[string]any, 0)
	for _, c := range cands {
		w := c.w
		enter, _ := asInt64(w.EnteredIdleTickMs)
		idleMs := T - enter
		if idleMs <= int64(pol.IdleTimeoutMs) {
			continue
		}
		if segmentFrozen(fr.Windows, w.Segment, T) {
			verdict[w.WrapperID] = "idle_preserved_freeze"
			continue
		}
		if int64(leasedLive+curIdle-1) >= int64(pol.MinSize) {
			verdict[w.WrapperID] = "reclaimed_idle"
			curIdle--
			idleEvents = append(idleEvents, map[string]any{
				"kind":       "idle_reclaim",
				"idle_ms":    idleMs,
				"reason":     "idle_timeout",
				"wrapper_id": w.WrapperID,
			})
		} else {
			verdict[w.WrapperID] = "idle_retained_cap"
		}
	}

	for _, w := range wrappers {
		if w.Phase != "idle" {
			continue
		}
		if verdict[w.WrapperID] == "" {
			verdict[w.WrapperID] = "healthy_idle"
		}
	}

	allEvents := append(leakEvents, idleEvents...)

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

	segments := map[string]struct{}{}
	for _, w := range wrappers {
		segments[w.Segment] = struct{}{}
	}
	segList := make([]string, 0, len(segments))
	for s := range segments {
		segList = append(segList, s)
	}
	sort.Strings(segList)

	uniq := map[string]struct{}{}
	for _, w := range wrappers {
		uniq[verdict[w.WrapperID]] = struct{}{}
	}
	uniqList := make([]string, 0, len(uniq))
	for s := range uniq {
		uniqList = append(uniqList, s)
	}
	sort.Strings(uniqList)

	echo := make([]map[string]any, 0, len(fr.Windows))
	for _, win := range fr.Windows {
		var segVal any = win.Segment
		if win.Scope != "segment" {
			segVal = nil
		}
		echo = append(echo, map[string]any{
			"end_tick_ms":   win.EndTickMs,
			"scope":         win.Scope,
			"segment":       segVal,
			"start_tick_ms": win.StartTickMs,
		})
	}
	sort.Slice(echo, func(i, j int) bool {
		si := echo[i]["start_tick_ms"].(int64)
		sj := echo[j]["start_tick_ms"].(int64)
		if si != sj {
			return si < sj
		}
		ei := echo[i]["end_tick_ms"].(int64)
		ej := echo[j]["end_tick_ms"].(int64)
		if ei != ej {
			return ei < ej
		}
		segi := fmt.Sprint(echo[i]["segment"])
		segj := fmt.Sprint(echo[j]["segment"])
		if segi != segj {
			return segi < segj
		}
		return fmt.Sprint(echo[i]["scope"]) < fmt.Sprint(echo[j]["scope"])
	})

	counters := map[string]any{
		"eval_tick_ms":             T,
		"healthy_idle_remaining":   count("healthy_idle"),
		"healthy_leased_remaining": count("healthy_leased"),
		"idle_evictions":           count("reclaimed_idle"),
		"idle_preserved_freeze":    count("idle_preserved_freeze"),
		"idle_retained_cap":        count("idle_retained_cap"),
		"leak_reclaims":            count("reclaimed_leak"),
		"max_size":                 pol.MaxSize,
		"min_size":                 pol.MinSize,
		"wrappers_total":           len(wrappers),
	}

	summary := map[string]any{
		"eval_tick_ms":    T,
		"segments":        segList,
		"unique_verdicts": uniqList,
	}

	out := map[string]any{
		"freeze_echo.json": map[string]any{
			"windows": echo,
		},
		"pool_counters.json": counters,
		"reclaim_events.json": map[string]any{
			"events": allEvents,
		},
		"summary.json": summary,
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
	enc.SetEscapeHTML(true)
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

func segmentFrozen(wins []freezeWindow, segment string, T int64) bool {
	for _, w := range wins {
		if w.StartTickMs <= T && T <= w.EndTickMs && w.Scope == "segment" && w.Segment == segment {
			return true
		}
	}
	return false
}
