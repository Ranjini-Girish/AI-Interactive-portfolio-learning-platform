package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type domainLayout struct {
	Nodes []string `json:"nodes"`
}

type policy struct {
	IncidentDayFloor *int `json:"incident_day_floor"`
}

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type incidentLog struct {
	Events []map[string]any `json:"events"`
}

type edgeFile struct {
	EdgeID string `json:"edge_id"`
	U      string `json:"u"`
	V      string `json:"v"`
	W      int    `json:"w"`
}

type pickedEdge struct {
	EdgeID string `json:"edge_id"`
	U      string `json:"u"`
	V      string `json:"v"`
	W      int    `json:"w"`
}

type eligibleOut struct {
	EdgeIDs []string `json:"edge_ids"`
}

type incidentTrail struct {
	Applied []map[string]any `json:"applied"`
	Ignored int              `json:"ignored"`
}

type summaryOut struct {
	AppliedIncidents       int `json:"applied_incidents"`
	ComponentCount         int `json:"component_count"`
	CompromisedNodeCount   int `json:"compromised_node_count"`
	CurrentDayUsed         int `json:"current_day_used"`
	EligibleEdgeCount      int `json:"eligible_edge_count"`
	FrozenEdgeCount        int `json:"frozen_edge_count"`
	IgnoredIncidents       int `json:"ignored_incidents"`
	IncidentDayFloorUsed  int `json:"incident_day_floor_used"`
	PickedEdgeCount        int `json:"picked_edge_count"`
	TotalWeight            int `json:"total_weight"`
	WeightFloorFinal       int `json:"weight_floor_final"`
}

type mstPickOut struct {
	Edges []pickedEdge `json:"edges"`
}

func mustReadJSON(path string, out any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, out); err != nil {
		panic(err)
	}
}

func canonicalMarshal(v any) []byte {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		panic(err)
	}
	out := buf.Bytes()
	for len(out) > 0 && out[len(out)-1] == '\n' {
		out = out[:len(out)-1]
	}
	out = append(out, '\n')
	return out
}

func writeFile(path string, data []byte) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		panic(err)
	}
	if err := os.WriteFile(path, data, 0o644); err != nil {
		panic(err)
	}
}

func sortKeysDeep(v any) any {
	switch t := v.(type) {
	case map[string]any:
		keys := make([]string, 0, len(t))
		for k := range t {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		out := map[string]any{}
		for _, k := range keys {
			out[k] = sortKeysDeep(t[k])
		}
		return out
	case []any:
		out := make([]any, len(t))
		for i, x := range t {
			out[i] = sortKeysDeep(x)
		}
		return out
	default:
		return v
	}
}

func sortEvents(events []map[string]any) []map[string]any {
	out := append([]map[string]any(nil), events...)
	sort.SliceStable(out, func(i, j int) bool {
		di := int(out[i]["day"].(float64))
		dj := int(out[j]["day"].(float64))
		if di != dj {
			return di < dj
		}
		ei := out[i]["event_id"].(string)
		ej := out[j]["event_id"].(string)
		return ei < ej
	})
	return out
}

type uf struct {
	parent map[string]string
	rank   map[string]int
}

func newUF(nodes []string) *uf {
	u := &uf{parent: map[string]string{}, rank: map[string]int{}}
	for _, n := range nodes {
		u.parent[n] = n
		u.rank[n] = 0
	}
	return u
}

func (u *uf) find(x string) string {
	if u.parent[x] != x {
		u.parent[x] = u.find(u.parent[x])
	}
	return u.parent[x]
}

func (u *uf) union(a, b string) bool {
	ra, rb := u.find(a), u.find(b)
	if ra == rb {
		return false
	}
	if u.rank[ra] < u.rank[rb] {
		ra, rb = rb, ra
	}
	u.parent[rb] = ra
	if u.rank[ra] == u.rank[rb] {
		u.rank[ra]++
	}
	return true
}

func (u *uf) components() int {
	roots := map[string]struct{}{}
	for k := range u.parent {
		roots[u.find(k)] = struct{}{}
	}
	return len(roots)
}

func main() {
	dataRoot := os.Getenv("SFM_DATA_DIR")
	if dataRoot == "" {
		dataRoot = "/app/sfm_lab"
	}
	auditRoot := os.Getenv("SFM_AUDIT_DIR")
	if auditRoot == "" {
		auditRoot = "/app/sfm_audit"
	}

	var layout domainLayout
	mustReadJSON(filepath.Join(dataRoot, "domain_layout.json"), &layout)
	nodeSet := map[string]struct{}{}
	for _, n := range layout.Nodes {
		nodeSet[n] = struct{}{}
	}

	var pol policy
	mustReadJSON(filepath.Join(dataRoot, "policy.json"), &pol)

	var pool poolState
	mustReadJSON(filepath.Join(dataRoot, "pool_state.json"), &pool)

	var dayFloor struct {
		StartDay int `json:"start_day"`
	}
	mustReadJSON(filepath.Join(dataRoot, "anchors", "day_floor.json"), &dayFloor)

	floorDay := dayFloor.StartDay
	if pol.IncidentDayFloor != nil {
		floorDay = max(floorDay, *pol.IncidentDayFloor)
	}

	edgeDir := filepath.Join(dataRoot, "edges")
	entries, err := os.ReadDir(edgeDir)
	if err != nil {
		panic(err)
	}
	allEdges := []edgeFile{}
	edgeIDs := map[string]edgeFile{}
	for _, ent := range entries {
		if ent.IsDir() || filepath.Ext(ent.Name()) != ".json" {
			continue
		}
		var ef edgeFile
		mustReadJSON(filepath.Join(edgeDir, ent.Name()), &ef)
		allEdges = append(allEdges, ef)
		edgeIDs[ef.EdgeID] = ef
	}
	sort.SliceStable(allEdges, func(i, j int) bool {
		if allEdges[i].W != allEdges[j].W {
			return allEdges[i].W < allEdges[j].W
		}
		return allEdges[i].EdgeID < allEdges[j].EdgeID
	})

	var log incidentLog
	mustReadJSON(filepath.Join(dataRoot, "incident_log.json"), &log)

	weightFloor := 0
	frozen := map[string]struct{}{}
	compromised := map[string]struct{}{}
	applied := []map[string]any{}
	ignored := 0

	for _, ev := range sortEvents(log.Events) {
		kind, _ := ev["kind"].(string)
		_, eidOK := ev["event_id"].(string)
		dayF, dayOK := ev["day"].(float64)
		day := int(dayF)
		if !eidOK || !dayOK || kind == "" {
			ignored++
			continue
		}
		if day < floorDay || day > pool.CurrentDay {
			ignored++
			continue
		}
		switch kind {
		case "raise_weight_floor":
			fl, ok := ev["floor"].(float64)
			if !ok {
				ignored++
				continue
			}
			v := int(fl)
			if v > weightFloor {
				weightFloor = v
			}
			if sm, ok := sortKeysDeep(ev).(map[string]any); ok {
				applied = append(applied, sm)
			}
		case "freeze_edge":
			eEdge, ok := ev["edge_id"].(string)
			if !ok {
				ignored++
				continue
			}
			if _, ok := edgeIDs[eEdge]; !ok {
				ignored++
				continue
			}
			frozen[eEdge] = struct{}{}
			if sm, ok := sortKeysDeep(ev).(map[string]any); ok {
				applied = append(applied, sm)
			}
		case "compromise_node":
			nid, ok := ev["node_id"].(string)
			if !ok {
				ignored++
				continue
			}
			if _, ok := nodeSet[nid]; !ok {
				ignored++
				continue
			}
			compromised[nid] = struct{}{}
			if sm, ok := sortKeysDeep(ev).(map[string]any); ok {
				applied = append(applied, sm)
			}
		default:
			ignored++
		}
	}

	eligible := []edgeFile{}
	for _, e := range allEdges {
		if e.W < weightFloor {
			continue
		}
		if _, ok := frozen[e.EdgeID]; ok {
			continue
		}
		if _, ok := compromised[e.U]; ok {
			continue
		}
		if _, ok := compromised[e.V]; ok {
			continue
		}
		eligible = append(eligible, e)
	}
	sort.SliceStable(eligible, func(i, j int) bool {
		if eligible[i].W != eligible[j].W {
			return eligible[i].W < eligible[j].W
		}
		return eligible[i].EdgeID < eligible[j].EdgeID
	})

	eligibleIDs := make([]string, 0, len(eligible))
	for _, e := range eligible {
		eligibleIDs = append(eligibleIDs, e.EdgeID)
	}
	sort.Strings(eligibleIDs)

	u := newUF(layout.Nodes)
	picked := []edgeFile{}
	total := 0
	for _, e := range eligible {
		if u.union(e.U, e.V) {
			picked = append(picked, e)
			total += e.W
		}
	}
	sort.SliceStable(picked, func(i, j int) bool {
		if picked[i].W != picked[j].W {
			return picked[i].W < picked[j].W
		}
		return picked[i].EdgeID < picked[j].EdgeID
	})

	pickedRows := make([]pickedEdge, 0, len(picked))
	for _, e := range picked {
		pickedRows = append(pickedRows, pickedEdge{EdgeID: e.EdgeID, U: e.U, V: e.V, W: e.W})
	}

	mstPick := mstPickOut{Edges: pickedRows}
	eligibleDoc := eligibleOut{EdgeIDs: eligibleIDs}
	trail := incidentTrail{Applied: applied, Ignored: ignored}
	summary := summaryOut{
		AppliedIncidents:      len(applied),
		ComponentCount:        u.components(),
		CompromisedNodeCount:  len(compromised),
		CurrentDayUsed:        pool.CurrentDay,
		EligibleEdgeCount:     len(eligible),
		FrozenEdgeCount:       len(frozen),
		IgnoredIncidents:      ignored,
		IncidentDayFloorUsed:   floorDay,
		PickedEdgeCount:       len(picked),
		TotalWeight:           total,
		WeightFloorFinal:      weightFloor,
	}

	writeFile(filepath.Join(auditRoot, "mst_pick.json"), canonicalMarshal(mstPick))
	writeFile(filepath.Join(auditRoot, "eligible_edges.json"), canonicalMarshal(eligibleDoc))
	writeFile(filepath.Join(auditRoot, "incident_trail.json"), canonicalMarshal(trail))
	writeFile(filepath.Join(auditRoot, "summary.json"), canonicalMarshal(summary))

	fmt.Fprintln(os.Stderr, "span-floor-mst audit complete")
}
