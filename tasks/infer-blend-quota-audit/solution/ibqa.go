package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type policyFile struct {
	AllocationDay int `json:"allocation_day"`
	SharedGroups  []struct {
		CapUnits int    `json:"cap_units"`
		GroupID  string `json:"group_id"`
	} `json:"shared_groups"`
	TierPriority []string `json:"tier_priority"`
}

type incidentFile struct {
	Events []incidentEvent `json:"events"`
}

type incidentEvent struct {
	Accepted *bool `json:"accepted"`
	EndDay   int   `json:"end_day"`
	FactorBP *int  `json:"factor_bp,omitempty"`
	Kind     string `json:"kind"`
	PoolID   string `json:"pool_id,omitempty"`
	RouteID  string `json:"route_id,omitempty"`
	StartDay int   `json:"start_day"`
}

type poolFile struct {
	CapacityUnits int    `json:"capacity_units"`
	PoolID        string `json:"pool_id"`
	ShareGroup    string `json:"share_group,omitempty"`
}

type routeFile struct {
	CanaryPool     string `json:"canary_pool"`
	ForecastUnits  int    `json:"forecast_units"`
	PrimaryPool    string `json:"primary_pool"`
	PrimaryShareBP int    `json:"primary_share_bp"`
	RouteID        string `json:"route_id"`
	ShadowCanary   bool   `json:"shadow_canary,omitempty"`
	Tier           string `json:"tier"`
}

type routeOut struct {
	CanaryAllocated  int      `json:"canary_allocated"`
	CanaryRequested  int      `json:"canary_requested"`
	PrimaryAllocated int      `json:"primary_allocated"`
	PrimaryRequested int      `json:"primary_requested"`
	Reasons          []string `json:"reasons"`
	RouteID          string   `json:"route_id"`
	ShadowCanary     bool     `json:"shadow_canary"`
	Status           string   `json:"status"`
	Tier             string   `json:"tier"`
}

type poolRow struct {
	CanaryDrawn       int    `json:"canary_drawn"`
	CapacityEffective int    `json:"capacity_effective"`
	PoolID            string `json:"pool_id"`
	PrimaryDrawn      int    `json:"primary_drawn"`
	RemainingUnits    int    `json:"remaining_units"`
}

type groupRow struct {
	CapUnits       int    `json:"cap_units"`
	GroupID        string `json:"group_id"`
	RemainingUnits int    `json:"remaining_units"`
}

type poolUsageOut struct {
	Pools        []poolRow  `json:"pools"`
	SharedGroups []groupRow `json:"shared_groups"`
}

type statusCounts struct {
	BothShortfall   int `json:"both_shortfall"`
	CanaryShortfall int `json:"canary_shortfall"`
	Frozen          int `json:"frozen"`
	OK              int `json:"ok"`
	PrimaryShort    int `json:"primary_shortfall"`
}

type summaryOut struct {
	AllocationDay   int          `json:"allocation_day"`
	FrozenRoutes    int          `json:"frozen_routes"`
	GroupsBinding   []string     `json:"groups_binding"`
	PoolsTouched    []string     `json:"pools_touched"`
	RoutesProcessed int          `json:"routes_processed"`
	StatusCounts    statusCounts `json:"status_counts"`
}

func readJSON(path string, dst any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, dst); err != nil {
		panic(fmt.Sprintf("%s: %v", path, err))
	}
}

func tierRank(tier string, priority []string) int {
	for i, t := range priority {
		if t == tier {
			return i
		}
	}
	return 1000
}

func main() {
	dataDir := os.Getenv("IBQA_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/infer_blend"
	}
	auditDir := os.Getenv("IBQA_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		panic(err)
	}

	var pol policyFile
	readJSON(filepath.Join(dataDir, "policy.json"), &pol)
	var inc incidentFile
	readJSON(filepath.Join(dataDir, "incidents.json"), &inc)

	poolPaths, err := filepath.Glob(filepath.Join(dataDir, "pools", "*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(poolPaths)
	pools := map[string]poolFile{}
	baseline := map[string]int{}
	for _, p := range poolPaths {
		var pf poolFile
		readJSON(p, &pf)
		pools[pf.PoolID] = pf
		baseline[pf.PoolID] = pf.CapacityUnits
	}

	routePaths, err := filepath.Glob(filepath.Join(dataDir, "routes", "*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(routePaths)
	routes := make([]routeFile, 0, len(routePaths))
	for _, rp := range routePaths {
		var rf routeFile
		readJSON(rp, &rf)
		routes = append(routes, rf)
	}

	eff := map[string]int{}
	for id, cap := range baseline {
		eff[id] = cap
	}
	day := pol.AllocationDay
	for _, ev := range inc.Events {
		if ev.Accepted == nil || !*ev.Accepted {
			continue
		}
		if ev.Kind != "pool_derate" {
			continue
		}
		if ev.FactorBP == nil || ev.PoolID == "" {
			continue
		}
		if day < ev.StartDay || day > ev.EndDay {
			continue
		}
		cur, ok := eff[ev.PoolID]
		if !ok {
			continue
		}
		eff[ev.PoolID] = (cur * (*ev.FactorBP)) / 10000
	}

	frozen := map[string]bool{}
	for _, ev := range inc.Events {
		if ev.Accepted == nil || !*ev.Accepted {
			continue
		}
		if ev.Kind != "route_freeze" {
			continue
		}
		if day < ev.StartDay || day > ev.EndDay {
			continue
		}
		if ev.RouteID != "" {
			frozen[ev.RouteID] = true
		}
	}

	groupCap := map[string]int{}
	for _, g := range pol.SharedGroups {
		groupCap[g.GroupID] = g.CapUnits
	}

	poolRem := map[string]int{}
	for id, cap := range eff {
		poolRem[id] = cap
	}
	groupRem := map[string]int{}
	for k, v := range groupCap {
		groupRem[k] = v
	}

	poolPrimary := map[string]int{}
	poolCanary := map[string]int{}
	for id := range pools {
		poolPrimary[id] = 0
		poolCanary[id] = 0
	}

	groupsBinding := map[string]bool{}

	type drawMeta struct {
		Actual           int
		LimitedByGroup   bool
		LimitedByPool    bool
		GroupID          string
		GroupRemBefore   int
		PoolRemBefore    int
	}

	draw := func(want int, poolID string, shadow bool) drawMeta {
		dm := drawMeta{Actual: 0, PoolRemBefore: poolRem[poolID]}
		if shadow || want <= 0 {
			return dm
		}
		plBefore := poolRem[poolID]
		dm.PoolRemBefore = plBefore
		gid := ""
		if p, ok := pools[poolID]; ok {
			gid = p.ShareGroup
		}
		lim := want
		if lim > plBefore {
			lim = plBefore
		}
		grBefore := 0
		if gid != "" {
			grBefore = groupRem[gid]
			dm.GroupID = gid
			dm.GroupRemBefore = grBefore
			if lim > grBefore {
				lim = grBefore
			}
		}
		dm.Actual = lim
		if want > lim {
			if lim == plBefore {
				dm.LimitedByPool = true
			}
			if gid != "" && lim == grBefore {
				dm.LimitedByGroup = true
				groupsBinding[gid] = true
			}
		}
		poolRem[poolID] -= dm.Actual
		if gid != "" {
			groupRem[gid] -= dm.Actual
		}
		return dm
	}

	sort.SliceStable(routes, func(i, j int) bool {
		ti := tierRank(routes[i].Tier, pol.TierPriority)
		tj := tierRank(routes[j].Tier, pol.TierPriority)
		if ti != tj {
			return ti < tj
		}
		return routes[i].RouteID < routes[j].RouteID
	})

	outs := make([]routeOut, 0, len(routes))
	sc := statusCounts{}

	for _, rt := range routes {
		if frozen[rt.RouteID] {
			sc.Frozen++
			outs = append(outs, routeOut{
				CanaryAllocated:  0,
				CanaryRequested:  0,
				PrimaryAllocated: 0,
				PrimaryRequested: 0,
				Reasons:          []string{},
				RouteID:          rt.RouteID,
				ShadowCanary:     rt.ShadowCanary,
				Status:           "frozen",
				Tier:             rt.Tier,
			})
			continue
		}

		pReq := (rt.ForecastUnits * rt.PrimaryShareBP) / 10000
		cReq := rt.ForecastUnits - pReq

		pMeta := draw(pReq, rt.PrimaryPool, false)
		pDraw := pMeta.Actual
		poolPrimary[rt.PrimaryPool] += pDraw

		cMeta := draw(cReq, rt.CanaryPool, rt.ShadowCanary)
		cDraw := cMeta.Actual
		if !rt.ShadowCanary {
			poolCanary[rt.CanaryPool] += cDraw
		}

		reasons := map[string]bool{}
		if pReq > pDraw {
			reasons["primary_pool_exhausted"] = true
		}
		if !rt.ShadowCanary && cReq > cDraw {
			reasons["canary_pool_exhausted"] = true
		}
		if pMeta.LimitedByGroup {
			reasons["shared_group_exhausted"] = true
		}
		if cMeta.LimitedByGroup {
			reasons["shared_group_exhausted"] = true
		}

		var status string
		ps := pReq > pDraw
		cs := cReq > cDraw
		switch {
		case ps && cs:
			status = "both_shortfall"
			sc.BothShortfall++
		case ps:
			status = "primary_shortfall"
			sc.PrimaryShort++
		case cs:
			status = "canary_shortfall"
			sc.CanaryShortfall++
		default:
			status = "ok"
			sc.OK++
		}

		rs := make([]string, 0, len(reasons))
		for k := range reasons {
			rs = append(rs, k)
		}
		sort.Strings(rs)

		outs = append(outs, routeOut{
			CanaryAllocated:  cDraw,
			CanaryRequested:  cReq,
			PrimaryAllocated: pDraw,
			PrimaryRequested: pReq,
			Reasons:          rs,
			RouteID:          rt.RouteID,
			ShadowCanary:     rt.ShadowCanary,
			Status:           status,
			Tier:             rt.Tier,
		})
	}

	sort.Slice(outs, func(i, j int) bool { return outs[i].RouteID < outs[j].RouteID })

	poolIDs := make([]string, 0, len(pools))
	for id := range pools {
		poolIDs = append(poolIDs, id)
	}
	sort.Strings(poolIDs)

	pu := make([]poolRow, 0, len(poolIDs))
	touched := []string{}
	for _, pid := range poolIDs {
		pr := poolPrimary[pid]
		cr := poolCanary[pid]
		if pr+cr > 0 {
			touched = append(touched, pid)
		}
		pu = append(pu, poolRow{
			CapacityEffective: eff[pid],
			CanaryDrawn:       cr,
			PoolID:            pid,
			PrimaryDrawn:      pr,
			RemainingUnits:    poolRem[pid],
		})
	}

	grIDs := make([]string, 0, len(groupCap))
	for gid := range groupCap {
		grIDs = append(grIDs, gid)
	}
	sort.Strings(grIDs)
	grOut := make([]groupRow, 0, len(grIDs))
	for _, gid := range grIDs {
		grOut = append(grOut, groupRow{
			CapUnits:       groupCap[gid],
			GroupID:        gid,
			RemainingUnits: groupRem[gid],
		})
	}

	gb := make([]string, 0, len(groupsBinding))
	for gid := range groupsBinding {
		gb = append(gb, gid)
	}
	sort.Strings(gb)

	sum := summaryOut{
		AllocationDay:   day,
		FrozenRoutes:    sc.Frozen,
		GroupsBinding:   gb,
		PoolsTouched:    touched,
		RoutesProcessed: len(routes),
		StatusCounts:    sc,
	}

	write := func(name string, v any) {
		b, err := json.MarshalIndent(v, "", "  ")
		if err != nil {
			panic(err)
		}
		b = append(b, '\n')
		if err := os.WriteFile(filepath.Join(auditDir, name), b, 0o644); err != nil {
			panic(err)
		}
	}

	type allocRoot struct {
		Routes []routeOut `json:"routes"`
	}
	write("allocations.json", allocRoot{Routes: outs})
	write("pool_usage.json", poolUsageOut{Pools: pu, SharedGroups: grOut})
	write("summary.json", sum)
}
