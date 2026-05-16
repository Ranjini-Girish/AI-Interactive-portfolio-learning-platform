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
	RebootBudgetMinutesPerHost int                       `json:"reboot_budget_minutes_per_host"`
	TierCalendar               map[string][][]int        `json:"tier_calendar"`
	TierRank                   map[string]int            `json:"tier_rank"`
}

type hostDoc struct {
	AppliedBundles      []string `json:"applied_bundles"`
	HostID              string   `json:"host_id"`
	MaintenanceWindows  [][]int  `json:"maintenance_windows"`
	Region              string   `json:"region"`
	Tier                string   `json:"tier"`
}

type bundleDoc struct {
	BundleID      string   `json:"bundle_id"`
	DependsOn     []string `json:"depends_on"`
	Priority      int      `json:"priority"`
	RebootMinutes int      `json:"reboot_minutes"`
}

type regionDoc struct {
	MaxHostsPerDay int    `json:"max_hosts_per_day"`
	RegionID       string `json:"region_id"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type blockedRow struct {
	BundleID string `json:"bundle_id"`
	Reason   string `json:"reason"`
}

type hostRow struct {
	BlockedCandidates []blockedRow `json:"blocked_candidates"`
	HostID            string       `json:"host_id"`
	HostStatus        string       `json:"host_status"`
	Region            string       `json:"region"`
	ScheduledBundle   any          `json:"scheduled_bundle"`
	Tier              string       `json:"tier"`
}

func main() {
	dataDir := getenv("PSLA_DATA_DIR", "/app/patch_slots")
	auditDir := getenv("PSLA_AUDIT_DIR", "/app/audit")
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

	bundles, err := loadBundles(filepath.Join(dataDir, "bundles"))
	if err != nil {
		return err
	}
	hosts, err := loadHosts(filepath.Join(dataDir, "hosts"))
	if err != nil {
		return err
	}
	regions, err := loadRegions(filepath.Join(dataDir, "regions"))
	if err != nil {
		return err
	}

	day := ps.CurrentDay
	applied, kept, ignored := processIncidents(il.Events, day)
	embargoed := embargoSet(applied, day)
	compromise := compromiseSet(applied, day)
	frozen := freezeSet(applied, day)
	effectiveCap := regionCaps(regions, applied)

	hostByID := map[string]hostDoc{}
	for _, h := range hosts {
		hostByID[h.HostID] = h
	}

	type pick struct {
		host   hostDoc
		bundle string
	}
	var contenders []pick

	hostBlocked := map[string][]blockedRow{}
	hostStatus := map[string]string{}
	hostScheduled := map[string]any{}

	for _, h := range hosts {
		appliedSet := stringSet(h.AppliedBundles)
		inWindow := dayInEffectiveWindow(h, pol, day)
		quarantined := compromise[h.HostID]
		frozenHost := frozen[h.Region]

		var blocked []blockedRow
		var candidates []bundleDoc

		for _, b := range bundles {
			if appliedSet[b.BundleID] {
				continue
			}
			reason := blockReason(b, h, appliedSet, inWindow, embargoed, quarantined, frozenHost, pol.RebootBudgetMinutesPerHost)
			if reason == "" {
				candidates = append(candidates, b)
				continue
			}
			blocked = append(blocked, blockedRow{BundleID: b.BundleID, Reason: reason})
		}

		sort.Slice(blocked, func(i, j int) bool { return blocked[i].BundleID < blocked[j].BundleID })
		if blocked == nil {
			blocked = []blockedRow{}
		}
		hostBlocked[h.HostID] = blocked

		switch {
		case quarantined:
			hostStatus[h.HostID] = "quarantined"
			hostScheduled[h.HostID] = nil
		case frozenHost:
			hostStatus[h.HostID] = "frozen_region"
			hostScheduled[h.HostID] = nil
		default:
			chosen := chooseBundle(candidates)
			if chosen == "" {
				hostStatus[h.HostID] = "idle"
				hostScheduled[h.HostID] = nil
			} else {
				contenders = append(contenders, pick{host: h, bundle: chosen})
			}
		}
	}

	sort.Slice(contenders, func(i, j int) bool {
		ri := pol.TierRank[contenders[i].host.Tier]
		rj := pol.TierRank[contenders[j].host.Tier]
		if ri != rj {
			return ri < rj
		}
		return contenders[i].host.HostID < contenders[j].host.HostID
	})

	regionScheduled := map[string]int{}
	for _, c := range contenders {
		cap := effectiveCap[c.host.Region]
		if regionScheduled[c.host.Region] < cap {
			regionScheduled[c.host.Region]++
			hostStatus[c.host.HostID] = "scheduled"
			hostScheduled[c.host.HostID] = c.bundle
		} else {
			hostStatus[c.host.HostID] = "deferred_capacity"
			hostScheduled[c.host.HostID] = nil
			updated := false
			for i := range hostBlocked[c.host.HostID] {
				if hostBlocked[c.host.HostID][i].BundleID == c.bundle {
					hostBlocked[c.host.HostID][i].Reason = "capacity_deferred"
					updated = true
				}
			}
			if !updated {
				hostBlocked[c.host.HostID] = append(
					hostBlocked[c.host.HostID],
					blockedRow{BundleID: c.bundle, Reason: "capacity_deferred"},
				)
				sort.Slice(hostBlocked[c.host.HostID], func(i, j int) bool {
					return hostBlocked[c.host.HostID][i].BundleID < hostBlocked[c.host.HostID][j].BundleID
				})
			}
		}
	}

	var hostRows []hostRow
	sort.Slice(hosts, func(i, j int) bool { return hosts[i].HostID < hosts[j].HostID })
	for _, h := range hosts {
		st := hostStatus[h.HostID]
		if st == "" {
			st = "idle"
		}
		hostRows = append(hostRows, hostRow{
			HostID:            h.HostID,
			Region:            h.Region,
			Tier:              h.Tier,
			HostStatus:        st,
			ScheduledBundle:   hostScheduled[h.HostID],
			BlockedCandidates: hostBlocked[h.HostID],
		})
	}

	regionLedger := buildRegionLedger(regions, effectiveCap, hostRows)
	bundleMatrix := buildBundleMatrix(bundles, hostRows)
	journal := buildJournal(kept)
	summary := buildSummary(hostRows, bundles, kept, ignored, il.Events)

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "host_plan.json"), map[string]any{"hosts": hostRows}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "region_ledger.json"), map[string]any{"regions": regionLedger}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "bundle_matrix.json"), map[string]any{"bundles": bundleMatrix}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(auditDir, "incident_journal.json"), map[string]any{"applied_events": journal}); err != nil {
		return err
	}
	return writeJSON(filepath.Join(auditDir, "summary.json"), summary)
}

func buildSummary(hostRows []hostRow, bundles []bundleDoc, kept []map[string]any, ignored int, all []map[string]any) map[string]any {
	counts := map[string]int{
		"quarantined": 0, "frozen_region": 0, "deferred_capacity": 0,
		"scheduled": 0, "idle": 0,
	}
	scheduledBundles := 0
	for _, r := range hostRows {
		counts[r.HostStatus]++
		if r.ScheduledBundle != nil {
			scheduledBundles++
		}
	}
	return map[string]any{
		"applied_incident_events": len(kept),
		"bundles_total":           len(bundles),
		"deferred_hosts":          counts["deferred_capacity"],
		"frozen_hosts":            counts["frozen_region"],
		"hosts_total":             len(hostRows),
		"idle_hosts":              counts["idle"],
		"ignored_incident_events": ignored,
		"quarantined_hosts":       counts["quarantined"],
		"scheduled_hosts":         counts["scheduled"],
		"scheduled_bundles_today": scheduledBundles,
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
		for _, k := range []string{"host_id", "region_id", "bundle_id", "delta", "start_day", "end_day"} {
			if v, ok := ev[k]; ok {
				row[k] = v
			}
		}
		out = append(out, sortedKeys(row))
	}
	return out
}

func buildBundleMatrix(bundles []bundleDoc, hostRows []hostRow) []map[string]any {
	sched := map[string]int{}
	blocked := map[string]int{}
	for _, r := range hostRows {
		if r.ScheduledBundle != nil {
			sched[r.ScheduledBundle.(string)]++
		}
		for _, br := range r.BlockedCandidates {
			blocked[br.BundleID]++
		}
	}
	var out []map[string]any
	for _, b := range bundles {
		out = append(out, map[string]any{
			"bundle_id":       b.BundleID,
			"hosts_blocked":   blocked[b.BundleID],
			"hosts_scheduled": sched[b.BundleID],
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i]["bundle_id"].(string) < out[j]["bundle_id"].(string) })
	return out
}

func buildRegionLedger(regions []regionDoc, effectiveCap map[string]int, hostRows []hostRow) map[string]any {
	ledger := map[string]any{}
	for _, reg := range regions {
		ledger[reg.RegionID] = map[string]any{
			"effective_cap":      effectiveCap[reg.RegionID],
			"hosts_deferred":     0,
			"hosts_scheduled":    0,
			"max_hosts_per_day":  reg.MaxHostsPerDay,
		}
	}
	for _, r := range hostRows {
		body := ledger[r.Region].(map[string]any)
		switch r.HostStatus {
		case "scheduled":
			body["hosts_scheduled"] = body["hosts_scheduled"].(int) + 1
		case "deferred_capacity":
			body["hosts_deferred"] = body["hosts_deferred"].(int) + 1
		}
	}
	return ledger
}

func chooseBundle(candidates []bundleDoc) string {
	if len(candidates) == 0 {
		return ""
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].Priority != candidates[j].Priority {
			return candidates[i].Priority < candidates[j].Priority
		}
		return candidates[i].BundleID < candidates[j].BundleID
	})
	return candidates[0].BundleID
}

func blockReason(b bundleDoc, h hostDoc, applied map[string]bool, inWindow bool, embargoed map[string]bool, quarantined, frozenHost bool, rebootBudget int) string {
	if quarantined {
		return "quarantine"
	}
	if frozenHost {
		return "region_frozen"
	}
	if embargoed[b.BundleID] {
		return "embargoed"
	}
	if !inWindow {
		return "outside_window"
	}
	for _, dep := range b.DependsOn {
		if !applied[dep] {
			return "missing_dependency"
		}
	}
	if b.RebootMinutes > rebootBudget {
		return "reboot_over_budget"
	}
	return ""
}

func dayInEffectiveWindow(h hostDoc, pol policyDoc, day int) bool {
	cal := pol.TierCalendar[h.Tier]
	for _, hw := range h.MaintenanceWindows {
		if len(hw) < 2 {
			continue
		}
		for _, tc := range cal {
			if len(tc) < 2 {
				continue
			}
			start := hw[0]
			if tc[0] > start {
				start = tc[0]
			}
			end := hw[1]
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
		"cap_bump": {}, "host_compromise": {}, "freeze_region": {}, "bundle_embargo": {},
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
	case "host_compromise":
		_, ok := ev["host_id"].(string)
		return ok
	case "freeze_region":
		_, ok := ev["region_id"].(string)
		return ok
	case "bundle_embargo":
		_, ok := ev["bundle_id"].(string)
		_, hasEnd := ev["end_day"]
		return ok && hasEnd
	case "cap_bump":
		_, ok := ev["region_id"].(string)
		return ok && ev["delta"] != nil
	default:
		return false
	}
}

func embargoSet(applied map[string][]map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range applied["bundle_embargo"] {
		bid := ev["bundle_id"].(string)
		start := intNum(ev["day"])
		if v, ok := ev["start_day"]; ok {
			start = intNum(v)
		}
		end := intNum(ev["end_day"])
		if day >= start && day <= end {
			out[bid] = true
		}
	}
	return out
}

func compromiseSet(applied map[string][]map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range applied["host_compromise"] {
		if intNum(ev["day"]) <= day {
			out[ev["host_id"].(string)] = true
		}
	}
	return out
}

func freezeSet(applied map[string][]map[string]any, day int) map[string]bool {
	out := map[string]bool{}
	for _, ev := range applied["freeze_region"] {
		if intNum(ev["day"]) <= day {
			out[ev["region_id"].(string)] = true
		}
	}
	return out
}

func regionCaps(regions []regionDoc, applied map[string][]map[string]any) map[string]int {
	out := map[string]int{}
	for _, r := range regions {
		out[r.RegionID] = r.MaxHostsPerDay
	}
	for _, ev := range applied["cap_bump"] {
		rid := ev["region_id"].(string)
		out[rid] += intNum(ev["delta"])
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

func loadHosts(dir string) ([]hostDoc, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var out []hostDoc
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var h hostDoc
		if err := json.Unmarshal(b, &h); err != nil {
			return nil, err
		}
		out = append(out, h)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].HostID < out[j].HostID })
	return out, nil
}

func loadBundles(dir string) ([]bundleDoc, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var out []bundleDoc
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var x bundleDoc
		if err := json.Unmarshal(b, &x); err != nil {
			return nil, err
		}
		out = append(out, x)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].BundleID < out[j].BundleID })
	return out, nil
}

func loadRegions(dir string) ([]regionDoc, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var out []regionDoc
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var x regionDoc
		if err := json.Unmarshal(b, &x); err != nil {
			return nil, err
		}
		out = append(out, x)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].RegionID < out[j].RegionID })
	return out, nil
}
