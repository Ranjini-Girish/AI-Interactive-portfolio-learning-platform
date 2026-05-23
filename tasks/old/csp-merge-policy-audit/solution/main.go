package main

import (
	"bytes"
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
	PinnedDirectives []string       `json:"pinned_directives"`
	ReportCaps       map[string]int `json:"report_caps"`
	SupportedKinds   []string       `json:"supported_kinds"`
}

type inheritanceDoc struct {
	Edges []struct {
		Child  string `json:"child"`
		Parent string `json:"parent"`
	} `json:"edges"`
}

type originDoc struct {
	OriginID string `json:"origin_id"`
	Tier     string `json:"tier"`
}

type bundleDoc struct {
	BundleID     string              `json:"bundle_id"`
	DeliveryMode string              `json:"delivery_mode"`
	Directives   map[string][]string `json:"directives"`
	Nonces       []string            `json:"nonces"`
	OriginID     string              `json:"origin_id"`
}

type incidentEvent struct {
	Accepted bool           `json:"accepted"`
	Day      int              `json:"day"`
	EventID  string           `json:"event_id"`
	Kind     string           `json:"kind"`
	Payload  map[string]any   `json:"payload"`
}

type incidentLog struct {
	Events []incidentEvent `json:"events"`
}

type dirEntry struct {
	mode    string
	sources []string
}

type originState struct {
	quarantined        bool
	frozenMaxBundleID  *string
	reportUses         int
	reviewTarget       *string
	reviewOverride     bool
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	dataDir := getenv("CMP_DATA_DIR", "/app/cspmerge")
	auditDir := getenv("CMP_AUDIT_DIR", "/app/audit")
	if err := run(dataDir, auditDir); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
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
	var inh inheritanceDoc
	if err := readJSON(filepath.Join(dataDir, "inheritance.json"), &inh); err != nil {
		return err
	}
	var il incidentLog
	if err := readJSON(filepath.Join(dataDir, "incident_log.json"), &il); err != nil {
		return err
	}

	origins, err := loadOrigins(filepath.Join(dataDir, "origins"))
	if err != nil {
		return err
	}
	bundles, err := loadBundles(filepath.Join(dataDir, "bundles"), origins)
	if err != nil {
		return err
	}

	pinned := map[string]bool{}
	for _, d := range pol.PinnedDirectives {
		pinned[d] = true
	}
	supported := map[string]bool{}
	for _, k := range pol.SupportedKinds {
		supported[k] = true
	}

	descendants := buildDescendants(inh)
	states := map[string]*originState{}
	for oid := range origins {
		states[oid] = &originState{}
	}

	sortedEvents := append([]incidentEvent(nil), il.Events...)
	sort.Slice(sortedEvents, func(i, j int) bool {
		if sortedEvents[i].Day != sortedEvents[j].Day {
			return sortedEvents[i].Day < sortedEvents[j].Day
		}
		return sortedEvents[i].EventID < sortedEvents[j].EventID
	})

	trace := make([]map[string]any, 0, len(sortedEvents))
	ignored := map[string]int{
		"ignored_future_day":      0,
		"ignored_not_accepted":    0,
		"ignored_unsupported_kind": 0,
	}
	applied := 0

	for _, ev := range sortedEvents {
		res := resolveEvent(ev, ps.CurrentDay, supported)
		if res != "applied" {
			ignored[res]++
		} else {
			applied++
			if err := applyEvent(ev, states, descendants); err != nil {
				return err
			}
		}
		trace = append(trace, map[string]any{
			"accepted":   ev.Accepted,
			"day":        ev.Day,
			"event_id":   ev.EventID,
			"kind":       ev.Kind,
			"resolution": res,
		})
	}

	bundlesByOrigin := map[string][]bundleDoc{}
	for _, b := range bundles {
		bundlesByOrigin[b.OriginID] = append(bundlesByOrigin[b.OriginID], b)
	}
	for oid := range bundlesByOrigin {
		sort.Slice(bundlesByOrigin[oid], func(i, j int) bool {
			return bundlesByOrigin[oid][i].BundleID < bundlesByOrigin[oid][j].BundleID
		})
	}

	matrixOrigins := make([]map[string]any, 0, len(origins))
	verdictOrigins := make([]map[string]any, 0, len(origins))
	enforceWinning := map[string]bool{}

	for _, oid := range sortedKeys(origins) {
		tier := origins[oid].Tier
		st := states[oid]
		var effective map[string][]string
		if st.quarantined {
			effective = map[string][]string{}
		} else {
			effective, enforceWinning[oid] = mergeBundles(
				bundlesByOrigin[oid], pinned, st.frozenMaxBundleID,
			)
		}
		matrixOrigins = append(matrixOrigins, map[string]any{
			"effective_directives": effectiveObject(effective),
			"origin_id":            oid,
			"quarantined":          st.quarantined,
		})

		prelim := preliminaryPosture(st, tier, enforceWinning[oid], pol.ReportCaps)
		delivery := prelim
		override := st.reviewOverride
		if st.reviewTarget != nil {
			delivery = *st.reviewTarget
		}
		verdictOrigins = append(verdictOrigins, map[string]any{
			"delivery_posture":        delivery,
			"origin_id":               oid,
			"preliminary_posture":     prelim,
			"review_override_applied": override,
		})
	}

	collisions := collectCollisions(bundles, states)
	collisionRows := make([]map[string]any, 0, len(collisions))
	for _, nonce := range sortedKeys(collisions) {
		collisionRows = append(collisionRows, map[string]any{
			"nonce":       nonce,
			"origin_ids":  collisions[nonce],
		})
	}

	quarantinedCount := 0
	reportSuppressed := 0
	enforceCount := 0
	reviewCount := 0
	for _, oid := range sortedKeys(origins) {
		st := states[oid]
		if st.quarantined {
			quarantinedCount++
		}
		for _, v := range verdictOrigins {
			if v["origin_id"] == oid {
				if v["delivery_posture"] == "report_suppressed" {
					reportSuppressed++
				}
				if v["delivery_posture"] == "enforce" {
					enforceCount++
				}
				break
			}
		}
		if st.reviewOverride {
			reviewCount++
		}
	}

	summary := map[string]any{
		"applied_incidents":          applied,
		"audit_version":              1,
		"bundle_count":               len(bundles),
		"collision_count":            len(collisionRows),
		"current_day":                ps.CurrentDay,
		"enforce_posture_origins":    enforceCount,
		"ignored_counts":             ignored,
		"origin_count":               len(origins),
		"quarantined_origins":        quarantinedCount,
		"report_suppressed_origins":  reportSuppressed,
		"review_override_origins":    reviewCount,
	}

	outputs := map[string]any{
		"directive_matrix.json": map[string]any{
			"current_day": ps.CurrentDay,
			"origins":     matrixOrigins,
		},
		"nonce_collisions.json": map[string]any{
			"collisions": collisionRows,
		},
		"enforce_verdicts.json": map[string]any{
			"origins": verdictOrigins,
		},
		"incident_overrides.json": map[string]any{
			"events": trace,
		},
		"summary.json": summary,
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	for name, payload := range outputs {
		if err := writeJSON(filepath.Join(auditDir, name), payload); err != nil {
			return err
		}
	}
	return nil
}

func resolveEvent(ev incidentEvent, currentDay int, supported map[string]bool) string {
	if ev.Day > currentDay {
		return "ignored_future_day"
	}
	if !ev.Accepted {
		return "ignored_not_accepted"
	}
	if !supported[ev.Kind] {
		return "ignored_unsupported_kind"
	}
	return "applied"
}

func applyEvent(ev incidentEvent, states map[string]*originState, descendants map[string][]string) error {
	switch ev.Kind {
	case "origin_compromise":
		oid, _ := ev.Payload["origin_id"].(string)
		if oid == "" {
			return fmt.Errorf("origin_compromise missing origin_id")
		}
		markQuarantine(oid, states, descendants)
	case "directive_freeze":
		oid, _ := ev.Payload["origin_id"].(string)
		maxID, _ := ev.Payload["max_bundle_id"].(string)
		if oid == "" || maxID == "" {
			return fmt.Errorf("directive_freeze missing fields")
		}
		st := states[oid]
		if st == nil {
			st = &originState{}
			states[oid] = st
		}
		st.frozenMaxBundleID = &maxID
	case "csp_report":
		oid, _ := ev.Payload["origin_id"].(string)
		if oid == "" {
			return fmt.Errorf("csp_report missing origin_id")
		}
		st := states[oid]
		if st == nil {
			st = &originState{}
			states[oid] = st
		}
		if !st.quarantined {
			st.reportUses++
		}
	case "audit_review":
		oid, _ := ev.Payload["origin_id"].(string)
		target, _ := ev.Payload["target_posture"].(string)
		if oid == "" || target == "" {
			return fmt.Errorf("audit_review missing fields")
		}
		if target != "enforce" && target != "report-only" && target != "report_suppressed" {
			return fmt.Errorf("invalid target_posture")
		}
		st := states[oid]
		if st == nil {
			st = &originState{}
			states[oid] = st
		}
		st.reviewTarget = &target
		st.reviewOverride = true
	}
	return nil
}

func markQuarantine(root string, states map[string]*originState, descendants map[string][]string) {
	queue := []string{root}
	seen := map[string]bool{}
	for len(queue) > 0 {
		oid := queue[0]
		queue = queue[1:]
		if seen[oid] {
			continue
		}
		seen[oid] = true
		st := states[oid]
		if st == nil {
			st = &originState{}
			states[oid] = st
		}
		st.quarantined = true
		queue = append(queue, descendants[oid]...)
	}
}

func buildDescendants(inh inheritanceDoc) map[string][]string {
	out := map[string][]string{}
	for _, e := range inh.Edges {
		out[e.Parent] = append(out[e.Parent], e.Child)
	}
	for k := range out {
		sort.Strings(out[k])
	}
	return out
}

func mergeBundles(bundles []bundleDoc, pinned map[string]bool, frozenMax *string) (map[string][]string, bool) {
	working := map[string]*dirEntry{}
	hasEnforce := false
	for _, b := range bundles {
		if frozenMax != nil && b.BundleID > *frozenMax {
			continue
		}
		for name, sources := range b.Directives {
			if existing, ok := working[name]; ok && pinned[name] {
				_ = existing
				continue
			}
			ent := working[name]
			if ent == nil {
				cp := append([]string(nil), sources...)
				working[name] = &dirEntry{mode: b.DeliveryMode, sources: cp}
				if b.DeliveryMode == "enforce" {
					hasEnforce = true
				}
				continue
			}
			switch {
			case ent.mode == "report-only" && b.DeliveryMode == "enforce":
				ent.mode = b.DeliveryMode
				ent.sources = append([]string(nil), sources...)
				hasEnforce = true
			case ent.mode == "enforce" && b.DeliveryMode == "report-only":
				// keep
			default:
				ent.mode = b.DeliveryMode
				ent.sources = append([]string(nil), sources...)
				if b.DeliveryMode == "enforce" {
					hasEnforce = true
				}
			}
		}
	}
	out := map[string][]string{}
	for name, ent := range working {
		out[name] = normalizeSources(ent.sources)
	}
	return out, hasEnforce
}

func normalizeSources(sources []string) []string {
	seen := map[string]bool{}
	ordered := make([]string, 0, len(sources))
	for _, s := range sources {
		if !seen[s] {
			seen[s] = true
			ordered = append(ordered, s)
		}
	}
	sort.Strings(ordered)
	hasHashOrNonce := false
	for _, s := range ordered {
		if strings.HasPrefix(s, "sha256-") || strings.HasPrefix(s, "sha384-") ||
			strings.HasPrefix(s, "sha512-") || strings.HasPrefix(s, "nonce-") {
			hasHashOrNonce = true
			break
		}
	}
	if !hasHashOrNonce {
		return ordered
	}
	filtered := make([]string, 0, len(ordered))
	for _, s := range ordered {
		if s == "'unsafe-inline'" {
			continue
		}
		filtered = append(filtered, s)
	}
	return filtered
}

func effectiveObject(effective map[string][]string) map[string]any {
	names := sortedKeys(effective)
	out := map[string]any{}
	for _, n := range names {
		out[n] = effective[n]
	}
	return out
}

func preliminaryPosture(st *originState, tier string, hasEnforce bool, caps map[string]int) string {
	if st.quarantined {
		return "blocked_quarantine"
	}
	if hasEnforce {
		return "enforce"
	}
	cap := caps[tier]
	if st.reportUses > cap {
		return "report_suppressed"
	}
	return "report-only"
}

func collectCollisions(bundles []bundleDoc, states map[string]*originState) map[string][]string {
	nonceOrigins := map[string]map[string]bool{}
	for _, b := range bundles {
		st := states[b.OriginID]
		if st != nil && st.quarantined {
			continue
		}
		for _, n := range b.Nonces {
			if nonceOrigins[n] == nil {
				nonceOrigins[n] = map[string]bool{}
			}
			nonceOrigins[n][b.OriginID] = true
		}
	}
	out := map[string][]string{}
	for nonce, ids := range nonceOrigins {
		if len(ids) < 2 {
			continue
		}
		list := sortedKeys(ids)
		out[nonce] = list
	}
	return out
}

func loadOrigins(dir string) (map[string]originDoc, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := map[string]originDoc{}
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var o originDoc
		if err := readJSON(filepath.Join(dir, e.Name()), &o); err != nil {
			return nil, err
		}
		if o.OriginID == "" {
			return nil, fmt.Errorf("empty origin_id in %s", e.Name())
		}
		if o.Tier != "gold" && o.Tier != "silver" && o.Tier != "bronze" {
			return nil, fmt.Errorf("invalid tier for %s", o.OriginID)
		}
		if _, dup := out[o.OriginID]; dup {
			return nil, fmt.Errorf("duplicate origin %s", o.OriginID)
		}
		out[o.OriginID] = o
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no origins")
	}
	return out, nil
}

func loadBundles(dir string, origins map[string]originDoc) ([]bundleDoc, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make([]bundleDoc, 0)
	seen := map[string]bool{}
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		var b bundleDoc
		if err := readJSON(filepath.Join(dir, e.Name()), &b); err != nil {
			return nil, err
		}
		if b.BundleID == "" {
			return nil, fmt.Errorf("empty bundle_id")
		}
		if seen[b.BundleID] {
			return nil, fmt.Errorf("duplicate bundle_id %s", b.BundleID)
		}
		seen[b.BundleID] = true
		if b.DeliveryMode != "enforce" && b.DeliveryMode != "report-only" {
			return nil, fmt.Errorf("invalid delivery_mode %s", b.BundleID)
		}
		if _, ok := origins[b.OriginID]; !ok {
			return nil, fmt.Errorf("unknown origin %s", b.OriginID)
		}
		if b.Directives == nil {
			b.Directives = map[string][]string{}
		}
		if b.Nonces == nil {
			b.Nonces = []string{}
		}
		out = append(out, b)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no bundles")
	}
	return out, nil
}

func sortedKeys[V any](m map[string]V) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func readJSON(path string, v any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, v)
}

func writeJSON(path string, v any) error {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(true)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		return err
	}
	return os.WriteFile(path, buf.Bytes(), 0o644)
}
