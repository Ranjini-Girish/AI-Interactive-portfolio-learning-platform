// Reference auditor for go-buildtag-import-audit (package main).
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type contextDoc struct {
	EntryPoints  []string `json:"entry_points"`
	ExtraTags    []string `json:"extra_tags"`
	Goarch       string   `json:"goarch"`
	Goos         string   `json:"goos"`
	ReferenceDay int      `json:"reference_day"`
}

type poolDoc struct {
	MaskedTags []string `json:"masked_tags"`
}

type policyDoc struct {
	ForbiddenImports []string `json:"forbidden_imports"`
}

type incident struct {
	Accepted bool           `json:"accepted"`
	Day      int            `json:"day"`
	EventID  string         `json:"event_id"`
	Kind     string         `json:"kind"`
	Payload  map[string]any `json:"payload"`
}

type fileSpec struct {
	CNF     [][]string `json:"cnf"`
	Imports []string   `json:"imports"`
	Name    string     `json:"name"`
}

type packageDoc struct {
	Files       []fileSpec `json:"files"`
	PackageKey  string     `json:"package_key"`
	PackagePath string     `json:"package_path"`
}

type activeRow struct {
	File        string `json:"file"`
	PackageKey  string `json:"package_key"`
	PackagePath string `json:"package_path"`
}

type edgeRow struct {
	From       string `json:"from"`
	ImportPath string `json:"import_path"`
	To         string `json:"to"`
}

type pkgStatus struct {
	PackageKey  string `json:"package_key"`
	PackagePath string `json:"package_path"`
	Status      string `json:"status"`
}

type entryRow struct {
	EntryPath            string   `json:"entry_path"`
	ExcludedEntry        bool     `json:"excluded_entry"`
	ReachablePackageKeys []string `json:"reachable_package_keys"`
}

type wrapActive struct {
	Rows []activeRow `json:"rows"`
}

type wrapEdges struct {
	Edges []edgeRow `json:"edges"`
}

type wrapPackages struct {
	Packages []pkgStatus `json:"packages"`
}

type wrapEntries struct {
	Entries []entryRow `json:"entries"`
}

type summaryDoc struct {
	ActiveFilesTotal               int `json:"active_files_total"`
	ActivePackagesTotal            int `json:"active_packages_total"`
	EdgesResolvedTotal             int `json:"edges_resolved_total"`
	EntriesExcludedTotal           int `json:"entries_excluded_total"`
	ForbiddenEdgesRawTotal         int `json:"forbidden_edges_raw_total"`
	ForbiddenEdgesWaivedTotal      int `json:"forbidden_edges_waived_total"`
	IncidentsAppliedTotal          int `json:"incidents_applied_total"`
	PackagesActiveOkTotal          int `json:"packages_active_ok_total"`
	PackagesActiveViolationTotal   int `json:"packages_active_violation_total"`
	PackagesExcludedTotal          int `json:"packages_excluded_total"`
	PackagesImportCycleTotal       int `json:"packages_import_cycle_total"`
	PackagesTotal                  int `json:"packages_total"`
}

func main() {
	root := os.Getenv("BTA_BUILDTAG_DIR")
	if root == "" {
		root = "/app/buildtag"
	}
	outDir := os.Getenv("BTA_OUT_DIR")
	if outDir == "" {
		outDir = "/app/outcome"
	}
	if err := run(root, outDir); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func run(root, outDir string) error {
	ctx, err := readJSON[contextDoc](filepath.Join(root, "context.json"))
	if err != nil {
		return err
	}
	pool, err := readJSON[poolDoc](filepath.Join(root, "pool_state.json"))
	if err != nil {
		return err
	}
	pol, err := readJSON[policyDoc](filepath.Join(root, "policy.json"))
	if err != nil {
		return err
	}
	incs, err := readJSONArray[incident](filepath.Join(root, "incidents.json"))
	if err != nil {
		return err
	}

	pkgs, err := loadPackages(filepath.Join(root, "packages"))
	if err != nil {
		return err
	}

	pathToKey := map[string]string{}
	for _, p := range pkgs {
		pathToKey[p.PackagePath] = p.PackageKey
	}

	forbiddenSet := map[string]struct{}{}
	for _, f := range pol.ForbiddenImports {
		forbiddenSet[f] = struct{}{}
	}

	T := buildTagSet(ctx, pool, incs)

	incidentsApplied := 0
	for _, inc := range incs {
		if inc.Accepted && inc.Day <= ctx.ReferenceDay {
			incidentsApplied++
		}
	}

	waivedPaths := waiverWinners(incs, ctx.ReferenceDay)

	activeFiles := []activeRow{}
	activeImports := []struct{ from, to, imp string }{}

	for _, p := range pkgs {
		for _, f := range p.Files {
			if ignoreFile(f.CNF) {
				continue
			}
			if !evalCNF(f.CNF, T) {
				continue
			}
			activeFiles = append(activeFiles, activeRow{
				File:        f.Name,
				PackageKey:  p.PackageKey,
				PackagePath: p.PackagePath,
			})
			for _, imp := range f.Imports {
				activeImports = append(activeImports, struct{ from, to, imp string }{
					from: p.PackageKey,
					to:   pathToKey[imp],
					imp:  imp,
				})
			}
		}
	}

	sort.Slice(activeFiles, func(i, j int) bool {
		a, b := activeFiles[i], activeFiles[j]
		if a.PackageKey != b.PackageKey {
			return a.PackageKey < b.PackageKey
		}
		if a.File != b.File {
			return a.File < b.File
		}
		return a.PackagePath < b.PackagePath
	})

	edgeSet := map[string]edgeRow{}
	for _, e := range activeImports {
		if e.to == "" {
			continue
		}
		key := e.from + "\x00" + e.to + "\x00" + e.imp
		edgeSet[key] = edgeRow{From: e.from, To: e.to, ImportPath: e.imp}
	}
	edges := make([]edgeRow, 0, len(edgeSet))
	for _, er := range edgeSet {
		edges = append(edges, er)
	}
	sort.Slice(edges, func(i, j int) bool {
		a, b := edges[i], edges[j]
		if a.From != b.From {
			return a.From < b.From
		}
		if a.To != b.To {
			return a.To < b.To
		}
		return a.ImportPath < b.ImportPath
	})

	activePkg := map[string]bool{}
	for _, r := range activeFiles {
		activePkg[r.PackageKey] = true
	}

	adj := buildAdjActive(activePkg, edgeSet)

	forbiddenRaw := 0
	forbiddenWaived := 0
	for _, p := range pkgs {
		for _, f := range p.Files {
			if ignoreFile(f.CNF) || !evalCNF(f.CNF, T) {
				continue
			}
			for _, imp := range f.Imports {
				if _, ok := forbiddenSet[imp]; !ok {
					continue
				}
				forbiddenRaw++
				if _, ok := waivedPaths[imp]; ok {
					forbiddenWaived++
				}
			}
		}
	}

	status := map[string]string{}
	for _, p := range pkgs {
		key := p.PackageKey
		if !activePkg[key] {
			status[key] = "excluded"
			continue
		}
		viol := false
		for _, f := range p.Files {
			if ignoreFile(f.CNF) || !evalCNF(f.CNF, T) {
				continue
			}
			for _, imp := range f.Imports {
				if _, ok := forbiddenSet[imp]; !ok {
					continue
				}
				if _, ok := waivedPaths[imp]; !ok {
					viol = true
					break
				}
			}
			if viol {
				break
			}
		}
		if viol {
			status[key] = "active_violation"
			continue
		}

		if participatesInCycle(key, adj) {
			status[key] = "import_cycle"
			continue
		}
		status[key] = "active_ok"
	}

	pkgRows := make([]pkgStatus, 0, len(pkgs))
	for _, p := range pkgs {
		pkgRows = append(pkgRows, pkgStatus{
			PackageKey:  p.PackageKey,
			PackagePath: p.PackagePath,
			Status:      status[p.PackageKey],
		})
	}
	sort.Slice(pkgRows, func(i, j int) bool {
		return pkgRows[i].PackageKey < pkgRows[j].PackageKey
	})

	entries := []entryRow{}
	entriesExcluded := 0
	for _, ep := range ctx.EntryPoints {
		k, ok := pathToKey[ep]
		er := entryRow{EntryPath: ep, ExcludedEntry: false, ReachablePackageKeys: []string{}}
		if !ok || status[k] == "excluded" {
			er.ExcludedEntry = true
			er.ReachablePackageKeys = []string{}
			entriesExcluded++
		} else {
			er.ReachablePackageKeys = reachableKeys(k, adj)
		}
		entries = append(entries, er)
	}
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].EntryPath < entries[j].EntryPath
	})

	sum := summaryDoc{
		PackagesTotal: len(pkgs),
	}
	sum.ActiveFilesTotal = len(activeFiles)
	for _, st := range status {
		switch st {
		case "excluded":
			sum.PackagesExcludedTotal++
		case "active_ok":
			sum.PackagesActiveOkTotal++
		case "active_violation":
			sum.PackagesActiveViolationTotal++
		case "import_cycle":
			sum.PackagesImportCycleTotal++
		}
	}
	sum.ActivePackagesTotal = sum.PackagesTotal - sum.PackagesExcludedTotal
	sum.EdgesResolvedTotal = len(edges)
	sum.ForbiddenEdgesRawTotal = forbiddenRaw
	sum.ForbiddenEdgesWaivedTotal = forbiddenWaived
	sum.IncidentsAppliedTotal = incidentsApplied
	sum.EntriesExcludedTotal = entriesExcluded

	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(outDir, "active_sources.json"), wrapActive{Rows: activeFiles}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(outDir, "resolved_import_edges.json"), wrapEdges{Edges: edges}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(outDir, "package_status.json"), wrapPackages{Packages: pkgRows}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(outDir, "entry_closure.json"), wrapEntries{Entries: entries}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(outDir, "summary.json"), sum); err != nil {
		return err
	}
	return nil
}

func buildAdjActive(active map[string]bool, edges map[string]edgeRow) map[string][]string {
	adj := map[string][]string{}
	for _, e := range edges {
		if !active[e.From] || !active[e.To] {
			continue
		}
		adj[e.From] = append(adj[e.From], e.To)
	}
	for k := range adj {
		sort.Strings(adj[k])
	}
	return adj
}

func participatesInCycle(start string, adj map[string][]string) bool {
	for _, v := range adj[start] {
		if v == start {
			return true
		}
	}
	for _, n := range adj[start] {
		if n == start {
			continue
		}
		if canReachBFS(n, start, adj) {
			return true
		}
	}
	return false
}

func canReachBFS(from, target string, adj map[string][]string) bool {
	q := []string{from}
	seen := map[string]bool{from: true}
	for qi := 0; qi < len(q); qi++ {
		u := q[qi]
		for _, v := range adj[u] {
			if v == target {
				return true
			}
			if !seen[v] {
				seen[v] = true
				q = append(q, v)
			}
		}
	}
	return false
}

func reachableKeys(start string, adj map[string][]string) []string {
	out := map[string]bool{start: true}
	q := []string{start}
	for qi := 0; qi < len(q); qi++ {
		u := q[qi]
		for _, v := range adj[u] {
			if !out[v] {
				out[v] = true
				q = append(q, v)
			}
		}
	}
	keys := make([]string, 0, len(out))
	for k := range out {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func waiverWinners(incs []incident, refDay int) map[string]struct{} {
	type win struct {
		day int
		eid string
	}
	best := map[string]win{}
	for _, inc := range incs {
		if !inc.Accepted || inc.Day > refDay || inc.Kind != "forbidden_waiver" {
			continue
		}
		ip, _ := inc.Payload["import_path"].(string)
		if ip == "" {
			continue
		}
		cur, ok := best[ip]
		if !ok || inc.Day > cur.day || (inc.Day == cur.day && inc.EventID > cur.eid) {
			best[ip] = win{day: inc.Day, eid: inc.EventID}
		}
	}
	out := map[string]struct{}{}
	for k := range best {
		out[k] = struct{}{}
	}
	return out
}

func buildTagSet(ctx *contextDoc, pool *poolDoc, incs []incident) map[string]bool {
	T := map[string]bool{}
	T[strings.ToLower(ctx.Goos)] = true
	T[strings.ToLower(ctx.Goarch)] = true
	for _, x := range ctx.ExtraTags {
		T[x] = true
	}
	switch strings.ToLower(ctx.Goos) {
	case "linux", "darwin", "freebsd", "openbsd", "netbsd":
		T["unix"] = true
	}

	var inj []incident
	for _, inc := range incs {
		if inc.Accepted && inc.Day <= ctx.ReferenceDay && inc.Kind == "tag_injection" {
			inj = append(inj, inc)
		}
	}
	sort.Slice(inj, func(i, j int) bool {
		if inj[i].Day != inj[j].Day {
			return inj[i].Day < inj[j].Day
		}
		return inj[i].EventID < inj[j].EventID
	})
	for _, inc := range inj {
		raw, _ := inc.Payload["tags"].([]any)
		for _, t := range raw {
			if s, ok := t.(string); ok {
				T[s] = true
			}
		}
	}
	for _, m := range pool.MaskedTags {
		delete(T, m)
	}
	return T
}

func ignoreFile(cnf [][]string) bool {
	for _, clause := range cnf {
		if len(clause) == 1 && clause[0] == "ignore" {
			return true
		}
	}
	return false
}

func evalCNF(cnf [][]string, T map[string]bool) bool {
	if len(cnf) == 0 {
		return true
	}
	for _, clause := range cnf {
		ok := false
		for _, lit := range clause {
			if strings.HasPrefix(lit, "!") && len(lit) > 1 {
				name := lit[1:]
				ok = ok || !T[name]
			} else {
				ok = ok || T[lit]
			}
			if ok {
				break
			}
		}
		if !ok {
			return false
		}
	}
	return true
}

func loadPackages(dir string) ([]packageDoc, error) {
	matches, err := filepath.Glob(filepath.Join(dir, "*.json"))
	if err != nil {
		return nil, err
	}
	sort.Strings(matches)
	var out []packageDoc
	for _, m := range matches {
		p, err := readJSON[packageDoc](m)
		if err != nil {
			return nil, err
		}
		out = append(out, *p)
	}
	return out, nil
}

func readJSON[T any](path string) (*T, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var v T
	if err := json.Unmarshal(b, &v); err != nil {
		return nil, err
	}
	return &v, nil
}

func readJSONArray[T any](path string) ([]T, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var v []T
	if err := json.Unmarshal(b, &v); err != nil {
		return nil, err
	}
	return v, nil
}

func writeJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(b, '\n'), 0o644)
}
