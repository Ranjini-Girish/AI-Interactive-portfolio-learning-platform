#!/bin/bash
set -euo pipefail

SRC_DIR="${GIA_SRC_DIR:-/app/src}"
BIN_DIR="${GIA_BIN_DIR:-/app/bin}"
REPORT_DIR="${GIA_REPORT_DIR:-/app/report}"

mkdir -p "$SRC_DIR" "$BIN_DIR" "$REPORT_DIR"

cat > "$SRC_DIR/go.mod" <<'GOMOD'
module auditor

go 1.23
GOMOD

cat > "$SRC_DIR/main.go" <<'GOEOF'
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

type Service struct {
	ServiceID    string   `json:"service_id"`
	NodeID       string   `json:"node_id"`
	Team         string   `json:"team"`
	Tier         string   `json:"tier"`
	Dependencies []string `json:"dependencies"`
}

type Window struct {
	Minute   int `json:"minute"`
	ErrorPct int `json:"error_pct"`
	P95Ms    int `json:"p95_ms"`
	QPS      int `json:"qps"`
}

type MetricsFile struct {
	ServiceID string   `json:"service_id"`
	Windows   []Window `json:"windows"`
}

type TierThresholds struct {
	WarningErrorPct    int `json:"warning_error_pct"`
	CriticalErrorPct   int `json:"critical_error_pct"`
	WarningP95Ms       int `json:"warning_p95_ms"`
	CriticalP95Ms      int `json:"critical_p95_ms"`
	WarningQpsDropPct  int `json:"warning_qps_drop_pct"`
	CriticalQpsDropPct int `json:"critical_qps_drop_pct"`
}

type Rotation struct {
	Primary   string `json:"primary"`
	Secondary string `json:"secondary"`
}

func getEnv(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func readFile(p string) []byte {
	b, err := os.ReadFile(p)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read %s: %v\n", p, err)
		os.Exit(1)
	}
	return b
}

func parseTyped(p string, out interface{}) {
	if err := json.Unmarshal(readFile(p), out); err != nil {
		fmt.Fprintf(os.Stderr, "parse %s: %v\n", p, err)
		os.Exit(1)
	}
}

func parseRaw(p string, out interface{}) {
	dec := json.NewDecoder(bytes.NewReader(readFile(p)))
	dec.UseNumber()
	if err := dec.Decode(out); err != nil {
		fmt.Fprintf(os.Stderr, "parse %s: %v\n", p, err)
		os.Exit(1)
	}
}

func writeJSON(p string, v interface{}) {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "marshal %s: %v\n", p, err)
		os.Exit(1)
	}
	data = append(data, '\n')
	if err := os.WriteFile(p, data, 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "write %s: %v\n", p, err)
		os.Exit(1)
	}
}

func intFromAny(v interface{}) (int, bool) {
	n, ok := v.(json.Number)
	if !ok {
		return 0, false
	}
	i, err := n.Int64()
	if err != nil {
		return 0, false
	}
	return int(i), true
}

func sortedKeys(m map[string]bool) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func main() {
	signalsDir := getEnv("GIA_SIGNALS_DIR", "/app/signals")
	reportDir := getEnv("GIA_REPORT_DIR", "/app/report")
	if err := os.MkdirAll(reportDir, 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "mkdir %s: %v\n", reportDir, err)
		os.Exit(1)
	}

	var pool struct {
		CurrentMinute int `json:"current_minute"`
	}
	parseTyped(filepath.Join(signalsDir, "pool_state.json"), &pool)
	currentMinute := pool.CurrentMinute

	var policy struct {
		Tiers map[string]TierThresholds `json:"tiers"`
	}
	parseTyped(filepath.Join(signalsDir, "policy", "triage_policy.json"), &policy)

	var rotations struct {
		Teams map[string]Rotation `json:"teams"`
	}
	parseTyped(filepath.Join(signalsDir, "oncall", "rotations.json"), &rotations)

	serviceFiles, _ := filepath.Glob(filepath.Join(signalsDir, "services", "*.json"))
	sort.Strings(serviceFiles)
	services := make(map[string]Service)
	for _, f := range serviceFiles {
		var s Service
		parseTyped(f, &s)
		services[s.ServiceID] = s
	}

	metricsFiles, _ := filepath.Glob(filepath.Join(signalsDir, "metrics", "*.json"))
	sort.Strings(metricsFiles)
	metrics := make(map[string][]Window)
	for _, f := range metricsFiles {
		var m MetricsFile
		parseTyped(f, &m)
		metrics[m.ServiceID] = m.Windows
	}

	knownServices := map[string]bool{}
	for sid := range services {
		knownServices[sid] = true
	}
	knownNodes := map[string]bool{}
	for _, svc := range services {
		knownNodes[svc.NodeID] = true
	}

	var incidents struct {
		Events []map[string]interface{} `json:"events"`
	}
	parseRaw(filepath.Join(signalsDir, "incidents", "incident_log.json"), &incidents)

	validKind := func(k string) bool {
		return k == "node_quarantine" || k == "throttle_window" || k == "severity_override"
	}
	validEvent := func(ev map[string]interface{}) bool {
		if a, ok := ev["accepted"].(bool); !ok || !a {
			return false
		}
		m, ok := intFromAny(ev["minute"])
		if !ok || m > currentMinute {
			return false
		}
		kind, _ := ev["kind"].(string)
		if !validKind(kind) {
			return false
		}
		switch kind {
		case "node_quarantine":
			nid, ok := ev["node_id"].(string)
			if !ok || !knownNodes[nid] {
				return false
			}
			from, fok := intFromAny(ev["from_minute"])
			to, tok := intFromAny(ev["to_minute"])
			if !fok || !tok {
				return false
			}
			return from <= to
		case "throttle_window":
			sid, ok := ev["service_id"].(string)
			if !ok || !knownServices[sid] {
				return false
			}
			start, sok := intFromAny(ev["start_minute"])
			end, eok := intFromAny(ev["end_minute"])
			if !sok || !eok {
				return false
			}
			extra, xok := intFromAny(ev["extra_error_pct"])
			if !xok || extra <= 0 {
				return false
			}
			return start <= end
		case "severity_override":
			sid, ok := ev["service_id"].(string)
			if !ok || !knownServices[sid] {
				return false
			}
			sev, ok := ev["severity"].(string)
			if !ok {
				return false
			}
			return sev == "healthy" || sev == "warning" || sev == "critical"
		}
		return false
	}

	var accepted []map[string]interface{}
	ignored := 0
	for _, ev := range incidents.Events {
		if validEvent(ev) {
			accepted = append(accepted, ev)
		} else {
			ignored++
		}
	}
	sort.SliceStable(accepted, func(i, j int) bool {
		mi, _ := intFromAny(accepted[i]["minute"])
		mj, _ := intFromAny(accepted[j]["minute"])
		if mi != mj {
			return mi < mj
		}
		ai, _ := accepted[i]["event_id"].(string)
		aj, _ := accepted[j]["event_id"].(string)
		return ai < aj
	})

	activeNodeQ := map[string]bool{}
	activeThrottles := map[string][]int{}
	lastOverride := map[string]string{}
	for _, ev := range accepted {
		kind := ev["kind"].(string)
		switch kind {
		case "node_quarantine":
			from, _ := intFromAny(ev["from_minute"])
			to, _ := intFromAny(ev["to_minute"])
			if from <= currentMinute && currentMinute <= to {
				activeNodeQ[ev["node_id"].(string)] = true
			}
		case "throttle_window":
			start, _ := intFromAny(ev["start_minute"])
			end, _ := intFromAny(ev["end_minute"])
			if start <= currentMinute && currentMinute <= end {
				sid := ev["service_id"].(string)
				extra, _ := intFromAny(ev["extra_error_pct"])
				activeThrottles[sid] = append(activeThrottles[sid], extra)
			}
		case "severity_override":
			lastOverride[ev["service_id"].(string)] = ev["severity"].(string)
		}
	}

	reverseDeps := map[string][]string{}
	for sid := range services {
		reverseDeps[sid] = nil
	}
	for sid, svc := range services {
		for _, dep := range svc.Dependencies {
			reverseDeps[dep] = append(reverseDeps[dep], sid)
		}
	}
	for k, v := range reverseDeps {
		sort.Strings(v)
		reverseDeps[k] = v
	}

	sortedSids := make([]string, 0, len(services))
	for sid := range services {
		sortedSids = append(sortedSids, sid)
	}
	sort.Strings(sortedSids)

	base := map[string]string{}
	qpsDrop := map[string]int{}
	var roots []string
	for _, sid := range sortedSids {
		svc := services[sid]
		windows := metrics[sid]
		latest := windows[len(windows)-1]
		prev := windows[:len(windows)-1]
		baselineQPS := latest.QPS
		if len(prev) > 0 {
			sum := 0
			for _, w := range prev {
				sum += w.QPS
			}
			baselineQPS = sum / len(prev)
		}
		drop := 0
		if baselineQPS > 0 {
			drop = (100 * (baselineQPS - latest.QPS)) / baselineQPS
			if drop < 0 {
				drop = 0
			}
		}
		qpsDrop[sid] = drop

		effError := latest.ErrorPct
		for _, e := range activeThrottles[sid] {
			effError += e
		}
		t := policy.Tiers[svc.Tier]
		sev := "healthy"
		if effError >= t.CriticalErrorPct || latest.P95Ms >= t.CriticalP95Ms || drop >= t.CriticalQpsDropPct {
			sev = "critical"
		} else if effError >= t.WarningErrorPct || latest.P95Ms >= t.WarningP95Ms || drop >= t.WarningQpsDropPct {
			sev = "warning"
		}
		base[sid] = sev
		if sev == "critical" {
			roots = append(roots, sid)
		}
	}
	sort.Strings(roots)

	propagatedFrom := map[string]map[string]bool{}
	for _, root := range roots {
		queue := []string{root}
		seen := map[string]bool{root: true}
		for len(queue) > 0 {
			cur := queue[0]
			queue = queue[1:]
			for _, nxt := range reverseDeps[cur] {
				if seen[nxt] {
					continue
				}
				seen[nxt] = true
				queue = append(queue, nxt)
				if nxt != root {
					if propagatedFrom[nxt] == nil {
						propagatedFrom[nxt] = map[string]bool{}
					}
					propagatedFrom[nxt][root] = true
				}
			}
		}
	}

	final := map[string]string{}
	for k, v := range base {
		final[k] = v
	}
	for _, sid := range sortedSids {
		if len(propagatedFrom[sid]) > 0 && final[sid] == "healthy" {
			final[sid] = "warning"
		}
	}
	for _, sid := range sortedSids {
		if activeNodeQ[services[sid].NodeID] && final[sid] == "healthy" {
			final[sid] = "warning"
		}
	}
	for sid, sev := range lastOverride {
		final[sid] = sev
	}

	reasonsBySid := map[string][]string{}
	anomalyServices := []map[string]interface{}{}
	for _, sid := range sortedSids {
		svc := services[sid]
		reasonSet := map[string]bool{}
		activeInc := map[string]bool{}
		if base[sid] == "warning" || base[sid] == "critical" {
			reasonSet["local_signal"] = true
		}
		if propagatedFrom[sid] != nil {
			for _, root := range sortedKeys(propagatedFrom[sid]) {
				reasonSet["propagated_from:"+root] = true
			}
		}
		if activeNodeQ[svc.NodeID] {
			reasonSet["node_quarantine"] = true
			activeInc["node_quarantine"] = true
		}
		if _, ok := activeThrottles[sid]; ok {
			activeInc["throttle_window"] = true
		}
		if _, ok := lastOverride[sid]; ok {
			reasonSet["override"] = true
			activeInc["severity_override"] = true
		}
		reasons := sortedKeys(reasonSet)
		incidentList := sortedKeys(activeInc)
		reasonsBySid[sid] = reasons
		anomalyServices = append(anomalyServices, map[string]interface{}{
			"active_incidents": incidentList,
			"base_severity":    base[sid],
			"final_severity":   final[sid],
			"node_id":          svc.NodeID,
			"qps_drop_pct":     qpsDrop[sid],
			"reasons":          reasons,
			"service_id":       sid,
			"team":             svc.Team,
			"tier":             svc.Tier,
		})
	}

	blastRoots := []map[string]interface{}{}
	for _, root := range roots {
		impacted := []string{}
		for _, sid := range sortedSids {
			if propagatedFrom[sid] != nil && propagatedFrom[sid][root] && final[sid] != "healthy" {
				impacted = append(impacted, sid)
			}
		}
		sort.Strings(impacted)
		blastRoots = append(blastRoots, map[string]interface{}{
			"impacted_services": impacted,
			"service_id":        root,
			"total_impacted":    len(impacted),
		})
	}

	pages := []map[string]interface{}{}
	for _, sid := range sortedSids {
		sev := final[sid]
		if sev == "healthy" {
			continue
		}
		rset := map[string]bool{}
		for _, r := range reasonsBySid[sid] {
			rset[r] = true
		}
		var pr string
		switch {
		case sev == "critical":
			pr = "p1"
		case rset["local_signal"] || rset["override"]:
			pr = "p2"
		default:
			pr = "p3"
		}
		team := services[sid].Team
		pages = append(pages, map[string]interface{}{
			"backup_pager": rotations.Teams[team].Secondary,
			"pager":        rotations.Teams[team].Primary,
			"priority":     pr,
			"service_id":   sid,
			"team":         team,
		})
	}
	priorityRank := map[string]int{"p1": 1, "p2": 2, "p3": 3}
	sort.SliceStable(pages, func(i, j int) bool {
		pi := priorityRank[pages[i]["priority"].(string)]
		pj := priorityRank[pages[j]["priority"].(string)]
		if pi != pj {
			return pi < pj
		}
		return pages[i]["service_id"].(string) < pages[j]["service_id"].(string)
	})

	nodeServices := map[string][]string{}
	for _, sid := range sortedSids {
		nid := services[sid].NodeID
		nodeServices[nid] = append(nodeServices[nid], sid)
	}
	sortedNodes := make([]string, 0, len(nodeServices))
	for nid := range nodeServices {
		sortedNodes = append(sortedNodes, nid)
	}
	sort.Strings(sortedNodes)
	nodes := []map[string]interface{}{}
	for _, nid := range sortedNodes {
		sids := append([]string{}, nodeServices[nid]...)
		sort.Strings(sids)
		critical := []string{}
		for _, sid := range sids {
			if final[sid] == "critical" {
				critical = append(critical, sid)
			}
		}
		sort.Strings(critical)
		isQ := activeNodeQ[nid]
		status := "healthy"
		switch {
		case isQ && len(critical) > 0:
			status = "quarantined_hotspot"
		case isQ:
			status = "quarantined"
		case len(critical) > 0:
			status = "hotspot"
		}
		nodes = append(nodes, map[string]interface{}{
			"critical_services": critical,
			"node_id":           nid,
			"services":          sids,
			"status":            status,
		})
	}

	countSev := func(s string) int {
		n := 0
		for _, e := range anomalyServices {
			if e["final_severity"] == s {
				n++
			}
		}
		return n
	}
	countNodeStatus := func(s string) int {
		n := 0
		for _, e := range nodes {
			if e["status"] == s {
				n++
			}
		}
		return n
	}
	countPriority := func(s string) int {
		n := 0
		for _, p := range pages {
			if p["priority"] == s {
				n++
			}
		}
		return n
	}
	propagatedCount := 0
	for _, e := range anomalyServices {
		for _, r := range e["reasons"].([]string) {
			if strings.HasPrefix(r, "propagated_from:") {
				propagatedCount++
				break
			}
		}
	}
	summary := map[string]interface{}{
		"accepted_incident_events":  len(accepted),
		"hotspot_nodes":             countNodeStatus("hotspot"),
		"ignored_incident_events":   ignored,
		"p1_pages":                  countPriority("p1"),
		"p2_pages":                  countPriority("p2"),
		"p3_pages":                  countPriority("p3"),
		"propagated_services":       propagatedCount,
		"quarantined_hotspot_nodes": countNodeStatus("quarantined_hotspot"),
		"quarantined_nodes":         countNodeStatus("quarantined"),
		"services_critical":         countSev("critical"),
		"services_healthy":          countSev("healthy"),
		"services_total":            len(anomalyServices),
		"services_warning":          countSev("warning"),
	}

	writeJSON(filepath.Join(reportDir, "anomaly_report.json"), map[string]interface{}{"services": anomalyServices})
	writeJSON(filepath.Join(reportDir, "blast_radius.json"), map[string]interface{}{"roots": blastRoots})
	writeJSON(filepath.Join(reportDir, "paging_plan.json"), map[string]interface{}{"pages": pages})
	writeJSON(filepath.Join(reportDir, "node_health.json"), map[string]interface{}{"nodes": nodes})
	writeJSON(filepath.Join(reportDir, "summary.json"), summary)
}
GOEOF

cd "$SRC_DIR"
go build -trimpath -o "$BIN_DIR/auditor" .

GIA_SIGNALS_DIR="${GIA_SIGNALS_DIR:-/app/signals}" \
GIA_REPORT_DIR="$REPORT_DIR" \
"$BIN_DIR/auditor"
