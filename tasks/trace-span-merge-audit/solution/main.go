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

const (
	white = 0
	gray  = 1
	black = 2
)

func getenv(key, def string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return def
}

func canonicalJSON(v any) []byte {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		panic(err)
	}
	out := buf.Bytes()
	for len(out) > 0 && out[len(out)-1] == '\n' {
		out = out[:len(out)-1]
	}
	return append(out, '\n')
}

func writeJSON(path string, v any) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		panic(err)
	}
	if err := os.WriteFile(path, canonicalJSON(v), 0o644); err != nil {
		panic(err)
	}
}

func readJSON(path string, out any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, out); err != nil {
		panic(fmt.Sprintf("%s: %v", path, err))
	}
}

type spanRow struct {
	SpanID   string `json:"span_id"`
	Service  string `json:"service"`
	ParentID string `json:"parent_id"`
	StartUS  int    `json:"start_us"`
	EndUS    int    `json:"end_us"`
	Status   string `json:"status"`
}

func main() {
	dataDir := getenv("TSM_DATA_DIR", "/app/tracespan")
	auditDir := getenv("TSM_AUDIT_DIR", "/app/audit")

	var policy struct {
		AnchorUS            int  `json:"anchor_us"`
		MaxDepth            int  `json:"max_depth"`
		DeductChildLatency  bool `json:"deduct_child_latency"`
	}
	readJSON(filepath.Join(dataDir, "policy.json"), &policy)

	var view struct {
		BundleTag  string `json:"bundle_tag"`
		QuorumTag  string `json:"quorum_tag"`
	}
	readJSON(filepath.Join(dataDir, "view.json"), &view)

	var patches struct {
		Events []struct {
			Kind   string `json:"kind"`
			SpanID string `json:"span_id"`
		} `json:"events"`
	}
	readJSON(filepath.Join(dataDir, "patches.json"), &patches)

	anchorUS := policy.AnchorUS
	maxDepth := policy.MaxDepth
	deduct := policy.DeductChildLatency

	relax := 0
	for _, e := range patches.Events {
		if e.Kind == "depth_relax" {
			relax++
		}
	}
	tagPenalty := 0
	if view.BundleTag != view.QuorumTag {
		tagPenalty = 1
	}
	effectiveMax := maxDepth - tagPenalty + relax
	if effectiveMax < 0 {
		effectiveMax = 0
	}

	forceOrphan := map[string]struct{}{}
	for _, e := range patches.Events {
		if e.Kind == "force_orphan" {
			forceOrphan[e.SpanID] = struct{}{}
		}
	}

	spanPaths, err := filepath.Glob(filepath.Join(dataDir, "spans", "*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(spanPaths)

	spans := map[string]spanRow{}
	parentOf := map[string]string{}
	for _, p := range spanPaths {
		var raw map[string]json.RawMessage
		readJSON(p, &raw)
		var row spanRow
		readJSON(p, &row)
		spans[row.SpanID] = row
		if parent, ok := raw["parent_id"]; ok && string(parent) != "null" {
			var pid string
			json.Unmarshal(parent, &pid)
			parentOf[row.SpanID] = pid
		}
	}

	color := map[string]int{}
	for sid := range spans {
		color[sid] = white
	}
	inCycle := map[string]struct{}{}

	var dfs func(u string)
	dfs = func(u string) {
		color[u] = gray
		p, hasP := parentOf[u]
		if hasP {
			if _, ok := spans[p]; ok {
				if color[p] == gray {
					cur := p
					for {
						inCycle[cur] = struct{}{}
						if cur == u {
							break
						}
						cur, hasP = parentOf[cur]
						if !hasP {
							break
						}
						if _, ok := spans[cur]; !ok {
							break
						}
					}
					inCycle[u] = struct{}{}
				} else if color[p] == white {
					dfs(p)
				}
			}
		}
		color[u] = black
	}

	var spanIDs []string
	for sid := range spans {
		spanIDs = append(spanIDs, sid)
	}
	sort.Strings(spanIDs)
	for _, sid := range spanIDs {
		if color[sid] == white {
			dfs(sid)
		}
	}

	mergeStatus := map[string]string{}
	depthMap := map[string]int{}
	var orphanRows []map[string]string

	for _, sid := range spanIDs {
		if _, ok := forceOrphan[sid]; ok {
			mergeStatus[sid] = "orphan"
			orphanRows = append(orphanRows, map[string]string{"reason": "forced", "span_id": sid})
			continue
		}
		if _, ok := inCycle[sid]; ok {
			mergeStatus[sid] = "cycle_member"
			orphanRows = append(orphanRows, map[string]string{"reason": "cycle", "span_id": sid})
			continue
		}
		p, hasP := parentOf[sid]
		if hasP {
			if _, ok := spans[p]; !ok {
				mergeStatus[sid] = "orphan"
				orphanRows = append(orphanRows, map[string]string{"reason": "missing_parent", "span_id": sid})
				continue
			}
		}
		depth := 0
		cur := p
		seen := map[string]struct{}{}
		for hasP && cur != "" {
			if _, ok := spans[cur]; !ok {
				break
			}
			if _, dup := seen[cur]; dup {
				break
			}
			seen[cur] = struct{}{}
			depth++
			cur, hasP = parentOf[cur]
		}
		depthMap[sid] = depth
		if depth > effectiveMax {
			mergeStatus[sid] = "depth_clamped"
		} else {
			mergeStatus[sid] = "attached"
		}
	}

	var spanStates []map[string]any
	for _, sid := range spanIDs {
		row := spans[sid]
		dur := row.EndUS - row.StartUS
		if dur < 0 {
			dur = 0
		}
		depth := -1
		if d, ok := depthMap[sid]; ok {
			depth = d
		}
		spanStates = append(spanStates, map[string]any{
			"depth":         depth,
			"duration_us":   dur,
			"exclusive_us":  dur,
			"merge_status":  mergeStatus[sid],
			"service":       row.Service,
			"span_id":       sid,
			"status":        row.Status,
		})
	}

	exMap := map[string]int{}
	statusMap := map[string]string{}
	for _, r := range spanStates {
		exMap[r["span_id"].(string)] = r["exclusive_us"].(int)
		statusMap[r["span_id"].(string)] = r["status"].(string)
	}

	if deduct {
		var attached []map[string]any
		for _, r := range spanStates {
			if r["merge_status"] == "attached" {
				attached = append(attached, r)
			}
		}
		sort.Slice(attached, func(i, j int) bool {
			if attached[i]["depth"].(int) != attached[j]["depth"].(int) {
				return attached[i]["depth"].(int) > attached[j]["depth"].(int)
			}
			return attached[i]["span_id"].(string) < attached[j]["span_id"].(string)
		})
		for _, r := range attached {
			sid := r["span_id"].(string)
			p, hasP := parentOf[sid]
			if !hasP {
				continue
			}
			if _, ok := spans[p]; !ok {
				continue
			}
			if mergeStatus[p] != "attached" {
				continue
			}
			if statusMap[p] != "ok" {
				continue
			}
			childDur := r["duration_us"].(int)
			ex := exMap[p]
			sub := childDur
			if sub > ex {
				sub = ex
			}
			exMap[p] = ex - sub
			if exMap[p] < 0 {
				exMap[p] = 0
			}
		}
		for _, r := range spanStates {
			r["exclusive_us"] = exMap[r["span_id"].(string)]
		}
	}

	var chains []map[string]any
	for _, sid := range spanIDs {
		if mergeStatus[sid] != "attached" {
			continue
		}
		chain := []string{sid}
		cur, hasP := parentOf[sid]
		seen := map[string]struct{}{}
		for hasP && cur != "" {
			if _, ok := spans[cur]; !ok {
				break
			}
			if _, dup := seen[cur]; dup {
				break
			}
			seen[cur] = struct{}{}
			chain = append(chain, cur)
			cur, hasP = parentOf[cur]
		}
		for i, j := 0, len(chain)-1; i < j; i, j = i+1, j-1 {
			chain[i], chain[j] = chain[j], chain[i]
		}
		chains = append(chains, map[string]any{"chain": chain, "span_id": sid})
	}

	services := map[string]map[string]any{}
	for _, r := range spanStates {
		svc := r["service"].(string)
		bucket, ok := services[svc]
		if !ok {
			bucket = map[string]any{
				"error_count":          0,
				"service":              svc,
				"span_count":           0,
				"total_exclusive_us":   0,
			}
			services[svc] = bucket
		}
		bucket["span_count"] = bucket["span_count"].(int) + 1
		if r["status"] == "error" {
			bucket["error_count"] = bucket["error_count"].(int) + 1
		}
		bucket["total_exclusive_us"] = bucket["total_exclusive_us"].(int) + r["exclusive_us"].(int)
	}
	var svcIDs []string
	for svc := range services {
		svcIDs = append(svcIDs, svc)
	}
	sort.Strings(svcIDs)
	var serviceRollups []map[string]any
	for _, svc := range svcIDs {
		serviceRollups = append(serviceRollups, services[svc])
	}

	attachedTotal, cycleTotal, depthClamped, orphanTotal, timeoutTotal := 0, 0, 0, 0, 0
	for _, r := range spanStates {
		switch r["merge_status"] {
		case "attached":
			attachedTotal++
		case "cycle_member":
			cycleTotal++
		case "depth_clamped":
			depthClamped++
		case "orphan":
			orphanTotal++
		}
		if r["status"] == "timeout" {
			timeoutTotal++
		}
	}

	sort.Slice(orphanRows, func(i, j int) bool {
		return orphanRows[i]["span_id"] < orphanRows[j]["span_id"]
	})

	writeJSON(filepath.Join(auditDir, "span_states.json"), map[string]any{
		"anchor_us": anchorUS,
		"spans":     spanStates,
	})
	writeJSON(filepath.Join(auditDir, "parent_chains.json"), map[string]any{"chains": chains})
	writeJSON(filepath.Join(auditDir, "orphan_report.json"), map[string]any{"orphans": orphanRows})
	writeJSON(filepath.Join(auditDir, "service_rollups.json"), map[string]any{"services": serviceRollups})
	writeJSON(filepath.Join(auditDir, "summary.json"), map[string]any{
		"anchor_us":            anchorUS,
		"attached_total":       attachedTotal,
		"cycle_total":          cycleTotal,
		"depth_clamped_total":  depthClamped,
		"effective_max_depth":  effectiveMax,
		"orphan_total":         orphanTotal,
		"span_total":           len(spanStates),
		"timeout_total":        timeoutTotal,
	})
}
