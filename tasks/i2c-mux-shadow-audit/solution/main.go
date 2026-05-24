package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type nodeRow struct {
	id, tier, mux string
	addr7, serial int
	parent        string
}

type incRow struct {
	id, kind, target string
	day, valA, valB  int
	accepted         bool
}

func readTSV(path string) [][]string {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	var rows [][]string
	for _, line := range strings.Split(string(b), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.Split(line, "|")
		for i := range parts {
			parts[i] = strings.TrimSpace(parts[i])
		}
		rows = append(rows, parts)
	}
	return rows
}

func atoi(s string) int {
	v, err := strconv.Atoi(strings.TrimSpace(s))
	if err != nil {
		panic(err)
	}
	return v
}

func tierRank(t string) int {
	switch t {
	case "gold":
		return 3
	case "silver":
		return 2
	case "bronze":
		return 1
	default:
		return 0
	}
}

func main() {
	bus := os.Getenv("IMX_BUS_DIR")
	if bus == "" {
		bus = "/app/i2c_bus"
	}
	outDir := os.Getenv("IMX_AUDIT_DIR")
	if outDir == "" {
		outDir = "/app/audit"
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		panic(err)
	}

	rows := readTSV(filepath.Join(bus, "clock.tsv"))
	currentDay := atoi(rows[0][1])

	policy := map[string]struct {
		floor int
		cap   int
	}{}
	for _, r := range readTSV(filepath.Join(bus, "policy.tsv"))[1:] {
		policy[r[0]] = struct {
			floor int
			cap   int
		}{atoi(r[1]), atoi(r[2])}
	}

	nodes := map[string]nodeRow{}
	var order []string
	for _, r := range readTSV(filepath.Join(bus, "nodes.tsv"))[1:] {
		n := nodeRow{
			id: r[0], tier: r[1], mux: r[3], parent: r[5],
			addr7: atoi(r[2]), serial: atoi(r[4]),
		}
		nodes[n.id] = n
		order = append(order, n.id)
	}
	sort.Strings(order)

	children := map[string][]string{}
	for id, n := range nodes {
		if n.parent == "-" {
			continue
		}
		children[n.parent] = append(children[n.parent], id)
	}
	for k := range children {
		sort.Strings(children[k])
	}

	descendants := func(root string) []string {
		out := []string{}
		var dfs func(string)
		dfs = func(x string) {
			out = append(out, x)
			for _, c := range children[x] {
				dfs(c)
			}
		}
		dfs(root)
		return out
	}

	var incs []incRow
	for _, r := range readTSV(filepath.Join(bus, "incidents.tsv"))[1:] {
		acc := r[6] == "true"
		incs = append(incs, incRow{
			id: r[0], kind: r[2], target: r[3],
			day: atoi(r[1]), valA: atoi(r[4]), valB: atoi(r[5]),
			accepted: acc,
		})
	}

	supported := map[string]bool{
		"hub_compromise": true,
		"mux_freeze":     true,
		"clock_stretch":  true,
		"nak_burst":      true,
	}

	validTarget := func(kind, target string) bool {
		switch kind {
		case "hub_compromise", "clock_stretch", "nak_burst":
			_, ok := nodes[target]
			return ok
		case "mux_freeze":
			for _, n := range nodes {
				if n.mux == target {
					return true
				}
			}
			return false
		default:
			return false
		}
	}

	type cand struct {
		inc incRow
	}
	buckets := map[string][]cand{}
	ignored := 0

	for _, ir := range incs {
		if !ir.accepted {
			ignored++
			continue
		}
		if ir.day > currentDay || !supported[ir.kind] || !validTarget(ir.kind, ir.target) {
			ignored++
			continue
		}
		key := ir.kind + "\x00" + ir.target
		buckets[key] = append(buckets[key], cand{ir})
	}

	winners := map[string]incRow{}
	for key, group := range buckets {
		if len(group) == 0 {
			continue
		}
		sort.SliceStable(group, func(i, j int) bool {
			if group[i].inc.day != group[j].inc.day {
				return group[i].inc.day > group[j].inc.day
			}
			return group[i].inc.id < group[j].inc.id
		})
		winners[key] = group[0].inc
		ignored += len(group) - 1
	}

	quarantine := map[string]bool{}
	frozenSeg := map[string]bool{}
	nak := map[string]bool{}
	stretchAdds := []incRow{}

	for _, ir := range winners {
		switch ir.kind {
		case "hub_compromise":
			for _, id := range descendants(ir.target) {
				quarantine[id] = true
			}
		case "mux_freeze":
			frozenSeg[ir.target] = true
		case "clock_stretch":
			stretchAdds = append(stretchAdds, ir)
		case "nak_burst":
			nak[ir.target] = true
		}
	}

	rawStretch := map[string]int{}
	for _, id := range order {
		rawStretch[id] = 0
	}
	for _, st := range stretchAdds {
		for _, id := range descendants(st.target) {
			rawStretch[id] += st.valA
		}
	}

	effectiveStretch := map[string]int{}
	clamped := map[string]bool{}
	for _, id := range order {
		n := nodes[id]
		p := policy[n.tier]
		sum := rawStretch[id]
		if sum > p.cap {
			clamped[id] = true
		}
		eff := sum
		if eff > p.cap {
			eff = p.cap
		}
		effectiveStretch[id] = eff
	}

	probePeak := map[string]int{}
	for _, id := range order {
		probePeak[id] = 0
	}
	entries, _ := os.ReadDir(filepath.Join(bus, "probes"))
	var names []string
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		if strings.HasSuffix(e.Name(), ".tsv") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		rows := readTSV(filepath.Join(bus, "probes", name))
		start := 0
		if len(rows) > 0 && len(rows[0]) > 0 && rows[0][0] == "node_id" {
			start = 1
		}
		for _, r := range rows[start:] {
			if len(r) < 2 {
				continue
			}
			id := r[0]
			ms := atoi(r[1])
			if _, ok := nodes[id]; !ok {
				continue
			}
			if ms > probePeak[id] {
				probePeak[id] = ms
			}
		}
	}

	activeForCollision := map[string]bool{}
	for id := range nodes {
		if quarantine[id] {
			continue
		}
		activeForCollision[id] = true
	}

	type groupKey struct {
		addr int
		mux  string
	}
	groups := map[groupKey][]string{}
	for id := range activeForCollision {
		n := nodes[id]
		gk := groupKey{addr: n.addr7, mux: n.mux}
		groups[gk] = append(groups[gk], id)
	}
	for k := range groups {
		sort.Strings(groups[k])
	}

	loser := map[string]bool{}
	winnersCollision := map[string]bool{}
	for _, ids := range groups {
		if len(ids) < 2 {
			continue
		}
		sort.Slice(ids, func(i, j int) bool {
			ni, nj := nodes[ids[i]], nodes[ids[j]]
			if tierRank(ni.tier) != tierRank(nj.tier) {
				return tierRank(ni.tier) > tierRank(nj.tier)
			}
			if ni.serial != nj.serial {
				return ni.serial < nj.serial
			}
			return ni.id < nj.id
		})
		w := ids[0]
		winnersCollision[w] = true
		for _, id := range ids[1:] {
			loser[id] = true
		}
	}

	status := map[string]string{}
	for _, id := range order {
		switch {
		case quarantine[id]:
			status[id] = "quarantined"
		case frozenSeg[nodes[id].mux]:
			status[id] = "frozen"
		case loser[id]:
			status[id] = "shadowed"
		case nak[id]:
			status[id] = "degraded"
		default:
			status[id] = "active"
		}
	}

	reasonsFor := func(id string) []string {
		var rs []string
		st := status[id]
		if st == "shadowed" {
			rs = append(rs, "collision_loser")
		}
		if st == "frozen" {
			rs = append(rs, "mux_frozen")
		}
		if nak[id] && st == "degraded" {
			rs = append(rs, "nak_degraded")
		}
		if st == "quarantined" {
			rs = append(rs, "quarantine")
		}
		if clamped[id] {
			rs = append(rs, "stretch_clamped")
		}
		if len(rs) == 0 {
			rs = append(rs, "nominal")
		}
		sort.Strings(rs)
		return rs
	}

	type nodeStatus struct {
		Addr7          int      `json:"addr7"`
		MergedBudgetMs int      `json:"merged_budget_ms"`
		MuxSegment     string   `json:"mux_segment"`
		NodeID         string   `json:"node_id"`
		Reasons        []string `json:"reasons"`
		Serial         int      `json:"serial"`
		Status         string   `json:"status"`
		Tier           string   `json:"tier"`
	}

	var nsOut []nodeStatus
	for _, id := range order {
		n := nodes[id]
		p := policy[n.tier]
		hold := p.floor + effectiveStretch[id]
		merged := hold + probePeak[id]
		nsOut = append(nsOut, nodeStatus{
			Addr7:          n.addr7,
			MergedBudgetMs: merged,
			MuxSegment:     n.mux,
			NodeID:         id,
			Reasons:        reasonsFor(id),
			Serial:         n.serial,
			Status:         status[id],
			Tier:           n.tier,
		})
	}

	type edge struct {
		Addr7      int    `json:"addr7"`
		Loser      string `json:"loser"`
		MuxSegment string `json:"mux_segment"`
		Winner     string `json:"winner"`
	}
	var edges []edge
	for _, ids := range groups {
		if len(ids) < 2 {
			continue
		}
		sort.Slice(ids, func(i, j int) bool {
			ni, nj := nodes[ids[i]], nodes[ids[j]]
			if tierRank(ni.tier) != tierRank(nj.tier) {
				return tierRank(ni.tier) > tierRank(nj.tier)
			}
			if ni.serial != nj.serial {
				return ni.serial < nj.serial
			}
			return ni.id < nj.id
		})
		w := ids[0]
		addr := nodes[w].addr7
		mux := nodes[w].mux
		for _, id := range ids[1:] {
			edges = append(edges, edge{Addr7: addr, Loser: id, MuxSegment: mux, Winner: w})
		}
	}
	sort.Slice(edges, func(i, j int) bool {
		if edges[i].Addr7 != edges[j].Addr7 {
			return edges[i].Addr7 < edges[j].Addr7
		}
		if edges[i].Loser != edges[j].Loser {
			return edges[i].Loser < edges[j].Loser
		}
		if edges[i].MuxSegment != edges[j].MuxSegment {
			return edges[i].MuxSegment < edges[j].MuxSegment
		}
		return edges[i].Winner < edges[j].Winner
	})

	segSet := map[string]bool{}
	for _, n := range nodes {
		segSet[n.mux] = true
	}
	var segs []string
	for s := range segSet {
		segs = append(segs, s)
	}
	sort.Strings(segs)

	type segRow struct {
		Frozen       bool   `json:"frozen"`
		Segment      string `json:"segment"`
		StretchSumMs int    `json:"stretch_sum_ms"`
	}
	var segOut []segRow
	for _, s := range segs {
		sum := 0
		for _, st := range stretchAdds {
			if nodes[st.target].mux == s {
				sum += st.valA
			}
		}
		segOut = append(segOut, segRow{
			Frozen:       frozenSeg[s],
			Segment:      s,
			StretchSumMs: sum,
		})
	}

	type timingRow struct {
		HoldMs             int    `json:"hold_ms"`
		MergedBudgetMs     int    `json:"merged_budget_ms"`
		NodeID             string `json:"node_id"`
		ProbePeakMs        int    `json:"probe_peak_ms"`
		StretchEffectiveMs int    `json:"stretch_effective_ms"`
	}
	var tm []timingRow
	for _, id := range order {
		n := nodes[id]
		p := policy[n.tier]
		hold := p.floor + effectiveStretch[id]
		tm = append(tm, timingRow{
			HoldMs:             hold,
			MergedBudgetMs:     hold + probePeak[id],
			NodeID:             id,
			ProbePeakMs:        probePeak[id],
			StretchEffectiveMs: effectiveStretch[id],
		})
	}

	byStatus := map[string]int{}
	for _, id := range order {
		byStatus[status[id]]++
	}
	frozenSegCount := 0
	for _, sr := range segOut {
		if sr.Frozen {
			frozenSegCount++
		}
	}
	qcount := 0
	for _, id := range order {
		if quarantine[id] {
			qcount++
		}
	}

	write := func(name string, v any) {
		b, err := json.MarshalIndent(v, "", "  ")
		if err != nil {
			panic(err)
		}
		b = append(b, '\n')
		if err := os.WriteFile(filepath.Join(outDir, name), b, 0o644); err != nil {
			panic(err)
		}
	}

	write("node_status.json", map[string]any{"nodes": nsOut})
	write("collision_edges.json", map[string]any{"edges": edges})
	write("segment_ledger.json", map[string]any{"segments": segOut})
	write("timing_merge.json", map[string]any{"nodes": tm})

	statusKeys := make([]string, 0, len(byStatus))
	for k := range byStatus {
		statusKeys = append(statusKeys, k)
	}
	sort.Strings(statusKeys)
	var statusPairs []string
	for _, k := range statusKeys {
		ke, err := json.Marshal(k)
		if err != nil {
			panic(err)
		}
		statusPairs = append(statusPairs, fmt.Sprintf("%s: %d", ke, byStatus[k]))
	}
	summaryJSON := fmt.Sprintf("{\n  \"collision_edge_count\": %d,\n  \"frozen_segments\": %d,\n  \"ignored_incident_events\": %d,\n  \"nodes_by_status\": {\n    %s\n  },\n  \"quarantined_nodes\": %d\n}\n",
		len(edges), frozenSegCount, ignored, strings.Join(statusPairs, ",\n    "), qcount)
	if err := os.WriteFile(filepath.Join(outDir, "summary.json"), []byte(summaryJSON), 0o644); err != nil {
		panic(err)
	}

	fmt.Fprintf(os.Stderr, "ignored=%d edges=%d\n", ignored, len(edges))
}
