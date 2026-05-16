package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func run() error {
	dataRoot := os.Getenv("JRMA_DATA_DIR")
	if dataRoot == "" {
		dataRoot = "/app/rate_merge_lab"
	}
	outRoot := os.Getenv("JRMA_AUDIT_DIR")
	if outRoot == "" {
		outRoot = "/app/audit"
	}
	if err := os.MkdirAll(outRoot, 0o755); err != nil {
		return err
	}

	poolRaw, err := os.ReadFile(filepath.Join(dataRoot, "pool_state.json"))
	if err != nil {
		return err
	}
	var pool struct {
		CurrentDay int `json:"current_day"`
		Quarantine struct {
			IntervalSec int `json:"interval_sec"`
			Burst       int `json:"burst"`
		} `json:"quarantine"`
	}
	if err := json.Unmarshal(poolRaw, &pool); err != nil {
		return err
	}
	curDay := pool.CurrentDay
	qI := pool.Quarantine.IntervalSec
	qB := pool.Quarantine.Burst
	if qI < 1 {
		qI = 1
	}
	if qB < 1 {
		qB = 1
	}

	hostDir := filepath.Join(dataRoot, "hosts")
	hostEntries, err := os.ReadDir(hostDir)
	if err != nil {
		return err
	}
	hostMax := map[string]int{}
	for _, e := range hostEntries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		id := e.Name()[:len(e.Name())-5]
		raw, err := os.ReadFile(filepath.Join(hostDir, e.Name()))
		if err != nil {
			return err
		}
		var h struct {
			MaxBurst int `json:"max_burst"`
		}
		if json.Unmarshal(raw, &h) == nil && h.MaxBurst >= 1 {
			hostMax[id] = h.MaxBurst
		} else {
			hostMax[id] = 1
		}
	}

	classDir := filepath.Join(dataRoot, "classes")
	loadClass := func(name string) (int, int) {
		raw, err := os.ReadFile(filepath.Join(classDir, name+".json"))
		if err != nil {
			return 1, 1
		}
		var c struct {
			IntervalSec int `json:"interval_sec"`
			Burst       int `json:"burst"`
		}
		if json.Unmarshal(raw, &c) != nil {
			return 1, 1
		}
		i, b := c.IntervalSec, c.Burst
		if i < 1 {
			i = 1
		}
		if b < 1 {
			b = 1
		}
		return i, b
	}
	stdI, stdB := loadClass("standard")

	unitGlob := filepath.Join(dataRoot, "units", "*.json")
	paths, err := filepath.Glob(unitGlob)
	if err != nil {
		return err
	}
	sort.Strings(paths)

	type svc struct {
		id              string
		host            string
		unitClass       string
		interval        int
		burst           int
		dropinsApplied  []string
	}

	svcs := make([]svc, 0, len(paths))
	for _, p := range paths {
		raw, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		var u struct {
			ServiceID string   `json:"service_id"`
			HostID    string   `json:"host_id"`
			UnitClass string   `json:"unit_class"`
			Dropins   []string `json:"dropins"`
		}
		if json.Unmarshal(raw, &u) != nil {
			continue
		}
		isLegacy := u.UnitClass == "legacy"
		ci, cb := stdI, stdB
		if isLegacy {
			ci, cb = loadClass("legacy")
		} else if u.UnitClass != "standard" {
			ci, cb = loadClass("standard")
		}
		appliedOrder := make([]string, 0, len(u.Dropins))
		mergeDropin := func(fn string) {
			dpath := filepath.Join(dataRoot, "dropins", fn)
			dr, err := os.ReadFile(dpath)
			if err != nil {
				return
			}
			var d map[string]any
			if json.Unmarshal(dr, &d) != nil {
				return
			}
			if v, ok := d["interval_sec"]; ok {
				if fv, ok := asInt(v); ok && fv >= 1 {
					ci = fv
				}
			}
			if v, ok := d["burst"]; ok {
				if fv, ok := asInt(v); ok && fv >= 1 {
					cb = fv
				}
			}
			appliedOrder = append(appliedOrder, fn)
		}
		if isLegacy {
			for i := len(u.Dropins) - 1; i >= 0; i-- {
				mergeDropin(u.Dropins[i])
			}
		} else {
			for _, fn := range u.Dropins {
				mergeDropin(fn)
			}
		}
		emittedClass := u.UnitClass
		if emittedClass != "legacy" && emittedClass != "standard" {
			emittedClass = "standard"
		}
		svcs = append(svcs, svc{
			id:             u.ServiceID,
			host:           u.HostID,
			unitClass:      emittedClass,
			interval:       ci,
			burst:          cb,
			dropinsApplied: appliedOrder,
		})
	}
	sort.Slice(svcs, func(i, j int) bool { return svcs[i].id < svcs[j].id })

	incRaw, err := os.ReadFile(filepath.Join(dataRoot, "incident_log.json"))
	if err != nil {
		return err
	}
	var incTop struct {
		Events []map[string]any `json:"events"`
	}
	if err := json.Unmarshal(incRaw, &incTop); err != nil {
		return err
	}
	totalEv := len(incTop.Events)

	type keptEv struct {
		day int
		id  string
		raw map[string]any
	}
	kept := make([]keptEv, 0, totalEv)
	for _, ev := range incTop.Events {
		if ok, _ := eventKept(ev, curDay); ok {
			day, _ := asInt(ev["day"])
			eid, _ := ev["event_id"].(string)
			kept = append(kept, keptEv{day: day, id: eid, raw: ev})
		}
	}
	sort.Slice(kept, func(i, j int) bool {
		if kept[i].day != kept[j].day {
			return kept[i].day < kept[j].day
		}
		return kept[i].id < kept[j].id
	})

	compromised := map[string]bool{}
	appliedJournal := make([]map[string]any, 0, len(kept))

	findIdx := func(sid string) int {
		for i := range svcs {
			if svcs[i].id == sid {
				return i
			}
		}
		return -1
	}

	for _, k := range kept {
		ev := k.raw
		kind, _ := ev["kind"].(string)
		switch kind {
		case "burst_add":
			delta, ok := asInt(ev["delta"])
			if !ok {
				continue
			}
			sids, sok := stringSlice(ev["service_ids"])
			if sok && len(sids) > 0 {
				for _, sid := range sids {
					if ix := findIdx(sid); ix >= 0 {
						svcs[ix].burst += delta
					}
				}
			} else if hid, hok := ev["host_id"].(string); hok && hid != "" {
				for i := range svcs {
					if svcs[i].host == hid {
						svcs[i].burst += delta
					}
				}
			} else {
				continue
			}
		case "interval_mult":
			num, nok := asInt(ev["num"])
			den, dok := asInt(ev["den"])
			if !nok || !dok || num <= 0 || den <= 0 {
				continue
			}
			hid, hasH := ev["host_id"].(string)
			for i := range svcs {
				if hasH && hid != "" {
					if svcs[i].host != hid {
						continue
					}
				}
				svcs[i].interval = max(1, (svcs[i].interval*num)/den)
			}
		case "host_compromise":
			hid, ok := ev["host_id"].(string)
			if !ok || hid == "" {
				continue
			}
			compromised[hid] = true
		case "burst_ceiling":
			ceil, ok := asInt(ev["ceiling"])
			if !ok || ceil < 1 {
				continue
			}
			for i := range svcs {
				if svcs[i].burst > ceil {
					svcs[i].burst = ceil
				}
			}
		}
		appliedJournal = append(appliedJournal, journalObj(ev))
	}

	for i := range svcs {
		if compromised[svcs[i].host] {
			svcs[i].interval = qI
			svcs[i].burst = qB
		}
	}

	for i := range svcs {
		if compromised[svcs[i].host] {
			continue
		}
		if mx, ok := hostMax[svcs[i].host]; ok {
			if svcs[i].burst > mx {
				svcs[i].burst = mx
			}
		}
	}

	// summary aggregates
	stdC, legC := 0, 0
	maxB, minI := 0, 0
	first := true
	for _, s := range svcs {
		if s.unitClass == "legacy" {
			legC++
		} else {
			stdC++
		}
		if first {
			maxB, minI = s.burst, s.interval
			first = false
		} else {
			if s.burst > maxB {
				maxB = s.burst
			}
			if s.interval < minI {
				minI = s.interval
			}
		}
	}
	compHostCount := 0
	for h, c := range compromised {
		if c {
			_ = h
			compHostCount++
		}
	}

	// host_summary
	hostIDs := make([]string, 0, len(hostMax))
	for h := range hostMax {
		hostIDs = append(hostIDs, h)
	}
	sort.Strings(hostIDs)
	hostsOut := map[string]any{}
	for _, hid := range hostIDs {
		sids := make([]string, 0)
		for _, s := range svcs {
			if s.host == hid {
				sids = append(sids, s.id)
			}
		}
		sort.Strings(sids)
		mb := hostMax[hid]
		hostsOut[hid] = map[string]any{
			"compromised":  compromised[hid],
			"max_burst":    mb,
			"service_ids":  sids,
		}
	}

	servicesArr := make([]any, 0, len(svcs))
	for _, s := range svcs {
		servicesArr = append(servicesArr, map[string]any{
			"burst":              s.burst,
			"compromised_host":   compromised[s.host],
			"dropins_applied":    cloneStrings(s.dropinsApplied),
			"host_id":            s.host,
			"interval_sec":       s.interval,
			"service_id":         s.id,
			"unit_class":         s.unitClass,
		})
	}

	ignored := totalEv - len(appliedJournal)

	files := map[string]any{
		"service_limits.json": map[string]any{
			"services": servicesArr,
		},
		"incident_journal.json": map[string]any{
			"applied_events":  appliedJournal,
			"ignored_events":  ignored,
		},
		"host_summary.json": map[string]any{
			"hosts": hostsOut,
		},
		"summary.json": map[string]any{
			"applied_incident_events":     len(appliedJournal),
			"compromised_hosts":           compHostCount,
			"ignored_incident_events":     ignored,
			"legacy_units":                legC,
			"max_burst_across_services": maxB,
			"min_interval_across_services": minI,
			"services_total":            len(svcs),
			"standard_units":            stdC,
		},
	}

	for fn, payload := range files {
		b, err := json.MarshalIndent(payload, "", "  ")
		if err != nil {
			return err
		}
		b = append(b, '\n')
		if err := os.WriteFile(filepath.Join(outRoot, fn), b, 0o644); err != nil {
			return err
		}
	}
	return nil
}

func cloneStrings(in []string) []string {
	out := make([]string, len(in))
	copy(out, in)
	return out
}

func journalObj(ev map[string]any) map[string]any {
	out := map[string]any{}
	if v, ok := ev["day"]; ok {
		out["day"] = v
	}
	if v, ok := ev["event_id"]; ok {
		out["event_id"] = v
	}
	if v, ok := ev["kind"]; ok {
		out["kind"] = v
	}
	for _, k := range []string{"ceiling", "delta", "den", "host_id", "num", "service_ids"} {
		if v, ok := ev[k]; ok {
			out[k] = v
		}
	}
	return out
}

func eventKept(ev map[string]any, curDay int) (bool, string) {
	acc, ok := ev["accepted"]
	if !ok || acc != true {
		return false, "accept"
	}
	day, dok := asInt(ev["day"])
	if !dok || day > curDay {
		return false, "day"
	}
	kind, kok := ev["kind"].(string)
	if !kok || kind == "" {
		return false, "kind"
	}
	eid, eok := ev["event_id"].(string)
	if !eok || eid == "" {
		return false, "id"
	}
	switch kind {
	case "burst_add":
		if _, ok := asInt(ev["delta"]); !ok {
			return false, "burst_add"
		}
		sids, sok := stringSlice(ev["service_ids"])
		hid, hok := ev["host_id"].(string)
		if sok && len(sids) > 0 {
			return true, ""
		}
		if hok && hid != "" {
			return true, ""
		}
		return false, "burst_add_tgt"
	case "interval_mult":
		num, n1 := asInt(ev["num"])
		den, n2 := asInt(ev["den"])
		if !n1 || !n2 || num <= 0 || den <= 0 {
			return false, "mult"
		}
		return true, ""
	case "host_compromise":
		hid, ok := ev["host_id"].(string)
		if !ok || hid == "" {
			return false, "cmp"
		}
		return true, ""
	case "burst_ceiling":
		c, ok := asInt(ev["ceiling"])
		if !ok || c < 1 {
			return false, "ceil"
		}
		return true, ""
	default:
		return false, "unknown"
	}
}

func asInt(v any) (int, bool) {
	switch t := v.(type) {
	case float64:
		if t != float64(int64(t)) {
			return 0, false
		}
		return int(t), true
	case int:
		return t, true
	case int64:
		return int(t), true
	case json.Number:
		i, err := t.Int64()
		if err != nil {
			return 0, false
		}
		return int(i), true
	default:
		return 0, false
	}
}

func stringSlice(v any) ([]string, bool) {
	arr, ok := v.([]any)
	if !ok {
		return nil, false
	}
	out := make([]string, 0, len(arr))
	for _, x := range arr {
		s, ok := x.(string)
		if !ok || s == "" {
			return nil, false
		}
		out = append(out, s)
	}
	return out, true
}
