package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type poolOverlay struct {
	Active    bool     `json:"active"`
	AddMillic int      `json:"add_millic"`
	SensorIDs []string `json:"sensor_ids"`
}

type poolState struct {
	AsOfDay         int          `json:"as_of_day"`
	TolPrimary      int          `json:"tol_millic_primary"`
	TolSecondary    int          `json:"tol_millic_secondary"`
	DriftGraceDays  int          `json:"drift_grace_days"`
	DriftPerDay     int          `json:"drift_per_day"`
	RecentWindowK   int          `json:"recent_window_k"`
	Overlay         *poolOverlay `json:"overlay,omitempty"`
}

type linearCalib struct {
	A int `json:"a"`
	B int `json:"b"`
}

type rawEdge struct {
	U string `json:"u"`
	V string `json:"v"`
	W int    `json:"w"`
}

type canonEdge struct {
	A string
	B string
	W int
}

type readingRow struct {
	SensorID string `json:"sensor_id"`
	Day      int    `json:"day"`
	ADC      int    `json:"adc"`
}

type incident struct {
	Kind         string   `json:"kind"`
	Day          int      `json:"day"`
	Accepted     bool     `json:"accepted"`
	StrapID      string   `json:"strap_id,omitempty"`
	RigID        string   `json:"rig_id,omitempty"`
	DeltaMillic  int      `json:"delta_millic,omitempty"`
	SeedSensors  []string `json:"seed_sensors,omitempty"`
}

type sensorRec struct {
	SensorID           string `json:"sensor_id"`
	StrapID            string `json:"strap_id"`
	RigID              string `json:"rig_id"`
	Tier               string `json:"tier"`
	CommissionedDay    int    `json:"commissioned_day"`
	LastCalibrationDay int    `json:"last_calibration_day"`
	NominalRangeMillic [2]int `json:"nominal_range_millic"`
}

type verdictRow struct {
	ReadingDay    *int     `json:"reading_day"`
	Reasons       []string `json:"reasons"`
	RelaxedMillic *int     `json:"relaxed_millic"`
	RigID         string   `json:"rig_id"`
	SensorID      string   `json:"sensor_id"`
	StrapID       string   `json:"strap_id"`
	Tier          string   `json:"tier"`
	Verdict       string   `json:"verdict"`
}

type touchRow struct {
	Marks    []string `json:"marks"`
	SensorID string   `json:"sensor_id"`
}

type summary struct {
	AsOfDay        int            `json:"as_of_day"`
	EdgeCount      int            `json:"edge_count"`
	ReadingRows    int            `json:"reading_rows"`
	RelaxRounds    int            `json:"relax_rounds"`
	SensorCount    int            `json:"sensor_count"`
	VerdictCounts  map[string]int `json:"verdict_counts"`
}

func envOr(name, def string) string {
	v := os.Getenv(name)
	if v == "" {
		return def
	}
	return v
}

func readJSON(path string, dst interface{}) {
	b, err := os.ReadFile(path)
	if err != nil {
		fail("read %s: %v", path, err)
	}
	if err := json.Unmarshal(b, dst); err != nil {
		fail("parse %s: %v", path, err)
	}
}

func fail(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(2)
}

// floorDiv returns the floor division of num/den (both signed) toward
// negative infinity, matching Python's `//` operator.
func floorDiv(num, den int) int {
	q := num / den
	r := num % den
	if (r != 0) && ((r < 0) != (den < 0)) {
		q--
	}
	return q
}

func medianInt(vals []int) int {
	cp := make([]int, len(vals))
	copy(cp, vals)
	sort.Ints(cp)
	n := len(cp)
	if n%2 == 1 {
		return cp[n/2]
	}
	return floorDiv(cp[n/2-1]+cp[n/2], 2)
}

func writePretty(path string, v interface{}) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		fail("encode %s: %v", path, err)
	}
	out := buf.Bytes()
	for len(out) > 0 && out[len(out)-1] == '\n' {
		out = out[:len(out)-1]
	}
	out = append(out, '\n')
	if err := os.WriteFile(path, out, 0o644); err != nil {
		fail("write %s: %v", path, err)
	}
}

func loadSensors(dir string) (map[string]*sensorRec, []string) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		fail("readdir %s: %v", dir, err)
	}
	out := map[string]*sensorRec{}
	var ids []string
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		var rec sensorRec
		readJSON(filepath.Join(dir, e.Name()), &rec)
		out[rec.SensorID] = &rec
		ids = append(ids, rec.SensorID)
	}
	sort.Strings(ids)
	return out, ids
}

func main() {
	root := envOr("CLR_DATA_DIR", "/app/cryostat")
	auditDir := envOr("CLR_AUDIT_DIR", "/app/audit")
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		fail("mkdir %s: %v", auditDir, err)
	}

	var pool poolState
	readJSON(filepath.Join(root, "pool_state.json"), &pool)
	asOf := pool.AsOfDay
	tolP, tolS := pool.TolPrimary, pool.TolSecondary
	driftGrace, driftPerDay := pool.DriftGraceDays, pool.DriftPerDay
	K := pool.RecentWindowK
	ovActive := false
	ovAdd := 0
	ovIDs := map[string]struct{}{}
	if pool.Overlay != nil {
		ovActive = pool.Overlay.Active
		ovAdd = pool.Overlay.AddMillic
		for _, id := range pool.Overlay.SensorIDs {
			ovIDs[id] = struct{}{}
		}
	}

	var lin linearCalib
	readJSON(filepath.Join(root, "calibration", "linear.json"), &lin)
	a, b := lin.A, lin.B

	var rawEdges []rawEdge
	readJSON(filepath.Join(root, "thermal", "edges.json"), &rawEdges)
	edges := make([]canonEdge, 0, len(rawEdges))
	for _, e := range rawEdges {
		u, v := e.U, e.V
		if u > v {
			u, v = v, u
		}
		edges = append(edges, canonEdge{A: u, B: v, W: e.W})
	}
	sort.Slice(edges, func(i, j int) bool {
		if edges[i].A != edges[j].A {
			return edges[i].A < edges[j].A
		}
		return edges[i].B < edges[j].B
	})
	edgeCount := len(edges)

	var readings []readingRow
	readJSON(filepath.Join(root, "readings", "readings.json"), &readings)
	readingRows := len(readings)

	var incidents []incident
	readJSON(filepath.Join(root, "incidents", "incident_log.json"), &incidents)

	sensors, sensorIDs := loadSensors(filepath.Join(root, "sensors"))

	bySensor := map[string][]readingRow{}
	for _, sid := range sensorIDs {
		bySensor[sid] = nil
	}
	for _, r := range readings {
		if _, ok := sensors[r.SensorID]; ok {
			bySensor[r.SensorID] = append(bySensor[r.SensorID], r)
		}
	}

	type chosenReading struct {
		Day  int
		ADC  int
		Have bool
	}
	chosen := map[string]chosenReading{}
	hasAnyInWindow := map[string]bool{}
	for _, sid := range sensorIDs {
		comm := sensors[sid].CommissionedDay
		var inWindow []readingRow
		for _, r := range bySensor[sid] {
			if r.Day >= comm && r.Day <= asOf {
				inWindow = append(inWindow, r)
			}
		}
		hasAnyInWindow[sid] = len(inWindow) > 0
		var kept []readingRow
		for _, r := range inWindow {
			if r.ADC > 0 {
				kept = append(kept, r)
			}
		}
		if len(kept) == 0 {
			chosen[sid] = chosenReading{Have: false}
			continue
		}
		sort.SliceStable(kept, func(i, j int) bool {
			if kept[i].Day != kept[j].Day {
				return kept[i].Day > kept[j].Day
			}
			return kept[i].ADC > kept[j].ADC
		})
		if len(kept) > K {
			kept = kept[:K]
		}
		adcs := make([]int, len(kept))
		maxDay := kept[0].Day
		for i, r := range kept {
			adcs[i] = r.ADC
			if r.Day > maxDay {
				maxDay = r.Day
			}
		}
		chosen[sid] = chosenReading{Day: maxDay, ADC: medianInt(adcs), Have: true}
	}

	adj := map[string]map[string]struct{}{}
	for _, sid := range sensorIDs {
		adj[sid] = map[string]struct{}{}
	}
	for _, e := range edges {
		if _, ok := adj[e.A]; !ok {
			adj[e.A] = map[string]struct{}{}
		}
		if _, ok := adj[e.B]; !ok {
			adj[e.B] = map[string]struct{}{}
		}
		adj[e.A][e.B] = struct{}{}
		adj[e.B][e.A] = struct{}{}
	}

	componentsTouchingSeeds := func(seeds []string) map[string]struct{} {
		seedsSet := map[string]struct{}{}
		for _, s := range seeds {
			if _, ok := sensors[s]; ok {
				seedsSet[s] = struct{}{}
			}
		}
		seen := map[string]struct{}{}
		faulted := map[string]struct{}{}
		for seed := range seedsSet {
			if _, ok := seen[seed]; ok {
				continue
			}
			stack := []string{seed}
			comp := map[string]struct{}{}
			for len(stack) > 0 {
				x := stack[len(stack)-1]
				stack = stack[:len(stack)-1]
				if _, ok := seen[x]; ok {
					continue
				}
				seen[x] = struct{}{}
				comp[x] = struct{}{}
				for y := range adj[x] {
					if _, ok := seen[y]; !ok {
						stack = append(stack, y)
					}
				}
			}
			intersect := false
			for x := range comp {
				if _, ok := seedsSet[x]; ok {
					intersect = true
					break
				}
			}
			if intersect {
				for x := range comp {
					faulted[x] = struct{}{}
				}
			}
		}
		return faulted
	}

	faultedCC := map[string]struct{}{}
	strapDayByStrap := map[string]int{}
	latticeDays := map[int]struct{}{}
	for _, inc := range incidents {
		if !inc.Accepted {
			continue
		}
		if asOf < inc.Day {
			continue
		}
		switch inc.Kind {
		case "lattice_fault":
			for k := range componentsTouchingSeeds(inc.SeedSensors) {
				faultedCC[k] = struct{}{}
			}
			latticeDays[inc.Day] = struct{}{}
		case "strap_quench":
			strapDayByStrap[inc.StrapID] = inc.Day
		}
	}
	latticeDayList := make([]int, 0, len(latticeDays))
	for d := range latticeDays {
		latticeDayList = append(latticeDayList, d)
	}
	sort.Ints(latticeDayList)

	preT := map[string]int{}
	marksBySensor := map[string]map[string]struct{}{}
	for _, sid := range sensorIDs {
		marksBySensor[sid] = map[string]struct{}{}
	}

	for _, sid := range sensorIDs {
		ch := chosen[sid]
		if !ch.Have {
			continue
		}
		rec := sensors[sid]
		T := a*ch.ADC + b

		for _, inc := range incidents {
			if !inc.Accepted || inc.Kind != "rig_warm" {
				continue
			}
			if asOf < inc.Day || ch.Day < inc.Day {
				continue
			}
			if inc.RigID != rec.RigID {
				continue
			}
			T += inc.DeltaMillic
			marksBySensor[sid][fmt.Sprintf("rig_warm:%s:%d", inc.RigID, inc.Day)] = struct{}{}
		}

		gap := ch.Day - rec.LastCalibrationDay
		if gap > driftGrace {
			T += driftPerDay * (gap - driftGrace)
			marksBySensor[sid]["calib_drift"] = struct{}{}
		}

		if ovActive {
			if _, ok := ovIDs[sid]; ok {
				T += ovAdd
				marksBySensor[sid]["overlay"] = struct{}{}
			}
		}
		preT[sid] = T
	}

	work := map[string]int{}
	for k, v := range preT {
		work[k] = v
	}

	tolFor := func(sid string) int {
		if sensors[sid].Tier == "primary" {
			return tolP
		}
		return tolS
	}
	isFrozen := func(sid string, t int) bool {
		rec := sensors[sid]
		low, high := rec.NominalRangeMillic[0], rec.NominalRangeMillic[1]
		tol := tolFor(sid)
		return t < low-tol || t > high+tol
	}

	prevFrozen := map[string]struct{}{}
	for round := 1; round <= 3; round++ {
		for _, e := range edges {
			ta, okA := work[e.A]
			tb, okB := work[e.B]
			if !okA || !okB {
				continue
			}
			effW := e.W
			if round > 1 {
				if _, frA := prevFrozen[e.A]; frA {
					effW = 0
				}
				if _, frB := prevFrozen[e.B]; frB {
					effW = 0
				}
			}
			work[e.B] = tb + floorDiv(effW*(ta-tb), 1000)
		}
		newFrozen := map[string]struct{}{}
		for sid, t := range work {
			if isFrozen(sid, t) {
				newFrozen[sid] = struct{}{}
			}
		}
		prevFrozen = newFrozen
	}
	relaxedAll := work

	for sid := range faultedCC {
		for _, d := range latticeDayList {
			marksBySensor[sid][fmt.Sprintf("lattice_fault:%d", d)] = struct{}{}
		}
	}
	for _, sid := range sensorIDs {
		strapID := sensors[sid].StrapID
		if d, ok := strapDayByStrap[strapID]; ok {
			marksBySensor[sid][fmt.Sprintf("strap_quench:%d", d)] = struct{}{}
		}
	}

	verdictCounts := map[string]int{}
	verdictRows := make([]verdictRow, 0, len(sensorIDs))

	for _, sid := range sensorIDs {
		rec := sensors[sid]
		strapID := rec.StrapID
		ch := chosen[sid]
		var relaxedPtr *int
		if v, ok := relaxedAll[sid]; ok {
			vv := v
			relaxedPtr = &vv
		}

		verdict := "ok"
		reasons := map[string]struct{}{}

		if _, ok := faultedCC[sid]; ok {
			verdict = "lattice_faulted"
			for _, d := range latticeDayList {
				reasons[fmt.Sprintf("lattice_fault:%d", d)] = struct{}{}
			}
		} else if d, ok := strapDayByStrap[strapID]; ok {
			verdict = "strap_quenched"
			reasons[fmt.Sprintf("strap_quench:%d", d)] = struct{}{}
		} else if !ch.Have && hasAnyInWindow[sid] {
			verdict = "missing_read"
		} else if !ch.Have && len(bySensor[sid]) > 0 {
			verdict = "precommission"
		} else if !ch.Have {
			verdict = "missing_read"
		} else if ch.Day < rec.LastCalibrationDay {
			verdict = "stale_calibration"
		} else if relaxedPtr != nil && (*relaxedPtr < rec.NominalRangeMillic[0]-tolFor(sid) || *relaxedPtr > rec.NominalRangeMillic[1]+tolFor(sid)) {
			verdict = "out_of_range"
		} else {
			verdict = "ok"
		}

		reasons[verdict] = struct{}{}
		for k := range marksBySensor[sid] {
			reasons[k] = struct{}{}
		}
		verdictCounts[verdict]++

		var readingDayPtr *int
		if ch.Have {
			d := ch.Day
			readingDayPtr = &d
		}
		reasonList := make([]string, 0, len(reasons))
		for k := range reasons {
			reasonList = append(reasonList, k)
		}
		sort.Strings(reasonList)
		verdictRows = append(verdictRows, verdictRow{
			ReadingDay:    readingDayPtr,
			Reasons:       reasonList,
			RelaxedMillic: relaxedPtr,
			RigID:         rec.RigID,
			SensorID:      sid,
			StrapID:       strapID,
			Tier:          rec.Tier,
			Verdict:       verdict,
		})
	}

	sort.Slice(verdictRows, func(i, j int) bool {
		return verdictRows[i].SensorID < verdictRows[j].SensorID
	})

	temps := map[string]int{}
	for k, v := range relaxedAll {
		temps[k] = v
	}

	touchesOut := make([]touchRow, 0, len(sensorIDs))
	for _, sid := range sensorIDs {
		marks := make([]string, 0, len(marksBySensor[sid]))
		for k := range marksBySensor[sid] {
			marks = append(marks, k)
		}
		sort.Strings(marks)
		touchesOut = append(touchesOut, touchRow{Marks: marks, SensorID: sid})
	}

	summaryOut := summary{
		AsOfDay:       asOf,
		EdgeCount:     edgeCount,
		ReadingRows:   readingRows,
		RelaxRounds:   3,
		SensorCount:   len(sensorIDs),
		VerdictCounts: verdictCounts,
	}

	writePretty(filepath.Join(auditDir, "sensor_verdicts.json"), map[string]interface{}{"verdicts": verdictRows})
	writePretty(filepath.Join(auditDir, "thermal_relaxed.json"), map[string]interface{}{"temps": temps})
	writePretty(filepath.Join(auditDir, "incident_touch.json"), map[string]interface{}{"touches": touchesOut})
	writePretty(filepath.Join(auditDir, "summary.json"), summaryOut)
}
