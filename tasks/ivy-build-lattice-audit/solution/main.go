package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type policy struct {
	GraphLabel string `json:"graph_label"`
	TieBreak   string `json:"tie_break"`
}

type module struct {
	BuildCost int      `json:"build_cost"`
	ModuleID  string   `json:"module_id"`
	Prereqs   []string `json:"prereqs"`
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	data := getenv("IBL_DATA_DIR", "/app/ivybuild")
	outd := getenv("IBL_AUDIT_DIR", "/app/audit")
	if err := run(data, outd); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func run(dataDir, auditDir string) error {
	polRaw, err := os.ReadFile(filepath.Join(dataDir, "policy.json"))
	if err != nil {
		return err
	}
	var pol policy
	if err := json.Unmarshal(polRaw, &pol); err != nil {
		return err
	}

	mods, err := loadModules(filepath.Join(dataDir, "modules"))
	if err != nil {
		return err
	}
	sort.Slice(mods, func(i, j int) bool { return mods[i].ModuleID < mods[j].ModuleID })
	for i := range mods {
		sort.Strings(mods[i].Prereqs)
	}

	idx := map[string]int{}
	for i, m := range mods {
		idx[m.ModuleID] = i
	}

	n := len(mods)
	adj := make([][]int, n)
	indeg := make([]int, n)
	for i, m := range mods {
		for _, p := range m.Prereqs {
			j, ok := idx[p]
			if !ok {
				return fmt.Errorf("unknown prereq %s for %s", p, m.ModuleID)
			}
			adj[j] = append(adj[j], i)
			indeg[i]++
		}
	}

	cycleMembers := tarjanMulti(n, adj, mods)
	sort.Strings(cycleMembers)
	linearizable := len(cycleMembers) == 0

	indegWork := append([]int(nil), indeg...)
	var order []string
	if linearizable {
		q := make([]int, 0)
		for i := 0; i < n; i++ {
			if indegWork[i] == 0 {
				q = append(q, i)
			}
		}
		sort.Ints(q)
		for len(q) > 0 {
			u := q[0]
			q = q[1:]
			order = append(order, mods[u].ModuleID)
			nbrs := append([]int(nil), adj[u]...)
			sort.Ints(nbrs)
			for _, v := range nbrs {
				indegWork[v]--
				if indegWork[v] == 0 {
					q = append(q, v)
					sort.Ints(q)
				}
			}
		}
		if len(order) != n {
			return fmt.Errorf("kahn failed")
		}
	}

	weights := map[string]int{}
	if linearizable {
		best := make([]int, n)
		for _, id := range order {
			i := idx[id]
			m := mods[i]
			cand := m.BuildCost
			for _, p := range m.Prereqs {
				pi := idx[p]
				if v := best[pi] + m.BuildCost; v > cand {
					cand = v
				}
			}
			best[i] = cand
			weights[m.ModuleID] = cand
		}
	}

	catalog := make([]map[string]any, 0, len(mods))
	for _, m := range mods {
		pr := append([]string{}, m.Prereqs...)
		sort.Strings(pr)
		catalog = append(catalog, map[string]any{
			"build_cost": m.BuildCost,
			"module_id":  m.ModuleID,
			"prereqs":    pr,
		})
	}

	summary := map[string]any{
		"cycle_member_count": len(cycleMembers),
		"graph_label":        pol.GraphLabel,
		"linearizable":       linearizable,
		"modules_total":      len(mods),
	}

	var lo any = order
	if !linearizable {
		lo = nil
	}

	payloads := map[string]any{
		"cycle_members.json": map[string]any{
			"members": cycleMembers,
		},
		"linear_order.json": map[string]any{
			"linear_order": lo,
		},
		"module_catalog.json": map[string]any{
			"modules": catalog,
		},
		"path_weights.json": map[string]any{
			"weights": weights,
		},
		"summary.json": summary,
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	for name, payload := range payloads {
		if err := writeJSON(filepath.Join(auditDir, name), payload); err != nil {
			return err
		}
	}
	_ = pol.TieBreak
	return nil
}

func tarjanMulti(n int, adj [][]int, mods []module) []string {
	index := 0
	indices := make([]int, n)
	low := make([]int, n)
	for i := range indices {
		indices[i] = -1
	}
	on := make([]bool, n)
	stack := make([]int, 0)
	out := map[string]struct{}{}

	var strong func(int)
	strong = func(v int) {
		indices[v] = index
		low[v] = index
		index++
		stack = append(stack, v)
		on[v] = true
		for _, w := range adj[v] {
			if indices[w] == -1 {
				strong(w)
				if low[w] < low[v] {
					low[v] = low[w]
				}
			} else if on[w] && indices[w] < low[v] {
				low[v] = indices[w]
			}
		}
		if low[v] == indices[v] {
			comp := make([]int, 0)
			for {
				w := stack[len(stack)-1]
				stack = stack[:len(stack)-1]
				on[w] = false
				comp = append(comp, w)
				if w == v {
					break
				}
			}
			if len(comp) > 1 {
				for _, id := range comp {
					out[mods[id].ModuleID] = struct{}{}
				}
			}
		}
	}

	for v := 0; v < n; v++ {
		if indices[v] == -1 {
			strong(v)
		}
	}
	res := make([]string, 0, len(out))
	for id := range out {
		res = append(res, id)
	}
	return res
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

func loadModules(dir string) ([]module, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make([]module, 0)
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var m module
		if err := json.Unmarshal(b, &m); err != nil {
			return nil, err
		}
		if m.Prereqs == nil {
			m.Prereqs = []string{}
		}
		out = append(out, m)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no modules")
	}
	return out, nil
}
