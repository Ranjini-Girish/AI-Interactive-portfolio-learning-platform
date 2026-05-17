package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type policyDoc struct {
	NodataCode     int `json:"nodata_code"`
	NodataTTLDays  int `json:"nodata_ttl_days"`
	NxTTLDays      int `json:"nx_ttl_days"`
	NxdomainCode   int `json:"nxdomain_code"`
	StaleGraceDays int `json:"stale_grace_days"`
}

type zoneDoc struct {
	Suffixes []string `json:"suffixes"`
	ZoneID   string   `json:"zone_id"`
}

type queryDoc struct {
	ObservedDay  int    `json:"observed_day"`
	Qname        string `json:"qname"`
	Qtype        string `json:"qtype"`
	QueryID      string `json:"query_id"`
	ResolverID   string `json:"resolver_id"`
	ResponseCode int    `json:"response_code"`
	ZoneID       string `json:"zone_id"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type hintEntry struct {
	QueryID string
	Status  string
	Order   int
}

type profileRow struct {
	CacheStatus   string `json:"cache_status"`
	EffectiveTTL  int    `json:"effective_ttl"`
	ObservedDay   int    `json:"observed_day"`
	Qname         string `json:"qname"`
	Qtype         string `json:"qtype"`
	QueryID       string `json:"query_id"`
	ReboundZoneID string `json:"rebound_zone_id"`
	ResolverID    string `json:"resolver_id"`
	ResponseCode  int    `json:"response_code"`
}

var negativeStatuses = []string{"expired", "flushed", "fresh", "poisoned", "stale_grace"}

func main() {
	dataDir := getenv("RNCA_DATA_DIR", "/app/resolver_negcache")
	auditDir := getenv("RNCA_AUDIT_DIR", "/app/audit")
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

	zones, err := loadZones(filepath.Join(dataDir, "zones"))
	if err != nil {
		return err
	}
	queries, err := loadQueries(filepath.Join(dataDir, "queries"))
	if err != nil {
		return err
	}
	bumps, err := loadTTLBumps(filepath.Join(dataDir, "ancillary"))
	if err != nil {
		return err
	}
	hints, err := loadHints(filepath.Join(dataDir, "hints"))
	if err != nil {
		return err
	}

	day := ps.CurrentDay
	applied := filterAppliedEvents(il.Events, day)
	sortAppliedEvents(applied)

	profiles := make([]profileRow, 0, len(queries))
	statusByID := map[string]string{}
	reboundByID := map[string]string{}
	effectiveTTLByID := map[string]int{}
	ageByID := map[string]int{}

	for _, q := range queries {
		rebound := rebindZone(q.Qname, q.ZoneID, zones)
		reboundByID[q.QueryID] = rebound
		age := day - q.ObservedDay
		ageByID[q.QueryID] = age

		status, effTTL := classifyTTL(q, rebound, age, pol, bumps)
		status = applyHints(q.QueryID, status, hints)
		statusByID[q.QueryID] = status
		effectiveTTLByID[q.QueryID] = effTTL

		profiles = append(profiles, profileRow{
			CacheStatus:   status,
			EffectiveTTL:  effTTL,
			ObservedDay:   q.ObservedDay,
			Qname:         q.Qname,
			Qtype:         q.Qtype,
			QueryID:       q.QueryID,
			ReboundZoneID: rebound,
			ResolverID:    q.ResolverID,
			ResponseCode:  q.ResponseCode,
		})
	}

	applyIncidents(applied, queries, reboundByID, statusByID)

	for i := range profiles {
		profiles[i].CacheStatus = statusByID[profiles[i].QueryID]
	}

	sort.Slice(profiles, func(i, j int) bool {
		return profiles[i].QueryID < profiles[j].QueryID
	})

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}

	zoneRollups := buildZoneRollups(profiles, day)
	staleEvents := buildStaleEvents(profiles, ageByID, effectiveTTLByID, day)
	summary := buildSummary(profiles, day)

	if err := writePretty(filepath.Join(auditDir, "query_profiles.json"), map[string]any{
		"current_day": day,
		"queries":     profiles,
	}); err != nil {
		return err
	}
	if err := writePretty(filepath.Join(auditDir, "zone_rollups.json"), zoneRollups); err != nil {
		return err
	}
	if err := writePretty(filepath.Join(auditDir, "stale_events.json"), staleEvents); err != nil {
		return err
	}
	if err := writePretty(filepath.Join(auditDir, "incident_journal.json"), map[string]any{
		"applied_events": applied,
		"current_day":    day,
	}); err != nil {
		return err
	}
	return writePretty(filepath.Join(auditDir, "summary.json"), summary)
}

func classifyTTL(q queryDoc, rebound string, age int, pol policyDoc, bumps map[string]int) (string, int) {
	if q.ResponseCode != pol.NxdomainCode && q.ResponseCode != pol.NodataCode {
		return "non_negative", 0
	}
	base := pol.NxTTLDays
	if q.ResponseCode == pol.NodataCode {
		base = pol.NodataTTLDays
	}
	eff := base + bumps[rebound]
	if age <= eff {
		return "fresh", eff
	}
	if age <= eff+pol.StaleGraceDays {
		return "stale_grace", eff
	}
	return "expired", eff
}

func applyHints(queryID, status string, hints map[string]string) string {
	if h, ok := hints[queryID]; ok {
		return h
	}
	return status
}

func applyIncidents(events []map[string]any, queries []queryDoc, rebound map[string]string, status map[string]string) {
	holds := []map[string]any{}
	flushes := []map[string]any{}
	compromises := []map[string]any{}
	for _, ev := range events {
		switch fmt.Sprint(ev["kind"]) {
		case "negative_hold":
			holds = append(holds, ev)
		case "zone_flush":
			flushes = append(flushes, ev)
		case "resolver_compromise":
			compromises = append(compromises, ev)
		}
	}
	for _, q := range queries {
		for _, ev := range holds {
			if fmt.Sprint(ev["query_id"]) != q.QueryID {
				continue
			}
			if dayGE(q.ObservedDay, ev["day"]) {
				status[q.QueryID] = "stale_grace"
			}
		}
		for _, ev := range flushes {
			if fmt.Sprint(ev["zone_id"]) != rebound[q.QueryID] {
				continue
			}
			if dayGE(q.ObservedDay, ev["day"]) {
				status[q.QueryID] = "flushed"
			}
		}
		for _, ev := range compromises {
			if fmt.Sprint(ev["resolver_id"]) != q.ResolverID {
				continue
			}
			if dayGE(q.ObservedDay, ev["day"]) {
				status[q.QueryID] = "poisoned"
			}
		}
	}
}

func dayGE(observed int, dayVal any) bool {
	switch d := dayVal.(type) {
	case float64:
		return observed >= int(d)
	case int:
		return observed >= d
	default:
		return false
	}
}

func rebindZone(qname, fallback string, zones []zoneDoc) string {
	bestLen := -1
	bestID := fallback
	for _, z := range zones {
		for _, suf := range z.Suffixes {
			if !strings.HasSuffix(qname, suf) {
				continue
			}
			if len(suf) > bestLen || (len(suf) == bestLen && z.ZoneID < bestID) {
				bestLen = len(suf)
				bestID = z.ZoneID
			}
		}
	}
	if bestLen < 0 {
		return fallback
	}
	return bestID
}

func loadTTLBumps(dir string) (map[string]int, error) {
	out := map[string]int{}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var names []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".json") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		var doc map[string]any
		if err := readJSON(filepath.Join(dir, name), &doc); err != nil {
			return nil, err
		}
		raw, ok := doc["zone_ttl_bump"].(map[string]any)
		if !ok {
			continue
		}
		for k, v := range raw {
			switch n := v.(type) {
			case float64:
				out[k] = int(n)
			case int:
				out[k] = n
			}
		}
	}
	return out, nil
}

func loadHints(dir string) (map[string]string, error) {
	var collected []hintEntry
	order := 0
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var names []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".txt") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		data, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			return nil, err
		}
		for _, line := range strings.Split(string(data), "\n") {
			line = strings.TrimSpace(line)
			if line == "" {
				continue
			}
			parts := strings.Fields(line)
			if len(parts) < 2 {
				continue
			}
			status := parts[1]
			if status != "fresh" && status != "stale_grace" && status != "expired" {
				continue
			}
			collected = append(collected, hintEntry{QueryID: parts[0], Status: status, Order: order})
			order++
		}
	}
	sort.Slice(collected, func(i, j int) bool {
		if collected[i].QueryID == collected[j].QueryID {
			return collected[i].Order < collected[j].Order
		}
		return collected[i].QueryID < collected[j].QueryID
	})
	out := map[string]string{}
	for _, h := range collected {
		out[h.QueryID] = h.Status
	}
	return out, nil
}

func loadZones(dir string) ([]zoneDoc, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var zones []zoneDoc
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		var z zoneDoc
		if err := readJSON(filepath.Join(dir, e.Name()), &z); err != nil {
			return nil, err
		}
		zones = append(zones, z)
	}
	return zones, nil
}

func loadQueries(dir string) ([]queryDoc, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var queries []queryDoc
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		var q queryDoc
		if err := readJSON(filepath.Join(dir, e.Name()), &q); err != nil {
			return nil, err
		}
		queries = append(queries, q)
	}
	sort.Slice(queries, func(i, j int) bool { return queries[i].QueryID < queries[j].QueryID })
	return queries, nil
}

func filterAppliedEvents(events []map[string]any, day int) []map[string]any {
	var out []map[string]any
	for _, ev := range events {
		if eventDay(ev) <= day {
			out = append(out, ev)
		}
	}
	return out
}

func sortAppliedEvents(events []map[string]any) {
	sort.Slice(events, func(i, j int) bool {
		di := eventDay(events[i])
		dj := eventDay(events[j])
		if di != dj {
			return di < dj
		}
		ki := fmt.Sprint(events[i]["kind"])
		kj := fmt.Sprint(events[j]["kind"])
		if ki != kj {
			return ki < kj
		}
		return eventTarget(events[i]) < eventTarget(events[j])
	})
}

func eventDay(ev map[string]any) int {
	switch d := ev["day"].(type) {
	case float64:
		return int(d)
	case int:
		return d
	default:
		return 0
	}
}

func eventTarget(ev map[string]any) string {
	for _, k := range []string{"resolver_id", "zone_id", "query_id"} {
		if v, ok := ev[k]; ok {
			return fmt.Sprint(v)
		}
	}
	return ""
}

func buildZoneRollups(profiles []profileRow, day int) map[string]any {
	counts := map[string]map[string]int{}
	for _, p := range profiles {
		if p.CacheStatus == "non_negative" {
			continue
		}
		if counts[p.ReboundZoneID] == nil {
			counts[p.ReboundZoneID] = map[string]int{}
			for _, s := range negativeStatuses {
				counts[p.ReboundZoneID][s] = 0
			}
		}
		counts[p.ReboundZoneID][p.CacheStatus]++
	}
	var zoneIDs []string
	for z := range counts {
		zoneIDs = append(zoneIDs, z)
	}
	sort.Strings(zoneIDs)
	zonesOut := make([]map[string]any, 0, len(zoneIDs))
	for _, zid := range zoneIDs {
		statusCounts := map[string]int{}
		for _, s := range negativeStatuses {
			statusCounts[s] = counts[zid][s]
		}
		zonesOut = append(zonesOut, map[string]any{
			"status_counts": statusCounts,
			"zone_id":       zid,
		})
	}
	return map[string]any{"current_day": day, "zones": zonesOut}
}

func buildStaleEvents(profiles []profileRow, ages, ttls map[string]int, day int) map[string]any {
	var events []map[string]any
	for _, p := range profiles {
		if p.CacheStatus != "stale_grace" && p.CacheStatus != "expired" {
			continue
		}
		events = append(events, map[string]any{
			"age_days":        ages[p.QueryID],
			"cache_status":    p.CacheStatus,
			"effective_ttl":   ttls[p.QueryID],
			"query_id":        p.QueryID,
			"rebound_zone_id": p.ReboundZoneID,
			"resolver_id":     p.ResolverID,
		})
	}
	sort.Slice(events, func(i, j int) bool {
		return fmt.Sprint(events[i]["query_id"]) < fmt.Sprint(events[j]["query_id"])
	})
	return map[string]any{"current_day": day, "events": events}
}

func buildSummary(profiles []profileRow, day int) map[string]any {
	totals := map[string]int{
		"expired": 0, "flushed": 0, "fresh": 0, "non_negative": 0,
		"poisoned": 0, "stale_grace": 0,
	}
	zoneSet := map[string]struct{}{}
	for _, p := range profiles {
		totals[p.CacheStatus]++
		zoneSet[p.ReboundZoneID] = struct{}{}
	}
	zones := make([]string, 0, len(zoneSet))
	for z := range zoneSet {
		zones = append(zones, z)
	}
	sort.Strings(zones)
	negative := len(profiles) - totals["non_negative"]
	return map[string]any{
		"current_day":        day,
		"expired_total":      totals["expired"],
		"flushed_total":      totals["flushed"],
		"fresh_total":        totals["fresh"],
		"negative_total":     negative,
		"non_negative_total": totals["non_negative"],
		"poisoned_total":     totals["poisoned"],
		"queries_total":      len(profiles),
		"stale_grace_total":  totals["stale_grace"],
		"zones":              zones,
	}
}

func readJSON(path string, dest any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, dest)
}

func writePretty(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(path, data, 0o644)
}
