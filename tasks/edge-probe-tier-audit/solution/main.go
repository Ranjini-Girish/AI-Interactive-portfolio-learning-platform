package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type policy struct {
	FailedStatusFloor int     `json:"failed_status_floor"`
	MadK              float64 `json:"mad_k"`
	RttFastMaxMs      int     `json:"rtt_fast_max_ms"`
	RttModerateMaxMs  int     `json:"rtt_moderate_max_ms"`
}

type poolState struct {
	WindowMs int64 `json:"window_ms"`
}

type incidents struct {
	Notes []struct {
		EndpointID string `json:"endpoint_id"`
		ForcedTier string `json:"forced_tier"`
	} `json:"notes"`
}

type probe struct {
	BytesDown  int64  `json:"bytes_down"`
	EndpointID string `json:"endpoint_id"`
	Region     string `json:"region"`
	RttMs      int64  `json:"rtt_ms"`
	StatusCode int    `json:"status_code"`
}

type incidentNote struct {
	EndpointID string
	ForcedTier string
	Order      int
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	data := getenv("EPT_DATA_DIR", "/app/edgeprobes")
	outd := getenv("EPT_AUDIT_DIR", "/app/audit")
	if err := run(data, outd); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func run(dataDir, auditDir string) error {
	polRaw, err := os.ReadFile(filepath.Join(dataDir, "policy.json"))
	if err != nil {
		return err
	}
	var pol policy
	if err := json.Unmarshal(polRaw, &pol); err != nil {
		return err
	}

	psRaw, err := os.ReadFile(filepath.Join(dataDir, "pool_state.json"))
	if err != nil {
		return err
	}
	var ps poolState
	if err := json.Unmarshal(psRaw, &ps); err != nil {
		return err
	}
	if ps.WindowMs <= 0 {
		return fmt.Errorf("invalid window")
	}

	regionFloors, madExclude, err := loadAncillary(filepath.Join(dataDir, "ancillary"))
	if err != nil {
		return err
	}

	notes, err := loadIncidentNotes(dataDir)
	if err != nil {
		return err
	}

	probes, err := loadProbes(filepath.Join(dataDir, "probes"))
	if err != nil {
		return err
	}
	sort.Slice(probes, func(i, j int) bool { return probes[i].EndpointID < probes[j].EndpointID })

	probeSet := map[string]struct{}{}
	for _, p := range probes {
		probeSet[p.EndpointID] = struct{}{}
	}

	forced := map[string]string{}
	sort.Slice(notes, func(i, j int) bool {
		if notes[i].EndpointID != notes[j].EndpointID {
			return notes[i].EndpointID < notes[j].EndpointID
		}
		return notes[i].Order < notes[j].Order
	})
	for _, n := range notes {
		if _, ok := probeSet[n.EndpointID]; ok {
			forced[n.EndpointID] = n.ForcedTier
		}
	}

	baseTier := func(p probe) string {
		if p.StatusCode >= pol.FailedStatusFloor {
			return "FAILED"
		}
		if p.RttMs <= int64(pol.RttFastMaxMs) {
			return "FAST"
		}
		if p.RttMs <= int64(pol.RttModerateMaxMs) {
			return "MODERATE"
		}
		return "SLOW"
	}

	demote := func(tier string) string {
		switch tier {
		case "FAST":
			return "MODERATE"
		case "MODERATE":
			return "SLOW"
		default:
			return tier
		}
	}

	tierAfterIncident := func(p probe) string {
		t := baseTier(p)
		if ft, ok := forced[p.EndpointID]; ok {
			return ft
		}
		return t
	}

	finalTier := func(p probe, kbps int64) (string, bool) {
		t := tierAfterIncident(p)
		if t == "FAILED" {
			return t, false
		}
		floor, ok := regionFloors[p.Region]
		if !ok || kbps >= floor {
			return t, false
		}
		d := demote(t)
		return d, d != t
	}

	regionMAD := buildRegionMAD(probes, pol, madExclude)

	outlier := func(p probe) (bool, int64, int64, int64) {
		st, ok := regionMAD[p.Region]
		if !ok || !st.usable {
			return false, 0, 0, 0
		}
		if p.StatusCode >= pol.FailedStatusFloor {
			return false, 0, 0, 0
		}
		if _, ex := madExclude[p.EndpointID]; ex {
			return false, 0, 0, 0
		}
		hi := float64(st.med) + pol.MadK*float64(st.mad)
		lo := float64(st.med) - pol.MadK*float64(st.mad)
		if float64(p.RttMs) > hi || float64(p.RttMs) < lo {
			dev := int64(math.Abs(float64(p.RttMs - st.med)))
			return true, st.med, st.mad, dev
		}
		return false, 0, 0, 0
	}

	profiles := make([]map[string]any, 0, len(probes))
	regions := map[string]struct{}{}
	failed := 0
	anomalyTotal := 0
	demotedTotal := 0
	events := make([]map[string]any, 0)

	for _, p := range probes {
		regions[p.Region] = struct{}{}
		kbps := (p.BytesDown * 8) / ps.WindowMs
		tier, demoted := finalTier(p, kbps)
		if demoted {
			demotedTotal++
		}
		if tier == "FAILED" {
			failed++
		}
		anom, med, mad, dev := outlier(p)
		if anom {
			anomalyTotal++
			events = append(events, map[string]any{
				"deviation_ms":     dev,
				"endpoint_id":      p.EndpointID,
				"global_mad_ms":    mad,
				"global_median_ms": med,
				"rtt_ms":           p.RttMs,
			})
		}
		profiles = append(profiles, map[string]any{
			"anomaly_flag": anom,
			"endpoint_id":  p.EndpointID,
			"kbps":         kbps,
			"region":       p.Region,
			"rtt_ms":       p.RttMs,
			"status_code":  p.StatusCode,
			"tier":         tier,
		})
	}

	sort.Slice(events, func(i, j int) bool {
		return fmt.Sprint(events[i]["endpoint_id"]) < fmt.Sprint(events[j]["endpoint_id"])
	})

	tiersByRegion := map[string]map[string]int{}
	for _, p := range probes {
		kbps := (p.BytesDown * 8) / ps.WindowMs
		t, _ := finalTier(p, kbps)
		if _, ok := tiersByRegion[p.Region]; !ok {
			tiersByRegion[p.Region] = map[string]int{
				"FAILED": 0, "FAST": 0, "MODERATE": 0, "SLOW": 0,
			}
		}
		tiersByRegion[p.Region][t]++
	}
	regNames := make([]string, 0, len(tiersByRegion))
	for r := range tiersByRegion {
		regNames = append(regNames, r)
	}
	sort.Strings(regNames)
	tiersOut := map[string]any{}
	for _, r := range regNames {
		row := tiersByRegion[r]
		tiersOut[r] = map[string]any{
			"FAILED": row["FAILED"], "FAST": row["FAST"],
			"MODERATE": row["MODERATE"], "SLOW": row["SLOW"],
		}
	}

	madRegions := make([]map[string]any, 0, len(regionMAD))
	for region, st := range regionMAD {
		entry := map[string]any{
			"region":      region,
			"sample_size": st.sampleSize,
		}
		if st.usable {
			entry["global_mad_ms"] = st.mad
			entry["global_median_ms"] = st.med
		} else {
			entry["global_mad_ms"] = nil
			entry["global_median_ms"] = nil
		}
		madRegions = append(madRegions, entry)
	}
	sort.Slice(madRegions, func(i, j int) bool {
		return fmt.Sprint(madRegions[i]["region"]) < fmt.Sprint(madRegions[j]["region"])
	})

	segList := make([]string, 0, len(regions))
	for r := range regions {
		segList = append(segList, r)
	}
	sort.Strings(segList)

	summary := map[string]any{
		"anomaly_total":            anomalyTotal,
		"endpoints_total":          len(probes),
		"failed_total":             failed,
		"regions":                  segList,
		"throughput_demoted_total": demotedTotal,
		"window_ms":                ps.WindowMs,
	}

	payloads := map[string]any{
		"anomaly_events.json":    map[string]any{"events": events},
		"endpoint_profiles.json": map[string]any{"endpoints": profiles, "window_ms": ps.WindowMs},
		"mad_summary.json":       map[string]any{"regions": madRegions},
		"summary.json":           summary,
		"tier_rollups.json":      map[string]any{"tiers": tiersOut, "window_ms": ps.WindowMs},
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

type madStats struct {
	med, mad   int64
	usable     bool
	sampleSize int
}

func buildRegionMAD(probes []probe, pol policy, madExclude map[string]struct{}) map[string]madStats {
	byRegion := map[string][]int64{}
	for _, p := range probes {
		if p.StatusCode >= pol.FailedStatusFloor {
			continue
		}
		if _, ex := madExclude[p.EndpointID]; ex {
			continue
		}
		byRegion[p.Region] = append(byRegion[p.Region], p.RttMs)
	}
	out := map[string]madStats{}
	for region, sample := range byRegion {
		st := madStats{sampleSize: len(sample)}
		if len(sample) < 3 {
			out[region] = st
			continue
		}
		sorted := append([]int64(nil), sample...)
		sort.Slice(sorted, func(i, j int) bool { return sorted[i] < sorted[j] })
		med := medianInt64(sorted)
		devs := make([]int64, len(sample))
		for i, v := range sample {
			devs[i] = int64(math.Abs(float64(v - med)))
		}
		mad := medianInt64(devs)
		st.med = med
		st.mad = mad
		st.usable = true
		out[region] = st
	}
	return out
}

func loadAncillary(dir string) (map[string]int64, map[string]struct{}, error) {
	floors := map[string]int64{}
	exclude := map[string]struct{}{}
	ents, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return floors, exclude, nil
		}
		return nil, nil, err
	}
	names := make([]string, 0)
	for _, e := range ents {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".json") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		b, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			return nil, nil, err
		}
		var raw map[string]json.RawMessage
		if json.Unmarshal(b, &raw) != nil {
			continue
		}
		if rf, ok := raw["region_min_kbps"]; ok {
			var m map[string]int64
			if json.Unmarshal(rf, &m) == nil {
				for k, v := range m {
					floors[k] = v
				}
			}
		}
		if re, ok := raw["mad_exclude"]; ok {
			var ids []string
			if json.Unmarshal(re, &ids) == nil {
				for _, id := range ids {
					exclude[id] = struct{}{}
				}
			}
		}
	}
	return floors, exclude, nil
}

func loadIncidentNotes(dataDir string) ([]incidentNote, error) {
	var notes []incidentNote
	order := 0
	if b, err := os.ReadFile(filepath.Join(dataDir, "incidents.json")); err == nil {
		var inc incidents
		if json.Unmarshal(b, &inc) == nil {
			for _, n := range inc.Notes {
				notes = append(notes, incidentNote{
					EndpointID: n.EndpointID,
					ForcedTier: n.ForcedTier,
					Order:      order,
				})
				order++
			}
		}
	}
	anchorDir := filepath.Join(dataDir, "anchors")
	ents, err := os.ReadDir(anchorDir)
	if err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	anchorNames := make([]string, 0)
	for _, e := range ents {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".txt") {
			anchorNames = append(anchorNames, e.Name())
		}
	}
	sort.Strings(anchorNames)
	for _, name := range anchorNames {
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
			notes = append(notes, incidentNote{
				EndpointID: parts[0],
				ForcedTier: parts[1],
				Order:      order,
			})
			order++
		}
	}
	return notes, nil
}

func medianInt64(xs []int64) int64 {
	if len(xs) == 0 {
		return 0
	}
	sorted := append([]int64(nil), xs...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i] < sorted[j] })
	n := len(sorted)
	if n%2 == 1 {
		return sorted[n/2]
	}
	return (sorted[n/2-1] + sorted[n/2]) / 2
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

func loadProbes(dir string) ([]probe, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make([]probe, 0)
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var p probe
		if err := json.Unmarshal(b, &p); err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no probes")
	}
	return out, nil
}
