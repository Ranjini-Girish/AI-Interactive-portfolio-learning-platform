package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

var root = "/app/sumlock_audit"

type manifest struct {
	Tags     map[string]struct{}
	Entries  []string
	Depends  []string
	Priority int
	File     string
}

type violation struct {
	Code    string `json:"code"`
	Module  string `json:"module"`
	Source  string `json:"source"`
	Version string `json:"version"`
}

type moduleOut struct {
	Entries []string `json:"entries"`
	Module  string   `json:"module"`
	Status  string   `json:"status"`
}

type summaryOut struct {
	TotalActive     int `json:"total_active"`
	TotalCycles     int `json:"total_cycles"`
	TotalExcluded   int `json:"total_excluded"`
	TotalMissing    int `json:"total_missing"`
	TotalModules    int `json:"total_modules"`
	TotalOrphan     int `json:"total_orphan"`
	TotalStale      int `json:"total_stale"`
	TotalUnknown    int `json:"total_unknown"`
	TotalViolations int `json:"total_violations"`
}

type reportOut struct {
	Cycles     [][]string  `json:"cycles"`
	Excluded   []string    `json:"excluded"`
	Modules    []moduleOut `json:"modules"`
	Summary    summaryOut  `json:"summary"`
	Violations []violation `json:"violations"`
}

func readKV(path string) map[string][]string {
	out := map[string][]string{}
	f, err := os.Open(path)
	if err != nil {
		return out
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		i := strings.Index(line, ":")
		if i < 0 {
			continue
		}
		out[strings.TrimSpace(line[:i])] = append(out[strings.TrimSpace(line[:i])], strings.TrimSpace(line[i+1:]))
	}
	return out
}

func fileSHA256(path string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}

func pickWinner(m []manifest) manifest {
	sort.Slice(m, func(i, j int) bool {
		if m[i].Priority != m[j].Priority {
			return m[i].Priority > m[j].Priority
		}
		return m[i].File < m[j].File
	})
	return m[0]
}

func pairKey(mod, ver string) string { return mod + "\x00" + ver }

func main() {
	if r := strings.TrimSpace(os.Getenv("SUMLOCK_ROOT")); r != "" {
		root = r
	}
	ws := readKV(filepath.Join(root, "workspace.wk"))
	profiles := map[string]struct{}{}
	for _, p := range strings.Split(ws["ACTIVE_PROFILES"][0], ",") {
		p = strings.TrimSpace(p)
		if p != "" {
			profiles[p] = struct{}{}
		}
	}
	lenient := len(ws["AUDIT_MODE"]) > 0 && strings.EqualFold(ws["AUDIT_MODE"][0], "lenient")
	pol := readKV(filepath.Join(root, "policies", "lenient.pol"))
	if len(pol["FORCE_LENIENT"]) > 0 && strings.EqualFold(pol["FORCE_LENIENT"][0], "true") {
		lenient = true
	}

	byMod := map[string][]manifest{}
	dir := filepath.Join(root, "manifests")
	ents, _ := os.ReadDir(dir)
	sort.Slice(ents, func(i, j int) bool { return ents[i].Name() < ents[j].Name() })
	for _, e := range ents {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".mft") {
			continue
		}
		kv := readKV(filepath.Join(dir, e.Name()))
		name := kv["MODULE"][0]
		tags := map[string]struct{}{}
		if len(kv["TAGS"]) > 0 {
			for _, t := range strings.Split(kv["TAGS"][0], ",") {
				t = strings.TrimSpace(t)
				if t != "" {
					tags[t] = struct{}{}
				}
			}
		}
		pri := 0
		if len(kv["PRIORITY"]) > 0 {
			fmt.Sscanf(kv["PRIORITY"][0], "%d", &pri)
		}
		byMod[name] = append(byMod[name], manifest{
			Tags: tags, Entries: kv["ENTRY"], Depends: kv["DEPENDS"], Priority: pri, File: e.Name(),
		})
	}

	winners := map[string]manifest{}
	for m, rs := range byMod {
		winners[m] = pickWinner(rs)
	}

	isActive := func(name string) bool {
		w := winners[name]
		if len(w.Tags) == 0 {
			return true
		}
		for t := range w.Tags {
			if _, ok := profiles[t]; !ok {
				return false
			}
		}
		return true
	}

	var excluded []string
	active := map[string]manifest{}
	for name := range byMod {
		if isActive(name) {
			active[name] = winners[name]
		} else {
			excluded = append(excluded, name)
		}
	}
	sort.Strings(excluded)

	owned := map[string][]string{}
	for n, w := range active {
		e := append([]string(nil), w.Entries...)
		sort.Strings(e)
		owned[n] = e
	}

	type useLine struct{ src, mod, ver string }
	var uses []useLine
	sdir := filepath.Join(root, "sources")
	sents, _ := os.ReadDir(sdir)
	sort.Slice(sents, func(i, j int) bool { return sents[i].Name() < sents[j].Name() })
	for _, e := range sents {
		if e.IsDir() {
			continue
		}
		kv := readKV(filepath.Join(sdir, e.Name()))
		src := kv["SOURCE"][0]
		for _, line := range kv["USE"] {
			p := strings.Fields(line)
			if len(p) == 2 {
				uses = append(uses, useLine{src, p[0], p[1]})
			}
		}
	}

	sums := map[string]string{}
	blobs := map[string]string{}
	sdb := filepath.Join(root, "sumdb")
	sdents, _ := os.ReadDir(sdb)
	sort.Slice(sdents, func(i, j int) bool { return sdents[i].Name() < sdents[j].Name() })
	for _, e := range sdents {
		if e.IsDir() {
			continue
		}
		kv := readKV(filepath.Join(sdb, e.Name()))
		mod, ver := kv["MODULE"][0], kv["VERSION"][0]
		sums[pairKey(mod, ver)] = kv["HASH"][0]
		blobs[pairKey(mod, ver)] = kv["BLOB"][0]
	}

	exSet := map[string]struct{}{}
	for _, x := range excluded {
		exSet[x] = struct{}{}
	}

	var violations []violation
	usePairs := map[string]struct{}{}

	for _, u := range uses {
		if _, ok := exSet[u.mod]; ok {
			continue
		}
		if _, ok := active[u.mod]; !ok {
			continue
		}
		usePairs[pairKey(u.mod, u.ver)] = struct{}{}
		okVer := false
		for _, v := range owned[u.mod] {
			if v == u.ver {
				okVer = true
				break
			}
		}
		if !okVer {
			violations = append(violations, violation{Code: "unknown_version", Module: u.mod, Source: u.src, Version: u.ver})
			continue
		}
		k := pairKey(u.mod, u.ver)
		if _, ok := sums[k]; !ok {
			violations = append(violations, violation{Code: "missing_sum", Module: u.mod, Source: u.src, Version: u.ver})
			continue
		}
		bpath := filepath.Join(root, "blobs", blobs[k])
		if sums[k] != fileSHA256(bpath) {
			violations = append(violations, violation{Code: "stale_sum", Module: u.mod, Source: u.src, Version: u.ver})
		}
	}

	if !lenient {
		for k := range sums {
			parts := strings.SplitN(k, "\x00", 2)
			mod, ver := parts[0], parts[1]
			if _, ok := exSet[mod]; ok {
				continue
			}
			if _, ok := usePairs[k]; !ok {
				violations = append(violations, violation{Code: "orphan_sum", Module: mod, Source: "", Version: ver})
			}
		}
	}

	graph := map[string][]string{}
	names := make([]string, 0, len(active))
	for n := range active {
		names = append(names, n)
	}
	sort.Strings(names)
	for _, n := range names {
		for _, d := range active[n].Depends {
			if _, ok := active[d]; ok {
				graph[n] = append(graph[n], d)
			}
		}
	}

	var cycles [][]string
	seen := map[string]struct{}{}
	normalize := func(cyc []string) []string {
		pivot := minString(cyc)
		i := indexOf(cyc, pivot)
		return append(cyc[i:], cyc[:i]...)
	}

	var dfs func(node string, path []string, stack map[string]bool)
	dfs = func(node string, path []string, stack map[string]bool) {
		if stack[node] {
			idx := indexOf(path, node)
			cyc := normalize(append(path[idx:], node))
			cyc = cyc[:len(cyc)-1]
			sort.Strings(cyc)
			sk := strings.Join(cyc, "\x00")
			if _, ok := seen[sk]; !ok {
				seen[sk] = struct{}{}
				cycles = append(cycles, cyc)
			}
			return
		}
		if indexOf(path, node) >= 0 {
			return
		}
		stack[node] = true
		path = append(path, node)
		for _, nxt := range graph[node] {
			dfs(nxt, path, stack)
		}
		delete(stack, node)
	}

	for _, n := range names {
		dfs(n, nil, map[string]bool{})
	}
	sort.Slice(cycles, func(i, j int) bool { return cycles[i][0] < cycles[j][0] })

	for _, cyc := range cycles {
		for i, mod := range cyc {
			violations = append(violations, violation{
				Code: "module_cycle", Module: mod, Source: "", Version: cyc[(i+1)%len(cyc)],
			})
		}
	}

	sort.Slice(violations, func(i, j int) bool {
		a, b := violations[i], violations[j]
		if a.Code != b.Code {
			return a.Code < b.Code
		}
		if a.Module != b.Module {
			return a.Module < b.Module
		}
		if a.Source != b.Source {
			return a.Source < b.Source
		}
		return a.Version < b.Version
	})

	violMods := map[string]struct{}{}
	for _, v := range violations {
		violMods[v.Module] = struct{}{}
	}

	var modules []moduleOut
	for _, name := range names {
		st := "ok"
		if _, ok := violMods[name]; ok {
			st = "violation"
		}
		modules = append(modules, moduleOut{Entries: owned[name], Module: name, Status: st})
	}

	count := func(code string) int {
		n := 0
		for _, v := range violations {
			if v.Code == code {
				n++
			}
		}
		return n
	}

	rep := reportOut{
		Cycles: cycles, Excluded: excluded, Modules: modules, Violations: violations,
		Summary: summaryOut{
			TotalActive: len(active), TotalCycles: len(cycles), TotalExcluded: len(excluded),
			TotalViolations: len(violations), TotalMissing: count("missing_sum"),
			TotalOrphan: count("orphan_sum"), TotalStale: count("stale_sum"),
			TotalModules: len(byMod), TotalUnknown: count("unknown_version"),
		},
	}
	b, err := json.Marshal(rep)
	if err != nil {
		fmt.Fprintf(os.Stderr, "json: %v\n", err)
		os.Exit(1)
	}
	os.Stdout.Write(b)
}

func minString(ss []string) string {
	m := ss[0]
	for _, s := range ss[1:] {
		if s < m {
			m = s
		}
	}
	return m
}

func indexOf(ss []string, x string) int {
	for i, s := range ss {
		if s == x {
			return i
		}
	}
	return -1
}
