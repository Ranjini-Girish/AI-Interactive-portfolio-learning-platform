package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type globalPolicy struct {
	SchemaVersion   int    `json:"schema_version"`
	DefaultDecision string `json:"default_decision"`
}

type incidentPolicy struct {
	Active          bool     `json:"active"`
	LockedHosts     []string `json:"locked_hosts"`
	BreakGlassToken string   `json:"break_glass_token"`
}

type groupsFile struct {
	Groups map[string]groupDef `json:"groups"`
}

type groupDef struct {
	Extends         []string          `json:"extends"`
	RequiredHeaders map[string]string `json:"required_headers"`
}

type routeFile struct {
	PackID string      `json:"pack_id"`
	Rules  []routeRule `json:"rules"`
}

type routeRule struct {
	ID         string   `json:"id"`
	Host       string   `json:"host"`
	HostType   string   `json:"host_type"`
	PathPrefix string   `json:"path_prefix"`
	Methods    []string `json:"methods"`
	Group      *string  `json:"group"`
	Decision   string   `json:"decision"`
}

type requestFile struct {
	RequestID string            `json:"request_id"`
	Host      string            `json:"host"`
	Method    string            `json:"method"`
	Path      string            `json:"path"`
	Headers   map[string]string `json:"headers"`
}

type violation struct {
	Code   string `json:"code"`
	Detail string `json:"detail"`
}

type evaluation struct {
	Decision            string `json:"decision"`
	HeadersRequiredMet  bool   `json:"headers_required_met"`
	MatchedPackID       any    `json:"matched_pack_id"`
	MatchedRuleID       any    `json:"matched_rule_id"`
	PathPrefixMatched   any    `json:"path_prefix_matched"`
	Reason              string `json:"reason"`
	RequestID           string `json:"request_id"`
}

type override struct {
	Kind      string `json:"kind"`
	RequestID string `json:"request_id"`
}

type packedRule struct {
	PackID string
	Rule   routeRule
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	gwRoot := "/app/gateway"
	outPath := "/app/out/gateway_audit.json"

	gp, err := readJSON[globalPolicy](filepath.Join(gwRoot, "policies", "global.json"))
	if err != nil {
		return err
	}
	ip, err := readJSON[incidentPolicy](filepath.Join(gwRoot, "policies", "incident.json"))
	if err != nil {
		return err
	}
	gf, err := readJSON[groupsFile](filepath.Join(gwRoot, "groups", "groups.json"))
	if err != nil {
		return err
	}

	var routes []packedRule
	packIDs := map[string]struct{}{}
	routeDir := filepath.Join(gwRoot, "routes")
	entries, err := os.ReadDir(routeDir)
	if err != nil {
		return err
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })
	for _, ent := range entries {
		if ent.IsDir() || !strings.HasSuffix(ent.Name(), ".json") {
			continue
		}
		rf, err := readJSON[routeFile](filepath.Join(routeDir, ent.Name()))
		if err != nil {
			return err
		}
		packIDs[rf.PackID] = struct{}{}
		for _, rl := range rf.Rules {
			routes = append(routes, packedRule{PackID: rf.PackID, Rule: rl})
		}
	}

	var requests []requestFile
	reqDir := filepath.Join(gwRoot, "requests")
	reqEnts, err := os.ReadDir(reqDir)
	if err != nil {
		return err
	}
	sort.Slice(reqEnts, func(i, j int) bool { return reqEnts[i].Name() < reqEnts[j].Name() })
	for _, ent := range reqEnts {
		if ent.IsDir() || !strings.HasSuffix(ent.Name(), ".json") {
			continue
		}
		q, err := readJSON[requestFile](filepath.Join(reqDir, ent.Name()))
		if err != nil {
			return err
		}
		requests = append(requests, q)
	}
	sort.Slice(requests, func(i, j int) bool { return requests[i].RequestID < requests[j].RequestID })

	cyclic := map[string]bool{}
	for name := range gf.Groups {
		vis := map[string]bool{}
		if _, err := linearized(name, gf.Groups, vis); err != nil {
			cyclic[name] = true
		}
	}

	idCounts := map[string]int{}
	for _, pr := range routes {
		idCounts[pr.Rule.ID]++
	}
	dupIDs := map[string]bool{}
	for id, c := range idCounts {
		if c > 1 {
			dupIDs[id] = true
		}
	}

	var violations []violation
	var dupList []string
	for id := range dupIDs {
		dupList = append(dupList, id)
	}
	sort.Strings(dupList)
	for _, id := range dupList {
		violations = append(violations, violation{Code: "duplicate_rule_id", Detail: "id=" + id})
	}
	var cycNames []string
	for name, is := range cyclic {
		if is {
			cycNames = append(cycNames, name)
		}
	}
	sort.Strings(cycNames)
	for _, name := range cycNames {
		violations = append(violations, violation{Code: "group_cycle", Detail: "group=" + name})
	}
	for _, pr := range routes {
		gname := groupName(pr.Rule)
		if gname == "" {
			continue
		}
		if _, ok := gf.Groups[gname]; !ok {
			violations = append(violations, violation{
				Code:   "unknown_group",
				Detail: fmt.Sprintf("pack=%s rule=%s group=%s", pr.PackID, pr.Rule.ID, gname),
			})
			continue
		}
		if cyclic[gname] {
			violations = append(violations, violation{
				Code:   "rule_uses_cyclic_group",
				Detail: fmt.Sprintf("pack=%s rule=%s group=%s", pr.PackID, pr.Rule.ID, gname),
			})
		}
	}
	sort.Slice(violations, func(i, j int) bool {
		if violations[i].Code != violations[j].Code {
			return violations[i].Code < violations[j].Code
		}
		return violations[i].Detail < violations[j].Detail
	})

	groupResolution := map[string]any{}
	var gnames []string
	for n := range gf.Groups {
		if !cyclic[n] {
			gnames = append(gnames, n)
		}
	}
	sort.Strings(gnames)
	for _, name := range gnames {
		vis := map[string]bool{}
		lin, err := linearized(name, gf.Groups, vis)
		if err != nil {
			continue
		}
		headers := mergedHeaders(lin, gf.Groups)
		sortedHdr := map[string]string{}
		hdrKeys := make([]string, 0, len(headers))
		for k := range headers {
			hdrKeys = append(hdrKeys, k)
		}
		sort.Strings(hdrKeys)
		for _, k := range hdrKeys {
			sortedHdr[k] = headers[k]
		}
		groupResolution[name] = map[string]any{
			"extends_linearized": lin,
			"required_headers":   sortedHdr,
		}
	}

	var evaluations []evaluation
	var overrides []override
	allowN, denyN := 0, 0
	incidentDenies := 0
	breakGlass := 0

	for _, req := range requests {
		ev, ov := evaluateRequest(req, gp, ip, routes, gf.Groups, dupIDs, cyclic)
		evaluations = append(evaluations, ev)
		if ov != nil {
			overrides = append(overrides, *ov)
			if ov.Kind == "incident_lock" {
				incidentDenies++
			} else {
				breakGlass++
			}
		}
		if ev.Decision == "allow" {
			allowN++
		} else {
			denyN++
		}
	}

	sort.Slice(overrides, func(i, j int) bool {
		if overrides[i].RequestID != overrides[j].RequestID {
			return overrides[i].RequestID < overrides[j].RequestID
		}
		return overrides[i].Kind < overrides[j].Kind
	})

	summary := map[string]any{
		"allow":                allowN,
		"break_glass_rescues":  breakGlass,
		"deny":                 denyN,
		"distinct_packs":       len(packIDs),
		"incident_lock_denies": incidentDenies,
		"requests_total":       len(evaluations),
		"violations_count":     len(violations),
	}

	out := map[string]any{
		"evaluations":      evaluationsToMaps(evaluations),
		"group_resolution": groupResolution,
		"overrides":        overridesToMaps(overrides),
		"summary":          summary,
		"violations":       violationsToMaps(violations),
	}

	raw, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(outPath, raw, 0o644)
}

func readJSON[T any](path string) (T, error) {
	var z T
	b, err := os.ReadFile(path)
	if err != nil {
		return z, err
	}
	if err := json.Unmarshal(b, &z); err != nil {
		return z, fmt.Errorf("parse %s: %w", path, err)
	}
	return z, nil
}

func groupName(r routeRule) string {
	if r.Group == nil {
		return ""
	}
	return strings.TrimSpace(*r.Group)
}

func linearized(name string, all map[string]groupDef, visiting map[string]bool) ([]string, error) {
	if visiting[name] {
		return nil, fmt.Errorf("cycle")
	}
	g, ok := all[name]
	if !ok {
		return nil, fmt.Errorf("missing group %s", name)
	}
	visiting[name] = true
	defer delete(visiting, name)

	var out []string
	for _, e := range g.Extends {
		if _, ok := all[e]; !ok {
			return nil, fmt.Errorf("missing extend %s", e)
		}
		sub, err := linearized(e, all, visiting)
		if err != nil {
			return nil, err
		}
		for _, x := range sub {
			if !containsStr(out, x) {
				out = append(out, x)
			}
		}
	}
	if !containsStr(out, name) {
		out = append(out, name)
	}
	return out, nil
}

func mergedHeaders(order []string, all map[string]groupDef) map[string]string {
	out := map[string]string{}
	for _, name := range order {
		g := all[name]
		for k, v := range g.RequiredHeaders {
			out[k] = v
		}
	}
	return out
}

func containsStr(xs []string, v string) bool {
	for _, x := range xs {
		if x == v {
			return true
		}
	}
	return false
}

func hostMatches(host string, rule routeRule) bool {
	h := strings.ToLower(strings.TrimSpace(host))
	switch rule.HostType {
	case "exact":
		return h == strings.ToLower(strings.TrimSpace(rule.Host))
	case "suffix":
		s := rule.Host
		if !strings.HasPrefix(s, "*.") {
			return false
		}
		base := strings.ToLower(strings.TrimSpace(s[2:]))
		if h == base {
			return false
		}
		return strings.HasSuffix(h, "."+base)
	case "any":
		return true
	default:
		return false
	}
}

func methodMatches(method string, methods []string) bool {
	if len(methods) == 1 && methods[0] == "*" {
		return true
	}
	for _, m := range methods {
		if m == method {
			return true
		}
	}
	return false
}

func headerValue(req requestFile, canonName string) (string, bool) {
	target := strings.ToLower(canonName)
	for k, v := range req.Headers {
		if strings.ToLower(k) == target {
			return strings.TrimSpace(v), true
		}
	}
	return "", false
}

func headersSatisfied(req requestFile, hdrs map[string]string) bool {
	for name, need := range hdrs {
		val, ok := headerValue(req, name)
		if !ok {
			return false
		}
		if strings.HasPrefix(need, "prefix:") {
			suf := need[len("prefix:"):]
			if !strings.HasPrefix(val, suf) {
				return false
			}
			continue
		}
		if val != need {
			return false
		}
	}
	return true
}

func breakGlassOK(req requestFile, token string) bool {
	if token == "" {
		return false
	}
	v, ok := headerValue(req, "X-Break-Glass")
	if !ok {
		return false
	}
	return v == token
}

func lockedHost(host string, locked []string) bool {
	h := strings.ToLower(strings.TrimSpace(host))
	for _, l := range locked {
		if h == strings.ToLower(strings.TrimSpace(l)) {
			return true
		}
	}
	return false
}

func ruleEligible(pr packedRule, req requestFile, groups map[string]groupDef, dupIDs map[string]bool, cyclic map[string]bool) bool {
	if dupIDs[pr.Rule.ID] {
		return false
	}
	gname := groupName(pr.Rule)
	if gname != "" {
		if _, ok := groups[gname]; !ok {
			return false
		}
		if cyclic[gname] {
			return false
		}
	}
	if !hostMatches(req.Host, pr.Rule) {
		return false
	}
	if !methodMatches(req.Method, pr.Rule.Methods) {
		return false
	}
	if !strings.HasPrefix(req.Path, pr.Rule.PathPrefix) {
		return false
	}
	if gname != "" {
		vis := map[string]bool{}
		lin, err := linearized(gname, groups, vis)
		if err != nil {
			return false
		}
		hdrs := mergedHeaders(lin, groups)
		if !headersSatisfied(req, hdrs) {
			return false
		}
	}
	return true
}

func pickWinner(cands []packedRule) packedRule {
	sort.SliceStable(cands, func(i, j int) bool {
		li := len(cands[i].Rule.PathPrefix)
		lj := len(cands[j].Rule.PathPrefix)
		if li != lj {
			return li > lj
		}
		if cands[i].Rule.ID != cands[j].Rule.ID {
			return cands[i].Rule.ID < cands[j].Rule.ID
		}
		return cands[i].PackID < cands[j].PackID
	})
	return cands[0]
}

func evaluateRequest(req requestFile, gp globalPolicy, ip incidentPolicy, routes []packedRule, groups map[string]groupDef, dupIDs map[string]bool, cyclic map[string]bool) (evaluation, *override) {
	var ov *override
	if ip.Active && lockedHost(req.Host, ip.LockedHosts) {
		if breakGlassOK(req, ip.BreakGlassToken) {
			ov = &override{RequestID: req.RequestID, Kind: "break_glass_skip"}
		} else {
			return evaluation{
				RequestID:          req.RequestID,
				Decision:           "deny",
				Reason:             "incident_lock",
				MatchedRuleID:      nil,
				MatchedPackID:      nil,
				PathPrefixMatched:  nil,
				HeadersRequiredMet: false,
			}, &override{RequestID: req.RequestID, Kind: "incident_lock"}
		}
	}

	var cands []packedRule
	for _, pr := range routes {
		if ruleEligible(pr, req, groups, dupIDs, cyclic) {
			cands = append(cands, pr)
		}
	}
	if len(cands) == 0 {
		dec := gp.DefaultDecision
		return evaluation{
			RequestID:          req.RequestID,
			Decision:           dec,
			Reason:             "default",
			MatchedRuleID:      nil,
			MatchedPackID:      nil,
			PathPrefixMatched:  nil,
			HeadersRequiredMet: false,
		}, ov
	}
	w := pickWinner(cands)
	return evaluation{
		RequestID:          req.RequestID,
		Decision:           w.Rule.Decision,
		Reason:             "matched",
		MatchedRuleID:      w.Rule.ID,
		MatchedPackID:      w.PackID,
		PathPrefixMatched:  w.Rule.PathPrefix,
		HeadersRequiredMet: true,
	}, ov
}

func evaluationsToMaps(xs []evaluation) []map[string]any {
	out := make([]map[string]any, 0, len(xs))
	for _, e := range xs {
		out = append(out, map[string]any{
			"decision":             e.Decision,
			"headers_required_met": e.HeadersRequiredMet,
			"matched_pack_id":      e.MatchedPackID,
			"matched_rule_id":      e.MatchedRuleID,
			"path_prefix_matched":  e.PathPrefixMatched,
			"reason":               e.Reason,
			"request_id":           e.RequestID,
		})
	}
	return out
}

func overridesToMaps(xs []override) []map[string]any {
	out := make([]map[string]any, 0, len(xs))
	for _, o := range xs {
		out = append(out, map[string]any{
			"kind":       o.Kind,
			"request_id": o.RequestID,
		})
	}
	return out
}

func violationsToMaps(xs []violation) []map[string]any {
	out := make([]map[string]any, 0, len(xs))
	for _, v := range xs {
		out = append(out, map[string]any{
			"code":   v.Code,
			"detail": v.Detail,
		})
	}
	return out
}
