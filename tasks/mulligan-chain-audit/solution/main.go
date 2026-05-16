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

type policy struct {
	OpeningHandSize    int            `json:"opening_hand_size"`
	MaxMulligansByTier map[string]int `json:"max_mulligans_by_tier"`
	SharedMulliganPool *int           `json:"shared_mulligan_pool"`
}

type formatDoc struct {
	FormatID         string         `json:"format_id"`
	MaxMulligans     int            `json:"max_mulligans"`
	MinKeepHandSize  int            `json:"min_keep_hand_size"`
	MulliganStyle    string         `json:"mulligan_style"`
	RestrictedCounts map[string]int `json:"restricted_counts"`
}

type deckDoc struct {
	DeckID    string   `json:"deck_id"`
	Maindeck  []string `json:"maindeck"`
	Sideboard []string `json:"sideboard"`
	Tier      string   `json:"tier"`
}

type chainStep struct {
	Step   int      `json:"step"`
	Action string   `json:"action"`
	Hand   []string `json:"hand"`
}

type sessionDoc struct {
	SessionID string      `json:"session_id"`
	DeckID    string      `json:"deck_id"`
	FormatID  string      `json:"format_id"`
	PlayedDay int         `json:"played_day"`
	Chain     []chainStep `json:"chain"`
}

type incidentFile struct {
	Events []map[string]any `json:"events"`
}

type violation struct {
	Card  string `json:"card"`
	Found int    `json:"found"`
	Limit int    `json:"limit"`
}

type stepTrace struct {
	Step     int    `json:"step"`
	Action   string `json:"action"`
	HandSize int    `json:"hand_size"`
	SizeOK   bool   `json:"size_ok"`
}

type traceRow struct {
	SessionID string      `json:"session_id"`
	Steps     []stepTrace `json:"steps"`
}

type sessionVerdict struct {
	SessionID        string   `json:"session_id"`
	DeckID           string   `json:"deck_id"`
	FormatID         string   `json:"format_id"`
	Verdict          string   `json:"verdict"`
	MulliganCount    int      `json:"mulligan_count"`
	BannedCardsFound []string `json:"banned_cards_found"`
	Reasons          []string `json:"reasons"`
}

type deckRestrictionRow struct {
	DeckID     string      `json:"deck_id"`
	Violations []violation `json:"violations"`
}

type incidentRow struct {
	Day     int    `json:"day"`
	EventID string `json:"event_id"`
	Kind    string `json:"kind"`
	Card    string `json:"card,omitempty"`
	DeckID  string `json:"deck_id,omitempty"`
	Format  string `json:"format_id,omitempty"`
}

func main() {
	dataDir := getenv("MCA_DATA_DIR", "/app/mulligan_pool")
	auditDir := getenv("MCA_AUDIT_DIR", "/app/audit")
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
	opening := pol.OpeningHandSize
	if opening < 1 {
		opening = 7
	}

	formats, err := loadFormats(filepath.Join(dataDir, "formats"))
	if err != nil {
		return err
	}
	decks, err := loadDecks(filepath.Join(dataDir, "decks"))
	if err != nil {
		return err
	}
	sessions, err := loadSessions(filepath.Join(dataDir, "sessions"))
	if err != nil {
		return err
	}

	incRaw, err := os.ReadFile(filepath.Join(dataDir, "incidents.json"))
	if err != nil {
		return err
	}
	var inc incidentFile
	if err := json.Unmarshal(incRaw, &inc); err != nil {
		return err
	}

	kept, ignored := filterIncidents(inc.Events, ps.CurrentDay)
	appliedLedger := buildLedger(kept)

	mullBySessionID := map[string]int{}
	for _, s := range sessions {
		_, mc, _, _ := buildTrace(s.Chain, formats[s.FormatID], opening)
		mullBySessionID[s.SessionID] = mc
	}

	bannedByDay := map[string]int{}
	compromisedDecks := map[string]int{}
	suspendedFormats := map[string]int{}
	for _, ev := range kept {
		kind, _ := ev["kind"].(string)
		day := intNum(ev["day"])
		switch kind {
		case "card_ban":
			if card, ok := ev["card"].(string); ok {
				bannedByDay[card] = day
			}
		case "deck_compromise":
			if did, ok := ev["deck_id"].(string); ok {
				compromisedDecks[did] = day
			}
		case "format_suspend":
			if fid, ok := ev["format_id"].(string); ok {
				suspendedFormats[fid] = day
			}
		}
	}

	deckFormatsUsed := map[string]map[string]bool{}
	for _, s := range sessions {
		if deckFormatsUsed[s.DeckID] == nil {
			deckFormatsUsed[s.DeckID] = map[string]bool{}
		}
		deckFormatsUsed[s.DeckID][s.FormatID] = true
	}

	deckViolations := map[string][]violation{}
	deckRows := make([]deckRestrictionRow, 0, len(decks))
	deckIDs := sortedKeys(decks)
	for _, did := range deckIDs {
		d := decks[did]
		fids := deckFormatsUsed[did]
		if fids == nil {
			fids = map[string]bool{}
		}
		limits := mergeRestrictedCounts(formats, fids)
		viol := computeViolations(d, limits)
		if viol == nil {
			viol = []violation{}
		}
		deckViolations[did] = viol
		deckRows = append(deckRows, deckRestrictionRow{DeckID: did, Violations: viol})
	}

	verdicts := make([]sessionVerdict, 0, len(sessions))
	traces := make([]traceRow, 0, len(sessions))
	var legalCount, quarantineCount, formatSuspendCount, chainInvalidCount int

	for _, s := range sessions {
		deck := decks[s.DeckID]
		fmtDoc := formats[s.FormatID]
		viol := deckViolations[s.DeckID]

		trace, mullCount, hasKeep, sizeMismatch := buildTrace(s.Chain, fmtDoc, opening)
		traces = append(traces, traceRow{SessionID: s.SessionID, Steps: trace})

		var finalHand []string
		for i := len(s.Chain) - 1; i >= 0; i-- {
			if s.Chain[i].Action == "keep" {
				finalHand = s.Chain[i].Hand
				break
			}
		}

		bannedFound := bannedInHand(finalHand, bannedByDay, s.PlayedDay)
		if bannedFound == nil {
			bannedFound = []string{}
		}
		effectiveMax := effectiveMaxMulligans(fmtDoc, pol, deck.Tier)
		effectiveMax = applySharedMulliganCap(effectiveMax, pol.SharedMulliganPool, sessions, s, mullBySessionID)

		structReasons := structuralChainIssues(s.Chain)

		reasons := []string{}
		verdict := "legal"

		if day, ok := compromisedDecks[s.DeckID]; ok && s.PlayedDay >= day {
			verdict = "quarantined"
			reasons = append(reasons, "deck_compromise")
		} else if day, ok := suspendedFormats[s.FormatID]; ok && s.PlayedDay >= day {
			verdict = "format_suspended"
			reasons = append(reasons, "format_suspend")
		} else if len(viol) > 0 {
			verdict = "deck_restriction"
			reasons = append(reasons, "deck_restriction")
		} else if len(bannedFound) > 0 {
			verdict = "banned_card"
			reasons = append(reasons, "banned_card")
		} else if len(structReasons) > 0 {
			verdict = "chain_invalid"
			reasons = append(reasons, structReasons...)
		} else if mullCount > effectiveMax {
			verdict = "mulligan_exceeded"
			reasons = append(reasons, "mulligan_exceeded")
		} else if sizeMismatch || !hasKeep {
			verdict = "hand_size_mismatch"
			reasons = append(reasons, "hand_size_mismatch")
		}

		sort.Strings(reasons)
		uniqReasons := uniqueStrings(reasons)
		if verdict == "legal" {
			uniqReasons = []string{}
			legalCount++
		} else if verdict == "quarantined" {
			quarantineCount++
		} else if verdict == "format_suspended" {
			formatSuspendCount++
		} else if verdict == "chain_invalid" {
			chainInvalidCount++
		}

		verdicts = append(verdicts, sessionVerdict{
			SessionID:        s.SessionID,
			DeckID:           s.DeckID,
			FormatID:         s.FormatID,
			Verdict:          verdict,
			MulliganCount:    mullCount,
			BannedCardsFound: bannedFound,
			Reasons:          uniqReasons,
		})
	}

	sort.Slice(verdicts, func(i, j int) bool { return verdicts[i].SessionID < verdicts[j].SessionID })
	sort.Slice(traces, func(i, j int) bool { return traces[i].SessionID < traces[j].SessionID })

	restrictionHits := 0
	for _, row := range deckRows {
		if len(row.Violations) > 0 {
			restrictionHits++
		}
	}

	summary := map[string]any{
		"applied_incident_events":   len(kept),
		"chain_invalid_sessions":    chainInvalidCount,
		"deck_restriction_hits":     restrictionHits,
		"format_suspended_sessions": formatSuspendCount,
		"ignored_incident_events":   ignored,
		"legal_sessions":            legalCount,
		"quarantined_sessions":      quarantineCount,
		"sessions_total":            len(sessions),
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	if err := writePretty(filepath.Join(auditDir, "session_verdicts.json"), map[string]any{"sessions": verdicts}); err != nil {
		return err
	}
	if err := writePretty(filepath.Join(auditDir, "mulligan_traces.json"), map[string]any{"traces": traces}); err != nil {
		return err
	}
	if err := writePretty(filepath.Join(auditDir, "deck_restrictions.json"), map[string]any{"decks": deckRows}); err != nil {
		return err
	}
	if err := writePretty(filepath.Join(auditDir, "incident_ledger.json"), map[string]any{"applied_events": appliedLedger}); err != nil {
		return err
	}
	return writePretty(filepath.Join(auditDir, "summary.json"), summary)
}

func sortedKeys[T any](m map[string]T) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func loadFormats(dir string) (map[string]formatDoc, error) {
	out := map[string]formatDoc{}
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
		var f formatDoc
		if err := json.Unmarshal(b, &f); err != nil {
			return nil, err
		}
		out[f.FormatID] = f
	}
	return out, nil
}

func loadDecks(dir string) (map[string]deckDoc, error) {
	out := map[string]deckDoc{}
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
		var d deckDoc
		if err := json.Unmarshal(b, &d); err != nil {
			return nil, err
		}
		out[d.DeckID] = d
	}
	return out, nil
}

func loadSessions(dir string) ([]sessionDoc, error) {
	var out []sessionDoc
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
		var s sessionDoc
		if err := json.Unmarshal(b, &s); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].SessionID < out[j].SessionID })
	return out, nil
}

func filterIncidents(events []map[string]any, currentDay int) ([]map[string]any, int) {
	type row struct {
		ev  map[string]any
		day int
		id  string
	}
	var rows []row
	for _, ev := range events {
		acc, ok := ev["accepted"].(bool)
		if !ok || !acc {
			continue
		}
		day := intNum(ev["day"])
		if day > currentDay {
			continue
		}
		kind, _ := ev["kind"].(string)
		if !validIncident(ev, kind) {
			continue
		}
		id, _ := ev["event_id"].(string)
		rows = append(rows, row{ev: ev, day: day, id: id})
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].day != rows[j].day {
			return rows[i].day < rows[j].day
		}
		return rows[i].id < rows[j].id
	})
	kept := make([]map[string]any, len(rows))
	for i, r := range rows {
		kept[i] = r.ev
	}
	return kept, len(events) - len(kept)
}

func validIncident(ev map[string]any, kind string) bool {
	switch kind {
	case "card_ban":
		_, ok := ev["card"].(string)
		return ok
	case "deck_compromise":
		_, ok := ev["deck_id"].(string)
		return ok
	case "format_suspend":
		_, ok := ev["format_id"].(string)
		return ok
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
	default:
		return 0
	}
}

func buildLedger(kept []map[string]any) []incidentRow {
	out := make([]incidentRow, 0, len(kept))
	for _, ev := range kept {
		row := incidentRow{
			Day:     intNum(ev["day"]),
			EventID: ev["event_id"].(string),
			Kind:    ev["kind"].(string),
		}
		switch row.Kind {
		case "card_ban":
			row.Card = ev["card"].(string)
		case "deck_compromise":
			row.DeckID = ev["deck_id"].(string)
		case "format_suspend":
			row.Format = ev["format_id"].(string)
		}
		out = append(out, row)
	}
	return out
}

func computeViolations(d deckDoc, limits map[string]int) []violation {
	if len(limits) == 0 {
		return []violation{}
	}
	counts := map[string]int{}
	for _, c := range d.Maindeck {
		counts[c]++
	}
	for _, c := range d.Sideboard {
		counts[c]++
	}
	var out []violation
	for card, limit := range limits {
		found := counts[card]
		if found > limit {
			out = append(out, violation{Card: card, Found: found, Limit: limit})
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Card < out[j].Card })
	return out
}

func expectedHandSize(style string, opening, m int, fmtDoc formatDoc) int {
	switch style {
	case "london":
		return opening
	case "vancouver":
		minKeep := fmtDoc.MinKeepHandSize
		if minKeep < 1 {
			minKeep = 4
		}
		sz := opening - m
		if sz < minKeep {
			return minKeep
		}
		return sz
	case "partial_paris":
		sz := opening - 2*m
		if sz < 1 {
			return 1
		}
		return sz
	default:
		return opening
	}
}

func buildTrace(chain []chainStep, fmtDoc formatDoc, opening int) ([]stepTrace, int, bool, bool) {
	trace := make([]stepTrace, 0, len(chain))
	hasKeep := false
	lastKeepIdx := -1
	for i, st := range chain {
		if st.Action == "keep" {
			hasKeep = true
			lastKeepIdx = i
		}
	}
	mullCount := 0
	if hasKeep {
		for i := 0; i < lastKeepIdx; i++ {
			if chain[i].Action == "mulligan" {
				mullCount++
			}
		}
	} else {
		for _, st := range chain {
			if st.Action == "mulligan" {
				mullCount++
			}
		}
	}

	sizeMismatch := !hasKeep
	mPrior := 0
	for _, st := range chain {
		exp := expectedHandSize(fmtDoc.MulliganStyle, opening, mPrior, fmtDoc)
		hs := len(st.Hand)
		ok := hs == exp
		if !ok {
			sizeMismatch = true
		}
		trace = append(trace, stepTrace{
			Step:     st.Step,
			Action:   st.Action,
			HandSize: hs,
			SizeOK:   ok,
		})
		if st.Action == "mulligan" {
			mPrior++
		}
	}
	return trace, mullCount, hasKeep, sizeMismatch
}

func effectiveMaxMulligans(f formatDoc, pol policy, tier string) int {
	cap := f.MaxMulligans
	if pol.MaxMulligansByTier != nil {
		if tcap, ok := pol.MaxMulligansByTier[tier]; ok && tcap < cap {
			cap = tcap
		}
	}
	return cap
}

func mergeRestrictedCounts(formats map[string]formatDoc, formatIDs map[string]bool) map[string]int {
	out := map[string]int{}
	for fid := range formatIDs {
		f, ok := formats[fid]
		if !ok {
			continue
		}
		for card, lim := range f.RestrictedCounts {
			if prev, ok := out[card]; !ok {
				out[card] = lim
			} else if lim < prev {
				out[card] = lim
			}
		}
	}
	return out
}

func structuralChainIssues(chain []chainStep) []string {
	flags := map[string]bool{}
	keeps := 0
	for i, st := range chain {
		if st.Action == "keep" {
			keeps++
		}
		if st.Step != i {
			flags["step_index_drift"] = true
		}
		if st.Action != "mulligan" && st.Action != "keep" {
			flags["invalid_action"] = true
		}
	}
	if keeps > 1 {
		flags["multiple_keep"] = true
	}
	keys := make([]string, 0, len(flags))
	for k := range flags {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func applySharedMulliganCap(effectiveMax int, pool *int, sessions []sessionDoc, cur sessionDoc, mullByID map[string]int) int {
	if pool == nil {
		return effectiveMax
	}
	prior := 0
	for _, t := range sessions {
		if t.SessionID == cur.SessionID {
			break
		}
		if t.DeckID == cur.DeckID {
			prior += mullByID[t.SessionID]
		}
	}
	room := *pool - prior
	if room < 0 {
		room = 0
	}
	if room < effectiveMax {
		return room
	}
	return effectiveMax
}

func bannedInHand(hand []string, banned map[string]int, playedDay int) []string {
	if len(hand) == 0 {
		return []string{}
	}
	seen := map[string]bool{}
	var out []string
	for _, c := range hand {
		if banDay, ok := banned[c]; ok && playedDay >= banDay {
			if !seen[c] {
				seen[c] = true
				out = append(out, c)
			}
		}
	}
	sort.Strings(out)
	return out
}

func uniqueStrings(in []string) []string {
	if len(in) == 0 {
		return []string{}
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

func writePretty(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}
