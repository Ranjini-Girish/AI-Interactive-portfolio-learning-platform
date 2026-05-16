package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
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
		Reason     string `json:"reason"`
	} `json:"notes"`
}

type probe struct {
	BytesDown  int64  `json:"bytes_down"`
	EndpointID string `json:"endpoint_id"`
	Region     string `json:"region"`
	RttMs      int64  `json:"rtt_ms"`
	StatusCode int    `json:"status_code"`
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

	forced := map[string]string{}
	if b, err := os.ReadFile(filepath.Join(dataDir, "incidents.json")); err == nil {
		var inc incidents
		if json.Unmarshal(b, &inc) == nil {
			sort.Slice(inc.Notes, func(i, j int) bool {
				return inc.Notes[i].EndpointID < inc.Notes[j].EndpointID
			})
			for _, n := range inc.Notes {
				forced[n.EndpointID] = n.ForcedTier
			}
		}
	}

	probes, err := loadProbes(filepath.Join(dataDir, "probes"))
	if err != nil {
		return err
	}
	sort.Slice(probes, func(i, j int) bool { return probes[i].EndpointID < probes[j].EndpointID })

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

	finalTier := func(p probe) string {
		t := baseTier(p)
		if ft, ok := forced[p.EndpointID]; ok {
			return ft
		}
		return t
	}

	madSample := make([]int64, 0, len(probes))
	for _, p := range probes {
		if p.StatusCode < pol.FailedStatusFloor {
			madSample = append(madSample, p.RttMs)
		}
	}
	sort.Slice(madSample, func(i, j int) bool { return madSample[i] < madSample[j] })

	var med int64
	var mad int64
	usable := len(madSample) >= 3
	if usable {
		med = medianInt64(append([]int64(nil), madSample...))
		devs := make([]int64, len(madSample))
		for i, v := range madSample {
			devs[i] = int64(math.Abs(float64(v - med)))
		}
		mad = medianInt64(devs)
	}

	outlier := func(rtt int64) bool {
		if !usable {
			return false
		}
		hi := float64(med) + pol.MadK*float64(mad)
		lo := float64(med) - pol.MadK*float64(mad)
		return float64(rtt) > hi || float64(rtt) < lo
	}

	profiles := make([]map[string]any, 0, len(probes))
	regions := map[string]struct{}{}
	failed := 0
	events := make([]map[string]any, 0)

	for _, p := range probes {
		regions[p.Region] = struct{}{}
		tier := finalTier(p)
		if tier == "FAILED" {
			failed++
		}
		kbps := (p.BytesDown * 8) / ps.WindowMs
		anom := false
		if p.StatusCode < pol.FailedStatusFloor && outlier(p.RttMs) {
			anom = true
			dev := int64(math.Abs(float64(p.RttMs - med)))
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
		t := finalTier(p)
		if _, ok := tiersByRegion[p.Region]; !ok {
			tiersByRegion[p.Region] = map[string]int{
				"FAILED":   0,
				"FAST":     0,
				"MODERATE": 0,
				"SLOW":     0,
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
			"FAILED":   row["FAILED"],
			"FAST":     row["FAST"],
			"MODERATE": row["MODERATE"],
			"SLOW":     row["SLOW"],
		}
	}

	madSummary := map[string]any{
		"global_mad_ms":    nil,
		"global_median_ms": nil,
		"sample_size":      len(madSample),
	}
	if usable {
		madSummary["global_mad_ms"] = mad
		madSummary["global_median_ms"] = med
	}

	segList := make([]string, 0, len(regions))
	for r := range regions {
		segList = append(segList, r)
	}
	sort.Strings(segList)

	summary := map[string]any{
		"endpoints_total": len(probes),
		"failed_total":    failed,
		"regions":         segList,
		"window_ms":       ps.WindowMs,
	}

	payloads := map[string]any{
		"anomaly_events.json": map[string]any{
			"events": events,
		},
		"endpoint_profiles.json": map[string]any{
			"endpoints": profiles,
			"window_ms": ps.WindowMs,
		},
		"mad_summary.json": madSummary,
		"summary.json":     summary,
		"tier_rollups.json": map[string]any{
			"tiers":     tiersOut,
			"window_ms": ps.WindowMs,
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

func medianInt64(xs []int64) int64 {
	if len(xs) == 0 {
		return 0
	}
	sort.Slice(xs, func(i, j int) bool { return xs[i] < xs[j] })
	n := len(xs)
	if n%2 == 1 {
		return xs[n/2]
	}
	return (xs[n/2-1] + xs[n/2]) / 2
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
