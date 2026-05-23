package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type policyFile struct {
	MinWitness              int            `json:"min_witness"`
	PityStreakThreshold     int            `json:"pity_streak_threshold"`
	PityMultiplierPercent   int            `json:"pity_multiplier_percent"`
	ReputationCapByTier     map[string]int `json:"reputation_cap_by_tier"`
	MaxPrereqDepth          int            `json:"max_prereq_depth"`
}

type poolFile struct {
	CurrentDay int    `json:"current_day"`
	SeasonID   string `json:"season_id"`
}

type questFile struct {
	BasePoints int      `json:"base_points"`
	ChainTag   string   `json:"chain_tag"`
	QuestID    string   `json:"quest_id"`
	Requires   []string `json:"requires"`
	Tier       string   `json:"tier"`
}

type guildMeta struct {
	ClusterID   string `json:"cluster_id"`
	GuildID     string `json:"guild_id"`
	TierCeiling string `json:"tier_ceiling"`
}

type attemptRow struct {
	Day     int    `json:"day"`
	QuestID string `json:"quest_id"`
	Witness int    `json:"witness"`
}

type submissionFile struct {
	Attempts []attemptRow `json:"attempts"`
	GuildID  string       `json:"guild_id"`
}

type completionEntry struct {
	GuildID       string   `json:"guild_id"`
	QuestID       string   `json:"quest_id"`
	Day           int      `json:"day"`
	Witness       int      `json:"witness"`
	PointsAwarded int      `json:"points_awarded"`
	Status        string   `json:"status"`
	Reasons       []string `json:"reasons"`
}

func writeJSON(path string, v any) error {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(data, '\n'), 0o644)
}

func sortedStrings(set map[string]struct{}) []string {
	out := make([]string, 0, len(set))
	for k := range set {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func addReason(reasons map[string]struct{}, label string) {
	reasons[label] = struct{}{}
}

func reasonList(reasons map[string]struct{}) []string {
	if len(reasons) == 0 {
		return []string{}
	}
	out := sortedStrings(reasons)
	return out
}

func findCycles(quests map[string]questFile, maxDepth int) ([][]string, map[string]bool) {
	inCycle := map[string]bool{}
	var cycles [][]string
	visited := map[string]int{} // 0 unvisited, 1 stack, 2 done
	stack := []string{}
	var path []string

	var dfs func(string) bool
	dfs = func(node string) bool {
		if visited[node] == 1 {
			start := -1
			for i, n := range path {
				if n == node {
					start = i
					break
				}
			}
			if start >= 0 {
				cyc := append([]string(nil), path[start:]...)
				sort.Strings(cyc)
				cycles = append(cycles, cyc)
				for _, id := range cyc {
					inCycle[id] = true
				}
			}
			return true
		}
		if visited[node] == 2 {
			return false
		}
		if len(stack) >= maxDepth {
			return false
		}
		visited[node] = 1
		stack = append(stack, node)
		path = append(path, node)
		q := quests[node]
		for _, dep := range q.Requires {
			if _, ok := quests[dep]; ok {
				dfs(dep)
			}
		}
		path = path[:len(path)-1]
		stack = stack[:len(stack)-1]
		visited[node] = 2
		return false
	}

	ids := sortedStrings(func() map[string]struct{} {
		m := map[string]struct{}{}
		for id := range quests {
			m[id] = struct{}{}
		}
		return m
	}())

	for _, id := range ids {
		if visited[id] == 0 {
			dfs(id)
		}
	}

	sort.Slice(cycles, func(i, j int) bool {
		return cycles[i][0] < cycles[j][0]
	})
	return cycles, inCycle
}

func topoOrder(quests map[string]questFile, inCycle map[string]bool) []string {
	indeg := map[string]int{}
	children := map[string][]string{}
	for id, q := range quests {
		if inCycle[id] {
			continue
		}
		if _, ok := indeg[id]; !ok {
			indeg[id] = 0
		}
		for _, dep := range q.Requires {
			if inCycle[dep] {
				continue
			}
			if _, ok := quests[dep]; !ok {
				continue
			}
			children[dep] = append(children[dep], id)
			indeg[id]++
		}
	}
	ready := []string{}
	for id, d := range indeg {
		if d == 0 {
			ready = append(ready, id)
		}
	}
	sort.Strings(ready)
	var order []string
	for len(ready) > 0 {
		n := ready[0]
		ready = ready[1:]
		order = append(order, n)
		kids := children[n]
		sort.Strings(kids)
		for _, ch := range kids {
			indeg[ch]--
			if indeg[ch] == 0 {
				ready = append(ready, ch)
			}
		}
		sort.Strings(ready)
	}
	return order
}

func main() {
	dataDir := os.Getenv("GBL_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/bounty"
	}
	auditDir := os.Getenv("GBL_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "mkdir audit: %v\n", err)
		os.Exit(1)
	}

	var policy policyFile
	load := func(name string, dest any) {
		b, err := os.ReadFile(filepath.Join(dataDir, name))
		if err != nil {
			panic(err)
		}
		if err := json.Unmarshal(b, dest); err != nil {
			panic(err)
		}
	}
	load("policy.json", &policy)
	var pool poolFile
	load("pool_state.json", &pool)

	quests := map[string]questFile{}
	questPaths, _ := filepath.Glob(filepath.Join(dataDir, "quests", "*.json"))
	for _, fp := range questPaths {
		var q questFile
		b, _ := os.ReadFile(fp)
		_ = json.Unmarshal(b, &q)
		quests[q.QuestID] = q
	}

	guilds := map[string]guildMeta{}
	guildPaths, _ := filepath.Glob(filepath.Join(dataDir, "guilds", "*.json"))
	for _, fp := range guildPaths {
		var g guildMeta
		b, _ := os.ReadFile(fp)
		_ = json.Unmarshal(b, &g)
		guilds[g.GuildID] = g
	}

	cycles, inCycle := findCycles(quests, policy.MaxPrereqDepth)
	order := topoOrder(quests, inCycle)

	type winKey struct {
		guild, quest string
	}
	winners := map[winKey]attemptRow{}
	winIdx := map[winKey]int{}

	subPaths, _ := filepath.Glob(filepath.Join(dataDir, "submissions", "*.json"))
	for _, fp := range subPaths {
		var sub submissionFile
		b, _ := os.ReadFile(fp)
		_ = json.Unmarshal(b, &sub)
		for idx, att := range sub.Attempts {
			k := winKey{sub.GuildID, att.QuestID}
			cur, ok := winners[k]
			if !ok || att.Day > cur.Day || (att.Day == cur.Day && att.Witness > cur.Witness) ||
				(att.Day == cur.Day && att.Witness == cur.Witness && idx > winIdx[k]) {
				winners[k] = att
				winIdx[k] = idx
			}
		}
	}

	streak := map[string]int{} // guild|chain_tag
	streakAtWin := map[winKey]int{}
	type successKey struct {
		guild, quest string
	}
	successDay := map[successKey]int{}

	type rawAttempt struct {
		guild string
		att   attemptRow
	}
	var allAttempts []rawAttempt
	for _, fp := range subPaths {
		var sub submissionFile
		b, _ := os.ReadFile(fp)
		_ = json.Unmarshal(b, &sub)
		for _, att := range sub.Attempts {
			allAttempts = append(allAttempts, rawAttempt{sub.GuildID, att})
		}
	}
	sort.Slice(allAttempts, func(i, j int) bool {
		a, b := allAttempts[i], allAttempts[j]
		if a.att.Day != b.att.Day {
			return a.att.Day < b.att.Day
		}
		if a.guild != b.guild {
			return a.guild < b.guild
		}
		return a.att.QuestID < b.att.QuestID
	})
	for _, ra := range allAttempts {
		q, ok := quests[ra.att.QuestID]
		if !ok {
			continue
		}
		tagKey := ra.guild + "|" + q.ChainTag
		if ra.att.Witness < policy.MinWitness {
			streak[tagKey]++
		} else {
			k := winKey{ra.guild, ra.att.QuestID}
			if w, ok := winners[k]; ok && w.Day == ra.att.Day && w.Witness == ra.att.Witness {
				streakAtWin[k] = streak[tagKey]
				streak[tagKey] = 0
			}
		}
	}

	type winPair struct {
		key winKey
		att attemptRow
	}
	var winList []winPair
	for k, att := range winners {
		winList = append(winList, winPair{k, att})
	}
	sort.Slice(winList, func(i, j int) bool {
		a, b := winList[i], winList[j]
		if a.att.Day != b.att.Day {
			return a.att.Day < b.att.Day
		}
		if a.key.guild != b.key.guild {
			return a.key.guild < b.key.guild
		}
		return a.key.quest < b.key.quest
	})

	var entries []completionEntry
	for _, wp := range winList {
		k := wp.key
		att := wp.att
		gid, qid := k.guild, k.quest
		q, ok := quests[qid]
		if !ok {
			continue
		}
		reasons := map[string]struct{}{}
		status := "valid"
		points := 0

		if inCycle[qid] {
			status = "chain_blocked"
			addReason(reasons, "cycle")
		} else if att.Witness < policy.MinWitness {
			status = "failed"
			addReason(reasons, "low_witness")
			_ = gid
		} else {
			blocked := false
			for _, req := range q.Requires {
				reqK := winKey{gid, req}
				win, has := winners[reqK]
				if !has {
					blocked = true
					break
				}
				reqQ, rok := quests[req]
				if !rok || inCycle[req] {
					blocked = true
					break
				}
				if win.Witness < policy.MinWitness {
					blocked = true
					break
				}
				if win.Day >= att.Day {
					blocked = true
					break
				}
				_ = reqQ
			}
			if blocked {
				status = "blocked_prereq"
				addReason(reasons, "missing_prereq")
			} else {
				status = "valid"
				tagKey := gid + "|" + q.ChainTag
				base := q.BasePoints
				if streakAtWin[k] >= policy.PityStreakThreshold {
					base = base * policy.PityMultiplierPercent / 100
					addReason(reasons, "pity_bonus")
				}
				cap := policy.ReputationCapByTier[q.Tier]
				if base > cap {
					base = cap
				}
				points = base
				_ = tagKey
				successDay[successKey{gid, qid}] = att.Day
			}
		}

		entries = append(entries, completionEntry{
			GuildID: gid, QuestID: qid, Day: att.Day, Witness: att.Witness,
			PointsAwarded: points, Status: status, Reasons: reasonList(reasons),
		})
	}

	sort.Slice(entries, func(i, j int) bool {
		if entries[i].GuildID != entries[j].GuildID {
			return entries[i].GuildID < entries[j].GuildID
		}
		return entries[i].QuestID < entries[j].QuestID
	})

	entryIndex := map[winKey]int{}
	for i := range entries {
		entryIndex[winKey{entries[i].GuildID, entries[i].QuestID}] = i
	}

	var incidents struct {
		Events []map[string]any `json:"events"`
	}
	load("incidents.json", &incidents)
	ignored := 0
	type appliedRow struct {
		Day     int    `json:"day"`
		Kind    string `json:"kind"`
		GuildID string `json:"guild_id,omitempty"`
		QuestID string `json:"quest_id,omitempty"`
		Effect  string `json:"effect"`
	}
	var applied []appliedRow

	sabotaged := map[string]struct{}{}
	frozenGuilds := map[string]struct{}{}
	type reviewEv struct {
		day    int
		target string
		idx    int
	}
	reviews := map[string]reviewEv{}

	for idx, ev := range incidents.Events {
		kind, _ := ev["kind"].(string)
		dayF, _ := ev["day"].(float64)
		day := int(dayF)
		if kind == "" || day > pool.CurrentDay {
			ignored++
			continue
		}
		switch kind {
		case "quest_sabotage":
			qid, _ := ev["quest_id"].(string)
			if _, ok := quests[qid]; !ok {
				ignored++
				continue
			}
			sabotaged[qid] = struct{}{}
			applied = append(applied, appliedRow{Day: day, Kind: kind, QuestID: qid, Effect: "void_quest"})
		case "guild_freeze":
			gid, _ := ev["guild_id"].(string)
			if _, ok := guilds[gid]; !ok {
				ignored++
				continue
			}
			frozenGuilds[gid] = struct{}{}
			applied = append(applied, appliedRow{Day: day, Kind: kind, GuildID: gid, Effect: "freeze_guild"})
		case "payout_review":
			gid, _ := ev["guild_id"].(string)
			target, _ := ev["target_payout"].(string)
			if _, ok := guilds[gid]; !ok || (target != "paid" && target != "withheld") {
				ignored++
				continue
			}
			cur := reviews[gid]
			if day > cur.day || (day == cur.day && idx > cur.idx) {
				reviews[gid] = reviewEv{day: day, target: target, idx: idx}
			}
			applied = append(applied, appliedRow{Day: day, Kind: kind, GuildID: gid, Effect: "payout_review"})
		default:
			ignored++
		}
	}

	for qid := range sabotaged {
		for i := range entries {
			if entries[i].QuestID == qid {
				entries[i].Status = "void"
				rs := map[string]struct{}{}
				for _, r := range entries[i].Reasons {
					rs[r] = struct{}{}
				}
				addReason(rs, "quest_sabotage")
				entries[i].Reasons = reasonList(rs)
				entries[i].PointsAwarded = 0
			}
		}
	}

	voidGuilds := map[string]struct{}{}
	for i := range entries {
		if entries[i].Status == "void" {
			voidGuilds[entries[i].GuildID] = struct{}{}
		}
	}
	taintClusters := map[string]struct{}{}
	for gid := range voidGuilds {
		taintClusters[guilds[gid].ClusterID] = struct{}{}
	}
	for i := range entries {
		if entries[i].Status != "valid" {
			continue
		}
		g := guilds[entries[i].GuildID]
		if _, ok := taintClusters[g.ClusterID]; !ok {
			continue
		}
		if _, vg := voidGuilds[entries[i].GuildID]; vg {
			continue // void guild's other rows are unchanged
		}
		// only guilds other than the void source guild, same cluster
		hasVoidPeer := false
		for vg := range voidGuilds {
			if guilds[vg].ClusterID == g.ClusterID {
				hasVoidPeer = true
				break
			}
		}
		if !hasVoidPeer {
			continue
		}
		rs := map[string]struct{}{}
		for _, r := range entries[i].Reasons {
			rs[r] = struct{}{}
		}
		entries[i].Status = "tainted"
		addReason(rs, "cluster_taint")
		entries[i].Reasons = reasonList(rs)
		entries[i].PointsAwarded = 0
	}

	for gid := range frozenGuilds {
		for i := range entries {
			if entries[i].GuildID == gid && entries[i].Status != "void" {
				rs := map[string]struct{}{}
				for _, r := range entries[i].Reasons {
					rs[r] = struct{}{}
				}
				entries[i].Status = "frozen"
				addReason(rs, "guild_freeze")
				entries[i].Reasons = reasonList(rs)
				entries[i].PointsAwarded = 0
			}
		}
	}

	// cluster cap trim on valid rows
	type clusterTier struct {
		raw, capped int
	}
	clusterTotals := map[string]map[string]clusterTier{}
	for i := range entries {
		if entries[i].Status != "valid" {
			continue
		}
		g := guilds[entries[i].GuildID]
		q := quests[entries[i].QuestID]
		if clusterTotals[g.ClusterID] == nil {
			clusterTotals[g.ClusterID] = map[string]clusterTier{}
		}
		ct := clusterTotals[g.ClusterID][q.Tier]
		ct.raw += entries[i].PointsAwarded
		ct.capped += entries[i].PointsAwarded
		clusterTotals[g.ClusterID][q.Tier] = ct
	}

	trimLoop := true
	for trimLoop {
		trimLoop = false
		for cluster, tiers := range clusterTotals {
			for tier, ct := range tiers {
				cap := policy.ReputationCapByTier[tier]
				if ct.capped <= cap {
					continue
				}
				var candidates []int
				for i := range entries {
					if entries[i].Status != "valid" {
						continue
					}
					g := guilds[entries[i].GuildID]
					q := quests[entries[i].QuestID]
					if g.ClusterID == cluster && q.Tier == tier && entries[i].PointsAwarded > 0 {
						candidates = append(candidates, i)
					}
				}
				if len(candidates) == 0 {
					continue
				}
				sort.Slice(candidates, func(a, b int) bool {
					ea, eb := entries[candidates[a]], entries[candidates[b]]
					if ea.Day != eb.Day {
						return ea.Day > eb.Day
					}
					return ea.QuestID > eb.QuestID
				})
				idx := candidates[0]
				sub := entries[idx].PointsAwarded
				if sub > ct.capped-cap {
					sub = ct.capped - cap
				}
				if sub <= 0 {
					sub = entries[idx].PointsAwarded
				}
				entries[idx].PointsAwarded -= sub
				if entries[idx].PointsAwarded == 0 {
					rs := map[string]struct{}{}
					for _, r := range entries[idx].Reasons {
						rs[r] = struct{}{}
					}
					addReason(rs, "cluster_cap_trim")
					entries[idx].Reasons = reasonList(rs)
				}
				ct.capped -= sub
				clusterTotals[cluster][tier] = ct
				trimLoop = true
				break
			}
		}
	}

	type guildLedger struct {
		GuildID           string         `json:"guild_id"`
		PointsByTier      map[string]int `json:"points_by_tier"`
		PreliminaryPayout string         `json:"preliminary_payout"`
		FinalPayout       string         `json:"final_payout"`
		Reasons           []string       `json:"reasons"`
	}

	ledger := map[string]*guildLedger{}
	for gid := range guilds {
		ledger[gid] = &guildLedger{
			GuildID: gid,
			PointsByTier: map[string]int{"bronze": 0, "silver": 0, "gold": 0},
			PreliminaryPayout: "withheld",
			FinalPayout:       "withheld",
			Reasons:           []string{},
		}
	}
	for i := range entries {
		if entries[i].Status != "valid" {
			continue
		}
		q := quests[entries[i].QuestID]
		gl := ledger[entries[i].GuildID]
		gl.PointsByTier[q.Tier] += entries[i].PointsAwarded
	}
	for _, gl := range ledger {
		total := gl.PointsByTier["bronze"] + gl.PointsByTier["silver"] + gl.PointsByTier["gold"]
		if total > 0 {
			gl.PreliminaryPayout = "paid"
			gl.FinalPayout = "paid"
		}
	}

	for gid, rev := range reviews {
		hasVoidOrTaint := false
		for i := range entries {
			if entries[i].GuildID == gid && (entries[i].Status == "void" || entries[i].Status == "tainted") {
				hasVoidOrTaint = true
				break
			}
		}
		if hasVoidOrTaint {
			continue
		}
		gl := ledger[gid]
		gl.FinalPayout = rev.target
		rs := map[string]struct{}{}
		for _, r := range gl.Reasons {
			rs[r] = struct{}{}
		}
		addReason(rs, "payout_review")
		gl.Reasons = reasonList(rs)
	}

	var ledgerList []guildLedger
	for _, gid := range sortedStrings(func() map[string]struct{} {
		m := map[string]struct{}{}
		for id := range guilds {
			m[id] = struct{}{}
		}
		return m
	}()) {
		ledgerList = append(ledgerList, *ledger[gid])
	}

	type tierTotals struct {
		RawTotal    int `json:"raw_total"`
		CappedTotal int `json:"capped_total"`
	}
	type clusterRow struct {
		ClusterID string                `json:"cluster_id"`
		Tiers     map[string]tierTotals `json:"tiers"`
	}
	var clusterRows []clusterRow
	for _, cid := range sortedStrings(func() map[string]struct{} {
		m := map[string]struct{}{}
		for _, g := range guilds {
			m[g.ClusterID] = struct{}{}
		}
		return m
	}()) {
		tiers := map[string]tierTotals{}
		for _, t := range []string{"bronze", "silver", "gold"} {
			ct := clusterTotals[cid][t]
			tiers[t] = tierTotals{RawTotal: ct.raw, CappedTotal: ct.capped}
		}
		clusterRows = append(clusterRows, clusterRow{ClusterID: cid, Tiers: tiers})
	}

	sort.Slice(applied, func(i, j int) bool {
		a, b := applied[i], applied[j]
		if a.Day != b.Day {
			return a.Day < b.Day
		}
		if a.Kind != b.Kind {
			return a.Kind < b.Kind
		}
		if a.GuildID != b.GuildID {
			return a.GuildID < b.GuildID
		}
		return a.QuestID < b.QuestID
	})

	byStatus := map[string]int{
		"valid": 0, "failed": 0, "void": 0, "tainted": 0, "frozen": 0,
		"blocked_prereq": 0, "chain_blocked": 0,
	}
	for i := range entries {
		byStatus[entries[i].Status]++
	}
	byPrelim := map[string]int{"paid": 0, "withheld": 0}
	byFinal := map[string]int{"paid": 0, "withheld": 0}
	for _, gl := range ledgerList {
		byPrelim[gl.PreliminaryPayout]++
		byFinal[gl.FinalPayout]++
	}

	_ = writeJSON(filepath.Join(auditDir, "completion_audit.json"), map[string]any{"entries": entries})
	_ = writeJSON(filepath.Join(auditDir, "quest_graph.json"), map[string]any{"cycles": cycles, "order": order})
	_ = writeJSON(filepath.Join(auditDir, "guild_ledger.json"), map[string]any{"guilds": ledgerList})
	_ = writeJSON(filepath.Join(auditDir, "cluster_pool.json"), map[string]any{"clusters": clusterRows})
	_ = writeJSON(filepath.Join(auditDir, "incident_trace.json"), map[string]any{"applied": applied})
	_ = writeJSON(filepath.Join(auditDir, "summary.json"), map[string]any{
		"current_day":              pool.CurrentDay,
		"season_id":                pool.SeasonID,
		"guilds_total":             len(guilds),
		"quests_total":             len(quests),
		"ignored_incident_events":  ignored,
		"by_status":                byStatus,
		"by_preliminary_payout":    byPrelim,
		"by_final_payout":          byFinal,
	})
}
