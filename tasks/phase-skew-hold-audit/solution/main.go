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

type streakFile struct {
	Site string   `json:"site"`
	Rows []rowRaw `json:"rows"`
}

type rowRaw struct {
	Day        int     `json:"day"`
	PhaseDeg   float64 `json:"phase_deg"`
	Quality    float64 `json:"quality"`
	Instrument string  `json:"instrument"`
}

type rowTagged struct {
	Site       string
	Day        int
	PhaseDeg   float64
	Quality    float64
	Instrument string
	State      string
}

func main() {
	data := getenv("PSHA_DATA_DIR", "/app/psh_lab")
	outd := getenv("PSHA_AUDIT_DIR", "/app/audit")
	if err := run(data, outd); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func run(dataDir, outDir string) error {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	policy, err := readJSONMap(filepath.Join(dataDir, "policy.json"))
	if err != nil {
		return err
	}
	pool, err := readJSONMap(filepath.Join(dataDir, "pool_state.json"))
	if err != nil {
		return err
	}
	inc, err := readJSONMap(filepath.Join(dataDir, "incident_log.json"))
	if err != nil {
		return err
	}
	win, err := readJSONMap(filepath.Join(dataDir, "anchors/window.json"))
	if err != nil {
		return err
	}
	flr, err := readJSONMap(filepath.Join(dataDir, "anchors/day_floor.json"))
	if err != nil {
		return err
	}

	minQ := num(policy["min_quality"])
	madK := num(policy["mad_multiplier"])
	grace := int(num(policy["grace_gap_days"]))
	maskPol := map[string]int{}
	if mp, ok := policy["instrument_mask_policy"].(map[string]any); ok {
		for k, v := range mp {
			maskPol[k] = int(num(v))
		}
	}
	poolMasks := map[string]int{}
	if pm, ok := pool["instrument_masks"].(map[string]any); ok {
		for k, v := range pm {
			poolMasks[k] = int(num(v))
		}
	}

	siteCompromiseDay := map[string]int{}
	instQuarantineDay := map[string]int{}
	if evs, ok := inc["events"].([]any); ok {
		for _, e := range evs {
			em, _ := e.(map[string]any)
			if em == nil {
				continue
			}
			kind, _ := em["kind"].(string)
			switch kind {
			case "site_compromise":
				site, _ := em["site"].(string)
				day := int(num(em["effective_day"]))
				if site != "" {
					siteCompromiseDay[site] = day
				}
			case "instrument_quarantine":
				ins, _ := em["instrument"].(string)
				day := int(num(em["effective_day"]))
				if ins != "" {
					instQuarantineDay[ins] = day
				}
			}
		}
	}

	coolWindows := map[string][2]int{} // site -> start,end inclusive
	if ws, ok := win["windows"].([]any); ok {
		for _, w := range ws {
			wm, _ := w.(map[string]any)
			if wm == nil {
				continue
			}
			site, _ := wm["site"].(string)
			a := int(num(wm["start_day"]))
			b := int(num(wm["end_day"]))
			if site != "" {
				coolWindows[site] = [2]int{a, b}
			}
		}
	}

	siteFloor := map[string]int{}
	if fl, ok := flr["floors"].([]any); ok {
		for _, f := range fl {
			fm, _ := f.(map[string]any)
			if fm == nil {
				continue
			}
			site, _ := fm["site"].(string)
			siteFloor[site] = int(num(fm["min_day"]))
		}
	}

	var rows []rowTagged
	matches, _ := filepath.Glob(filepath.Join(dataDir, "streaks", "*.json"))
	sort.Strings(matches)
	for _, path := range matches {
		var sf streakFile
		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		if err := json.Unmarshal(raw, &sf); err != nil {
			return err
		}
		for _, r := range sf.Rows {
			rows = append(rows, rowTagged{
				Site:       sf.Site,
				Day:        r.Day,
				PhaseDeg:   r.PhaseDeg,
				Quality:    r.Quality,
				Instrument: r.Instrument,
			})
		}
	}

	bySite := map[string][]rowTagged{}
	for _, r := range rows {
		bySite[r.Site] = append(bySite[r.Site], r)
	}
	for site := range bySite {
		rs := bySite[site]
		sort.Slice(rs, func(i, j int) bool {
			if rs[i].Day != rs[j].Day {
				return rs[i].Day < rs[j].Day
			}
			return rs[i].Instrument < rs[j].Instrument
		})
		prevDay := 0
		hasPrev := false
		for i := range rs {
			st := classifyRow(rs[i], prevDay, hasPrev, minQ, grace, siteCompromiseDay, instQuarantineDay, coolWindows, siteFloor)
			rs[i].State = st
			prevDay = rs[i].Day
			hasPrev = true
		}
		bySite[site] = rs
	}

	type key struct {
		site string
		day  int
	}
	grouped := map[key][]rowTagged{}
	for site, rs := range bySite {
		for _, r := range rs {
			k := key{site: site, day: r.Day}
			grouped[k] = append(grouped[k], r)
		}
	}

	var keys []key
	for k := range grouped {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool {
		if keys[i].site != keys[j].site {
			return keys[i].site < keys[j].site
		}
		return keys[i].day < keys[j].day
	})

	var siteDays []map[string]any
	minDay := 1 << 30
	maxDay := -1 << 30
	stateCounts := map[string]int{}

	for _, k := range keys {
		rs := grouped[k]
		if len(rs) == 0 {
			continue
		}
		if k.day < minDay {
			minDay = k.day
		}
		if k.day > maxDay {
			maxDay = k.day
		}

		agg := aggregateState(rs)
		stateCounts[agg]++

		merged := mergePhases(rs, minQ, madK, maskPol, poolMasks)

		ins := make([]string, 0, len(rs))
		seen := map[string]struct{}{}
		for _, r := range rs {
			if _, ok := seen[r.Instrument]; !ok {
				seen[r.Instrument] = struct{}{}
				ins = append(ins, r.Instrument)
			}
		}
		sort.Strings(ins)

		row := map[string]any{
			"aggregate_state": agg,
			"day":             k.day,
			"instruments":     ins,
			"site":            k.site,
		}
		if merged == nil {
			row["merged_phase_deg"] = nil
		} else {
			row["merged_phase_deg"] = round6(*merged)
		}
		siteDays = append(siteDays, row)
	}

	summary := map[string]any{
		"days_span":        []int{minDay, maxDay},
		"rows_ingested":    len(rows),
		"site_day_rows":    len(siteDays),
		"sites_considered": len(bySite),
		"state_counts":     stateCounts,
	}

	report := map[string]any{
		"site_days": siteDays,
		"summary":   summary,
	}
	raw, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	raw = append(raw, '\n')
	return os.WriteFile(filepath.Join(outDir, "report.json"), raw, 0o644)
}

func classifyRow(
	r rowTagged,
	prevDay int,
	hasPrev bool,
	minQ float64,
	grace int,
	siteCD map[string]int,
	instQD map[string]int,
	cool map[string][2]int,
	siteFloor map[string]int,
) string {
	if md, ok := siteFloor[r.Site]; ok && r.Day < md {
		return "below_floor"
	}
	if d0, ok := siteCD[r.Site]; ok && r.Day >= d0 {
		return "compromised"
	}
	if d0, ok := instQD[r.Instrument]; ok && r.Day >= d0 {
		return "quarantined"
	}
	if r.Quality < minQ {
		return "weak"
	}
	if hasPrev && r.Day-prevDay > grace {
		return "hold"
	}
	if w, ok := cool[r.Site]; ok && r.Day >= w[0] && r.Day <= w[1] {
		return "cool"
	}
	return "ok"
}

func severity(s string) int {
	order := []string{"missing", "ok", "cool", "hold", "weak", "below_floor", "quarantined", "compromised"}
	for i, v := range order {
		if v == s {
			return i
		}
	}
	return 0
}

func aggregateState(rs []rowTagged) string {
	best := "ok"
	for _, r := range rs {
		if severity(r.State) > severity(best) {
			best = r.State
		}
	}
	return best
}

func mergePhases(rs []rowTagged, minQ, madK float64, maskPol map[string]int, poolMasks map[string]int) *float64 {
	type cand struct {
		phi float64
		ins string
	}
	var pool []cand
	for _, r := range rs {
		if r.Quality < minQ {
			continue
		}
		switch r.State {
		case "ok", "cool":
			pool = append(pool, cand{phi: r.PhaseDeg, ins: r.Instrument})
		default:
		}
	}
	if len(pool) == 0 {
		return nil
	}

	phases := make([]float64, len(pool))
	for i, c := range pool {
		phases[i] = c.phi
	}
	mean0 := circularMeanDeg(phases)

	devs := make([]float64, len(pool))
	for i, c := range pool {
		devs[i] = angDiffDeg(mean0, c.phi)
	}
	mad := median(devs)
	thr := madK * math.Max(mad, 0.05)

	var kept []float64
	for i, c := range pool {
		bit := maskPol[c.ins]
		pm := poolMasks[c.ins]
		skip := bit != 0 && (pm&bit) != 0
		if skip || devs[i] <= thr {
			kept = append(kept, c.phi)
		}
	}
	if len(kept) == 0 {
		kept = phases
	}
	m := circularMeanDeg(kept)
	return &m
}

func angDiffDeg(a, b float64) float64 {
	d := math.Mod(math.Abs(a-b), 360.0)
	if d > 180 {
		d = 360 - d
	}
	return d
}

func circularMeanDeg(xs []float64) float64 {
	var sx, sy float64
	for _, d := range xs {
		r := d * math.Pi / 180.0
		sx += math.Cos(r)
		sy += math.Sin(r)
	}
	ang := math.Atan2(sy, sx) * 180.0 / math.Pi
	return math.Mod(ang+360.0, 360.0)
}

func median(xs []float64) float64 {
	if len(xs) == 0 {
		return 0
	}
	cp := append([]float64(nil), xs...)
	sort.Float64s(cp)
	n := len(cp)
	if n%2 == 1 {
		return cp[n/2]
	}
	return (cp[n/2-1] + cp[n/2]) / 2
}

func round6(x float64) float64 {
	v, _ := strconv.ParseFloat(strconv.FormatFloat(x, 'f', 6, 64), 64)
	return v
}

func readJSONMap(path string) (map[string]any, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		return nil, err
	}
	return m, nil
}

func num(v any) float64 {
	switch t := v.(type) {
	case float64:
		return t
	case int:
		return float64(t)
	case int64:
		return float64(t)
	case json.Number:
		f, _ := t.Float64()
		return f
	default:
		return 0
	}
}
