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
	CurrentDay              int            `json:"current_day"`
	PreviousWindowCarryover map[string]int `json:"previous_window_carryover"`
}

type policy struct {
	BronzeSurgeExtraFailures        int            `json:"bronze_surge_extra_failures"`
	GoldEndpointThrottleExtraFailures int          `json:"gold_endpoint_throttle_extra_failures"`
	GraceDaysByTier                 map[string]int `json:"grace_days_by_tier"`
	RetriesByTier                   map[string]int `json:"retries_by_tier"`
	RollingWindowDays               int            `json:"rolling_window_days"`
	SigningRotationLagDays          int            `json:"signing_rotation_lag_days"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type endpointDoc struct {
	EndpointID     string `json:"endpoint_id"`
	RateLimited    bool   `json:"rate_limited"`
	SigningProfile string `json:"signing_profile"`
}

type signingProfile struct {
	Keys []struct {
		KeyID        string `json:"key_id"`
		ValidFromDay int    `json:"valid_from_day"`
	} `json:"keys"`
}

type subscriptionDoc struct {
	EndpointID     string            `json:"endpoint_id"`
	OutcomesByDay  map[string]string `json:"outcomes_by_day"`
	SlipDays       map[string]int    `json:"slip_days"`
	SubscriptionID string            `json:"subscription_id"`
	Tier           string            `json:"tier"`
}

func main() {
	dataDir := getenv("WRLA_DATA_DIR", "/app/webhooks")
	auditDir := getenv("WRLA_AUDIT_DIR", "/app/audit")
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
	if pol.RollingWindowDays < 1 {
		pol.RollingWindowDays = 1
	}

	incRaw, err := os.ReadFile(filepath.Join(dataDir, "incident_log.json"))
	if err != nil {
		return err
	}
	var il incidentLog
	if err := json.Unmarshal(incRaw, &il); err != nil {
		return err
	}

	subs, err := loadSubscriptions(filepath.Join(dataDir, "subscriptions"))
	if err != nil {
		return err
	}
	sort.Slice(subs, func(i, j int) bool { return subs[i].SubscriptionID < subs[j].SubscriptionID })

	endpoints := loadEndpoints(filepath.Join(dataDir, "endpoints"))
	profiles := loadSigningProfiles(filepath.Join(dataDir, "signing_profiles"))

	cutoff := ps.CurrentDay - pol.SigningRotationLagDays

	candidates := make([]map[string]any, 0)
	ignored := 0
	for _, ev := range il.Events {
		if !boolVal(ev["accepted"]) {
			ignored++
			continue
		}
		if intVal(ev["day"]) > ps.CurrentDay {
			ignored++
			continue
		}
		candidates = append(candidates, ev)
	}
	sort.Slice(candidates, func(i, j int) bool {
		di := intVal(candidates[i]["day"])
		dj := intVal(candidates[j]["day"])
		if di != dj {
			return di < dj
		}
		return strVal(candidates[i]["event_id"]) < strVal(candidates[j]["event_id"])
	})

	applied := make([]map[string]any, 0)
	for _, ev := range candidates {
		kind := strVal(ev["kind"])
		if !incidentWellFormed(kind, ev) {
			ignored++
			continue
		}
		applied = append(applied, ev)
	}

	deltaByTier := map[string]int{"bronze": 0, "gold": 0, "silver": 0}
	bronzeSurge := false
	compromiseEndpoints := map[string]bool{}
	forceExhausted := map[string]bool{}

	for _, ev := range applied {
		kind := strVal(ev["kind"])
		switch kind {
		case "tier_retry_delta":
			tt := strVal(ev["target_tier"])
			deltaByTier[tt] += intVal(ev["delta"])
		case "bronze_surge":
			bronzeSurge = true
		case "endpoint_compromise":
			compromiseEndpoints[strVal(ev["endpoint_id"])] = true
		case "force_exhausted":
			forceExhausted[strVal(ev["subscription_id"])] = true
		}
	}

	journal := make([]map[string]any, 0, len(applied))
	for _, ev := range applied {
		journal = append(journal, journalEntry(ev))
	}
	sort.Slice(journal, func(i, j int) bool {
		di := intVal(journal[i]["day"])
		dj := intVal(journal[j]["day"])
		if di != dj {
			return di < dj
		}
		return strVal(journal[i]["event_id"]) < strVal(journal[j]["event_id"])
	})

	tiersOut := map[string]any{}
	for _, tier := range []string{"bronze", "gold", "silver"} {
		base := pol.RetriesByTier[tier]
		ds := deltaByTier[tier]
		adj := base + ds
		if adj < 1 {
			adj = 1
		}
		tiersOut[tier] = map[string]any{
			"adjusted_retry_budget": adj,
			"base_budget":           base,
			"delta_sum":             ds,
		}
	}

	winStart := ps.CurrentDay - (pol.RollingWindowDays - 1)
	bronzeExtra := pol.BronzeSurgeExtraFailures
	if bronzeExtra < 0 {
		bronzeExtra = 0
	}
	goldThrottle := pol.GoldEndpointThrottleExtraFailures
	if goldThrottle < 0 {
		goldThrottle = 0
	}

	subOut := make([]map[string]any, 0, len(subs))
	exhaustedN := 0
	quarantinedN := 0
	goldThrottleN := 0

	for _, sub := range subs {
		ep := endpoints[sub.EndpointID]
		if sub.Tier == "gold" && ep.RateLimited && goldThrottle > 0 {
			goldThrottleN++
		}
	}

	consumedSuppressPairs := map[string]bool{}
	for _, sub := range subs {
		ep := endpoints[sub.EndpointID]
		grace := pol.GraceDaysByTier[sub.Tier]
		raw := countChargeable(sub, winStart, ps.CurrentDay, grace)

		rf := raw
		for _, ev := range applied {
			if strVal(ev["kind"]) != "failure_day_suppress" {
				continue
			}
			if strVal(ev["subscription_id"]) != sub.SubscriptionID {
				continue
			}
			for _, d := range daySlice(ev["days"]) {
				if d < winStart || d > ps.CurrentDay {
					continue
				}
				key := strconv.Itoa(d)
				outcome := sub.OutcomesByDay[key]
				if !isChargeable(sub.Tier, outcome) || slipExcuses(sub, d, grace) {
					continue
				}
				pair := sub.SubscriptionID + "|" + key
				if consumedSuppressPairs[pair] {
					continue
				}
				consumedSuppressPairs[pair] = true
				if rf > 0 {
					rf--
				}
			}
		}
		if rf < 0 {
			rf = 0
		}

		eff := rf
		if sub.Tier == "bronze" && bronzeSurge {
			eff += bronzeExtra
		}
		if sub.Tier == "gold" && ep.RateLimited && goldThrottle > 0 {
			eff += goldThrottle
		}

		rawCarryover := 0
		if ps.PreviousWindowCarryover != nil {
			if v, ok := ps.PreviousWindowCarryover[sub.SubscriptionID]; ok {
				rawCarryover = v
			}
		}
		if rawCarryover < 0 {
			rawCarryover = 0
		}
		carryover := rawCarryover
		if deltaByTier[sub.Tier] < 0 {
			carryover = 0
		}
		eff += carryover

		baseBudget := pol.RetriesByTier[sub.Tier]
		adjBudget := baseBudget + deltaByTier[sub.Tier]
		if adjBudget < 1 {
			adjBudget = 1
		}

		quarantined := compromiseEndpoints[sub.EndpointID]
		forced := forceExhausted[sub.SubscriptionID]
		numericExhaust := eff >= adjBudget

		disposition := "active"
		retriesExhausted := false
		if quarantined {
			disposition = "quarantined"
			retriesExhausted = true
		} else if forced {
			disposition = "exhausted"
			retriesExhausted = true
		} else if numericExhaust {
			disposition = "exhausted"
			retriesExhausted = true
		}

		reasons := []string{}
		if quarantined {
			reasons = append(reasons, "endpoint_compromise")
		}
		if forced {
			reasons = append(reasons, "force_exhausted_incident")
		}
		if numericExhaust {
			reasons = append(reasons, "retry_budget_exhausted")
		}
		if sub.Tier == "bronze" && bronzeSurge && bronzeExtra > 0 {
			reasons = append(reasons, "bronze_surge_active")
		}
		if sub.Tier == "gold" && ep.RateLimited && goldThrottle > 0 {
			reasons = append(reasons, "gold_endpoint_throttle_penalty")
		}
		if carryover > 0 && numericExhaust {
			reasons = append(reasons, "previous_window_carryover")
		}
		reasons = uniqSort(reasons)

		if disposition == "active" {
			reasons = []string{}
		}

		if disposition == "exhausted" {
			exhaustedN++
		}
		if disposition == "quarantined" {
			quarantinedN++
		}

		signKey := resolveSigningKey(ep.SigningProfile, profiles, cutoff)

		subOut = append(subOut, map[string]any{
			"adjusted_retry_budget":    adjBudget,
			"carryover_failures":       carryover,
			"disposition":              disposition,
			"effective_failures":       eff,
			"effective_signing_key_id": signKey,
			"endpoint_id":              sub.EndpointID,
			"raw_chargeable":           raw,
			"reasons":                  reasons,
			"retries_exhausted":        retriesExhausted,
			"subscription_id":          sub.SubscriptionID,
			"tier":                     sub.Tier,
		})
	}

	touch := map[string][]string{}
	for _, sub := range subs {
		touch[sub.EndpointID] = append(touch[sub.EndpointID], sub.SubscriptionID)
	}
	epKeys := make([]string, 0, len(touch))
	for k := range touch {
		epKeys = append(epKeys, k)
	}
	sort.Strings(epKeys)
	epOut := map[string]any{}
	for _, k := range epKeys {
		ss := touch[k]
		sort.Strings(ss)
		ep := endpoints[k]
		epOut[k] = map[string]any{
			"rate_limited":              ep.RateLimited,
			"referencing_subscriptions": ss,
		}
	}

	summary := map[string]any{
		"applied_incident_events":                len(journal),
		"bronze_surge_active":                    bronzeSurge,
		"endpoints_total":                        len(epKeys),
		"exhausted_subscriptions":                exhaustedN,
		"gold_subscriptions_with_throttle_penalty": goldThrottleN,
		"ignored_incident_events":                ignored,
		"quarantined_subscriptions":              quarantinedN,
		"subscriptions_total":                    len(subs),
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	writes := []struct {
		name string
		body any
	}{
		{"subscription_verdicts.json", map[string]any{"subscriptions": subOut}},
		{"tier_retry_budgets.json", map[string]any{"tiers": tiersOut}},
		{"incident_journal.json", map[string]any{"applied_events": journal}},
		{"endpoint_touchpoints.json", map[string]any{"endpoints": epOut}},
		{"summary.json", summary},
	}
	for _, w := range writes {
		if err := writeJSON(filepath.Join(auditDir, w.name), w.body); err != nil {
			return err
		}
	}
	return nil
}

func loadSubscriptions(dir string) ([]subscriptionDoc, error) {
	var out []subscriptionDoc
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var s subscriptionDoc
		if err := json.Unmarshal(b, &s); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, nil
}

func loadEndpoints(dir string) map[string]endpointDoc {
	out := map[string]endpointDoc{}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return out
	}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		stem := e.Name()[:len(e.Name())-5]
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			out[stem] = endpointDoc{EndpointID: stem, RateLimited: false}
			continue
		}
		var ep endpointDoc
		if json.Unmarshal(b, &ep) != nil {
			out[stem] = endpointDoc{EndpointID: stem, RateLimited: false}
			continue
		}
		out[stem] = ep
	}
	return out
}

func loadSigningProfiles(dir string) map[string]signingProfile {
	out := map[string]signingProfile{}
	entries, err := os.ReadDir(dir)
	if err != nil {
		return out
	}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		stem := e.Name()[:len(e.Name())-5]
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			continue
		}
		var sp signingProfile
		if json.Unmarshal(b, &sp) == nil {
			out[stem] = sp
		}
	}
	return out
}

func resolveSigningKey(profileStem string, profiles map[string]signingProfile, cutoff int) string {
	sp, ok := profiles[profileStem]
	if !ok || len(sp.Keys) == 0 {
		return "none"
	}
	best := ""
	for _, k := range sp.Keys {
		if k.ValidFromDay <= cutoff {
			if best == "" || k.KeyID > best {
				best = k.KeyID
			}
		}
	}
	if best == "" {
		return "none"
	}
	return best
}

func countChargeable(sub subscriptionDoc, start, end, grace int) int {
	n := 0
	for d := start; d <= end; d++ {
		key := strconv.Itoa(d)
		outcome := sub.OutcomesByDay[key]
		if !isChargeable(sub.Tier, outcome) {
			continue
		}
		if slipExcuses(sub, d, grace) {
			continue
		}
		n++
	}
	return n
}

func isChargeable(tier, outcome string) bool {
	switch tier {
	case "gold", "bronze":
		return outcome == "fail" || outcome == "timeout"
	case "silver":
		return outcome == "fail" || outcome == "timeout" || outcome == "rate_limited"
	default:
		return false
	}
}

func slipExcuses(sub subscriptionDoc, day, grace int) bool {
	if sub.SlipDays == nil {
		return false
	}
	key := strconv.Itoa(day)
	sched, ok := sub.SlipDays[key]
	if !ok {
		return false
	}
	return day <= sched+grace
}

func incidentWellFormed(kind string, ev map[string]any) bool {
	switch kind {
	case "tier_retry_delta":
		tt := strVal(ev["target_tier"])
		if tt != "gold" && tt != "silver" && tt != "bronze" {
			return false
		}
		if _, ok := ev["delta"]; !ok {
			return false
		}
		return true
	case "failure_day_suppress":
		if strVal(ev["subscription_id"]) == "" {
			return false
		}
		if _, ok := ev["days"]; !ok {
			return false
		}
		return true
	case "bronze_surge":
		return true
	case "endpoint_compromise":
		return strVal(ev["endpoint_id"]) != ""
	case "force_exhausted":
		return strVal(ev["subscription_id"]) != ""
	default:
		return false
	}
}

func journalEntry(ev map[string]any) map[string]any {
	kind := strVal(ev["kind"])
	m := map[string]any{
		"day":      intVal(ev["day"]),
		"event_id": strVal(ev["event_id"]),
		"kind":     kind,
	}
	switch kind {
	case "tier_retry_delta":
		m["delta"] = intVal(ev["delta"])
		m["target_tier"] = strVal(ev["target_tier"])
	case "failure_day_suppress":
		m["days"] = daySlice(ev["days"])
		m["subscription_id"] = strVal(ev["subscription_id"])
	case "endpoint_compromise":
		m["endpoint_id"] = strVal(ev["endpoint_id"])
	case "force_exhausted":
		m["subscription_id"] = strVal(ev["subscription_id"])
	}
	return m
}

func writeJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}

func boolVal(v any) bool {
	b, ok := v.(bool)
	return ok && b
}

func strVal(v any) string {
	if v == nil {
		return ""
	}
	s, ok := v.(string)
	if ok {
		return s
	}
	return fmt.Sprint(v)
}

func intVal(v any) int {
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

func daySlice(v any) []int {
	arr, ok := v.([]any)
	if !ok {
		return nil
	}
	out := make([]int, 0, len(arr))
	for _, x := range arr {
		out = append(out, intVal(x))
	}
	return out
}

func uniqSort(in []string) []string {
	sort.Strings(in)
	out := make([]string, 0, len(in))
	var prev string
	for _, s := range in {
		if s == prev {
			continue
		}
		out = append(out, s)
		prev = s
	}
	return out
}
