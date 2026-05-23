package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
)

const boltzmannJPerK = 1.380649e-23
const driftWindowDays = 6

type poolState struct {
	KelvinOffsetGlobal   float64  `json:"kelvin_offset_global"`
	RadiusFloorNM        *float64 `json:"radius_floor_nm,omitempty"`
	RadiusCeilingNM      *float64 `json:"radius_ceiling_nm,omitempty"`
	DriftCapK            *float64 `json:"drift_cap_K,omitempty"`
	StictionLookbackDays *int     `json:"stiction_lookback_days,omitempty"`
}

type viscosityPoint struct {
	TempK       float64 `json:"temp_K"`
	ViscosityCP float64 `json:"viscosity_cP"`
}

type solventFile struct {
	SolventID       string           `json:"solvent_id"`
	ViscosityPoints []viscosityPoint `json:"viscosity_points"`
}

type probeFile struct {
	ProbeID   string `json:"probe_id"`
	ChainID   string `json:"chain_id,omitempty"`
	ChainRole string `json:"chain_role,omitempty"`
}

type measurement struct {
	MeasurementID        string  `json:"measurement_id"`
	ProbeID              string  `json:"probe_id"`
	SolventID            string  `json:"solvent_id"`
	SoluteID             string  `json:"solute_id"`
	HydrodynamicRadiusNM float64 `json:"hydrodynamic_radius_nm"`
	TempReportedK        float64 `json:"temp_reported_K"`
	RunDay               int     `json:"run_day"`
}

type rawEvent struct {
	EventID   string   `json:"event_id"`
	Kind      string   `json:"kind"`
	Accepted  *bool    `json:"accepted,omitempty"`
	Day       int      `json:"day"`
	ProbeID   string   `json:"probe_id"`
	SolventID string   `json:"solvent_id"`
	DeltaK    *float64 `json:"delta_K,omitempty"`
}

type incidentLog struct {
	Events []rawEvent `json:"events"`
}

func acceptedFlag(ev rawEvent) bool {
	if ev.Accepted == nil {
		return true
	}
	return *ev.Accepted
}

func roundHalfEven(x float64, places int) float64 {
	scale := math.Pow10(places)
	return math.RoundToEven(x*scale) / scale
}

func contains(m map[string]struct{}, k string) bool {
	_, ok := m[k]
	return ok
}

func isIgnoredEvent(ev rawEvent, corpusProbes map[string]struct{}, corpusSolvents map[string]struct{}) bool {
	if !acceptedFlag(ev) {
		return true
	}
	switch ev.Kind {
	case "sensor_drift":
		if ev.ProbeID == "" || !contains(corpusProbes, ev.ProbeID) {
			return true
		}
		if ev.DeltaK == nil {
			return true
		}
	case "probe_stiction":
		if ev.ProbeID == "" || !contains(corpusProbes, ev.ProbeID) {
			return true
		}
	case "solvent_recall":
		if ev.SolventID == "" || !contains(corpusSolvents, ev.SolventID) {
			return true
		}
	case "bench_correction":
		if ev.ProbeID == "" || !contains(corpusProbes, ev.ProbeID) {
			return true
		}
		if ev.DeltaK == nil {
			return true
		}
		if ev.SolventID != "" && !contains(corpusSolvents, ev.SolventID) {
			return true
		}
	case "recall_lift":
		if ev.SolventID == "" || !contains(corpusSolvents, ev.SolventID) {
			return true
		}
		if ev.ProbeID != "" && !contains(corpusProbes, ev.ProbeID) {
			return true
		}
	case "recall_relift":
		if ev.SolventID == "" || !contains(corpusSolvents, ev.SolventID) {
			return true
		}
		if ev.ProbeID != "" && !contains(corpusProbes, ev.ProbeID) {
			return true
		}
	default:
		return true
	}
	return false
}

func driftWindowContributors(evts []rawEvent, m measurement, corpusProbes map[string]struct{}, corpusSolvents map[string]struct{}) (float64, []string) {
	sum := 0.0
	var ids []string
	low := m.RunDay - driftWindowDays
	for _, ev := range evts {
		if isIgnoredEvent(ev, corpusProbes, corpusSolvents) {
			continue
		}
		if ev.Kind != "sensor_drift" {
			continue
		}
		if ev.ProbeID != m.ProbeID {
			continue
		}
		if ev.Day < low || ev.Day > m.RunDay {
			continue
		}
		sum += *ev.DeltaK
		ids = append(ids, ev.EventID)
	}
	return sum, ids
}

func solventRecallFloorDay(evts []rawEvent, m measurement, corpusProbes map[string]struct{}, corpusSolvents map[string]struct{}) int {
	best := -1
	for _, ev := range evts {
		if isIgnoredEvent(ev, corpusProbes, corpusSolvents) {
			continue
		}
		if ev.Kind != "solvent_recall" {
			continue
		}
		if ev.SolventID != m.SolventID {
			continue
		}
		if ev.Day > m.RunDay {
			continue
		}
		if ev.Day > best {
			best = ev.Day
		}
	}
	return best
}

func capDrift(raw float64, capK *float64) (float64, bool) {
	if capK == nil {
		return raw, false
	}
	if raw > *capK {
		return *capK, true
	}
	if raw < -*capK {
		return -*capK, true
	}
	return raw, false
}

func selectBenchDelta(
	evts []rawEvent,
	m measurement,
	corpusProbes map[string]struct{},
	corpusSolvents map[string]struct{},
	rFloor int,
) (float64, *rawEvent) {
	type cand struct {
		idx int
		day int
		ev  rawEvent
	}
	var cands []cand
	for i, ev := range evts {
		if isIgnoredEvent(ev, corpusProbes, corpusSolvents) {
			continue
		}
		if ev.Kind != "bench_correction" {
			continue
		}
		if ev.ProbeID != m.ProbeID {
			continue
		}
		if ev.Day > m.RunDay {
			continue
		}
		if rFloor >= 0 && ev.Day <= rFloor {
			continue
		}
		if ev.SolventID != "" && ev.SolventID != m.SolventID {
			continue
		}
		cands = append(cands, cand{idx: i, day: ev.Day, ev: ev})
	}
	if len(cands) == 0 {
		return 0, nil
	}
	best := cands[0]
	for _, c := range cands[1:] {
		if c.day > best.day {
			best = c
		} else if c.day == best.day && c.idx > best.idx {
			best = c
		}
	}
	return *best.ev.DeltaK, &best.ev
}

func directStictionActive(
	evts []rawEvent,
	m measurement,
	corpusProbes map[string]struct{},
	corpusSolvents map[string]struct{},
	lookback *int,
) bool {
	low := m.RunDay
	if lookback != nil {
		low = m.RunDay - *lookback
	}
	for _, ev := range evts {
		if isIgnoredEvent(ev, corpusProbes, corpusSolvents) {
			continue
		}
		if ev.Kind != "probe_stiction" {
			continue
		}
		if ev.ProbeID != m.ProbeID {
			continue
		}
		if ev.Day > m.RunDay {
			continue
		}
		if lookback != nil && ev.Day < low {
			continue
		}
		return true
	}
	return false
}

func chainPropagatedStictionActive(
	evts []rawEvent,
	m measurement,
	corpusProbes map[string]struct{},
	corpusSolvents map[string]struct{},
	lookback *int,
	probeRoles map[string]string,
	probeChains map[string]string,
) bool {
	mChain, mHasChain := probeChains[m.ProbeID]
	mRole := probeRoles[m.ProbeID]
	if !mHasChain || mChain == "" || mRole != "secondary" {
		return false
	}
	var propLow int
	if lookback != nil {
		propLow = m.RunDay - (*lookback / 2)
	}
	for _, ev := range evts {
		if isIgnoredEvent(ev, corpusProbes, corpusSolvents) {
			continue
		}
		if ev.Kind != "probe_stiction" {
			continue
		}
		// Chain propagation never fires for the event's own probe.
		if ev.ProbeID == m.ProbeID {
			continue
		}
		evChain, evHasChain := probeChains[ev.ProbeID]
		evRole := probeRoles[ev.ProbeID]
		if !evHasChain || evChain == "" || evRole != "primary" {
			continue
		}
		if evChain != mChain {
			continue
		}
		if ev.Day > m.RunDay {
			continue
		}
		if lookback != nil && ev.Day < propLow {
			continue
		}
		return true
	}
	return false
}

func recallLatestDay(evts []rawEvent, m measurement, corpusProbes map[string]struct{}, corpusSolvents map[string]struct{}) (int, []int) {
	var winners []int
	best := -1
	for i, ev := range evts {
		if isIgnoredEvent(ev, corpusProbes, corpusSolvents) {
			continue
		}
		if ev.Kind != "solvent_recall" {
			continue
		}
		if ev.SolventID != m.SolventID {
			continue
		}
		if ev.Day > m.RunDay {
			continue
		}
		if ev.Day > best {
			best = ev.Day
			winners = []int{i}
		} else if ev.Day == best {
			winners = append(winners, i)
		}
	}
	return best, winners
}

func liftLatestDay(evts []rawEvent, m measurement, corpusProbes map[string]struct{}, corpusSolvents map[string]struct{}) (int, []int) {
	var winners []int
	best := -1
	for i, ev := range evts {
		if isIgnoredEvent(ev, corpusProbes, corpusSolvents) {
			continue
		}
		if ev.Kind != "recall_lift" {
			continue
		}
		if ev.SolventID != m.SolventID {
			continue
		}
		if ev.Day > m.RunDay {
			continue
		}
		if ev.ProbeID != "" && ev.ProbeID != m.ProbeID {
			continue
		}
		if ev.Day > best {
			best = ev.Day
			winners = []int{i}
		} else if ev.Day == best {
			winners = append(winners, i)
		}
	}
	return best, winners
}

func reliftLatestDay(evts []rawEvent, m measurement, corpusProbes map[string]struct{}, corpusSolvents map[string]struct{}) (int, []int) {
	var winners []int
	best := -1
	for i, ev := range evts {
		if isIgnoredEvent(ev, corpusProbes, corpusSolvents) {
			continue
		}
		if ev.Kind != "recall_relift" {
			continue
		}
		if ev.SolventID != m.SolventID {
			continue
		}
		if ev.Day > m.RunDay {
			continue
		}
		if ev.ProbeID != "" && ev.ProbeID != m.ProbeID {
			continue
		}
		if ev.Day > best {
			best = ev.Day
			winners = []int{i}
		} else if ev.Day == best {
			winners = append(winners, i)
		}
	}
	return best, winners
}

func viscosityFor(
	T float64,
	points []viscosityPoint,
	lowCount *int,
	highCount *int,
) float64 {
	if len(points) == 0 {
		return math.NaN()
	}
	if T < points[0].TempK {
		*lowCount++
		return points[0].ViscosityCP
	}
	last := points[len(points)-1]
	if T > last.TempK {
		*highCount++
		return last.ViscosityCP
	}
	for j := 0; j < len(points)-1; j++ {
		t0 := points[j].TempK
		t1 := points[j+1].TempK
		if T >= t0 && T <= t1 {
			v0 := points[j].ViscosityCP
			v1 := points[j+1].ViscosityCP
			if t1 == t0 {
				return v0
			}
			w := (T - t0) / (t1 - t0)
			return v0 + (v1-v0)*w
		}
	}
	return last.ViscosityCP
}

func diffusionSI(T, etaPas, rM float64) float64 {
	return (boltzmannJPerK * T) / (6 * math.Pi * etaPas * rM)
}

func clampRadiusNM(orig float64, floorNM, ceilingNM *float64) float64 {
	fl := floorNM
	ce := ceilingNM
	if fl != nil && ce != nil && *fl > *ce {
		fl, ce = ce, fl
	}
	r := orig
	if fl != nil && r < *fl {
		r = *fl
	}
	if ce != nil && r > *ce {
		r = *ce
	}
	return r
}

func main() {
	dataDir := os.Getenv("SDA_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/stokes_lab"
	}
	outDir := os.Getenv("SDA_AUDIT_DIR")
	if outDir == "" {
		outDir = "/app/audit"
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		panic(err)
	}

	poolBytes, err := os.ReadFile(filepath.Join(dataDir, "pool_state.json"))
	if err != nil {
		panic(err)
	}
	var pool poolState
	if err := json.Unmarshal(poolBytes, &pool); err != nil {
		panic(err)
	}
	fl := pool.RadiusFloorNM
	ce := pool.RadiusCeilingNM

	incBytes, err := os.ReadFile(filepath.Join(dataDir, "incident_log.json"))
	if err != nil {
		panic(err)
	}
	var inc incidentLog
	if err := json.Unmarshal(incBytes, &inc); err != nil {
		panic(err)
	}

	solventPaths, err := filepath.Glob(filepath.Join(dataDir, "solvents", "*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(solventPaths)
	solvents := map[string][]viscosityPoint{}
	for _, p := range solventPaths {
		b, err := os.ReadFile(p)
		if err != nil {
			panic(err)
		}
		var sf solventFile
		if err := json.Unmarshal(b, &sf); err != nil {
			panic(err)
		}
		solvents[sf.SolventID] = sf.ViscosityPoints
	}

	probePaths, err := filepath.Glob(filepath.Join(dataDir, "probes", "*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(probePaths)
	probeRoles := map[string]string{}
	probeChains := map[string]string{}
	for _, p := range probePaths {
		b, err := os.ReadFile(p)
		if err != nil {
			panic(err)
		}
		var pf probeFile
		if err := json.Unmarshal(b, &pf); err != nil {
			panic(err)
		}
		role := pf.ChainRole
		if role != "primary" && role != "secondary" {
			role = ""
		}
		if pf.ChainID != "" && role != "" {
			probeRoles[pf.ProbeID] = role
			probeChains[pf.ProbeID] = pf.ChainID
		}
	}

	measPaths, err := filepath.Glob(filepath.Join(dataDir, "measurements", "*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(measPaths)
	var ms []measurement
	corpusProbes := map[string]struct{}{}
	corpusSolvents := map[string]struct{}{}
	for _, p := range measPaths {
		b, err := os.ReadFile(p)
		if err != nil {
			panic(err)
		}
		var m measurement
		if err := json.Unmarshal(b, &m); err != nil {
			panic(err)
		}
		ms = append(ms, m)
		corpusProbes[m.ProbeID] = struct{}{}
		corpusSolvents[m.SolventID] = struct{}{}
	}
	sort.Slice(ms, func(i, j int) bool { return ms[i].MeasurementID < ms[j].MeasurementID })

	ignored := 0
	for _, ev := range inc.Events {
		if isIgnoredEvent(ev, corpusProbes, corpusSolvents) {
			ignored++
		}
	}

	lowEx := 0
	highEx := 0
	okCount := 0
	probeVoid := 0
	solventVoid := 0
	radiusClamped := 0
	driftCapped := 0
	chainPropagatedVoid := 0
	recallRelift := 0

	var entries []map[string]any

	driftContribIDs := make([][]string, len(ms))
	benchWinner := make([]*rawEvent, len(ms))
	statuses := make([]string, len(ms))
	recallWinnerIdx := make([][]int, len(ms))
	liftWinnerIdx := make([][]int, len(ms))
	reliftWinnerIdx := make([][]int, len(ms))
	recallActiveForMeas := make([]bool, len(ms))
	directStictionForMeas := make([]bool, len(ms))
	chainStictionForMeas := make([]bool, len(ms))

	for i, m := range ms {
		deltaRaw, contribIDs := driftWindowContributors(inc.Events, m, corpusProbes, corpusSolvents)
		driftContribIDs[i] = contribIDs
		deltaD, wasCapped := capDrift(deltaRaw, pool.DriftCapK)
		if wasCapped {
			driftCapped++
		}

		rFloor := solventRecallFloorDay(inc.Events, m, corpusProbes, corpusSolvents)
		deltaB, bw := selectBenchDelta(inc.Events, m, corpusProbes, corpusSolvents, rFloor)
		benchWinner[i] = bw

		rMaxDay, rWinners := recallLatestDay(inc.Events, m, corpusProbes, corpusSolvents)
		lMaxDay, lWinners := liftLatestDay(inc.Events, m, corpusProbes, corpusSolvents)
		rlMaxDay, rlWinners := reliftLatestDay(inc.Events, m, corpusProbes, corpusSolvents)
		recallWinnerIdx[i] = rWinners
		liftWinnerIdx[i] = lWinners
		reliftWinnerIdx[i] = rlWinners

		recallApplies := false
		if rMaxDay >= 0 {
			latestSurvive := rMaxDay
			if rlMaxDay > latestSurvive {
				latestSurvive = rlMaxDay
			}
			if latestSurvive >= lMaxDay {
				recallApplies = true
			}
		}
		recallActiveForMeas[i] = recallApplies

		direct := directStictionActive(inc.Events, m, corpusProbes, corpusSolvents, pool.StictionLookbackDays)
		chained := chainPropagatedStictionActive(inc.Events, m, corpusProbes, corpusSolvents, pool.StictionLookbackDays, probeRoles, probeChains)
		directStictionForMeas[i] = direct
		chainStictionForMeas[i] = chained

		status := "ok"
		if direct || chained {
			status = "probe_void"
		} else if recallApplies {
			status = "solvent_void"
		}
		statuses[i] = status

		if status == "probe_void" && !direct && chained {
			chainPropagatedVoid++
		}
		if rMaxDay >= 0 && recallApplies && rlMaxDay >= 0 && rlMaxDay >= lMaxDay {
			recallRelift++
		}

		Tbase := m.TempReportedK + pool.KelvinOffsetGlobal
		Tvisc := Tbase + deltaD
		Teff := Tvisc + deltaB

		origR := m.HydrodynamicRadiusNM
		rClamped := clampRadiusNM(origR, fl, ce)
		if math.Float64bits(rClamped) != math.Float64bits(origR) {
			radiusClamped++
		}

		var tempOut any = nil
		var viscOut any = nil
		var dOut any = nil
		var rUsedOut any = nil

		if status == "ok" {
			points := solvents[m.SolventID]
			etaCP := viscosityFor(Tvisc, points, &lowEx, &highEx)
			etaPas := etaCP * 1e-3
			rM := rClamped * 1e-9
			dSI := diffusionSI(Teff, etaPas, rM)
			dNm2s := dSI * 1e18

			tempOut = roundHalfEven(Teff, 3)
			viscOut = roundHalfEven(etaCP, 6)
			dOut = roundHalfEven(dNm2s, 6)
			rUsedOut = roundHalfEven(rClamped, 6)
			okCount++
		} else if status == "probe_void" {
			probeVoid++
		} else if status == "solvent_void" {
			solventVoid++
		}

		row := map[string]any{
			"d_stokes_nm2_per_s":          dOut,
			"hydrodynamic_radius_nm_used": rUsedOut,
			"measurement_id":              m.MeasurementID,
			"probe_id":                    m.ProbeID,
			"solute_id":                   m.SoluteID,
			"solvent_id":                  m.SolventID,
			"status":                      status,
			"temp_effective_K":            tempOut,
			"viscosity_cP_used":           viscOut,
		}
		entries = append(entries, row)
	}

	applied := map[string]struct{}{}

	for i := range ms {
		if statuses[i] != "ok" {
			continue
		}
		for _, eid := range driftContribIDs[i] {
			applied[eid] = struct{}{}
		}
		if benchWinner[i] != nil {
			applied[benchWinner[i].EventID] = struct{}{}
		}
	}

	// (b) probe_stiction directly active OR chain-propagated for at least one measurement.
	for i, m := range ms {
		_ = m
		if directStictionForMeas[i] {
			for _, ev := range inc.Events {
				if isIgnoredEvent(ev, corpusProbes, corpusSolvents) {
					continue
				}
				if ev.Kind != "probe_stiction" {
					continue
				}
				if ev.ProbeID != m.ProbeID {
					continue
				}
				if ev.Day > m.RunDay {
					continue
				}
				low := m.RunDay
				if pool.StictionLookbackDays != nil {
					low = m.RunDay - *pool.StictionLookbackDays
				}
				if pool.StictionLookbackDays != nil && ev.Day < low {
					continue
				}
				applied[ev.EventID] = struct{}{}
			}
		}
		if chainStictionForMeas[i] {
			mChain, mHasChain := probeChains[m.ProbeID]
			mRole := probeRoles[m.ProbeID]
			if mHasChain && mRole == "secondary" {
				var propLow int
				if pool.StictionLookbackDays != nil {
					propLow = m.RunDay - (*pool.StictionLookbackDays / 2)
				}
				for _, ev := range inc.Events {
					if isIgnoredEvent(ev, corpusProbes, corpusSolvents) {
						continue
					}
					if ev.Kind != "probe_stiction" {
						continue
					}
					if ev.ProbeID == m.ProbeID {
						continue
					}
					evChain, evHasChain := probeChains[ev.ProbeID]
					evRole := probeRoles[ev.ProbeID]
					if !evHasChain || evRole != "primary" {
						continue
					}
					if evChain != mChain {
						continue
					}
					if ev.Day > m.RunDay {
						continue
					}
					if pool.StictionLookbackDays != nil && ev.Day < propLow {
						continue
					}
					applied[ev.EventID] = struct{}{}
				}
			}
		}
	}

	// (c) solvent_recall: latest matching for some measurement and recall active for that measurement.
	for i := range ms {
		if !recallActiveForMeas[i] {
			continue
		}
		for _, idx := range recallWinnerIdx[i] {
			applied[inc.Events[idx].EventID] = struct{}{}
		}
	}

	// (d) recall_lift: applicable to some measurement with l_max_day >= r_max_day (regardless of relift).
	for i := range ms {
		if len(recallWinnerIdx[i]) == 0 {
			continue
		}
		if len(liftWinnerIdx[i]) == 0 {
			continue
		}
		rMaxDay := inc.Events[recallWinnerIdx[i][0]].Day
		lMaxDay := inc.Events[liftWinnerIdx[i][0]].Day
		if lMaxDay < rMaxDay {
			continue
		}
		for _, idx := range liftWinnerIdx[i] {
			applied[inc.Events[idx].EventID] = struct{}{}
		}
	}

	// (e) recall_relift: applicable to some measurement with r_max defined, recall active, day == rl_max_day.
	for i := range ms {
		if !recallActiveForMeas[i] {
			continue
		}
		if len(recallWinnerIdx[i]) == 0 {
			continue
		}
		if len(reliftWinnerIdx[i]) == 0 {
			continue
		}
		for _, idx := range reliftWinnerIdx[i] {
			applied[inc.Events[idx].EventID] = struct{}{}
		}
	}

	appliedList := make([]string, 0, len(applied))
	for id := range applied {
		appliedList = append(appliedList, id)
	}
	sort.Strings(appliedList)

	summary := map[string]any{
		"chain_propagated_void_count":        chainPropagatedVoid,
		"drift_capped_count":                 driftCapped,
		"ignored_incident_events":            ignored,
		"measurements_total":                 len(ms),
		"ok_count":                           okCount,
		"probe_void_count":                   probeVoid,
		"radius_clamped_count":               radiusClamped,
		"recall_relift_count":                recallRelift,
		"solvent_void_count":                 solventVoid,
		"viscosity_extrapolation_high_count": highEx,
		"viscosity_extrapolation_low_count":  lowEx,
	}

	resultsDoc := map[string]any{"entries": entries}
	anomDoc := map[string]any{"applied_events": appliedList}

	write := func(name string, doc any) {
		bs, err := json.MarshalIndent(doc, "", "  ")
		if err != nil {
			panic(err)
		}
		bs = append(bs, '\n')
		outPath := filepath.Join(outDir, name)
		if err := os.WriteFile(outPath, bs, 0o644); err != nil {
			panic(err)
		}
	}

	write("diffusion_results.json", resultsDoc)
	write("anomalies.json", anomDoc)
	write("summary.json", summary)

	fmt.Fprintln(os.Stderr, "wrote audit artifacts")
}
