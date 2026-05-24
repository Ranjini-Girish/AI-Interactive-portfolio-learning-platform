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

type policy struct {
	CapRank              []string `json:"cap_rank"`
	ImportDenySubstrings []string `json:"import_deny_substrings"`
	SupportedKinds       []string `json:"supported_incident_kinds"`
}

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type moduleRec struct {
	ModuleID         string   `json:"module_id"`
	Tier             string   `json:"tier"`
	DeclaredImports  []string `json:"declared_imports"`
	Capabilities     []string `json:"capabilities"`
}

type reexportLink struct {
	From          string   `json:"from"`
	To            string   `json:"to"`
	PrefixFilters []string `json:"prefix_filters"`
}

type hostFile struct {
	HostSlot string   `json:"host_slot"`
	Members  []string `json:"members"`
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	data := getenv("WCA_DATA_DIR", "/app/wasmcaps")
	outd := getenv("WCA_AUDIT_DIR", "/app/audit")
	if err := run(data, outd); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func run(dataDir, auditDir string) error {
	var pol policy
	if err := readJSON(filepath.Join(dataDir, "policy.json"), &pol); err != nil {
		return err
	}
	var ps poolState
	if err := readJSON(filepath.Join(dataDir, "pool_state.json"), &ps); err != nil {
		return err
	}

	modules, err := loadModules(filepath.Join(dataDir, "modules"))
	if err != nil {
		return err
	}
	allowlists, err := loadAllowlists(filepath.Join(dataDir, "allowlists"))
	if err != nil {
		return err
	}
	var rex struct {
		Links []reexportLink `json:"links"`
	}
	if err := readJSON(filepath.Join(dataDir, "reexports.json"), &rex); err != nil {
		return err
	}
	hosts, err := loadHosts(filepath.Join(dataDir, "hosts"))
	if err != nil {
		return err
	}

	quarantined, frozen, revoked, accepted, ignored, err := processIncidents(
		dataDir, pol, ps.CurrentDay, rex.Links,
	)
	if err != nil {
		return err
	}

	capRankIdx := make(map[string]int)
	for i, c := range pol.CapRank {
		capRankIdx[c] = i
	}

	effMaps := computeAllEffective(modules, rex.Links, quarantined)
	eff := make(map[string][]string)
	verdicts := make(map[string]string)
	ids := moduleIDs(modules)

	for _, id := range ids {
		m := modules[id]
		if quarantined[id] {
			eff[id] = []string{}
			verdicts[id] = "quarantined"
			continue
		}
		eff[id] = sortedKeys(effMaps[id])
		verdicts[id] = judgeModule(m, eff[id], frozen[id], allowlists[m.Tier], pol.ImportDenySubstrings)
	}

	closures := make(map[string][]string)
	for _, id := range ids {
		closures[id] = append([]string(nil), eff[id]...)
	}

	modRows := make([]map[string]any, 0, len(ids))
	for _, id := range ids {
		m := modules[id]
		modRows = append(modRows, map[string]any{
			"declared_imports":  sortedCopy(m.DeclaredImports),
			"effective_imports": sortedCopy(eff[id]),
			"module_id":         id,
			"tier":              m.Tier,
			"verdict":           verdicts[id],
		})
	}

	hostOut := buildHostLattice(hosts, modules, quarantined, revoked, capRankIdx)

	verdictCounts := map[string]int{}
	for _, v := range verdicts {
		verdictCounts[v]++
	}

	summary := map[string]any{
		"evaluation_day":   ps.CurrentDay,
		"host_slots_total": len(hosts),
		"modules_total":    len(modules),
		"service_tiers":    []string{"bronze", "gold", "silver"},
		"verdict_counts":   sortedKeysInt(verdictCounts),
	}

	outputs := map[string]any{
		"module_verdicts.json": map[string]any{
			"evaluation_day": ps.CurrentDay,
			"modules":        modRows,
		},
		"import_closure.json": map[string]any{"closures": closures},
		"capability_lattice.json": map[string]any{
			"host_slots": hostOut,
		},
		"incident_journal.json": map[string]any{
			"accepted":  accepted,
			"ignored":   ignored,
		},
		"summary.json": summary,
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	names := []string{
		"module_verdicts.json",
		"import_closure.json",
		"capability_lattice.json",
		"incident_journal.json",
		"summary.json",
	}
	for _, name := range names {
		if err := writeCanonical(filepath.Join(auditDir, name), outputs[name]); err != nil {
			return err
		}
	}
	return nil
}

func readJSON(path string, v any) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(raw, v)
}

func loadModules(dir string) (map[string]moduleRec, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make(map[string]moduleRec)
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		var m moduleRec
		if err := readJSON(filepath.Join(dir, e.Name()), &m); err != nil {
			return nil, err
		}
		out[m.ModuleID] = m
	}
	return out, nil
}

func loadAllowlists(dir string) (map[string][]string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make(map[string][]string)
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		tier := strings.TrimSuffix(e.Name(), ".json")
		var raw struct {
			Prefixes []string `json:"prefixes"`
		}
		if err := readJSON(filepath.Join(dir, e.Name()), &raw); err != nil {
			return nil, err
		}
		out[tier] = raw.Prefixes
	}
	return out, nil
}

func loadHosts(dir string) ([]hostFile, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var hosts []hostFile
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		var h hostFile
		if err := readJSON(filepath.Join(dir, e.Name()), &h); err != nil {
			return nil, err
		}
		hosts = append(hosts, h)
	}
	sort.Slice(hosts, func(i, j int) bool { return hosts[i].HostSlot < hosts[j].HostSlot })
	return hosts, nil
}

func processIncidents(
	dataDir string,
	pol policy,
	currentDay int,
	links []reexportLink,
) (map[string]bool, map[string]bool, map[string]bool, []map[string]any, []map[string]any, error) {
	var log struct {
		Events []map[string]any `json:"events"`
	}
	if err := readJSON(filepath.Join(dataDir, "incident_log.json"), &log); err != nil {
		return nil, nil, nil, nil, nil, err
	}
	supported := make(map[string]bool)
	for _, k := range pol.SupportedKinds {
		supported[k] = true
	}

	quarantined := make(map[string]bool)
	frozen := make(map[string]bool)
	revoked := make(map[string]bool)
	var accepted, ignored []map[string]any

	events := append([]map[string]any(nil), log.Events...)
	sort.Slice(events, func(i, j int) bool {
		di := intFrom(events[i]["day"])
		dj := intFrom(events[j]["day"])
		if di != dj {
			return di < dj
		}
		return fmt.Sprint(events[i]["event_id"]) < fmt.Sprint(events[j]["event_id"])
	})

	for _, ev := range events {
		kind := fmt.Sprint(ev["kind"])
		day := intFrom(ev["day"])
		eid := fmt.Sprint(ev["event_id"])
		acc := true
		if v, ok := ev["accepted"]; ok {
			acc = boolFrom(v)
		}
		scope, _ := ev["scope"].(map[string]any)
		reason := ""
		switch {
		case !acc:
			reason = "accepted_false"
		case day > currentDay:
			reason = "future_day"
		case !supported[kind]:
			reason = "unsupported_kind"
		}
		if reason != "" {
			ignored = append(ignored, map[string]any{
				"day": day, "event_id": eid, "kind": kind, "reason": reason,
			})
			continue
		}
		accepted = append(accepted, ev)
		switch kind {
		case "module_compromise":
			mid := fmt.Sprint(scope["module_id"])
			quarantined[mid] = true
			propagateQuarantine(mid, links, quarantined)
		case "capability_revoke":
			revoked[fmt.Sprint(scope["capability"])] = true
		case "import_freeze":
			frozen[fmt.Sprint(scope["module_id"])] = true
		}
	}
	sortJournal(accepted)
	sortJournal(ignored)
	return quarantined, frozen, revoked, accepted, ignored, nil
}

func propagateQuarantine(seed string, links []reexportLink, q map[string]bool) {
	changed := true
	for changed {
		changed = false
		for _, l := range links {
			if q[l.From] && !q[l.To] {
				q[l.To] = true
				changed = true
			}
		}
	}
}

func computeAllEffective(
	modules map[string]moduleRec,
	links []reexportLink,
	quarantined map[string]bool,
) map[string]map[string]bool {
	eff := make(map[string]map[string]bool)
	for id, m := range modules {
		if quarantined[id] {
			eff[id] = make(map[string]bool)
			continue
		}
		set := make(map[string]bool)
		for _, imp := range m.DeclaredImports {
			set[imp] = true
		}
		eff[id] = set
	}
	changed := true
	for changed {
		changed = false
		for _, l := range links {
			if quarantined[l.To] || quarantined[l.From] {
				continue
			}
			for imp := range eff[l.From] {
				if !matchesPrefix(imp, l.PrefixFilters) {
					continue
				}
				if !eff[l.To][imp] {
					eff[l.To][imp] = true
					changed = true
				}
			}
		}
	}
	return eff
}

func matchesPrefix(imp string, prefixes []string) bool {
	for _, p := range prefixes {
		if strings.HasPrefix(imp, p) {
			return true
		}
	}
	return false
}

func judgeModule(
	m moduleRec,
	effective []string,
	isFrozen bool,
	allowPrefixes []string,
	denySubs []string,
) string {
	declSet := make(map[string]bool)
	for _, d := range m.DeclaredImports {
		declSet[d] = true
	}
	if isFrozen {
		for _, imp := range effective {
			if !declSet[imp] {
				return "import_frozen"
			}
		}
	}
	for _, imp := range effective {
		for _, sub := range denySubs {
			if strings.Contains(imp, sub) {
				return "import_denied"
			}
		}
		if !matchesPrefix(imp, allowPrefixes) {
			return "import_denied"
		}
	}
	return "ok"
}

func buildHostLattice(
	hosts []hostFile,
	modules map[string]moduleRec,
	quarantined map[string]bool,
	revoked map[string]bool,
	capRankIdx map[string]int,
) map[string]any {
	out := make(map[string]any)
	for _, h := range hosts {
		byCat := make(map[string][]string)
		for _, mid := range h.Members {
			if quarantined[mid] {
				continue
			}
			m := modules[mid]
			for _, cap := range m.Capabilities {
				if revoked[cap] {
					continue
				}
				cat := cap
				if i := strings.Index(cap, "."); i >= 0 {
					cat = cap[:i]
				}
				byCat[cat] = append(byCat[cat], cap)
			}
		}
		var merged []string
		cats := make([]string, 0, len(byCat))
		for c := range byCat {
			cats = append(cats, c)
		}
		sort.Strings(cats)
		for _, cat := range cats {
			merged = append(merged, pickCap(byCat[cat], capRankIdx))
		}
		sort.Strings(merged)
		out[h.HostSlot] = map[string]any{
			"host_slot":            h.HostSlot,
			"merged_capabilities":  merged,
			"members":              sortedCopy(h.Members),
		}
	}
	return out
}

func pickCap(caps []string, capRankIdx map[string]int) string {
	var ranked, unranked []string
	for _, c := range caps {
		if _, ok := capRankIdx[c]; ok {
			ranked = append(ranked, c)
		} else {
			unranked = append(unranked, c)
		}
	}
	if len(ranked) > 0 {
		best := ranked[0]
		bestIdx := capRankIdx[best]
		for _, c := range ranked[1:] {
			idx := capRankIdx[c]
			if idx < bestIdx || (idx == bestIdx && c < best) {
				best = c
				bestIdx = idx
			}
		}
		return best
	}
	sort.Strings(unranked)
	return unranked[0]
}

func moduleIDs(modules map[string]moduleRec) []string {
	ids := make([]string, 0, len(modules))
	for id := range modules {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

func sortedCopy(ss []string) []string {
	out := append([]string(nil), ss...)
	sort.Strings(out)
	return out
}

func sortedKeys(set map[string]bool) []string {
	out := make([]string, 0, len(set))
	for k := range set {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func sortedKeysInt(m map[string]int) map[string]int {
	out := make(map[string]int)
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		out[k] = m[k]
	}
	return out
}

func sortJournal(rows []map[string]any) {
	sort.Slice(rows, func(i, j int) bool {
		di := intFrom(rows[i]["day"])
		dj := intFrom(rows[j]["day"])
		if di != dj {
			return di < dj
		}
		return fmt.Sprint(rows[i]["event_id"]) < fmt.Sprint(rows[j]["event_id"])
	})
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

func boolFrom(v any) bool {
	switch x := v.(type) {
	case bool:
		return x
	default:
		return true
	}
}

func writeCanonical(path string, v any) error {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		return err
	}
	b := buf.Bytes()
	if len(b) == 0 || b[len(b)-1] != '\n' {
		b = append(b, '\n')
	}
	return os.WriteFile(path, b, 0o644)
}
