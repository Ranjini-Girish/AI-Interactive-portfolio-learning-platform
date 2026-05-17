package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type policyDoc struct {
	MaxWarmupCostPerStack map[string]int     `json:"max_warmup_cost_per_stack"`
	TierCalendar          map[string][][]int `json:"tier_calendar"`
	TierRank              map[string]int     `json:"tier_rank"`
}

type stackDoc struct {
	ActiveProfiles  []string       `json:"active_profiles"`
	AlreadyStarted  []string       `json:"already_started"`
	ClusterID       string         `json:"cluster_id"`
	HealthStreak    map[string]int `json:"health_streak"`
	RolloutWindows  [][]int        `json:"rollout_windows"`
	StackID         string         `json:"stack_id"`
	Tier            string         `json:"tier"`
}

type serviceDoc struct {
	DependsOn           []string `json:"depends_on"`
	HealthDaysRequired  int      `json:"health_days_required"`
	Priority            int      `json:"priority"`
	Profiles            []string `json:"profiles"`
	ServiceID           string   `json:"service_id"`
	WarmupCost          int      `json:"warmup_cost"`
}

type clusterDoc struct {
	ClusterID        string `json:"cluster_id"`
	MaxStartsPerDay  int    `json:"max_starts_per_day"`
	StartCredits     int    `json:"start_credits"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type blockedRow struct {
	Reason    string `json:"reason"`
	ServiceID string `json:"service_id"`
}

type stackRow struct {
	BlockedCandidates []blockedRow `json:"blocked_candidates"`
	ClusterID         string       `json:"cluster_id"`
	ScheduledService  any          `json:"scheduled_service"`
	StackID           string       `json:"stack_id"`
	StackStatus       string       `json:"stack_status"`
	Tier              string       `json:"tier"`
}

func main() {
	dataDir := getenv("CSOA_DATA_DIR", "/app/compose_plans")
	auditDir := getenv("CSOA_AUDIT_DIR", "/app/audit")
	if err := run(dataDir, auditDir); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func run(dataDir, auditDir string) error {
	var ps poolState
	if err := readJSON(filepath.Join(dataDir, "pool_state.json"), &ps); err != nil {
		return err
	}
	var pol policyDoc
	if err := readJSON(filepath.Join(dataDir, "policy.json"), &pol); err != nil {
		return err
	}
	var il incidentLog
	if err := readJSON(filepath.Join(dataDir, "incident_log.json"), &il); err != nil {
		return err
	}

	services, err := loadServices(filepath.Join(dataDir, "services"))
	if err != nil {
		return err
	}
	serviceByID := map[string]serviceDoc{}
	for _, s := range services {
		serviceByID[s.ServiceID] = s
	}
	stacks, err := loadStacks(filepath.Join(dataDir, "stacks"))
	if err != nil {
		return err
	}
	clusters, err := loadClusters(filepath.Join(dataDir, "clusters"))
	if err != nil {
		return err
	}

	day := ps.CurrentDay
	applied, kept, ignored := processIncidents(il.Events, day)
	embargoed := embargoSet(applied, day)
	compromise := compromiseSet(applied, day)
	frozen := freezeSet(applied, day)
	effectiveCap := clusterCaps(clusters, applied)
	creditsStart := clusterCredits(clusters, applied)
	creditsRemaining := map[string]int{}
	for k, v := range creditsStart {
		creditsRemaining[k] = v
	}

	type pick struct {
		service string
		stack   stackDoc
	}
	var contenders []pick

	stackBlocked := map[string][]blockedRow{}
	stackStatus := map[string]string{}
	stackScheduled := map[string]any{}

	for _, st := range stacks {
		startedSet := stringSet(st.AlreadyStarted)
		inWindow := dayInEffectiveWindow(st, pol, day)
		quarantined := compromise[st.StackID]
		frozenStack := frozen[st.ClusterID]
		maxCost := pol.MaxWarmupCostPerStack[st.Tier]

		var blocked []blockedRow
		var candidates []serviceDoc

		for _, svc := range services {
			if startedSet[svc.ServiceID] {
				continue
			}
			reason := blockReason(svc, st, inWindow, embargoed, quarantined, frozenStack, startedSet, maxCost)
			if reason == "" {
				candidates = append(candidates, svc)
				continue
			}
			blocked = append(blocked, blockedRow{ServiceID: svc.ServiceID, Reason: reason})
		}

		sort.Slice(blocked, func(i, j int) bool { return blocked[i].ServiceID < blocked[j].ServiceID })
		if blocked == nil {
			blocked = []blockedRow{}
		}
		stackBlocked[st.StackID] = blocked

		switch {
		case quarantined:
			stackStatus[st.StackID] = "quarantined"
			stackScheduled[st.StackID] = nil
		case frozenStack:
			stackStatus[st.StackID] = "cluster_frozen"
			stackScheduled[st.StackID] = nil
		default:
			chosen := chooseService(candidates)
			if chosen == "" {
				stackStatus[st.StackID] = "idle"
				stackScheduled[st.StackID] = nil
			} else {
				contenders = append(contenders, pick{stack: st, service: chosen})
			}
		}
	}

	sort.Slice(contenders, func(i, j int) bool {
		ri := pol.TierRank[contenders[i].stack.Tier]
		rj := pol.TierRank[contenders[j].stack.Tier]
		if ri != rj {
			return ri < rj
		}
		return contenders[i].stack.StackID < contenders[j].stack.StackID
	})

	clScheduled := map[string]int{}
	clDeferredCap := map[string]int{}
	clDeferredWarmup := map[string]int{}

	for _, c := range contenders {
		cl := c.stack.ClusterID
		cap := effectiveCap[cl]
		svc := serviceByID[c.service]
		if clScheduled[cl] >= cap {
			stackStatus[c.stack.StackID] = "deferred_capacity"
			stackScheduled[c.stack.StackID] = nil
			clDeferredCap[cl]++
			updateBlockedReason(stackBlocked, c.stack.StackID, c.service, "capacity_deferred")
			continue
		}
		if creditsRemaining[cl] < svc.WarmupCost {
			stackStatus[c.stack.StackID] = "warmup_deferred"
			stackScheduled[c.stack.StackID] = nil
			clDeferredWarmup[cl]++
			updateBlockedReason(stackBlocked, c.stack.StackID, c.service, "warmup_deferred")
			continue
		}
		clScheduled[cl]++
		creditsRemaining[cl] -= svc.WarmupCost
		stackStatus[c.stack.StackID] = "scheduled"
		stackScheduled[c.stack.StackID] = c.service
	}

	var stackRows []stackRow
	sort.Slice(stacks, func(i, j int) bool { return stacks[i].StackID < stacks[j].StackID })
	for _, st := range stacks {
		status := stackStatus[st.StackID]
		if status == "" {
			status = "idle"
		}
		stackRows = append(stackRows, stackRow{
			StackID:           st.StackID,
			ClusterID:         st.ClusterID,
			Tier:              st.Tier,
			StackStatus:       status,
			ScheduledService:  stackScheduled[st.StackID],
			BlockedCandidates: stackBlocked[st.StackID],
		})
	}

	clusterLedger := buildClusterLedger(
		clusters, effectiveCap, creditsStart, creditsRemaining,
		clScheduled, clDeferredCap, clDeferredWarmup,
	)
	serviceMatrix := buildServiceMatrix(services, stackRows)
	journal := buildJournal(kept)
	summary := buildSummary(stackRows, services, clusters, kept, ignored, il.Events)

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "stack_plan.json"), map[string]any{"stacks": stackRows}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "cluster_ledger.json"), map[string]any{"clusters": clusterLedger}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "service_matrix.json"), map[string]any{"services": serviceMatrix}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "incident_journal.json"), map[string]any{"applied_events": journal}); err != nil {
		return err
	}
	return writeJSON(filepath.Join(auditDir, "summary.json"), summary)
}

func profileOverlap(svc serviceDoc, st stackDoc) bool {
	for _, p := range svc.Profiles {
		for _, ap := range st.ActiveProfiles {
			if p == ap {
				return true
			}
		}
	}
	return false
}

func healthOK(svc serviceDoc, st stackDoc) bool {
	streak := 0
	if st.HealthStreak != nil {
		streak = st.HealthStreak[svc.ServiceID]
	}
	return streak >= svc.HealthDaysRequired
}

func updateBlockedReason(blocked map[string][]blockedRow, stackID, serviceID, reason string) {
	updated := false
	for i := range blocked[stackID] {
		if blocked[stackID][i].ServiceID == serviceID {
			blocked[stackID][i].Reason = reason
			updated = true
		}
	}
	if !updated {
		blocked[stackID] = append(blocked[stackID], blockedRow{ServiceID: serviceID, Reason: reason})
		sort.Slice(blocked[stackID], func(i, j int) bool {
			return blocked[stackID][i].ServiceID < blocked[stackID][j].ServiceID
		})
	}
}

func buildSummary(
	stackRows []stackRow,
	services []serviceDoc,
	clusters []clusterDoc,
	kept []map[string]any,
	ignored int,
	all []map[string]any,
) map[string]any {
	counts := map[string]int{
		"quarantined": 0, "cluster_frozen": 0, "deferred_capacity": 0,
		"warmup_deferred": 0, "scheduled": 0, "idle": 0,
	}
	scheduledServices := 0
	for _, r := range stackRows {
		counts[r.StackStatus]++
		if r.ScheduledService != nil {
			scheduledServices++
		}
	}
	return map[string]any{
		"applied_incident_events": len(kept),
		"clusters_total":          len(clusters),
		"deferred_stacks":         counts["deferred_capacity"],
		"frozen_stacks":           counts["cluster_frozen"],
		"idle_stacks":             counts["idle"],
		"ignored_incident_events": ignored,
		"quarantined_stacks":      counts["quarantined"],
		"scheduled_services_today": scheduledServices,
		"scheduled_stacks":        counts["scheduled"],
		"services_total":          len(services),
		"stacks_total":            len(stackRows),
		"warmup_deferred_stacks":  counts["warmup_deferred"],
	}
}

func buildJournal(kept []map[string]any) []map[string]any {
	out := make([]map[string]any, 0, len(kept))
	for _, ev := range kept {
		row := map[string]any{
			"day":      ev["day"],
			"event_id": ev["event_id"],
			"kind":     ev["kind"],
		}
		for _, k := range []string{"stack_id", "cluster_id", "service_id", "delta", "start_day", "end_day"} {
			if v, ok := ev[k]; ok {
				row[k] = v
			}
		}
		out = append(out, sortedKeys(row))
	}
	return out
}

func buildServiceMatrix(services []serviceDoc, stackRows []stackRow) []map[string]any {
	sched := map[string]int{}
	blocked := map[string]int{}
	for _, r := range stackRows {
		if r.ScheduledService != nil {
			sched[r.ScheduledService.(string)]++
		}
		for _, br := range r.BlockedCandidates {
			blocked[br.ServiceID]++
		}
	}
	var out []map[string]any
	for _, svc := range services {
		out = append(out, map[string]any{
			"service_id":        svc.ServiceID,
			"stacks_blocked":    blocked[svc.ServiceID],
			"stacks_scheduled":  sched[svc.ServiceID],
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i]["service_id"].(string) < out[j]["service_id"].(string) })
	return out
}

func buildClusterLedger(
	clusters []clusterDoc,
	effectiveCap map[string]int,
	creditsStart map[string]int,
	creditsRemaining map[string]int,
	clScheduled map[string]int,
	clDeferredCap map[string]int,
	clDeferredWarmup map[string]int,
) map[string]any {
	ledger := map[string]any{}
	for _, cl := range clusters {
		cid := cl.ClusterID
		ledger[cid] = map[string]any{
			"effective_cap":            effectiveCap[cid],
			"max_starts_per_day":       cl.MaxStartsPerDay,
			"start_credits_remaining":  creditsRemaining[cid],
			"start_credits_start":      creditsStart[cid],
			"stacks_deferred_capacity": clDeferredCap[cid],
			"stacks_deferred_warmup":   clDeferredWarmup[cid],
			"stacks_scheduled":         clScheduled[cid],
		}
	}
	return ledger
}

func chooseService(candidates []serviceDoc) string {
	if len(candidates) == 0 {
		return ""
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].Priority != candidates[j].Priority {
			return candidates[i].Priority < candidates[j].Priority
		}
		return candidates[i].ServiceID < candidates[j].ServiceID
	})
	return candidates[0].ServiceID
}

func blockReason(
	svc serviceDoc,
	st stackDoc,
	inWindow bool,
	embargoed map[string]bool,
	quarantined, frozenStack bool,
	started map[string]bool,
	maxCost int,
) string {
	if quarantined {
		return "quarantine"
	}
	if frozenStack {
		return "cluster_frozen"
	}
	if embargoed[svc.ServiceID] {
		return "embargoed"
	}
	if !inWindow {
		return "outside_window"
	}
	if !profileOverlap(svc, st) {
		return "profile_mismatch"
	}
	if !healthOK(svc, st) {
		return "insufficient_health"
	}
	for _, dep := range svc.DependsOn {
		if !started[dep] {
			return "missing_dependency"
		}
	}
	if svc.WarmupCost > maxCost {
		return "warmup_over_budget"
	}
	return ""
}

func dayInEffectiveWindow(st stackDoc, pol policyDoc, day int) bool {
	cal := pol.TierCalendar[st.Tier]
	for _, rw := range st.RolloutWindows {
		if len(rw) < 2 {
			continue
		}
		for _, tc := range cal {
			if len(tc) < 2 {
				continue
			}
			start := rw[0]
			if tc[0] > start {
				start = tc[0]
			}
			end := rw[1]
			if tc[1] < end {
				end = tc[1]
			}
			if start <= end && day >= start && day <= end {
				return true
			}
		}
	}
	return false
}

func processIncidents(events []map[string]any, day int) (applied map[string][]map[string]any, kept []map[string]any, ignored int) {
	applied = map[string][]map[string]any{
		"cap_bump": {}, "credit_grant": {}, "stack_compromise": {},
		"freeze_cluster": {}, "service_embargo": {},
	}
	var candidates []map[string]any
	for _, ev := range events {
		if !eventAccepted(ev) {
			ignored++
			continue
		}
		evDay := intNum(ev["day"])
		if evDay > day {
			ignored++
			continue
		}
		kind, _ := ev["kind"].(string)
		if !validIncident(ev, kind) {
			ignored++
			continue
		}
		candidates = append(candidates, ev)
	}
	sort.Slice(candidates, func(i, j int) bool {
		di, dj := intNum(candidates[i]["day"]), intNum(candidates[j]["day"])
		if di != dj {
			return di < dj
		}
		return fmt.Sprint(candidates[i]["event_id"]) < fmt.Sprint(candidates[j]["event_id"])
	})
	kept = candidates
	for _, ev := range kept {
		kind := ev["kind"].(string)
		applied[kind] = append(applied[kind], ev)
	}
	return applied, kept, len(events) - len(kept)
}

func validIncident(ev map[string]any, kind string) bool {
	switch kind {
	case "stack_compromise":
		_, ok := ev["stack_id"].(string)
		return ok
	case "freeze_cluster":
		_, ok := ev["cluster_id"].(string)
		return ok
	case "service_embargo":
		_, ok := ev["service_id"].(string)
		_, hasEnd := ev["end_day"]
		return ok && hasEnd
	case "cap_bump", "credit_grant":
		_, ok := ev["cluster_id"].(string)
		return ok && ev["delta"] != nil
	default:
		return false
	}
}

func embargoSet(applied map[string][]map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range applied["service_embargo"] {
		sid := ev["service_id"].(string)
		start := intNum(ev["day"])
		if v, ok := ev["start_day"]; ok {
			start = intNum(v)
		}
		end := intNum(ev["end_day"])
		if day >= start && day <= end {
			out[sid] = true
		}
	}
	return out
}

func compromiseSet(applied map[string][]map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range applied["stack_compromise"] {
		if intNum(ev["day"]) <= day {
			out[ev["stack_id"].(string)] = true
		}
	}
	return out
}

func freezeSet(applied map[string][]map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range applied["freeze_cluster"] {
		if intNum(ev["day"]) <= day {
			out[ev["cluster_id"].(string)] = true
		}
	}
	return out
}

func clusterCaps(clusters []clusterDoc, applied map[string][]map[string]any) map[string]int {
	out := map[string]int{}
	for _, c := range clusters {
		out[c.ClusterID] = c.MaxStartsPerDay
	}
	for _, ev := range applied["cap_bump"] {
		cid := ev["cluster_id"].(string)
		out[cid] += intNum(ev["delta"])
	}
	return out
}

func clusterCredits(clusters []clusterDoc, applied map[string][]map[string]any) map[string]int {
	out := map[string]int{}
	for _, c := range clusters {
		out[c.ClusterID] = c.StartCredits
	}
	for _, ev := range applied["credit_grant"] {
		cid := ev["cluster_id"].(string)
		out[cid] += intNum(ev["delta"])
	}
	return out
}

func eventAccepted(ev map[string]any) bool {
	v, ok := ev["accepted"]
	if !ok {
		return false
	}
	switch t := v.(type) {
	case bool:
		return t
	default:
		return false
	}
}

func intNum(v any) int {
	switch t := v.(type) {
	case float64:
		return int(t)
	case int:
		return t
	case json.Number:
		i, _ := t.Int64()
		return int(i)
	default:
		return 0
	}
}

func stringSet(xs []string) map[string]bool {
	m := map[string]bool{}
	for _, x := range xs {
		m[x] = true
	}
	return m
}

func sortedKeys(m map[string]any) map[string]any {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := map[string]any{}
	for _, k := range keys {
		out[k] = m[k]
	}
	return out
}

func readJSON(path string, out any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, &out)
}

func writeJSON(path string, v any) error {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(path, data, 0o644)
}

func loadStacks(dir string) ([]stackDoc, error) {
	return loadDir(dir, func(b []byte) (stackDoc, error) {
		var s stackDoc
		err := json.Unmarshal(b, &s)
		return s, err
	})
}

func loadServices(dir string) ([]serviceDoc, error) {
	return loadDir(dir, func(b []byte) (serviceDoc, error) {
		var x serviceDoc
		err := json.Unmarshal(b, &x)
		return x, err
	})
}

func loadClusters(dir string) ([]clusterDoc, error) {
	return loadDir(dir, func(b []byte) (clusterDoc, error) {
		var x clusterDoc
		err := json.Unmarshal(b, &x)
		return x, err
	})
}

func loadDir[T any](dir string, parse func([]byte) (T, error)) ([]T, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var out []T
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		x, err := parse(b)
		if err != nil {
			return nil, err
		}
		out = append(out, x)
	}
	return out, nil
}
