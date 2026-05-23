package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
)

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type policyDoc struct {
	RetentionMinTier map[string]string `json:"retention_min_tier"`
	TierRank         map[string]int    `json:"tier_rank"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type manifestRec struct {
	ContentDigest  string  `json:"content_digest"`
	DeclaredParent *string `json:"declared_parent"`
	ManifestID     string  `json:"manifest_id"`
	RetentionClass string  `json:"retention_class"`
	SigningTier    string  `json:"signing_tier"`
}

type graphNode struct {
	DeclaredParent  *string `json:"declared_parent"`
	DepthCapHit     bool    `json:"depth_cap_hit"`
	InCycle         bool    `json:"in_cycle"`
	LineageDepth    int     `json:"lineage_depth"`
	ManifestID      string  `json:"manifest_id"`
	RawLineageDepth int     `json:"raw_lineage_depth"`
	ResolvedParent  *string `json:"resolved_parent"`
}

type integrityReport struct {
	DigestInvalid []string `json:"digest_invalid"`
	MissingParent []string `json:"missing_parent"`
}

type tierViol struct {
	ManifestID      string `json:"manifest_id"`
	RequiredMinTier string `json:"required_min_tier"`
	SigningTier     string `json:"signing_tier"`
}

type policyScreen struct {
	DepthCapValue  *int       `json:"depth_cap_value"`
	Quarantined    []string   `json:"quarantined"`
	TierViolations []tierViol `json:"tier_violations"`
}

type journalEntry struct {
	Day     int    `json:"day"`
	EventID string `json:"event_id"`
	Kind    string `json:"kind"`
}

type incidentJournal struct {
	AppliedEvents []journalEntry `json:"applied_events"`
}

type manifestGraph struct {
	Nodes    []graphNode `json:"nodes"`
	SccLists [][]string  `json:"scc_lists"`
}

type summaryOut struct {
	CyclesDetected       int `json:"cycles_detected"`
	DigestInvalid        int `json:"digest_invalid"`
	ManifestsInCatalog   int `json:"manifests_in_catalog"`
	MissingParent        int `json:"missing_parent"`
	NodesInCycle         int `json:"nodes_in_cycle"`
	QuarantinedManifests int `json:"quarantined_manifests"`
	TierViolationCount   int `json:"tier_violation_count"`
}

var digestRe = regexp.MustCompile(`^[0-9a-f]{64}$`)

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	dataDir := getenv("LMA_DATA_DIR", "/app/lineage_manifests")
	auditDir := getenv("LMA_AUDIT_DIR", "/app/audit")
	if err := run(dataDir, auditDir); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func writeJSON(path string, v any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
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

func intVal(v any) int {
	switch t := v.(type) {
	case int:
		return t
	case int64:
		return int(t)
	case float64:
		return int(t)
	default:
		return 0
	}
}

func strSlice(v any) []string {
	arr, ok := v.([]any)
	if !ok {
		return nil
	}
	out := make([]string, 0, len(arr))
	for _, x := range arr {
		if s, ok := x.(string); ok {
			out = append(out, s)
		}
	}
	return out
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
	var pol policyDoc
	if err := json.Unmarshal(polRaw, &pol); err != nil {
		return err
	}

	incRaw, err := os.ReadFile(filepath.Join(dataDir, "incident_log.json"))
	if err != nil {
		return err
	}
	var il incidentLog
	if err := json.Unmarshal(incRaw, &il); err != nil {
		return err
	}

	catalog := map[string]manifestRec{}
	manDir := filepath.Join(dataDir, "manifests")
	entries, err := os.ReadDir(manDir)
	if err != nil {
		return err
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(manDir, e.Name()))
		if err != nil {
			return err
		}
		var m manifestRec
		if err := json.Unmarshal(b, &m); err != nil {
			return fmt.Errorf("manifest %s: %w", e.Name(), err)
		}
		catalog[m.ManifestID] = m
	}

	ids := make([]string, 0, len(catalog))
	for id := range catalog {
		ids = append(ids, id)
	}
	sort.Strings(ids)

	digestInvalid := make([]string, 0)
	for _, id := range ids {
		if !digestRe.MatchString(catalog[id].ContentDigest) {
			digestInvalid = append(digestInvalid, id)
		}
	}

	Q := map[string]struct{}{}
	var capVals []int
	journal := make([]journalEntry, 0)
	for _, ev := range il.Events {
		if !boolVal(ev["accepted"]) {
			continue
		}
		if intVal(ev["day"]) > ps.CurrentDay {
			continue
		}
		kind, _ := ev["kind"].(string)
		eid, _ := ev["event_id"].(string)
		journal = append(journal, journalEntry{
			Day:     intVal(ev["day"]),
			EventID: eid,
			Kind:    kind,
		})
		switch kind {
		case "manifest_quarantine":
			for _, mid := range strSlice(ev["manifest_ids"]) {
				Q[mid] = struct{}{}
			}
		case "lineage_depth_cap":
			capVals = append(capVals, intVal(ev["max_depth"]))
		}
	}
	sort.Slice(journal, func(i, j int) bool {
		if journal[i].Day != journal[j].Day {
			return journal[i].Day < journal[j].Day
		}
		return journal[i].EventID < journal[j].EventID
	})

	quar := make([]string, 0, len(Q))
	for id := range Q {
		quar = append(quar, id)
	}
	sort.Strings(quar)

	var capPtr *int
	if len(capVals) > 0 {
		mn := capVals[0]
		for _, c := range capVals[1:] {
			if c < mn {
				mn = c
			}
		}
		capPtr = &mn
	}

	missing := make([]string, 0)
	eff := map[string]*string{}
	for _, id := range ids {
		rec := catalog[id]
		var res *string
		if _, q := Q[id]; q {
			res = nil
		} else if rec.DeclaredParent == nil || *rec.DeclaredParent == id {
			res = nil
		} else {
			p := *rec.DeclaredParent
			if _, ok := catalog[p]; !ok {
				res = nil
				missing = append(missing, id)
			} else if _, q := Q[p]; q {
				res = nil
			} else {
				res = rec.DeclaredParent
			}
		}
		eff[id] = res
	}
	sort.Strings(missing)

	succ := map[string]string{}
	for _, id := range ids {
		if p := eff[id]; p != nil {
			succ[id] = *p
		} else {
			succ[id] = ""
		}
	}

	sccs := tarjanSCCs(ids, succ)
	core := map[string]struct{}{}
	for _, comp := range sccs {
		for _, x := range comp {
			core[x] = struct{}{}
		}
	}
	rev := map[string][]string{}
	for u, w := range succ {
		if w != "" {
			rev[w] = append(rev[w], u)
		}
	}
	cycleSet := map[string]struct{}{}
	q := make([]string, 0, len(core))
	for x := range core {
		q = append(q, x)
	}
	sort.Strings(q)
	for head := 0; head < len(q); head++ {
		u := q[head]
		if _, ok := cycleSet[u]; ok {
			continue
		}
		cycleSet[u] = struct{}{}
		for _, up := range rev[u] {
			q = append(q, up)
		}
	}

	digestBad := map[string]struct{}{}
	for _, id := range digestInvalid {
		digestBad[id] = struct{}{}
	}

	tierV := make([]tierViol, 0)
	for _, id := range ids {
		if _, bad := digestBad[id]; bad {
			continue
		}
		rec := catalog[id]
		reqName, ok := pol.RetentionMinTier[rec.RetentionClass]
		if !ok {
			continue
		}
		reqR, ok1 := pol.TierRank[reqName]
		gotR, ok2 := pol.TierRank[rec.SigningTier]
		if !ok1 {
			reqR = -1
		}
		if !ok2 {
			gotR = -1
		}
		if gotR < reqR {
			tierV = append(tierV, tierViol{
				ManifestID:      id,
				RequiredMinTier: reqName,
				SigningTier:     rec.SigningTier,
			})
		}
	}

	nodes := make([]graphNode, 0, len(ids))
	nodesInCycle := 0
	for _, id := range ids {
		rec := catalog[id]
		_, inC := cycleSet[id]
		if inC {
			nodesInCycle++
		}
		raw := rawLineageDepth(id, eff, cycleSet, inC)
		ld := raw
		capHit := false
		if !inC && capPtr != nil && raw >= 0 {
			if raw > *capPtr {
				ld = *capPtr
				capHit = true
			}
		}
		if inC {
			ld = -1
		}
		nodes = append(nodes, graphNode{
			DeclaredParent:  rec.DeclaredParent,
			DepthCapHit:     capHit,
			InCycle:         inC,
			LineageDepth:    ld,
			ManifestID:      id,
			RawLineageDepth: raw,
			ResolvedParent:  eff[id],
		})
	}

	mg := manifestGraph{Nodes: nodes, SccLists: sccs}
	if err := writeJSON(filepath.Join(auditDir, "manifest_graph.json"), mg); err != nil {
		return err
	}
	ir := integrityReport{DigestInvalid: digestInvalid, MissingParent: missing}
	if err := writeJSON(filepath.Join(auditDir, "integrity_report.json"), ir); err != nil {
		return err
	}
	psc := policyScreen{DepthCapValue: capPtr, Quarantined: quar, TierViolations: tierV}
	if err := writeJSON(filepath.Join(auditDir, "policy_screen.json"), psc); err != nil {
		return err
	}
	ij := incidentJournal{AppliedEvents: journal}
	if err := writeJSON(filepath.Join(auditDir, "incident_journal.json"), ij); err != nil {
		return err
	}
	sm := summaryOut{
		CyclesDetected:       len(sccs),
		DigestInvalid:        len(digestInvalid),
		ManifestsInCatalog:   len(catalog),
		MissingParent:        len(missing),
		NodesInCycle:         nodesInCycle,
		QuarantinedManifests: len(quar),
		TierViolationCount:   len(tierV),
	}
	return writeJSON(filepath.Join(auditDir, "summary.json"), sm)
}

func rawLineageDepth(id string, eff map[string]*string, cycleSet map[string]struct{}, inC bool) int {
	if inC {
		return -1
	}
	seen := map[string]struct{}{}
	cur := id
	d := 0
	for {
		if _, ok := seen[cur]; ok {
			return -1
		}
		seen[cur] = struct{}{}
		p := eff[cur]
		if p == nil {
			return d
		}
		if _, c := cycleSet[*p]; c {
			return -1
		}
		d++
		cur = *p
	}
}

var (
	tin, low map[string]int
	onStack  map[string]bool
	stack    []string
	timeTick int
	comps    [][]string
)

func tarjanSCCs(ids []string, succ map[string]string) [][]string {
	tin = map[string]int{}
	low = map[string]int{}
	onStack = map[string]bool{}
	stack = nil
	timeTick = 0
	comps = nil
	for _, v := range ids {
		if _, ok := tin[v]; !ok {
			tarjanVisit(v, succ)
		}
	}
	sort.Slice(comps, func(i, j int) bool {
		return comps[i][0] < comps[j][0]
	})
	return comps
}

func tarjanVisit(v string, succ map[string]string) {
	tin[v] = timeTick
	low[v] = timeTick
	timeTick++
	stack = append(stack, v)
	onStack[v] = true

	if w := succ[v]; w != "" {
		if _, ok := tin[w]; !ok {
			tarjanVisit(w, succ)
			if low[w] < low[v] {
				low[v] = low[w]
			}
		} else if onStack[w] {
			if tin[w] < low[v] {
				low[v] = tin[w]
			}
		}
	}

	if low[v] == tin[v] {
		comp := []string{}
		for {
			u := stack[len(stack)-1]
			stack = stack[:len(stack)-1]
			onStack[u] = false
			comp = append(comp, u)
			if u == v {
				break
			}
		}
		sort.Strings(comp)
		if len(comp) >= 2 {
			comps = append(comps, comp)
		}
	}
}
