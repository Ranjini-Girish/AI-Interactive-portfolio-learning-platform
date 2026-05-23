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

type policy struct {
	BucketDays int `json:"bucket_days"`
	GraceDays  int `json:"grace_days"`
	ValueFloor int `json:"value_floor"`
}

type poolState struct {
	CurrentDay      int `json:"current_day"`
	WindowEndDay    int `json:"window_end_day"`
	WindowStartDay  int `json:"window_start_day"`
}

type sample struct {
	Day   int `json:"day"`
	Value int `json:"value"`
}

type metricSeries struct {
	Samples      []sample `json:"samples"`
	SeriesID     string   `json:"series_id"`
	SourceID     string   `json:"source_id"`
	WatermarkDay int      `json:"watermark_day"`
}

type incidentEvent struct {
	Accepted bool   `json:"accepted"`
	Day      int    `json:"day"`
	Kind     string `json:"kind"`
	SourceID string `json:"source_id"`
}

type overlayState struct {
	MinSampleCount int
	BucketCap      int
	ExcludeSources map[string]struct{}
}

type anchorNote struct {
	SeriesID      string
	ForcedStatus  string
	Order         int
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	data := getenv("RWM_DATA_DIR", "/app/rollupmerge")
	outd := getenv("RWM_AUDIT_DIR", "/app/audit")
	if err := run(data, outd); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func run(dataDir, auditDir string) error {
	var pol policy
	if err := readJSON(filepath.Join(dataDir, "policy.json"), &pol); err != nil {
		return err
	}
	var ps poolState
	if err := readJSON(filepath.Join(dataDir, "pool_state.json"), &ps); err != nil {
		return err
	}
	if pol.BucketDays <= 0 {
		return fmt.Errorf("invalid bucket_days")
	}

	ov, err := loadOverlays(filepath.Join(dataDir, "overlays"))
	if err != nil {
		return err
	}
	compromised, err := loadCompromisedSources(filepath.Join(dataDir, "incidents.json"))
	if err != nil {
		return err
	}
	anchors, err := loadAnchors(dataDir)
	if err != nil {
		return err
	}

	seriesList, err := loadSeries(filepath.Join(dataDir, "series"))
	if err != nil {
		return err
	}
	sort.Slice(seriesList, func(i, j int) bool {
		return seriesList[i].SeriesID < seriesList[j].SeriesID
	})

	seriesSet := map[string]struct{}{}
	for _, s := range seriesList {
		seriesSet[s.SeriesID] = struct{}{}
	}

	forced := map[string]string{}
	sort.Slice(anchors, func(i, j int) bool {
		if anchors[i].SeriesID != anchors[j].SeriesID {
			return anchors[i].SeriesID < anchors[j].SeriesID
		}
		return anchors[i].Order < anchors[j].Order
	})
	for _, a := range anchors {
		if _, ok := seriesSet[a.SeriesID]; ok {
			forced[a.SeriesID] = a.ForcedStatus
		}
	}

	complete := completeBuckets(ps.WindowStartDay, ps.WindowEndDay, pol.BucketDays)

	type contrib struct {
		seriesID string
		sum      int
	}

	bucketContrib := map[int][]contrib{}
	profiles := make([]map[string]any, 0, len(seriesList))
	staleRows := make([]map[string]any, 0)
	compromiseSeries := make([]map[string]any, 0)
	staleTotal := 0
	quarantinedTotal := 0

	for _, s := range seriesList {
		participating := filterSamples(s.Samples, ps, pol)
		_, quarantined := compromised[s.SourceID]
		stale := ps.CurrentDay-s.WatermarkDay > pol.GraceDays

		status := "ok"
		switch {
		case quarantined:
			status = "quarantined"
			quarantinedTotal++
		case forced[s.SeriesID] == "hold":
			status = "hold"
		case stale:
			status = "stale"
		}
		if stale {
			staleTotal++
		}

		excluded := false
		if _, ok := ov.ExcludeSources[s.SourceID]; ok {
			excluded = true
		}

		completeForSeries := make([]int, 0)
		windowSum := 0
		if !quarantined {
			for _, bStart := range complete {
				cnt, sum := bucketStats(participating, bStart, pol.BucketDays)
				if cnt >= ov.MinSampleCount {
					completeForSeries = append(completeForSeries, bStart)
					windowSum += sum
					if !excluded && !quarantined {
						bucketContrib[bStart] = append(bucketContrib[bStart], contrib{
							seriesID: s.SeriesID,
							sum:      sum,
						})
					}
				}
			}
		}

		var sumAny any = windowSum
		if quarantined {
			sumAny = nil
		}

		profiles = append(profiles, map[string]any{
			"complete_buckets": completeForSeries,
			"series_id":        s.SeriesID,
			"source_id":        s.SourceID,
			"stale_flag":       stale,
			"status":           status,
			"watermark_day":    s.WatermarkDay,
			"window_sum":       sumAny,
		})

		if stale && !quarantined {
			staleRows = append(staleRows, map[string]any{
				"series_id":     s.SeriesID,
				"source_id":     s.SourceID,
				"watermark_day": s.WatermarkDay,
			})
		}
		if quarantined {
			compromiseSeries = append(compromiseSeries, map[string]any{
				"series_id":     s.SeriesID,
				"source_id":     s.SourceID,
				"watermark_day": s.WatermarkDay,
			})
		}
	}

	bucketsOut := make([]map[string]any, 0, len(complete))
	for _, bStart := range complete {
		contribs := bucketContrib[bStart]
		sort.Slice(contribs, func(i, j int) bool {
			return contribs[i].seriesID < contribs[j].seriesID
		})
		if len(contribs) > ov.BucketCap {
			contribs = contribs[:ov.BucketCap]
		}
		rows := make([]map[string]any, 0, len(contribs))
		for _, c := range contribs {
			rows = append(rows, map[string]any{
				"series_id": c.seriesID,
				"sum":       c.sum,
			})
		}
		bucketsOut = append(bucketsOut, map[string]any{
			"bucket_start": bStart,
			"series":       rows,
		})
	}

	sourceSet := make([]string, 0, len(compromised))
	for src := range compromised {
		sourceSet = append(sourceSet, src)
	}
	sort.Strings(sourceSet)

	sort.Slice(staleRows, func(i, j int) bool {
		return fmt.Sprint(staleRows[i]["series_id"]) < fmt.Sprint(staleRows[j]["series_id"])
	})

	payloads := map[string]any{
		"bucket_rollups.json": map[string]any{
			"buckets":           bucketsOut,
			"window_end_day":    ps.WindowEndDay,
			"window_start_day":  ps.WindowStartDay,
		},
		"compromise_report.json": map[string]any{
			"series":  compromiseSeries,
			"sources": sourceSet,
		},
		"series_profiles.json": map[string]any{
			"series":           profiles,
			"window_end_day":   ps.WindowEndDay,
			"window_start_day": ps.WindowStartDay,
		},
		"stale_report.json": map[string]any{"series": staleRows},
		"summary.json": map[string]any{
			"bucket_count":            len(complete),
			"complete_bucket_starts":  complete,
			"current_day":             ps.CurrentDay,
			"quarantined_total":       quarantinedTotal,
			"series_total":            len(seriesList),
			"stale_total":             staleTotal,
			"window_end_day":          ps.WindowEndDay,
			"window_start_day":        ps.WindowStartDay,
		},
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	for name, payload := range payloads {
		if err := writeJSON(filepath.Join(auditDir, name), payload); err != nil {
			return err
		}
	}
	return nil
}

func completeBuckets(ws, we, bd int) []int {
	out := make([]int, 0)
	for b := ws; b+bd-1 <= we; b += bd {
		out = append(out, b)
	}
	return out
}

func filterSamples(samples []sample, ps poolState, pol policy) []sample {
	out := make([]sample, 0, len(samples))
	for _, s := range samples {
		if s.Day < ps.WindowStartDay || s.Day > ps.WindowEndDay {
			continue
		}
		if s.Value < pol.ValueFloor {
			continue
		}
		out = append(out, s)
	}
	return out
}

func bucketStats(samples []sample, bucketStart, bucketDays int) (count, sum int) {
	end := bucketStart + bucketDays - 1
	for _, s := range samples {
		if s.Day >= bucketStart && s.Day <= end {
			count++
			sum += s.Value
		}
	}
	return count, sum
}

func loadOverlays(dir string) (overlayState, error) {
	st := overlayState{
		MinSampleCount: 1,
		BucketCap:      1 << 30,
		ExcludeSources: map[string]struct{}{},
	}
	ents, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return st, nil
		}
		return st, err
	}
	names := make([]string, 0)
	for _, e := range ents {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".json") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		var raw map[string]json.RawMessage
		if err := readJSON(filepath.Join(dir, name), &raw); err != nil {
			return st, err
		}
		if v, ok := raw["min_sample_count"]; ok {
			var n int
			if json.Unmarshal(v, &n) == nil && n > 0 {
				st.MinSampleCount = n
			}
		}
		if v, ok := raw["bucket_cap"]; ok {
			var n int
			if json.Unmarshal(v, &n) == nil && n > 0 {
				st.BucketCap = n
			}
		}
		if v, ok := raw["exclude_sources"]; ok {
			var ids []string
			if json.Unmarshal(v, &ids) == nil {
				for _, id := range ids {
					st.ExcludeSources[id] = struct{}{}
				}
			}
		}
	}
	return st, nil
}

func loadCompromisedSources(path string) (map[string]struct{}, error) {
	out := map[string]struct{}{}
	var raw struct {
		Events []incidentEvent `json:"events"`
	}
	if err := readJSON(path, &raw); err != nil {
		return out, err
	}
	for _, ev := range raw.Events {
		if ev.Accepted && ev.Kind == "source_compromise" {
			out[ev.SourceID] = struct{}{}
		}
	}
	return out, nil
}

func loadAnchors(dataDir string) ([]anchorNote, error) {
	var notes []anchorNote
	order := 0
	anchorDir := filepath.Join(dataDir, "anchors")
	ents, err := os.ReadDir(anchorDir)
	if err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	names := make([]string, 0)
	for _, e := range ents {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".txt") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		b, err := os.ReadFile(filepath.Join(anchorDir, name))
		if err != nil {
			return nil, err
		}
		for _, line := range strings.Split(string(b), "\n") {
			line = strings.TrimSpace(line)
			if line == "" {
				continue
			}
			parts := strings.Fields(line)
			if len(parts) < 2 {
				continue
			}
			notes = append(notes, anchorNote{
				SeriesID:     parts[0],
				ForcedStatus: parts[1],
				Order:        order,
			})
			order++
		}
	}
	return notes, nil
}

func loadSeries(dir string) ([]metricSeries, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make([]metricSeries, 0)
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var s metricSeries
		if err := readJSON(filepath.Join(dir, e.Name()), &s); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no series")
	}
	return out, nil
}

func readJSON(path string, v any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, v)
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
