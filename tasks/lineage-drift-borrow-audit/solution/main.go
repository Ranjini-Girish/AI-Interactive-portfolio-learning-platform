package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type channel struct {
	ID        string `json:"channel_id"`
	Tier      string `json:"tier"`
	BaseDrift int    `json:"base_drift"`
	Parent    any    `json:"parent"`
}

type incident struct {
	Day        int             `json:"day"`
	Seq        int             `json:"seq"`
	IncidentID string          `json:"incident_id"`
	Kind       string          `json:"kind"`
	Payload    json.RawMessage `json:"payload"`
}

func readJSON(path string, out any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, out); err != nil {
		panic(err)
	}
}

func toInt(v any) (int, bool) {
	switch t := v.(type) {
	case float64:
		return int(t), true
	case int:
		return t, true
	case int64:
		return int(t), true
	default:
		return 0, false
	}
}

func toString(v any) (string, bool) {
	s, ok := v.(string)
	return s, ok
}

func canonicalJSON(v any) []byte {
	b, err := json.Marshal(v)
	if err != nil {
		panic(err)
	}
	return b
}

func writeJSON(path string, v any) {
	if err := os.WriteFile(path, canonicalJSON(v), 0o644); err != nil {
		panic(err)
	}
}

func main() {
	dataDir := os.Getenv("LDB_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/ldb_lab"
	}
	auditDir := os.Getenv("LDB_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		panic(err)
	}

	var window struct {
		StartDay int `json:"start_day"`
		EndDay   int `json:"end_day"`
	}
	readJSON(filepath.Join(dataDir, "anchors", "window.json"), &window)
	if window.EndDay < window.StartDay {
		panic("invalid window")
	}
	windowDays := window.EndDay - window.StartDay + 1

	var policy struct {
		TierNums      map[string]int `json:"tier_weight_numerators"`
		Divisor       int            `json:"weight_divisor"`
		Escalation    int            `json:"escalation_line"`
		TierBorrowCap map[string]int `json:"tier_borrow_caps"`
	}
	readJSON(filepath.Join(dataDir, "policy.json"), &policy)
	if policy.Divisor <= 0 {
		panic("bad divisor")
	}

	var pool struct {
		Budget int `json:"token_budget"`
	}
	readJSON(filepath.Join(dataDir, "pool_state.json"), &pool)

	var incidents []incident
	readJSON(filepath.Join(dataDir, "incident_log.json"), &incidents)

	entries, err := os.ReadDir(filepath.Join(dataDir, "channels"))
	if err != nil {
		panic(err)
	}
	channels := map[string]channel{}
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		var ch channel
		readJSON(filepath.Join(dataDir, "channels", e.Name()), &ch)
		channels[ch.ID] = ch
	}

	ids := make([]string, 0, len(channels))
	for id := range channels {
		ids = append(ids, id)
	}
	sort.Strings(ids)

	parentResolved := map[string]string{}
	for _, id := range ids {
		ch := channels[id]
		if ch.Parent == nil {
			continue
		}
		ps, ok := ch.Parent.(string)
		if !ok || ps == "" {
			continue
		}
		if _, ok := channels[ps]; !ok {
			continue
		}
		parentResolved[id] = ps
	}

	cyclic := map[string]bool{}
	for _, start := range ids {
		if cyclic[start] {
			continue
		}
		path := []string{}
		index := map[string]int{}
		cur := start
		for {
			if cur == "" {
				break
			}
			p, ok := parentResolved[cur]
			if !ok {
				break
			}
			if ix, seen := index[cur]; seen {
				for j := ix; j < len(path); j++ {
					cyclic[path[j]] = true
				}
				break
			}
			index[cur] = len(path)
			path = append(path, cur)
			cur = p
		}
	}

	lineage := map[string]string{}
	for _, id := range ids {
		if cyclic[id] {
			lineage[id] = "cyclic"
			continue
		}
		if _, ok := parentResolved[id]; ok {
			lineage[id] = "chained"
		} else {
			lineage[id] = "root"
		}
	}

	weighted := map[string]int{}
	for _, id := range ids {
		ch := channels[id]
		num := policy.TierNums[ch.Tier]
		weighted[id] = (ch.BaseDrift * num) / policy.Divisor
	}

	effective := map[string]int{}
	done := map[string]bool{}
	for id := range cyclic {
		effective[id] = weighted[id]
		done[id] = true
	}
	for round := 0; round < len(ids)+5; round++ {
		progress := false
		for _, id := range ids {
			if done[id] {
				continue
			}
			p, has := parentResolved[id]
			if !has {
				effective[id] = weighted[id]
				done[id] = true
				progress = true
				continue
			}
			if !done[p] {
				continue
			}
			effective[id] = weighted[id] + effective[p]/4
			done[id] = true
			progress = true
		}
		if !progress {
			break
		}
	}
	for _, id := range ids {
		if !done[id] {
			panic(fmt.Errorf("unresolved effective drift for %s", id))
		}
	}

	poolRemaining := pool.Budget
	tierCaps := map[string]int{}
	for k, v := range policy.TierBorrowCap {
		tierCaps[k] = v
	}
	embargoed := map[string]bool{}
	applied := []string{}
	ignored := []string{}
	ignoredKinds := 0

	type incSort struct {
		inc incident
	}
	incList := make([]incident, len(incidents))
	copy(incList, incidents)
	sort.SliceStable(incList, func(i, j int) bool {
		a, b := incList[i], incList[j]
		if a.Day != b.Day {
			return a.Day < b.Day
		}
		if a.Seq != b.Seq {
			return a.Seq < b.Seq
		}
		return a.IncidentID < b.IncidentID
	})

	for _, inc := range incidents {
		if inc.Day < window.StartDay || inc.Day > window.EndDay {
			ignored = append(ignored, inc.IncidentID)
		}
	}

	for _, inc := range incList {
		if inc.Day < window.StartDay || inc.Day > window.EndDay {
			continue
		}
		applied = append(applied, inc.IncidentID)
		switch inc.Kind {
		case "gift_tokens":
			var p map[string]any
			_ = json.Unmarshal(inc.Payload, &p)
			if amt, ok := toInt(p["amount"]); ok && amt >= 0 {
				poolRemaining += amt
			}
		case "tighten_tier_cap":
			var p map[string]any
			_ = json.Unmarshal(inc.Payload, &p)
			tier, ok := toString(p["tier"])
			if !ok {
				break
			}
			if _, ok := tierCaps[tier]; !ok {
				break
			}
			nc, ok := toInt(p["new_cap"])
			if !ok {
				break
			}
			tierCaps[tier] = min(tierCaps[tier], nc)
		case "embargo":
			var p map[string]any
			_ = json.Unmarshal(inc.Payload, &p)
			if cid, ok := toString(p["channel_id"]); ok && cid != "" {
				embargoed[cid] = true
			}
		default:
			ignoredKinds++
		}
	}

	for t := range tierCaps {
		if tierCaps[t] < 0 {
			tierCaps[t] = 0
		}
	}
	poolAfterIncidents := poolRemaining
	tierRemaining := map[string]int{}
	for k, v := range tierCaps {
		tierRemaining[k] = v
	}

	type borrowRow struct {
		id  string
		eff int
	}
	borrowOrder := make([]borrowRow, 0, len(ids))
	for _, id := range ids {
		borrowOrder = append(borrowOrder, borrowRow{id: id, eff: effective[id]})
	}
	sort.SliceStable(borrowOrder, func(i, j int) bool {
		a, b := borrowOrder[i], borrowOrder[j]
		if a.eff != b.eff {
			return a.eff > b.eff
		}
		return a.id < b.id
	})

	borrowed := map[string]int{}
	for _, row := range borrowOrder {
		id := row.id
		ch := channels[id]
		if embargoed[id] {
			borrowed[id] = 0
			continue
		}
		eff := effective[id]
		tRem := tierRemaining[ch.Tier]
		b := eff
		if b > poolRemaining {
			b = poolRemaining
		}
		if b > tRem {
			b = tRem
		}
		if b < 0 {
			b = 0
		}
		borrowed[id] = b
		poolRemaining -= b
		tierRemaining[ch.Tier] -= b
		if tierRemaining[ch.Tier] < 0 {
			tierRemaining[ch.Tier] = 0
		}
		if poolRemaining < 0 {
			poolRemaining = 0
		}
	}

	cut := policy.Escalation * windowDays
	verdicts := make([]map[string]any, 0, len(ids))
	verdictCounts := map[string]int{
		"cleared":   0,
		"watch":     0,
		"escalate":  0,
		"embargoed": 0,
	}
	for _, id := range ids {
		ch := channels[id]
		b := borrowed[id]
		eff := effective[id]
		res := eff - b
		var verdict string
		if embargoed[id] {
			verdict = "embargoed"
		} else if b == eff {
			verdict = "cleared"
		} else if res > cut {
			verdict = "escalate"
		} else {
			verdict = "watch"
		}
		verdictCounts[verdict]++
		verdicts = append(verdicts, map[string]any{
			"borrowed":        b,
			"channel_id":      id,
			"effective_drift": eff,
			"lineage":         lineage[id],
			"residual":        res,
			"tier":            ch.Tier,
			"verdict":         verdict,
			"weighted_base":   weighted[id],
		})
	}

	writeJSON(filepath.Join(auditDir, "channel_verdicts.json"), map[string]any{
		"channels": verdicts,
	})
	writeJSON(filepath.Join(auditDir, "incident_journal.json"), map[string]any{
		"applied_events":  applied,
		"ignored_events":  ignored,
	})
	writeJSON(filepath.Join(auditDir, "summary.json"), map[string]any{
		"embargoed_channels":     len(embargoed),
		"ignored_incident_kinds": ignoredKinds,
		"pool_after_borrow":      poolRemaining,
		"pool_after_incidents":   poolAfterIncidents,
		"verdict_counts":         verdictCounts,
		"window_days":            windowDays,
	})
}
