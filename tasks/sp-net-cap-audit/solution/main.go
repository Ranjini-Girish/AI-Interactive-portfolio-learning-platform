package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
)

type capSnap struct {
	Cnf     float64 `json:"c_nf"`
	EsrMohm float64 `json:"esr_mohm"`
}

type rackFile struct {
	RackID   string     `json:"rack_id"`
	HostID   string     `json:"host_id"`
	RatedMV  int        `json:"rated_mv"`
	Tier     string     `json:"tier"`
	Stages   [][]string `json:"stages"`
}

type incidentEvent map[string]any

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

func r3(x float64) float64 {
	return math.Round((x+1e-12)*1000) / 1000
}

func energyUJ(cnf float64, ratedMV int) int {
	v := float64(ratedMV) / 1000.0
	cf := cnf * 1e-9
	return int(math.Round(0.5 * cf * v * v * 1e6))
}

func parallelStage(caps []capSnap) (float64, float64) {
	var csum float64
	zeroBranch := false
	for _, c := range caps {
		csum += c.Cnf
		if c.EsrMohm <= 0 {
			zeroBranch = true
		}
	}
	if zeroBranch {
		return csum, 0
	}
	var g float64
	for _, c := range caps {
		g += 1.0 / c.EsrMohm
	}
	return csum, 1.0 / g
}

func seriesStages(stages []struct {
	c float64
	e float64
}) (float64, float64) {
	var inv float64
	var esrSum float64
	for _, st := range stages {
		inv += 1.0 / st.c
		esrSum += st.e
	}
	return 1.0 / inv, esrSum
}

func eventInt(ev incidentEvent, key string) int {
	v, ok := ev[key]
	if !ok {
		panic("missing " + key)
	}
	switch t := v.(type) {
	case float64:
		return int(t)
	case json.Number:
		i, err := strconv.Atoi(string(t))
		must(err)
		return i
	default:
		panic(fmt.Sprintf("bad type %T", v))
	}
}

func eventFloat(ev incidentEvent, key string) float64 {
	v, ok := ev[key]
	if !ok {
		panic("missing " + key)
	}
	switch t := v.(type) {
	case float64:
		return t
	case json.Number:
		f, err := strconv.ParseFloat(string(t), 64)
		must(err)
		return f
	default:
		panic(fmt.Sprintf("bad type %T", v))
	}
}

func eventBool(ev incidentEvent, key string) bool {
	v, ok := ev[key]
	if !ok {
		return false
	}
	b, ok := v.(bool)
	if !ok {
		panic(fmt.Sprintf("bad bool %T", v))
	}
	return b
}

func eventStr(ev incidentEvent, key string) string {
	v, ok := ev[key]
	if !ok {
		return ""
	}
	s, ok := v.(string)
	if !ok {
		panic(fmt.Sprintf("bad string %T", v))
	}
	return s
}

func marshalOut(path string, v any) {
	var buf []byte
	var err error
	buf, err = json.MarshalIndent(v, "", "  ")
	must(err)
	buf = append(buf, '\n')
	must(os.WriteFile(path, buf, 0o644))
}

func main() {
	dataDir := os.Getenv("SPN_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/spn_lab"
	}
	auditDir := os.Getenv("SPN_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/spn_audit"
	}
	must(os.MkdirAll(auditDir, 0o755))

	var policy struct {
		ThermalCeiling map[string]int `json:"thermal_ceiling_uj"`
	}
	readJSON(filepath.Join(dataDir, "policy.json"), &policy)

	var pool struct {
		CurrentDay         int      `json:"current_day"`
		CompromisedHosts   []string `json:"compromised_hosts"`
		FrozenRacks        []string `json:"frozen_racks"`
	}
	readJSON(filepath.Join(dataDir, "pool_state.json"), &pool)

	var inc struct {
		Events []incidentEvent `json:"events"`
	}
	readJSON(filepath.Join(dataDir, "incident_log.json"), &inc)

	base := map[string]capSnap{}
	matches, err := filepath.Glob(filepath.Join(dataDir, "caps", "*.json"))
	must(err)
	sort.Strings(matches)
	for _, p := range matches {
		var cf struct {
			CapID   string  `json:"cap_id"`
			Cnf     float64 `json:"c_nf"`
			EsrMohm float64 `json:"esr_mohm"`
		}
		readJSON(p, &cf)
		base[cf.CapID] = capSnap{Cnf: cf.Cnf, EsrMohm: cf.EsrMohm}
	}

	work := map[string]capSnap{}
	for k, v := range base {
		work[k] = v
	}

	currentDay := pool.CurrentDay
	compromised := map[string]struct{}{}
	for _, h := range pool.CompromisedHosts {
		compromised[h] = struct{}{}
	}
	frozen := map[string]struct{}{}
	for _, r := range pool.FrozenRacks {
		frozen[r] = struct{}{}
	}

	applied := []map[string]string{}

	for _, ev := range inc.Events {
		if !eventBool(ev, "accepted") {
			continue
		}
		start := eventInt(ev, "start_day")
		end := eventInt(ev, "end_day")
		if currentDay < start || currentDay > end {
			continue
		}
		kind := eventStr(ev, "kind")
		eid := eventStr(ev, "event_id")
		switch kind {
		case "cap_scale":
			cid := eventStr(ev, "cap_id")
			mult := eventFloat(ev, "c_mult")
			w := work[cid]
			w.Cnf *= mult
			work[cid] = w
			applied = append(applied, map[string]string{
				"detail":  fmt.Sprintf("cap %s x%.3f", cid, mult),
				"event_id": eid,
				"kind":    kind,
			})
		case "rack_esr_offset":
			rid := eventStr(ev, "rack_id")
			add := eventFloat(ev, "add_mohm")
			applied = append(applied, map[string]string{
				"detail":  fmt.Sprintf("rack %s +%.3f mOhm", rid, add),
				"event_id": eid,
				"kind":    kind,
			})
		default:
			panic("unknown kind " + kind)
		}
	}

	rackPaths, err := filepath.Glob(filepath.Join(dataDir, "racks", "*.json"))
	must(err)
	sort.Strings(rackPaths)
	var racks []rackFile
	for _, p := range rackPaths {
		var rf rackFile
		readJSON(p, &rf)
		racks = append(racks, rf)
	}

	rackCaps := map[string]map[string]struct{}{}
	for _, r := range racks {
		set := map[string]struct{}{}
		for _, st := range r.Stages {
			for _, cid := range st {
				set[cid] = struct{}{}
			}
		}
		rackCaps[r.RackID] = set
	}

	snapshot := func(rid, cid string) capSnap {
		if _, ok := frozen[rid]; ok {
			if _, ok2 := rackCaps[rid][cid]; ok2 {
				return base[cid]
			}
		}
		return work[cid]
	}

	type rackOut map[string]any

	var rackRows []rackOut

	for _, r := range racks {
		rid := r.RackID
		if _, bad := compromised[r.HostID]; bad {
			rackRows = append(rackRows, rackOut{
				"energy_uj":         0,
				"equiv_c_nf":       r3(0),
				"equiv_esr_mohm":   nil,
				"headroom_uj":      nil,
				"rack_id":          rid,
				"reasons":          []string{"host_compromised"},
				"state":            "quarantine",
			})
			continue
		}

		var stagePairs []struct {
			c float64
			e float64
		}
		for _, st := range r.Stages {
			var caps []capSnap
			for _, cid := range st {
				caps = append(caps, snapshot(rid, cid))
			}
			csum, esr := parallelStage(caps)
			stagePairs = append(stagePairs, struct {
				c float64
				e float64
			}{c: csum, e: esr})
		}
		ceq, esr0 := seriesStages(stagePairs)

		extra := 0.0
		for _, ev := range inc.Events {
			if !eventBool(ev, "accepted") {
				continue
			}
			start := eventInt(ev, "start_day")
			end := eventInt(ev, "end_day")
			if currentDay < start || currentDay > end {
				continue
			}
			if eventStr(ev, "kind") == "rack_esr_offset" && eventStr(ev, "rack_id") == rid {
				extra += eventFloat(ev, "add_mohm")
			}
		}
		esrTot := r3(esr0 + extra)
		ceqR := r3(ceq)
		eu := energyUJ(ceq, r.RatedMV)
		ceiling := policy.ThermalCeiling[r.Tier]
		head := ceiling - eu

		capTouched := false
		for _, ev := range inc.Events {
			if !eventBool(ev, "accepted") {
				continue
			}
			start := eventInt(ev, "start_day")
			end := eventInt(ev, "end_day")
			if currentDay < start || currentDay > end {
				continue
			}
			if eventStr(ev, "kind") == "cap_scale" {
				cid := eventStr(ev, "cap_id")
				if _, ok := rackCaps[rid][cid]; ok {
					capTouched = true
				}
			}
		}

		esrHit := false
		for _, ev := range inc.Events {
			if !eventBool(ev, "accepted") {
				continue
			}
			start := eventInt(ev, "start_day")
			end := eventInt(ev, "end_day")
			if currentDay < start || currentDay > end {
				continue
			}
			if eventStr(ev, "kind") == "rack_esr_offset" && eventStr(ev, "rack_id") == rid {
				esrHit = true
			}
		}

		reasons := make([]string, 0)
		if head < 0 {
			reasons = append(reasons, "negative_headroom")
		}
		if capTouched {
			reasons = append(reasons, "incident_touch")
		}
		if esrHit {
			reasons = append(reasons, "esr_offset")
		}
		sort.Strings(reasons)

		state := "ok"
		if len(reasons) > 0 {
			state = "degraded"
		}

		rackRows = append(rackRows, rackOut{
			"energy_uj":        eu,
			"equiv_c_nf":      ceqR,
			"equiv_esr_mohm":  esrTot,
			"headroom_uj":     head,
			"rack_id":         rid,
			"reasons":         reasons,
			"state":           state,
		})
	}

	sort.Slice(rackRows, func(i, j int) bool {
		return rackRows[i]["rack_id"].(string) < rackRows[j]["rack_id"].(string)
	})

	capOut := map[string]any{}
	for _, cid := range sortedKeys(work) {
		w := work[cid]
		capOut[cid] = map[string]any{
			"c_nf":     r3(w.Cnf),
			"esr_mohm": r3(w.EsrMohm),
		}
	}

	states := map[string]int{"degraded": 0, "ok": 0, "quarantine": 0}
	var minHead *int
	totalE := 0
	for _, row := range rackRows {
		st := row["state"].(string)
		states[st]++
		totalE += row["energy_uj"].(int)
		if st != "quarantine" {
			h := row["headroom_uj"].(int)
			if minHead == nil || h < *minHead {
				hh := h
				minHead = &hh
			}
		}
	}

	summary := map[string]any{
		"min_headroom_uj":   nil,
		"rack_count":        len(rackRows),
		"states":            states,
		"total_energy_uj":   totalE,
	}
	if minHead != nil {
		summary["min_headroom_uj"] = *minHead
	}

	marshalOut(filepath.Join(auditDir, "rack_equivalents.json"), map[string]any{"racks": rackRows})
	marshalOut(filepath.Join(auditDir, "incident_applied.json"), map[string]any{"applied": applied})
	marshalOut(filepath.Join(auditDir, "cap_working.json"), capOut)
	marshalOut(filepath.Join(auditDir, "summary.json"), summary)
}

func sortedKeys(m map[string]capSnap) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}
