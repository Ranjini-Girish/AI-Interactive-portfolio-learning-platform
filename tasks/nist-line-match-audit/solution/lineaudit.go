package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
)

type PoolState struct {
	SigmaMultiplierMilli       int       `json:"sigma_multiplier_milli"`
	MatchSlackNm               int       `json:"match_slack_nm"`
	WeakRelIntThreshold        int       `json:"weak_rel_int_threshold"`
	MinAmpForWeak              float64   `json:"min_amp_for_weak"`
	ElementTieOrder            []string  `json:"element_tie_order"`
	MinSameElementSeparationNm int       `json:"min_same_element_separation_nm"`
}

type InstrumentsFile struct {
	Instruments map[string]struct {
		BaseBiasNm int `json:"base_bias_nm"`
	} `json:"instruments"`
}

type IncidentEvent struct {
	Kind          string `json:"kind"`
	Accepted      *bool  `json:"accepted"`
	EffectiveDay  *int   `json:"effective_day"`
	InstrumentID  string `json:"instrument_id"`
	LineID        string `json:"line_id"`
	DeltaBiasNm   *int   `json:"delta_bias_nm"`
}

type IncidentLog struct {
	Events []IncidentEvent `json:"events"`
}

type CatalogFile struct {
	Element string `json:"element"`
	Lines   []struct {
		LineID  string `json:"line_id"`
		WaveNm  int    `json:"wave_nm"`
		RelInt  int    `json:"rel_int"`
		Label   string `json:"label"`
	} `json:"lines"`
}

type ObsFile struct {
	RunID         string `json:"run_id"`
	InstrumentID  string `json:"instrument_id"`
	RunDay        int    `json:"run_day"`
	Peaks         []struct {
		PeakIndex int     `json:"peak_index"`
		WaveNm    int     `json:"wave_nm"`
		SigmaNm   float64 `json:"sigma_nm"`
		Amp       float64 `json:"amp"`
	} `json:"peaks"`
}

type CatalogLine struct {
	LineID  string
	Element string
	WaveNm  int
	RelInt  int
}

type PeakOut struct {
	CatalogWaveNm *int    `json:"catalog_wave_nm"`
	DeltaNm       *int    `json:"delta_nm"`
	LineID        *string `json:"line_id"`
	PeakIndex     int     `json:"peak_index"`
	Status        string  `json:"status"`
}

type RunOut struct {
	InstrumentID string    `json:"instrument_id"`
	Peaks        []PeakOut `json:"peaks"`
	RunDay       int       `json:"run_day"`
	RunID        string    `json:"run_id"`
}

func main() {
	dataDir := os.Getenv("NLMA_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/nist_lines"
	}
	auditDir := os.Getenv("NLMA_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := run(dataDir, auditDir); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func run(dataDir, auditDir string) error {
	poolRaw, err := os.ReadFile(filepath.Join(dataDir, "pool_state.json"))
	if err != nil {
		return err
	}
	var pool PoolState
	if err := json.Unmarshal(poolRaw, &pool); err != nil {
		return err
	}
	instRaw, err := os.ReadFile(filepath.Join(dataDir, "instruments.json"))
	if err != nil {
		return err
	}
	var instFile InstrumentsFile
	if err := json.Unmarshal(instRaw, &instFile); err != nil {
		return err
	}
	incRaw, err := os.ReadFile(filepath.Join(dataDir, "incident_log.json"))
	if err != nil {
		return err
	}
	var inc IncidentLog
	if err := json.Unmarshal(incRaw, &inc); err != nil {
		return err
	}

	catGlob, err := filepath.Glob(filepath.Join(dataDir, "catalog", "*.json"))
	if err != nil {
		return err
	}
	sort.Strings(catGlob)
	var catalog []CatalogLine
	for _, p := range catGlob {
		b, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		var cf CatalogFile
		if err := json.Unmarshal(b, &cf); err != nil {
			return err
		}
		for _, ln := range cf.Lines {
			catalog = append(catalog, CatalogLine{
				LineID:  ln.LineID,
				Element: cf.Element,
				WaveNm:  ln.WaveNm,
				RelInt:  ln.RelInt,
			})
		}
	}
	sort.Slice(catalog, func(i, j int) bool {
		a, b := catalog[i], catalog[j]
		if a.WaveNm != b.WaveNm {
			return a.WaveNm < b.WaveNm
		}
		if a.Element != b.Element {
			return a.Element < b.Element
		}
		return a.LineID < b.LineID
	})

	obsGlob, err := filepath.Glob(filepath.Join(dataDir, "observations", "*.json"))
	if err != nil {
		return err
	}
	sort.Strings(obsGlob)

	elementRank := map[string]int{}
	for i, e := range pool.ElementTieOrder {
		elementRank[e] = i
	}

	ignored := 0
	var biasShifts []IncidentEvent
	var suppress []IncidentEvent
	for _, ev := range inc.Events {
		acc := true
		if ev.Accepted != nil && !*ev.Accepted {
			acc = false
		}
		if !acc {
			ignored++
			continue
		}
		switch ev.Kind {
		case "instrument_bias_shift":
			if ev.InstrumentID == "" || ev.EffectiveDay == nil || ev.DeltaBiasNm == nil {
				ignored++
				continue
			}
			if _, ok := instFile.Instruments[ev.InstrumentID]; !ok {
				ignored++
				continue
			}
			biasShifts = append(biasShifts, ev)
		case "catalog_line_suppress":
			if ev.LineID == "" || ev.EffectiveDay == nil {
				ignored++
				continue
			}
			okID := false
			for _, ln := range catalog {
				if ln.LineID == ev.LineID {
					okID = true
					break
				}
			}
			if !okID {
				ignored++
				continue
			}
			suppress = append(suppress, ev)
		default:
			ignored++
		}
	}

	lineIDs := map[string]bool{}
	for _, ln := range catalog {
		lineIDs[ln.LineID] = true
	}

	maxRunDay := 0
	for _, p := range obsGlob {
		b, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		var o ObsFile
		if err := json.Unmarshal(b, &o); err != nil {
			return err
		}
		if o.RunDay > maxRunDay {
			maxRunDay = o.RunDay
		}
	}

	isSuppressed := func(lineID string, runDay int) bool {
		for _, ev := range suppress {
			if ev.LineID != lineID {
				continue
			}
			if *ev.EffectiveDay <= runDay {
				return true
			}
		}
		return false
	}

	biasFor := func(inst string, runDay int) int {
		base := instFile.Instruments[inst].BaseBiasNm
		sum := base
		for _, ev := range biasShifts {
			if ev.InstrumentID != inst {
				continue
			}
			if *ev.EffectiveDay <= runDay {
				sum += *ev.DeltaBiasNm
			}
		}
		return sum
	}

	halfWidth := func(sigma float64) int {
		prod := float64(pool.SigmaMultiplierMilli) * sigma / 1000.0
		return pool.MatchSlackNm + int(math.Ceil(prod))
	}

	elemIdx := func(el string) int {
		if v, ok := elementRank[el]; ok {
			return v
		}
		return len(pool.ElementTieOrder) + 1
	}

	matchCount := map[string]int{}
	for k := range lineIDs {
		matchCount[k] = 0
	}

	var runsOut []RunOut
	peaksTotal := 0
	matchedC, unmatchedC, weakC, blendC := 0, 0, 0, 0

	for _, p := range obsGlob {
		b, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		var o ObsFile
		if err := json.Unmarshal(b, &o); err != nil {
			return err
		}
		sort.Slice(o.Peaks, func(i, j int) bool { return o.Peaks[i].PeakIndex < o.Peaks[j].PeakIndex })

		bias := biasFor(o.InstrumentID, o.RunDay)
		claimed := map[string]bool{}
		var peaksOut []PeakOut

		for _, pk := range o.Peaks {
			peaksTotal++
			adj := pk.WaveNm + bias
			hw := halfWidth(pk.SigmaNm)

			inWindow := func(ln CatalogLine) bool {
				if isSuppressed(ln.LineID, o.RunDay) {
					return false
				}
				d := ln.WaveNm - adj
				if d < 0 {
					d = -d
				}
				return d <= hw
			}

			var cand0 []CatalogLine
			for _, ln := range catalog {
				if inWindow(ln) {
					cand0 = append(cand0, ln)
				}
			}

			ampOK := func(ln CatalogLine) bool {
				return ln.RelInt >= pool.WeakRelIntThreshold || pk.Amp >= pool.MinAmpForWeak
			}

			var candS []CatalogLine
			for _, ln := range cand0 {
				if ampOK(ln) {
					candS = append(candS, ln)
				}
			}

			blended := func(lines []CatalogLine) bool {
				for i := 0; i < len(lines); i++ {
					for j := i + 1; j < len(lines); j++ {
						a, b := lines[i], lines[j]
						if a.Element != b.Element {
							continue
						}
						d := a.WaveNm - b.WaveNm
						if d < 0 {
							d = -d
						}
						if d < pool.MinSameElementSeparationNm {
							return true
						}
					}
				}
				return false
			}

			if len(candS) > 0 && blended(candS) {
				blendC++
				peaksOut = append(peaksOut, PeakOut{
					CatalogWaveNm: nil,
					DeltaNm:       nil,
					LineID:        nil,
					PeakIndex:     pk.PeakIndex,
					Status:        "blended_conflict",
				})
				continue
			}

			if len(candS) == 0 {
				if len(cand0) > 0 {
					weakC++
					peaksOut = append(peaksOut, PeakOut{
						CatalogWaveNm: nil,
						DeltaNm:       nil,
						LineID:        nil,
						PeakIndex:     pk.PeakIndex,
						Status:        "weak_suppressed",
					})
				} else {
					unmatchedC++
					peaksOut = append(peaksOut, PeakOut{
						CatalogWaveNm: nil,
						DeltaNm:       nil,
						LineID:        nil,
						PeakIndex:     pk.PeakIndex,
						Status:        "unmatched",
					})
				}
				continue
			}

			best := -1
			for idx, ln := range candS {
				if claimed[ln.LineID] {
					continue
				}
				if best < 0 {
					best = idx
					continue
				}
				cur, win := candS[idx], candS[best]
				cd := cur.WaveNm - adj
				if cd < 0 {
					cd = -cd
				}
				wd := win.WaveNm - adj
				if wd < 0 {
					wd = -wd
				}
				if cd != wd {
					if cd < wd {
						best = idx
					}
					continue
				}
				if cur.RelInt != win.RelInt {
					if cur.RelInt > win.RelInt {
						best = idx
					}
					continue
				}
				if cur.WaveNm != win.WaveNm {
					if cur.WaveNm < win.WaveNm {
						best = idx
					}
					continue
				}
				ei, ej := elemIdx(cur.Element), elemIdx(win.Element)
				if ei != ej {
					if ei < ej {
						best = idx
					}
					continue
				}
				if cur.LineID < win.LineID {
					best = idx
				}
			}

			if best < 0 {
				unmatchedC++
				peaksOut = append(peaksOut, PeakOut{
					CatalogWaveNm: nil,
					DeltaNm:       nil,
					LineID:        nil,
					PeakIndex:     pk.PeakIndex,
					Status:        "unmatched",
				})
				continue
			}

			win := candS[best]
			claimed[win.LineID] = true
			matchedC++
			matchCount[win.LineID]++
			d := win.WaveNm - adj
			lid := win.LineID
			wv := win.WaveNm
			peaksOut = append(peaksOut, PeakOut{
				CatalogWaveNm: &wv,
				DeltaNm:       &d,
				LineID:        &lid,
				PeakIndex:     pk.PeakIndex,
				Status:        "matched",
			})
		}

		runsOut = append(runsOut, RunOut{
			RunID:        o.RunID,
			InstrumentID: o.InstrumentID,
			RunDay:       o.RunDay,
			Peaks:        peaksOut,
		})
	}

	sort.Slice(runsOut, func(i, j int) bool { return runsOut[i].RunID < runsOut[j].RunID })

	type LineUtil struct {
		LineID     string `json:"line_id"`
		MatchCount int    `json:"match_count"`
	}
	var lineUtil []LineUtil
	for _, ln := range catalog {
		lineUtil = append(lineUtil, LineUtil{LineID: ln.LineID, MatchCount: matchCount[ln.LineID]})
	}
	sort.Slice(lineUtil, func(i, j int) bool { return lineUtil[i].LineID < lineUtil[j].LineID })

	type InstState struct {
		BaseBiasNm           int    `json:"base_bias_nm"`
		FinalBiasNm          int    `json:"final_bias_nm"`
		IncidentDeltaTotalNm int    `json:"incident_delta_total_nm"`
		InstrumentID         string `json:"instrument_id"`
	}
	instSeen := map[string]bool{}
	maxDayByInst := map[string]int{}
	for _, ro := range runsOut {
		instSeen[ro.InstrumentID] = true
		if ro.RunDay > maxDayByInst[ro.InstrumentID] {
			maxDayByInst[ro.InstrumentID] = ro.RunDay
		}
	}
	var instStates []InstState
	for id := range instFile.Instruments {
		if !instSeen[id] {
			continue
		}
		base := instFile.Instruments[id].BaseBiasNm
		totalDelta := 0
		for _, ev := range biasShifts {
			if ev.InstrumentID != id {
				continue
			}
			applies := false
			for _, ro := range runsOut {
				if ro.InstrumentID != id {
					continue
				}
				if ro.RunDay >= *ev.EffectiveDay {
					applies = true
					break
				}
			}
			if applies {
				totalDelta += *ev.DeltaBiasNm
			}
		}
		final := biasFor(id, maxDayByInst[id])
		instStates = append(instStates, InstState{
			InstrumentID:         id,
			BaseBiasNm:           base,
			IncidentDeltaTotalNm: totalDelta,
			FinalBiasNm:          final,
		})
	}
	sort.Slice(instStates, func(i, j int) bool { return instStates[i].InstrumentID < instStates[j].InstrumentID })

	type SupEntry struct {
		ActiveOnLastDay bool   `json:"active_on_last_day"`
		EffectiveDay    int    `json:"effective_day"`
		LineID          string `json:"line_id"`
	}
	var supOut []SupEntry
	supMin := map[string]int{}
	for _, ev := range suppress {
		d := *ev.EffectiveDay
		if prev, ok := supMin[ev.LineID]; !ok || d < prev {
			supMin[ev.LineID] = d
		}
	}
	for lid, d := range supMin {
		active := d <= maxRunDay
		supOut = append(supOut, SupEntry{LineID: lid, EffectiveDay: d, ActiveOnLastDay: active})
	}
	sort.Slice(supOut, func(i, j int) bool { return supOut[i].LineID < supOut[j].LineID })

	summary := map[string]int{
		"catalog_lines_loaded":   len(catalog),
		"ignored_incidents":      ignored,
		"max_run_day":            maxRunDay,
		"peaks_blended_conflict": blendC,
		"peaks_matched":          matchedC,
		"peaks_total":            peaksTotal,
		"peaks_unmatched":        unmatchedC,
		"peaks_weak_suppressed":  weakC,
		"runs_processed":         len(obsGlob),
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	if err := writeIndented(filepath.Join(auditDir, "run_matches.json"), map[string]any{"runs": runsOut}); err != nil {
		return err
	}
	if err := writeIndented(filepath.Join(auditDir, "line_utilization.json"), map[string]any{"lines": lineUtil}); err != nil {
		return err
	}
	if err := writeIndented(filepath.Join(auditDir, "instrument_bias_state.json"), map[string]any{"instruments": instStates}); err != nil {
		return err
	}
	if err := writeIndented(filepath.Join(auditDir, "suppressed_catalog.json"), map[string]any{"entries": supOut}); err != nil {
		return err
	}
	if err := writeIndented(filepath.Join(auditDir, "summary.json"), summary); err != nil {
		return err
	}
	return nil
}

func writeIndented(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}
