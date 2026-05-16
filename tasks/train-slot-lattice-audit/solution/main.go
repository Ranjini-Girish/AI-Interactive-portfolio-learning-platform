package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
)

type PoolState struct {
	CurrentDay     int `json:"current_day"`
	ClusterSlotCap int `json:"cluster_slot_cap"`
}

type Policy struct {
	RungPrecedence []string `json:"rung_precedence"`
	TieBreak       []string `json:"tie_break"`
}

type Index struct {
	TenantFiles  []string `json:"tenant_files"`
	RequestFiles []string `json:"request_files"`
}

type Tenant struct {
	TenantID string `json:"tenant_id"`
	Weight   int    `json:"weight"`
}

type Request struct {
	RunID      string  `json:"run_id"`
	TenantID   string  `json:"tenant_id"`
	Rung       string  `json:"rung"`
	SubmitDay  int     `json:"submit_day"`
	SlotsAsked int     `json:"slots_asked"`
	DependsOn  *string `json:"depends_on"`
}

type Incident struct {
	Seq            int     `json:"seq"`
	Day            int     `json:"day"`
	Kind           string  `json:"kind"`
	TenantID       *string `json:"tenant_id"`
	RunID          *string `json:"run_id"`
	NewRung        *string `json:"new_rung"`
	ClusterSlotCap *int    `json:"cluster_slot_cap"`
}

type IncidentsFile struct {
	Events []Incident `json:"events"`
}

type edge struct {
	From string `json:"from"`
	To   string `json:"to"`
}

func main() {
	dataDir := os.Getenv("TSL_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/tslattice"
	}
	auditDir := os.Getenv("TSL_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		panic(err)
	}

	ps := mustReadJSON[PoolState](filepath.Join(dataDir, "pool_state.json"))
	pol := mustReadJSON[Policy](filepath.Join(dataDir, "policy.json"))
	idx := mustReadJSON[Index](filepath.Join(dataDir, "index.json"))
	incf := mustReadJSON[IncidentsFile](filepath.Join(dataDir, "incidents.json"))

	tenants := map[string]Tenant{}
	for _, rel := range idx.TenantFiles {
		t := mustReadJSON[Tenant](filepath.Join(dataDir, rel))
		tenants[t.TenantID] = t
	}

	requests := []Request{}
	runSet := map[string]bool{}
	for _, rel := range idx.RequestFiles {
		r := mustReadJSON[Request](filepath.Join(dataDir, rel))
		requests = append(requests, r)
		runSet[r.RunID] = true
	}

	sort.Slice(incf.Events, func(i, j int) bool { return incf.Events[i].Seq < incf.Events[j].Seq })
	trace := make([]map[string]any, 0, len(incf.Events))
	for _, ev := range incf.Events {
		applied := ev.Day <= ps.CurrentDay
		note := "future"
		if applied {
			note = "ok"
		}
		trace = append(trace, map[string]any{
			"applied": applied,
			"note":    note,
			"seq":     ev.Seq,
		})
	}

	active := make([]Incident, 0, len(incf.Events))
	for _, ev := range incf.Events {
		if ev.Day <= ps.CurrentDay {
			active = append(active, ev)
		}
	}
	sort.Slice(active, func(i, j int) bool { return active[i].Seq < active[j].Seq })

	effectiveCap := ps.ClusterSlotCap
	rungOverride := map[string]string{}
	freezeDay := map[string]int{}

	for _, ev := range active {
		switch ev.Kind {
		case "cap_trim":
			if ev.ClusterSlotCap != nil {
				effectiveCap = *ev.ClusterSlotCap
			}
		case "rung_override":
			if ev.RunID != nil && ev.NewRung != nil {
				rungOverride[*ev.RunID] = *ev.NewRung
			}
		case "freeze_tenant":
			if ev.TenantID != nil {
				tid := *ev.TenantID
				d := ev.Day
				if prev, ok := freezeDay[tid]; !ok || d < prev {
					freezeDay[tid] = d
				}
			}
		}
	}

	adj := map[string][]string{}
	edges := []edge{}
	for _, r := range requests {
		if r.DependsOn != nil && *r.DependsOn != "" {
			from := *r.DependsOn
			to := r.RunID
			adj[from] = append(adj[from], to)
			edges = append(edges, edge{From: from, To: to})
		}
	}
	for k := range adj {
		sort.Strings(adj[k])
		adj[k] = uniqSortedCopy(adj[k])
	}
	sort.Slice(edges, func(i, j int) bool {
		if edges[i].From != edges[j].From {
			return edges[i].From < edges[j].From
		}
		return edges[i].To < edges[j].To
	})

	verts := map[string]bool{}
	for _, r := range requests {
		verts[r.RunID] = true
	}
	for _, e := range edges {
		verts[e.From] = true
		verts[e.To] = true
	}
	vlist := make([]string, 0, len(verts))
	for v := range verts {
		vlist = append(vlist, v)
	}
	sort.Strings(vlist)

	components := kosaraju(vlist, adj)

	cycleMembers := map[string]bool{}
	var cycleGroups [][]string
	for _, comp := range components {
		cyclic := false
		if len(comp) > 1 {
			cyclic = true
		} else if len(comp) == 1 {
			u := comp[0]
			for _, w := range adj[u] {
				if w == u {
					cyclic = true
					break
				}
			}
		}
		if cyclic {
			cp := append([]string(nil), comp...)
			sort.Strings(cp)
			cycleGroups = append(cycleGroups, cp)
			for _, u := range cp {
				cycleMembers[u] = true
			}
		}
	}
	sort.Slice(cycleGroups, func(i, j int) bool {
		ai, aj := cycleGroups[i], cycleGroups[j]
		for k := 0; k < len(ai) && k < len(aj); k++ {
			if ai[k] != aj[k] {
				return ai[k] < aj[k]
			}
		}
		return len(ai) < len(aj)
	})

	knownRunIDs := make([]string, 0, len(requests))
	for _, r := range requests {
		knownRunIDs = append(knownRunIDs, r.RunID)
	}
	sort.Strings(knownRunIDs)
	knownRunIDs = uniqSortedCopy(knownRunIDs)

	type row struct {
		runID         string
		tenantID      string
		granted       int
		denied        any
		effectiveRung string
		req           Request
	}

	rows := make([]row, 0, len(requests))
	for _, r := range requests {
		effRung := r.Rung
		if nr, ok := rungOverride[r.RunID]; ok {
			effRung = nr
		}
		var dReason any = nil

		if r.SubmitDay > ps.CurrentDay {
			dReason = "not_submitted"
		} else if fd, ok := freezeDay[r.TenantID]; ok && r.SubmitDay >= fd {
			dReason = "frozen_tenant"
		} else if r.DependsOn != nil && *r.DependsOn != "" && !runSet[*r.DependsOn] {
			dReason = "unknown_dependency"
		} else if cycleMembers[r.RunID] {
			dReason = "cycle"
		} else if r.DependsOn != nil && *r.DependsOn != "" && cycleMembers[*r.DependsOn] {
			dReason = "blocked_dependency"
		}

		rows = append(rows, row{
			runID:         r.RunID,
			tenantID:      r.TenantID,
			granted:       0,
			denied:        dReason,
			effectiveRung: effRung,
			req:           r,
		})
	}

	rungIndex := func(name string) int {
		for i, n := range pol.RungPrecedence {
			if n == name {
				return i
			}
		}
		return 1_000_000_000
	}

	remain := effectiveCap
	grantedByRun := map[string]int{}

	candIdx := []int{}
	eligible := 0
	for i := range rows {
		if rows[i].denied == nil {
			candIdx = append(candIdx, i)
			eligible++
		}
	}
	sort.Slice(candIdx, func(a, b int) bool {
		ra, rb := rows[candIdx[a]], rows[candIdx[b]]
		ia, ib := rungIndex(ra.effectiveRung), rungIndex(rb.effectiveRung)
		if ia != ib {
			return ia < ib
		}
		if ra.effectiveRung != rb.effectiveRung {
			return ra.effectiveRung < rb.effectiveRung
		}
		wa := tenants[ra.tenantID].Weight
		wb := tenants[rb.tenantID].Weight
		for _, tb := range pol.TieBreak {
			switch tb {
			case "tenant_weight_desc":
				if wa != wb {
					return wa > wb
				}
				if ra.tenantID != rb.tenantID {
					return ra.tenantID < rb.tenantID
				}
			case "run_id_asc":
				return ra.runID < rb.runID
			}
		}
		return ra.runID < rb.runID
	})

	for _, ci := range candIdx {
		r := rows[ci].req
		if r.DependsOn != nil && *r.DependsOn != "" {
			if grantedByRun[*r.DependsOn] <= 0 {
				rows[ci].denied = "blocked_dependency"
				continue
			}
		}
		if remain <= 0 {
			rows[ci].denied = "saturated"
			continue
		}
		g := r.SlotsAsked
		if g > remain {
			g = remain
		}
		rows[ci].granted = g
		rows[ci].denied = nil
		grantedByRun[r.RunID] = g
		remain -= g
	}

	edgeObjs := make([]map[string]any, 0, len(edges))
	for _, e := range edges {
		edgeObjs = append(edgeObjs, map[string]any{
			"from": e.From,
			"to":   e.To,
		})
	}

	allocs := make([]map[string]any, 0, len(rows))
	for _, rw := range rows {
		allocs = append(allocs, map[string]any{
			"denied_reason": rw.denied,
			"granted_slots": rw.granted,
			"run_id":        rw.runID,
			"tenant_id":     rw.tenantID,
		})
	}
	sort.Slice(allocs, func(i, j int) bool {
		return allocs[i]["run_id"].(string) < allocs[j]["run_id"].(string)
	})

	tenantIDs := map[string]bool{}
	for _, rw := range rows {
		tenantIDs[rw.tenantID] = true
	}
	tids := make([]string, 0, len(tenantIDs))
	for t := range tenantIDs {
		tids = append(tids, t)
	}
	sort.Strings(tids)

	tutil := map[string]any{}
	for _, tid := range tids {
		slots := 0
		served := 0
		denied := 0
		for _, rw := range rows {
			if rw.tenantID != tid {
				continue
			}
			slots += rw.granted
			if rw.granted > 0 {
				served++
			} else if rw.denied != nil {
				denied++
			}
		}
		tutil[tid] = map[string]any{
			"requests_denied": denied,
			"requests_served": served,
			"slots_granted":   slots,
		}
	}

	cycleBound := 0
	grantedPos := 0
	for _, rw := range rows {
		if rw.denied == "cycle" {
			cycleBound++
		}
		if rw.granted > 0 {
			grantedPos++
		}
	}

	appliedN := 0
	for _, t := range trace {
		if t["applied"].(bool) {
			appliedN++
		}
	}

	summary := map[string]any{
		"cycle_bound_total":            cycleBound,
		"effective_cluster_slot_cap":   effectiveCap,
		"eligible_total":               eligible,
		"granted_positive_total":       grantedPos,
		"incidents_applied_total":      appliedN,
		"incidents_seen_total":         len(incf.Events),
		"requests_total":               len(rows),
	}

	writeCanonicalJSON(filepath.Join(auditDir, "dependency_graph.json"), map[string]any{
		"cycle_groups":  toAny2D(cycleGroups),
		"edges":         toAnySlice(edgeObjs),
		"known_run_ids": toAnyStringSlice(knownRunIDs),
	})
	writeCanonicalJSON(filepath.Join(auditDir, "allocation_plan.json"), map[string]any{
		"allocations": toAnySlice(allocs),
	})
	writeCanonicalJSON(filepath.Join(auditDir, "incident_trace.json"), map[string]any{
		"events": toAnySlice(trace),
	})
	writeCanonicalJSON(filepath.Join(auditDir, "tenant_utilization.json"), map[string]any{
		"tenants": tutil,
	})
	writeCanonicalJSON(filepath.Join(auditDir, "summary.json"), summary)
}

func kosaraju(vertices []string, adj map[string][]string) [][]string {
	seen := map[string]bool{}
	var order []string
	var dfs1 func(string)
	dfs1 = func(v string) {
		if seen[v] {
			return
		}
		seen[v] = true
		for _, w := range adj[v] {
			dfs1(w)
		}
		order = append(order, v)
	}
	for _, v := range vertices {
		dfs1(v)
	}

	radj := map[string][]string{}
	for v, ws := range adj {
		for _, w := range ws {
			radj[w] = append(radj[w], v)
		}
	}
	for k := range radj {
		sort.Strings(radj[k])
	}

	seen2 := map[string]bool{}
	var dfs2 func(string, *[]string)
	dfs2 = func(v string, acc *[]string) {
		if seen2[v] {
			return
		}
		seen2[v] = true
		*acc = append(*acc, v)
		for _, w := range radj[v] {
			dfs2(w, acc)
		}
	}

	var comps [][]string
	for i := len(order) - 1; i >= 0; i-- {
		v := order[i]
		if seen2[v] {
			continue
		}
		var comp []string
		dfs2(v, &comp)
		sort.Strings(comp)
		comps = append(comps, comp)
	}
	return comps
}

func writeCanonicalJSON(path string, v any) {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		panic(err)
	}
	b = bytes.TrimRight(b, "\n")
	if err := os.WriteFile(path, append(b, '\n'), 0o644); err != nil {
		panic(err)
	}
}

func mustReadJSON[T any](path string) T {
	raw, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	var out T
	if err := json.Unmarshal(raw, &out); err != nil {
		panic(err)
	}
	return out
}

func uniqSortedCopy(in []string) []string {
	if len(in) == 0 {
		return in
	}
	sort.Strings(in)
	out := []string{in[0]}
	for i := 1; i < len(in); i++ {
		if in[i] != in[i-1] {
			out = append(out, in[i])
		}
	}
	return out
}

func toAny2D(in [][]string) []any {
	out := make([]any, len(in))
	for i := range in {
		out[i] = toAnyStringSlice(in[i])
	}
	return out
}

func toAnyStringSlice(in []string) []any {
	out := make([]any, len(in))
	for i, s := range in {
		out[i] = s
	}
	return out
}

func toAnySlice(in []map[string]any) []any {
	out := make([]any, len(in))
	for i, m := range in {
		out[i] = m
	}
	return out
}
