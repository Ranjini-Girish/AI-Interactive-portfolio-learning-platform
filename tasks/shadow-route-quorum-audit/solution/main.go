package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type policy struct {
	GraceDays       int `json:"grace_days"`
	LatencyMedianK  int `json:"latency_median_k"`
	QuorumMin       int `json:"quorum_min"`
	SampleFloor     int `json:"sample_floor"`
}

type poolState struct {
	CurrentDay     int `json:"current_day"`
	WindowEndDay   int `json:"window_end_day"`
	WindowStartDay int `json:"window_start_day"`
}

type tierInfo struct {
	QuorumWeight    float64 `json:"quorum_weight"`
	ShadowFraction  float64 `json:"shadow_fraction"`
}

type shadowSample struct {
	Accepted   bool `json:"accepted"`
	Day        int  `json:"day"`
	LatencyMs  int  `json:"latency_ms"`
}

type routeDef struct {
	DependsOn     []string       `json:"depends_on"`
	ModelID       string         `json:"model_id"`
	RouteID       string         `json:"route_id"`
	ShadowSamples []shadowSample `json:"shadow_samples"`
	Tier          string         `json:"tier"`
}

type incidentEvent struct {
	Accepted bool   `json:"accepted"`
	Day      int    `json:"day"`
	Kind     string `json:"kind"`
	ModelID  string `json:"model_id"`
}

type overlayState struct {
	MinSamples     int
	ExcludeModels  map[string]struct{}
}

type pinNote struct {
	ModelID      string
	ForcedStatus string
	Order        int
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	data := getenv("SRQ_DATA_DIR", "/app/shadowroute")
	outd := getenv("SRQ_AUDIT_DIR", "/app/audit")
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
	if pol.QuorumMin <= 0 || pol.LatencyMedianK <= 0 {
		return fmt.Errorf("invalid policy")
	}

	var tiers map[string]tierInfo
	if err := readJSON(filepath.Join(dataDir, "tiers.json"), &tiers); err != nil {
		return err
	}

	ov, err := loadOverlays(filepath.Join(dataDir, "overlays"))
	if err != nil {
		return err
	}
	compromised, frozen, err := loadIncidents(filepath.Join(dataDir, "incidents.json"))
	if err != nil {
		return err
	}
	pins, err := loadPins(dataDir)
	if err != nil {
		return err
	}

	routes, err := loadRoutes(filepath.Join(dataDir, "routes"))
	if err != nil {
		return err
	}
	sort.Slice(routes, func(i, j int) bool { return routes[i].RouteID < routes[j].RouteID })

	quarantinedModels := compromisedSet(compromised, routes)
	holdModels := mergeHoldModels(frozen, pins, routes)

	profiles := make([]map[string]any, 0, len(routes))
	edges := make([]map[string]any, 0)
	blockedChains := make([]map[string]any, 0)
	degradeRows := make([]map[string]any, 0)
	compromiseRoutes := make([]map[string]any, 0)

	counts := map[string]int{
		"quarantined": 0, "hold": 0, "blocked": 0, "stale": 0, "degraded": 0,
	}

	for _, r := range routes {
		for _, dep := range r.DependsOn {
			edges = append(edges, map[string]any{
				"depends_on_model_id": dep,
				"route_id":            r.RouteID,
			})
		}

		winSamples := windowSamples(r.ShadowSamples, ps, pol)
		excluded := false
		if _, ok := ov.ExcludeModels[r.ModelID]; ok {
			excluded = true
		}
		sampleOK := !excluded && len(winSamples) >= ov.MinSamples

		tier, ok := tiers[r.Tier]
		if !ok {
			return fmt.Errorf("unknown tier %s", r.Tier)
		}
		effQ := int(math.Max(1, math.Ceil(float64(pol.QuorumMin)*tier.QuorumWeight)))

		median := medianLatency(winSamples, pol.LatencyMedianK)
		latest := latestWindowSample(winSamples)
		degraded := isDegraded(median, latest)

		status := resolveStatus(r, ps, pol, quarantinedModels, holdModels, pins, degraded)

		var shadowFrac any = tier.ShadowFraction
		switch status {
		case "quarantined":
			shadowFrac = nil
		case "blocked":
			shadowFrac = 0
		}

		var medianAny any = median
		if median < 0 {
			medianAny = nil
		}
		var lastSeenAny any
		if lastSeen, ok := lastSeenDay(r.ShadowSamples); ok {
			lastSeenAny = lastSeen
		}

		profiles = append(profiles, map[string]any{
			"effective_quorum":          effQ,
			"last_seen_day":             lastSeenAny,
			"median_latency_ms":         medianAny,
			"model_id":                  r.ModelID,
			"route_id":                  r.RouteID,
			"sample_ok":                 sampleOK,
			"shadow_fraction_effective": shadowFrac,
			"status":                    status,
			"tier":                      r.Tier,
			"window_sample_count":       len(winSamples),
		})

		counts[status]++

		if status == "quarantined" {
			compromiseRoutes = append(compromiseRoutes, map[string]any{
				"model_id": r.ModelID,
				"route_id": r.RouteID,
			})
		}
		if status == "blocked" {
			by, reason := blockReason(r, quarantinedModels, holdModels)
			blockedChains = append(blockedChains, map[string]any{
				"blocked_by_model_id": by,
				"reason":              reason,
				"route_id":            r.RouteID,
			})
		}
		if status == "degraded" && latest != nil {
			degradeRows = append(degradeRows, map[string]any{
				"latest_latency_ms": latest.LatencyMs,
				"median_latency_ms": median,
				"model_id":          r.ModelID,
				"route_id":          r.RouteID,
			})
		}
	}

	sort.Slice(edges, func(i, j int) bool {
		a, b := edges[i], edges[j]
		if a["route_id"].(string) != b["route_id"].(string) {
			return a["route_id"].(string) < b["route_id"].(string)
		}
		return a["depends_on_model_id"].(string) < b["depends_on_model_id"].(string)
	})
	sort.Slice(blockedChains, func(i, j int) bool {
		return blockedChains[i]["route_id"].(string) < blockedChains[j]["route_id"].(string)
	})
	sort.Slice(degradeRows, func(i, j int) bool {
		return degradeRows[i]["route_id"].(string) < degradeRows[j]["route_id"].(string)
	})
	sort.Slice(compromiseRoutes, func(i, j int) bool {
		return compromiseRoutes[i]["route_id"].(string) < compromiseRoutes[j]["route_id"].(string)
	})

	models := make([]string, 0, len(compromised))
	for m := range compromised {
		models = append(models, m)
	}
	sort.Strings(models)

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	files := map[string]any{
		"route_profiles.json": map[string]any{
			"routes":           profiles,
			"window_end_day":   ps.WindowEndDay,
			"window_start_day": ps.WindowStartDay,
		},
		"dependency_report.json": map[string]any{
			"blocked_chains": blockedChains,
			"edges":          edges,
		},
		"degrade_report.json": map[string]any{"routes": degradeRows},
		"compromise_report.json": map[string]any{
			"models": models,
			"routes": compromiseRoutes,
		},
		"summary.json": map[string]any{
			"blocked_total":    counts["blocked"],
			"current_day":      ps.CurrentDay,
			"degraded_total":   counts["degraded"],
			"hold_total":       counts["hold"],
			"quarantined_total": counts["quarantined"],
			"route_total":      len(routes),
			"stale_total":      counts["stale"],
			"window_end_day":   ps.WindowEndDay,
			"window_start_day": ps.WindowStartDay,
		},
	}
	for name, body := range files {
		if err := writePrettyJSON(filepath.Join(auditDir, name), body); err != nil {
			return err
		}
	}
	return nil
}

func compromisedSet(compromised map[string]struct{}, routes []routeDef) map[string]struct{} {
	out := map[string]struct{}{}
	for m := range compromised {
		out[m] = struct{}{}
	}
	changed := true
	for changed {
		changed = false
		for _, r := range routes {
			if routeUsesCompromised(r, out) {
				if _, ok := out[r.ModelID]; !ok {
					out[r.ModelID] = struct{}{}
					changed = true
				}
			}
		}
	}
	return out
}

func routeUsesCompromised(r routeDef, compromised map[string]struct{}) bool {
	if _, ok := compromised[r.ModelID]; ok {
		return true
	}
	for _, dep := range r.DependsOn {
		if _, ok := compromised[dep]; ok {
			return true
		}
	}
	return false
}

func mergeHoldModels(frozen map[string]struct{}, pins map[string]string, routes []routeDef) map[string]struct{} {
	out := map[string]struct{}{}
	for m := range frozen {
		out[m] = struct{}{}
	}
	for m, st := range pins {
		if st == "hold" {
			out[m] = struct{}{}
		}
	}
	for _, r := range routes {
		if _, ok := frozen[r.ModelID]; ok {
			out[r.ModelID] = struct{}{}
		}
	}
	return out
}

func resolveStatus(
	r routeDef,
	ps poolState,
	pol policy,
	compromised, holdModels map[string]struct{},
	pins map[string]string,
	degraded bool,
) string {
	if routeUsesCompromised(r, compromised) {
		return "quarantined"
	}
	if _, ok := holdModels[r.ModelID]; ok {
		return "hold"
	}
	if dependencyBlocked(r, compromised, holdModels) {
		return "blocked"
	}
	if pins[r.ModelID] == "shadow_only" {
		return "shadow_only"
	}
	if last, ok := lastSeenDay(r.ShadowSamples); ok {
		if ps.CurrentDay-last > pol.GraceDays {
			return "stale"
		}
	}
	if degraded {
		return "degraded"
	}
	return "ok"
}

func dependencyBlocked(r routeDef, compromised, holdModels map[string]struct{}) bool {
	for _, dep := range r.DependsOn {
		if _, ok := compromised[dep]; ok {
			return true
		}
		if _, ok := holdModels[dep]; ok {
			return true
		}
	}
	return false
}

func blockReason(r routeDef, compromised, holdModels map[string]struct{}) (string, string) {
	for _, dep := range r.DependsOn {
		if _, ok := compromised[dep]; ok {
			return dep, "compromised_upstream"
		}
	}
	for _, dep := range r.DependsOn {
		if _, ok := holdModels[dep]; ok {
			return dep, "hold_upstream"
		}
	}
	return "", "hold_upstream"
}

func lastSeenDay(samples []shadowSample) (int, bool) {
	if len(samples) == 0 {
		return 0, false
	}
	maxDay := samples[0].Day
	for _, s := range samples[1:] {
		if s.Day > maxDay {
			maxDay = s.Day
		}
	}
	return maxDay, true
}

func windowSamples(samples []shadowSample, ps poolState, pol policy) []shadowSample {
	out := make([]shadowSample, 0)
	for _, s := range samples {
		if s.Day < ps.WindowStartDay || s.Day > ps.WindowEndDay {
			continue
		}
		if !s.Accepted || s.LatencyMs < pol.SampleFloor {
			continue
		}
		out = append(out, s)
	}
	return out
}

func medianLatency(samples []shadowSample, k int) int {
	if len(samples) < k {
		return -1
	}
	sorted := append([]shadowSample{}, samples...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].Day < sorted[j].Day })
	tail := sorted[len(sorted)-k:]
	lat := make([]int, len(tail))
	for i, s := range tail {
		lat[i] = s.LatencyMs
	}
	sort.Ints(lat)
	mid := len(lat) / 2
	if len(lat)%2 == 1 {
		return lat[mid]
	}
	return lat[mid-1]
}

func latestWindowSample(samples []shadowSample) *shadowSample {
	if len(samples) == 0 {
		return nil
	}
	best := samples[0]
	bestIdx := 0
	for i, s := range samples[1:] {
		if s.Day > best.Day || (s.Day == best.Day && i > bestIdx) {
			best = s
			bestIdx = i
		}
	}
	return &best
}

func isDegraded(median int, latest *shadowSample) bool {
	if median < 0 || latest == nil {
		return false
	}
	return latest.LatencyMs > 2*median
}

func loadRoutes(dir string) ([]routeDef, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var routes []routeDef
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		var r routeDef
		if err := readJSON(filepath.Join(dir, e.Name()), &r); err != nil {
			return nil, err
		}
		want := strings.TrimSuffix(e.Name(), ".json")
		if r.RouteID != want {
			return nil, fmt.Errorf("route_id mismatch %s", e.Name())
		}
		routes = append(routes, r)
	}
	return routes, nil
}

func loadOverlays(dir string) (overlayState, error) {
	st := overlayState{MinSamples: 1, ExcludeModels: map[string]struct{}{}}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return st, err
	}
	var names []string
	for _, e := range entries {
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
		if v, ok := raw["min_samples"]; ok {
			var n int
			if err := json.Unmarshal(v, &n); err == nil {
				st.MinSamples = n
			}
		}
		if v, ok := raw["exclude_models"]; ok {
			var arr []string
			if err := json.Unmarshal(v, &arr); err == nil {
				for _, id := range arr {
					st.ExcludeModels[id] = struct{}{}
				}
			}
		}
	}
	return st, nil
}

func loadIncidents(path string) (map[string]struct{}, map[string]struct{}, error) {
	var doc struct {
		Events []incidentEvent `json:"events"`
	}
	if err := readJSON(path, &doc); err != nil {
		return nil, nil, err
	}
	comp := map[string]struct{}{}
	frozen := map[string]struct{}{}
	for _, ev := range doc.Events {
		if !ev.Accepted {
			continue
		}
		switch ev.Kind {
		case "model_compromise":
			comp[ev.ModelID] = struct{}{}
		case "route_freeze":
			frozen[ev.ModelID] = struct{}{}
		}
	}
	return comp, frozen, nil
}

func loadPins(dataDir string) (map[string]string, error) {
	dir := filepath.Join(dataDir, "pins")
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var notes []pinNote
	order := 0
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
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
			notes = append(notes, pinNote{ModelID: parts[0], ForcedStatus: parts[1], Order: order})
			order++
		}
	}
	sort.Slice(notes, func(i, j int) bool {
		if notes[i].ModelID != notes[j].ModelID {
			return notes[i].ModelID < notes[j].ModelID
		}
		return notes[i].Order < notes[j].Order
	})
	out := map[string]string{}
	for _, n := range notes {
		out[n.ModelID] = n.ForcedStatus
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

func writePrettyJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}
