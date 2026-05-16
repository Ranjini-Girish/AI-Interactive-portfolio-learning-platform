package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
)

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type policy struct {
	GraceDaysByTier      map[string]int `json:"grace_days_by_tier"`
	MaxRenewalsByTier    map[string]int `json:"max_renewals_by_tier"`
	RenewalWindowDays    int            `json:"renewal_window_days"`
	WitnessDayFloor      int            `json:"witness_day_floor"`
	WitnessQuorumByTier  map[string]int `json:"witness_quorum_by_tier"`
}

type hostDoc struct {
	HostID         string           `json:"host_id"`
	Tier           string           `json:"tier"`
	RenewalsByDay  map[string]int   `json:"renewals_by_day"`
	Leases         []leaseRec       `json:"leases"`
}

type leaseRec struct {
	SlotID        string `json:"slot_id"`
	LeaseUntilDay int    `json:"lease_until_day"`
	RenewCount    int    `json:"renew_count"`
	LastRenewDay  int    `json:"last_renew_day"`
}

type slotDoc struct {
	SlotID                 string `json:"slot_id"`
	Capacity               int    `json:"capacity"`
	WitnessQuorumOverride  *int   `json:"witness_quorum_override,omitempty"`
}

type witnessDoc struct {
	SlotID       string         `json:"slot_id"`
	Attestations []attestation  `json:"attestations"`
}

type attestation struct {
	WitnessHost string `json:"witness_host"`
	SubjectHost string `json:"subject_host"`
	Day         int    `json:"day"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type leaseRow struct {
	ComputedStatus       string   `json:"computed_status"`
	EffectiveGrace       int      `json:"effective_grace"`
	HostID               string   `json:"host_id"`
	LeaseUntilDay        int      `json:"lease_until_day"`
	LastRenewDay         int      `json:"last_renew_day"`
	MaxRenewals          int      `json:"max_renewals"`
	RenewCount           int      `json:"renew_count"`
	RenewalBlocked       bool     `json:"renewal_blocked"`
	Reasons              []string `json:"reasons"`
	SlotID               string   `json:"slot_id"`
	Tier                 string   `json:"tier"`
	WindowRenewals       int      `json:"window_renewals"`
	WitnessPairsCredited int      `json:"witness_pairs_credited"`
}

func main() {
	dataDir := getenv("LSCA_DATA_DIR", "/app/leases")
	auditDir := getenv("LSCA_AUDIT_DIR", "/app/audit")
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
	psRaw, err := os.ReadFile(filepath.Join(dataDir, "pool_state.json"))
	if err != nil {
		return err
	}
	var ps poolState
	if err := json.Unmarshal(psRaw, &ps); err != nil {
		return err
	}

	polRaw, err := os.ReadFile(filepath.Join(dataDir, "policy.json"))
	if err != nil {
		return err
	}
	var pol policy
	if err := json.Unmarshal(polRaw, &pol); err != nil {
		return err
	}
	if pol.RenewalWindowDays < 1 {
		pol.RenewalWindowDays = 1
	}

	incRaw, err := os.ReadFile(filepath.Join(dataDir, "incident_log.json"))
	if err != nil {
		return err
	}
	var il incidentLog
	if err := json.Unmarshal(incRaw, &il); err != nil {
		return err
	}

	slots, err := loadSlots(filepath.Join(dataDir, "slots"))
	if err != nil {
		return err
	}
	hosts, err := loadHosts(filepath.Join(dataDir, "hosts"))
	if err != nil {
		return err
	}
	witnesses, err := loadWitnesses(filepath.Join(dataDir, "witnesses"))
	if err != nil {
		return err
	}

	keptEvents, ignored := filterIncidents(il.Events, ps.CurrentDay)
	graceDelta := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	renewDelta := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	hostComp := map[string]bool{}
	slotComp := map[string]bool{}
	freezeHosts := map[string]bool{}
	forceExpire := map[string]bool{}

	appliedJournal := make([]map[string]any, 0, len(keptEvents))
	for _, ev := range keptEvents {
		kind, _ := ev["kind"].(string)
		entry := map[string]any{
			"day":      ev["day"],
			"event_id": ev["event_id"],
			"kind":     kind,
		}
		switch kind {
		case "extend_grace":
			tier, _ := ev["target_tier"].(string)
			extra := intFrom(ev["extra_days"])
			graceDelta[tier] += extra
			entry["extra_days"] = extra
			entry["target_tier"] = tier
		case "renewal_cap_delta":
			tier, _ := ev["target_tier"].(string)
			delta := intFrom(ev["delta"])
			renewDelta[tier] += delta
			entry["delta"] = delta
			entry["target_tier"] = tier
		case "freeze_renewals":
			hid, _ := ev["host_id"].(string)
			freezeHosts[hid] = true
			entry["host_id"] = hid
		case "slot_compromise":
			sid, _ := ev["slot_id"].(string)
			slotComp[sid] = true
			entry["slot_id"] = sid
		case "host_compromise":
			hid, _ := ev["host_id"].(string)
			hostComp[hid] = true
			entry["host_id"] = hid
		case "force_expire":
			hid, _ := ev["host_id"].(string)
			sid, _ := ev["slot_id"].(string)
			forceExpire[hid+"\x00"+sid] = true
			entry["host_id"] = hid
			entry["slot_id"] = sid
		}
		appliedJournal = append(appliedJournal, sortKeys(entry))
	}

	winLo := ps.CurrentDay - (pol.RenewalWindowDays - 1)
	witnessLo := winLo
	if pol.WitnessDayFloor > witnessLo {
		witnessLo = pol.WitnessDayFloor
	}

	slotHosts := map[string]map[string]bool{}
	allLeases := []struct {
		host hostDoc
		lease leaseRec
	}{}
	for _, h := range hosts {
		for _, l := range h.Leases {
			allLeases = append(allLeases, struct {
				host hostDoc
				lease leaseRec
			}{h, l})
			if slotHosts[l.SlotID] == nil {
				slotHosts[l.SlotID] = map[string]bool{}
			}
			slotHosts[l.SlotID][h.HostID] = true
		}
	}

	contested := map[string]bool{}
	activeHostsBySlot := map[string][]string{}
	for sid, hs := range slotHosts {
		list := make([]string, 0, len(hs))
		for h := range hs {
			list = append(list, h)
		}
		sort.Strings(list)
		activeHostsBySlot[sid] = list
		contested[sid] = len(list) >= 2
	}

	leaseRows := make([]leaseRow, 0, len(allLeases))
	statusCounts := map[string]int{
		"quarantined": 0, "frozen": 0, "witness_pending": 0,
		"expired": 0, "grace": 0, "renewal_capped": 0, "active": 0,
	}

	for _, pair := range allLeases {
		h := pair.host
		l := pair.lease
		tier := h.Tier
		baseGrace := pol.GraceDaysByTier[tier] + graceDelta[tier]
		baseMax := pol.MaxRenewalsByTier[tier] + renewDelta[tier]
		if baseMax < 0 {
			baseMax = 0
		}
		winRen := windowSum(h.RenewalsByDay, winLo, ps.CurrentDay)

		quorum := pol.WitnessQuorumByTier[tier]
		if sd, ok := slots[l.SlotID]; ok && sd.WitnessQuorumOverride != nil {
			quorum = *sd.WitnessQuorumOverride
		}

		status, blocked, reasons, witPairs := computeStatus(
			h.HostID, l, ps.CurrentDay, baseGrace, baseMax,
			hostComp, slotComp, freezeHosts, forceExpire,
			contested[l.SlotID], quorum, witnesses[l.SlotID], witnessLo, ps.CurrentDay,
			slotHosts[l.SlotID],
		)
		statusCounts[status]++
		leaseRows = append(leaseRows, leaseRow{
			ComputedStatus:       status,
			EffectiveGrace:       baseGrace,
			HostID:               h.HostID,
			LeaseUntilDay:        l.LeaseUntilDay,
			LastRenewDay:        l.LastRenewDay,
			MaxRenewals:          baseMax,
			RenewCount:           l.RenewCount,
			RenewalBlocked:       blocked,
			Reasons:              reasons,
			SlotID:               l.SlotID,
			Tier:                 tier,
			WindowRenewals:       winRen,
			WitnessPairsCredited: witPairs,
		})
	}

	sort.Slice(leaseRows, func(i, j int) bool {
		if leaseRows[i].HostID != leaseRows[j].HostID {
			return leaseRows[i].HostID < leaseRows[j].HostID
		}
		return leaseRows[i].SlotID < leaseRows[j].SlotID
	})

	tierPolicy := map[string]any{}
	for _, tier := range []string{"bronze", "gold", "silver"} {
		bg := pol.GraceDaysByTier[tier]
		gd := graceDelta[tier]
		br := pol.MaxRenewalsByTier[tier]
		rd := renewDelta[tier]
		em := br + rd
		if em < 0 {
			em = 0
		}
		tierPolicy[tier] = map[string]any{
			"base_grace":              bg,
			"grace_delta_sum":         gd,
			"effective_grace":         bg + gd,
			"base_max_renewals":       br,
			"renewal_cap_delta_sum":   rd,
			"effective_max_renewals":  em,
			"witness_quorum_default":  pol.WitnessQuorumByTier[tier],
		}
	}

	slotContention := map[string]any{}
	slotIDs := make([]string, 0, len(slots))
	for sid := range slots {
		slotIDs = append(slotIDs, sid)
	}
	sort.Strings(slotIDs)
	contestedSlots := 0
	for _, sid := range slotIDs {
		sd := slots[sid]
		q := pol.WitnessQuorumByTier["bronze"]
		if sd.WitnessQuorumOverride != nil {
			q = *sd.WitnessQuorumOverride
		}
		if contested[sid] {
			contestedSlots++
		}
		slotContention[sid] = map[string]any{
			"capacity":        sd.Capacity,
			"contested":       contested[sid],
			"active_hosts":    activeHostsBySlot[sid],
			"quorum_required": q,
		}
	}

	summary := map[string]any{
		"leases_total":              len(leaseRows),
		"quarantined_leases":        statusCounts["quarantined"],
		"frozen_leases":             statusCounts["frozen"],
		"witness_pending_leases":    statusCounts["witness_pending"],
		"expired_leases":            statusCounts["expired"],
		"grace_leases":              statusCounts["grace"],
		"renewal_capped_leases":     statusCounts["renewal_capped"],
		"active_leases":             statusCounts["active"],
		"contested_slots":           contestedSlots,
		"applied_incident_events":   len(keptEvents),
		"ignored_incident_events":   ignored,
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	outputs := map[string]any{
		"lease_verdicts.json":   map[string]any{"leases": leaseRows},
		"tier_policy.json":      map[string]any{"tiers": tierPolicy},
		"incident_journal.json": map[string]any{"applied_events": appliedJournal},
		"slot_contention.json":  map[string]any{"slots": slotContention},
		"summary.json":          summary,
	}
	for name, body := range outputs {
		if err := writeCanonical(filepath.Join(auditDir, name), body); err != nil {
			return err
		}
	}
	return nil
}

func computeStatus(
	hostID string, l leaseRec, currentDay, baseGrace, baseMax int,
	hostComp, slotComp, freezeHosts, forceExpire map[string]bool,
	contested bool, quorum int, wd witnessDoc, witnessLo, currentHi int,
	cohosts map[string]bool,
) (status string, blocked bool, reasons []string, witnessPairs int) {
	reasons = []string{}
	if hostComp[hostID] || slotComp[l.SlotID] {
		return "quarantined", true, reasons, 0
	}
	if forceExpire[hostID+"\x00"+l.SlotID] {
		return "expired", true, []string{"force_expire_incident"}, 0
	}
	if freezeHosts[hostID] {
		return "frozen", true, reasons, 0
	}
	if contested {
		score, sufficient := witnessScore(wd, hostID, witnessLo, currentHi, quorum, cohosts)
		if !sufficient {
			return "witness_pending", true, []string{"insufficient_witnesses"}, score
		}
		witnessPairs = score
	}
	if currentDay > l.LeaseUntilDay+baseGrace {
		return "expired", true, []string{"past_grace"}, witnessPairs
	}
	if currentDay > l.LeaseUntilDay {
		return "grace", false, reasons, witnessPairs
	}
	if l.RenewCount >= baseMax {
		return "renewal_capped", true, []string{"renewal_cap_reached"}, witnessPairs
	}
	return "active", false, reasons, witnessPairs
}

func witnessScore(
	wd witnessDoc, hostID string, lo, hi, quorum int, cohosts map[string]bool,
) (int, bool) {
	seen := map[string]bool{}
	for _, a := range wd.Attestations {
		if a.SubjectHost != hostID || a.WitnessHost == hostID {
			continue
		}
		if !cohosts[a.WitnessHost] {
			continue
		}
		if a.Day < lo || a.Day > hi {
			continue
		}
		key := a.WitnessHost + "\x00" + strconv.Itoa(a.Day)
		if seen[key] {
			continue
		}
		seen[key] = true
	}
	cnt := len(seen)
	return cnt, cnt >= quorum
}

func windowSum(m map[string]int, lo, hi int) int {
	sum := 0
	for k, v := range m {
		d, err := strconv.Atoi(k)
		if err != nil || d < lo || d > hi {
			continue
		}
		sum += v
	}
	return sum
}

func filterIncidents(events []map[string]any, currentDay int) ([]map[string]any, int) {
	type row struct {
		ev  map[string]any
		day int
		eid string
	}
	var rows []row
	ignored := 0
	for _, ev := range events {
		acc, ok := ev["accepted"].(bool)
		if !ok || !acc {
			ignored++
			continue
		}
		day := intFrom(ev["day"])
		if day > currentDay {
			ignored++
			continue
		}
		kind, _ := ev["kind"].(string)
		if !validKind(kind, ev) {
			ignored++
			continue
		}
		eid, _ := ev["event_id"].(string)
		rows = append(rows, row{ev, day, eid})
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].day != rows[j].day {
			return rows[i].day < rows[j].day
		}
		return rows[i].eid < rows[j].eid
	})
	out := make([]map[string]any, len(rows))
	for i, r := range rows {
		out[i] = r.ev
	}
	return out, ignored
}

func validKind(kind string, ev map[string]any) bool {
	switch kind {
	case "extend_grace":
		t, ok := ev["target_tier"].(string)
		return ok && (t == "gold" || t == "silver" || t == "bronze") && hasInt(ev, "extra_days")
	case "renewal_cap_delta":
		t, ok := ev["target_tier"].(string)
		return ok && (t == "gold" || t == "silver" || t == "bronze") && hasInt(ev, "delta")
	case "freeze_renewals":
		_, ok := ev["host_id"].(string)
		return ok
	case "slot_compromise":
		_, ok := ev["slot_id"].(string)
		return ok
	case "host_compromise":
		_, ok := ev["host_id"].(string)
		return ok
	case "force_expire":
		_, hok := ev["host_id"].(string)
		_, sok := ev["slot_id"].(string)
		return hok && sok
	default:
		return false
	}
}

func hasInt(ev map[string]any, key string) bool {
	switch ev[key].(type) {
	case float64, int, json.Number:
		return true
	default:
		return false
	}
}

func intFrom(v any) int {
	switch x := v.(type) {
	case float64:
		return int(x)
	case int:
		return x
	case json.Number:
		i, _ := x.Int64()
		return int(i)
	default:
		return 0
	}
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

func loadSlots(dir string) (map[string]slotDoc, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := map[string]slotDoc{}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var s slotDoc
		if err := json.Unmarshal(b, &s); err != nil {
			return nil, err
		}
		out[s.SlotID] = s
	}
	return out, nil
}

func loadWitnesses(dir string) (map[string]witnessDoc, error) {
	out := map[string]witnessDoc{}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return out, nil
	}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var w witnessDoc
		if err := json.Unmarshal(b, &w); err != nil {
			return nil, err
		}
		seen := map[string]bool{}
		uniq := make([]attestation, 0, len(w.Attestations))
		for _, a := range w.Attestations {
			key := fmt.Sprintf("%s\x00%s\x00%d", a.WitnessHost, a.SubjectHost, a.Day)
			if seen[key] {
				continue
			}
			seen[key] = true
			uniq = append(uniq, a)
		}
		w.Attestations = uniq
		out[w.SlotID] = w
	}
	return out, nil
}

func sortKeys(m map[string]any) map[string]any {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	out := make(map[string]any, len(m))
	for _, k := range keys {
		out[k] = m[k]
	}
	return out
}

func writeCanonical(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}
