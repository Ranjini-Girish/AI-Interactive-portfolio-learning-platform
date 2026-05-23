#!/bin/bash
set -euo pipefail

SRC_DIR="${MLA_SRC_DIR:-/app/src}"
BIN_DIR="${MLA_BIN_DIR:-/app/bin}"
REPORT_DIR="${MLA_AUDIT_DIR:-/app/audit}"
MODGRAPH_DIR="${MLA_MODGRAPH_DIR:-/app/modgraph}"

mkdir -p "$SRC_DIR" "$BIN_DIR" "$REPORT_DIR"

cat > "$SRC_DIR/go.mod" <<'GOMOD'
module lattice

go 1.23
GOMOD

cat > "$SRC_DIR/main.go" <<'GOEOF'
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

type replaceEntry struct {
	From    string           `json:"from"`
	To      string           `json:"to"`
	Expires *json.RawMessage `json:"expires_on_day"`
}

type moduleFile struct {
	ModuleID   string         `json:"module_id"`
	ModulePath string         `json:"module_path"`
	Replaces   []replaceEntry `json:"replaces"`
	Requires   []string       `json:"requires"`
	Manifest   string         `json:"-"`
}

func getEnv(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func readJSON(path string, out interface{}) {
	b, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read %s: %v\n", path, err)
		os.Exit(1)
	}
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.UseNumber()
	if err := dec.Decode(out); err != nil {
		fmt.Fprintf(os.Stderr, "parse %s: %v\n", path, err)
		os.Exit(1)
	}
}

func writeJSON(path string, v interface{}) {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "marshal: %v\n", err)
		os.Exit(1)
	}
	data = append(data, '\n')
	if err := os.WriteFile(path, data, 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "write %s: %v\n", path, err)
		os.Exit(1)
	}
}

func asInt(n json.Number) (int, bool) {
	i, err := n.Int64()
	if err != nil {
		return 0, false
	}
	return int(i), true
}

func replaceExpired(exp *json.RawMessage, asOf int) bool {
	if exp == nil {
		return false
	}
	var n json.Number
	if err := json.Unmarshal(*exp, &n); err != nil {
		return false
	}
	ed, ok := asInt(n)
	if !ok {
		return false
	}
	return asOf > ed
}

func stripHit(from string, prefixes []string) bool {
	for _, p := range prefixes {
		if strings.HasPrefix(from, p) {
			return true
		}
	}
	return false
}

func resolveWalk(m map[string]string, start string) string {
	cur := start
	stack := []string{}
	for step := 0; step < 1024; step++ {
		nxt, ok := m[cur]
		if !ok {
			return cur
		}
		if nxt == cur {
			return "__self_loop__"
		}
		for _, v := range stack {
			if v == nxt {
				return "__cycle__"
			}
		}
		stack = append(stack, cur)
		cur = nxt
	}
	return "__cycle__"
}

type edge struct{ from, to string }

func tarjan(vertices []string, adj map[string][]string) [][]string {
	index := 0
	stack := []string{}
	onStack := map[string]bool{}
	indices := map[string]int{}
	lowlink := map[string]int{}
	sccs := [][]string{}

	var strongConnect func(v string)
	strongConnect = func(v string) {
		indices[v] = index
		lowlink[v] = index
		index++
		stack = append(stack, v)
		onStack[v] = true
		for _, w := range adj[v] {
			if _, ok := indices[w]; !ok {
				strongConnect(w)
				if lowlink[w] < lowlink[v] {
					lowlink[v] = lowlink[w]
				}
			} else if onStack[w] {
				if indices[w] < lowlink[v] {
					lowlink[v] = indices[w]
				}
			}
		}
		if lowlink[v] == indices[v] {
			comp := []string{}
			for {
				w := stack[len(stack)-1]
				stack = stack[:len(stack)-1]
				onStack[w] = false
				comp = append(comp, w)
				if w == v {
					break
				}
			}
			sort.Strings(comp)
			sccs = append(sccs, comp)
		}
	}
	for _, v := range vertices {
		if _, ok := indices[v]; !ok {
			strongConnect(v)
		}
	}
	return sccs
}

func main() {
	root := getEnv("MLA_MODGRAPH_DIR", "/app/modgraph")
	outDir := getEnv("MLA_AUDIT_DIR", "/app/audit")

	var pool struct {
		AsOfDay                 int      `json:"as_of_day"`
		GlobalRevokePrefixes    []string `json:"global_revoke_prefixes"`
		LocalStripAfterManifest string   `json:"local_strip_after_manifest"`
	}
	readJSON(filepath.Join(root, "pool_state.json"), &pool)
	asOf := pool.AsOfDay

	var pol struct {
		Prefixes []string `json:"prefixes"`
	}
	readJSON(filepath.Join(root, "policy", "strip_prefixes.json"), &pol)

	var localPol struct {
		Prefixes []string `json:"prefixes"`
	}
	readJSON(filepath.Join(root, "policy", "local_strip_prefixes.json"), &localPol)

	var scan struct {
		Manifests []string `json:"module_manifests"`
	}
	readJSON(filepath.Join(root, "workspace", "scan_order.json"), &scan)

	var expiredDrops int
	var stripHits int
	var localStripSkipped int

	anchor := strings.TrimSpace(pool.LocalStripAfterManifest)
	anchorIdx := len(scan.Manifests)
	if anchor != "" {
		found := false
		for i, m := range scan.Manifests {
			if m == anchor {
				anchorIdx = i
				found = true
				break
			}
		}
		if !found {
			anchorIdx = len(scan.Manifests)
		}
	}

	type gEnt struct {
		To           string
		WonManifest  string
	}
	G := map[string]gEnt{}

	unionEdges := []edge{}

	for mi, rel := range scan.Manifests {
		full := filepath.Join(root, filepath.FromSlash(rel))
		var mf moduleFile
		readJSON(full, &mf)
		mf.Manifest = rel
		for _, r := range mf.Replaces {
			if replaceExpired(r.Expires, asOf) {
				expiredDrops++
				continue
			}
			unionEdges = append(unionEdges, edge{r.From, r.To})
			if stripHit(r.From, pol.Prefixes) {
				stripHits++
				continue
			}
			if mi > anchorIdx && stripHit(r.From, localPol.Prefixes) && !stripHit(r.From, pol.Prefixes) {
				localStripSkipped++
				continue
			}
			G[r.From] = gEnt{To: r.To, WonManifest: rel}
		}
	}

	gKeys := make([]string, 0, len(G))
	for k := range G {
		gKeys = append(gKeys, k)
	}
	globalRevokeDrops := 0
	for _, k := range gKeys {
		drop := false
		for _, pfx := range pool.GlobalRevokePrefixes {
			if pfx != "" && strings.HasPrefix(k, pfx) {
				drop = true
				break
			}
		}
		if drop {
			delete(G, k)
			globalRevokeDrops++
		}
	}

	// reload modules for E maps and requires
	var modules []moduleFile
	manifestIdx := map[string]int{}
	for mi, rel := range scan.Manifests {
		full := filepath.Join(root, filepath.FromSlash(rel))
		var mf moduleFile
		readJSON(full, &mf)
		mf.Manifest = rel
		modules = append(modules, mf)
		manifestIdx[mf.ModuleID] = mi
	}

	gTo := map[string]string{}
	for k, v := range G {
		gTo[k] = v.To
	}

	byID := map[string]moduleFile{}
	for _, m := range modules {
		byID[m.ModuleID] = m
	}

	ids := make([]string, 0, len(byID))
	for id := range byID {
		ids = append(ids, id)
	}
	sort.Strings(ids)

	E := map[string]map[string]string{}
	for _, id := range ids {
		mf := byID[id]
		mi := manifestIdx[id]
		em := map[string]string{}
		for k, v := range gTo {
			em[k] = v
		}
		for _, r := range mf.Replaces {
			if replaceExpired(r.Expires, asOf) {
				continue
			}
			if mi > anchorIdx && stripHit(r.From, localPol.Prefixes) && !stripHit(r.From, pol.Prefixes) {
				continue
			}
			em[r.From] = r.To
		}
		E[id] = em
	}

	resolution := map[string]interface{}{}
	usedLocalTrueRows := 0
	modulesWithUsedLocal := map[string]bool{}
	for _, id := range ids {
		mf := byID[id]
		em := E[id]
		rows := make([]map[string]interface{}, 0)
		for _, req := range mf.Requires {
			fullR := resolveWalk(em, req)
			gOnly := resolveWalk(gTo, req)
			usedLocal := fullR != gOnly
			if usedLocal {
				usedLocalTrueRows++
				modulesWithUsedLocal[id] = true
			}
			rows = append(rows, map[string]interface{}{
				"require":    req,
				"resolved":   fullR,
				"used_local": usedLocal,
			})
		}
		sort.Slice(rows, func(i, j int) bool {
			ri := rows[i]["require"].(string)
			rj := rows[j]["require"].(string)
			if ri != rj {
				return ri < rj
			}
			si := rows[i]["resolved"].(string)
			sj := rows[j]["resolved"].(string)
			if si != sj {
				return si < sj
			}
			bi := rows[i]["used_local"].(bool)
			bj := rows[j]["used_local"].(bool)
			if bi != bj {
				return !bi && bj
			}
			return false
		})
		resolution[id] = rows
	}
	resOut := map[string]interface{}{"by_module": resolution}

	pairs := make([]map[string]string, 0)
	for i := 0; i < len(ids); i++ {
		for j := i + 1; j < len(ids); j++ {
			a, b := ids[i], ids[j]
			ma, mb := byID[a], byID[b]
			reqSet := map[string]bool{}
			for _, r := range ma.Requires {
				reqSet[r] = true
			}
			common := []string{}
			for _, r := range mb.Requires {
				if reqSet[r] {
					common = append(common, r)
				}
			}
			sort.Strings(common)
			for _, r := range common {
				ra := resolveWalk(E[a], r)
				rb := resolveWalk(E[b], r)
				if ra != rb {
					pairs = append(pairs, map[string]string{
						"module_a":     a,
						"module_b":     b,
						"require_path": r,
						"resolved_a":   ra,
						"resolved_b":   rb,
					})
				}
			}
		}
	}
	sort.Slice(pairs, func(i, j int) bool {
		pi, pj := pairs[i], pairs[j]
		if pi["module_a"] != pj["module_a"] {
			return pi["module_a"] < pj["module_a"]
		}
		if pi["module_b"] != pj["module_b"] {
			return pi["module_b"] < pj["module_b"]
		}
		return pi["require_path"] < pj["require_path"]
	})

	skewDistinctRequirePaths := map[string]bool{}
	for _, p := range pairs {
		skewDistinctRequirePaths[p["require_path"]] = true
	}

	// SCC on union edge set (unique from->to)
	edgeSeen := map[string]bool{}
	adj := map[string][]string{}
	verts := map[string]bool{}
	for _, e := range unionEdges {
		key := e.from + "\x00" + e.to
		if edgeSeen[key] {
			continue
		}
		edgeSeen[key] = true
		verts[e.from] = true
		verts[e.to] = true
		adj[e.from] = append(adj[e.from], e.to)
	}
	for v := range adj {
		sort.Strings(adj[v])
	}
	vlist := make([]string, 0, len(verts))
	for v := range verts {
		vlist = append(vlist, v)
	}
	sort.Strings(vlist)

	unionReplaceEdgeCount := len(edgeSeen)
	unionVertexCount := len(verts)

	rawSCC := tarjan(vlist, adj)

	selfLoop := map[string]bool{}
	for _, e := range unionEdges {
		if e.from == e.to {
			selfLoop[e.from] = true
		}
	}

	components := make([][]string, 0)
	for _, comp := range rawSCC {
		if len(comp) > 1 {
			components = append(components, comp)
			continue
		}
		if len(comp) == 1 && selfLoop[comp[0]] {
			components = append(components, comp)
		}
	}
	sort.Slice(components, func(i, j int) bool {
		ci, cj := components[i], components[j]
		for k := 0; k < len(ci) && k < len(cj); k++ {
			if ci[k] != cj[k] {
				return ci[k] < cj[k]
			}
		}
		return len(ci) < len(cj)
	})

	finalObj := map[string]interface{}{}
	finalKeys := make([]string, 0, len(G))
	for k := range G {
		finalKeys = append(finalKeys, k)
	}
	sort.Strings(finalKeys)
	finalInner := map[string]interface{}{}
	for _, k := range finalKeys {
		ent := G[k]
		finalInner[k] = map[string]interface{}{
			"to":            ent.To,
			"won_manifest": ent.WonManifest,
		}
	}
	finalObj["final"] = finalInner

	modulesWithUsedLocalCount := len(modulesWithUsedLocal)

	summary := map[string]interface{}{
		"cycle_component_count":         len(components),
		"expired_replace_drops":         expiredDrops,
		"global_replace_keys":           len(G),
		"global_revoke_drops":           globalRevokeDrops,
		"local_strip_skipped_entries":   localStripSkipped,
		"module_manifests_read":         len(scan.Manifests),
		"modules_with_used_local":       modulesWithUsedLocalCount,
		"skew_distinct_require_paths":   len(skewDistinctRequirePaths),
		"skew_pair_count":               len(pairs),
		"strip_excluded_entries":        stripHits,
		"union_replace_edge_count":      unionReplaceEdgeCount,
		"union_vertex_count":            unionVertexCount,
		"used_local_true_rows":          usedLocalTrueRows,
	}

	writeJSON(filepath.Join(outDir, "global_replace.json"), finalObj)
	writeJSON(filepath.Join(outDir, "resolution.json"), resOut)
	writeJSON(filepath.Join(outDir, "skew_pairs.json"), map[string]interface{}{"pairs": pairs})
	writeJSON(filepath.Join(outDir, "cycle_report.json"), map[string]interface{}{
		"components": components,
		"has_cycle":  len(components) > 0,
	})
	writeJSON(filepath.Join(outDir, "summary.json"), summary)
}
GOEOF

cd "$SRC_DIR"
go build -trimpath -o "$BIN_DIR/lattice-auditor" .

MLA_MODGRAPH_DIR="${MLA_MODGRAPH_DIR:-$MODGRAPH_DIR}" \
MLA_AUDIT_DIR="$REPORT_DIR" \
"$BIN_DIR/lattice-auditor"
