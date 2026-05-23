package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type rod struct {
	RodID string `json:"rod_id"`
	A     int    `json:"a"`
	B     int    `json:"b"`
}

type cellFile struct {
	ID   string `json:"id"`
	Rods []rod  `json:"rods"`
}

type layoutCell struct {
	ID string `json:"id"`
	Lo int    `json:"lo"`
	Hi int    `json:"hi"`
}

type domainLayout struct {
	DomainEnd int          `json:"domain_end"`
	Cells     []layoutCell `json:"cells"`
}

type policy struct {
	GhostMode         string `json:"ghost_mode"`
	IncidentDayFloor  *int   `json:"incident_day_floor"`
	Clusters          []struct {
		Name    string   `json:"name"`
		CellIDs []string `json:"cell_ids"`
	} `json:"clusters"`
}

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type incidentEvent map[string]any

type incidentLog struct {
	Events []incidentEvent `json:"events"`
}

type anchorWindow struct {
	StartDay int `json:"start_day"`
}

type ghostAdditions struct {
	Additions []struct {
		CellID string `json:"cell_id"`
		Rods   []rod  `json:"rods"`
	} `json:"additions"`
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
	// Encoder always ends with \n; SPEC wants single trailing newline.
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

func sortEvents(events []incidentEvent) []incidentEvent {
	out := append([]incidentEvent(nil), events...)
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

func main() {
	dataRoot := os.Getenv("RPV_DATA_DIR")
	if dataRoot == "" {
		dataRoot = "/app/rod_lat"
	}
	auditRoot := os.Getenv("RPV_AUDIT_DIR")
	if auditRoot == "" {
		auditRoot = "/app/rod_audit"
	}

	var layout domainLayout
	mustReadJSON(filepath.Join(dataRoot, "domain_layout.json"), &layout)
	cellBounds := map[string]layoutCell{}
	for _, c := range layout.Cells {
		cellBounds[c.ID] = c
	}

	var pol policy
	mustReadJSON(filepath.Join(dataRoot, "policy.json"), &pol)

	var pool poolState
	mustReadJSON(filepath.Join(dataRoot, "pool_state.json"), &pool)

	var log incidentLog
	mustReadJSON(filepath.Join(dataRoot, "incident_log.json"), &log)

	var win anchorWindow
	mustReadJSON(filepath.Join(dataRoot, "anchors", "window.json"), &win)

	floorDay := win.StartDay
	if pol.IncidentDayFloor != nil {
		floorDay = *pol.IncidentDayFloor
	}

	// Load baseline rods per cell.
	rodsByCell := map[string][]rod{}
	for _, c := range layout.Cells {
		var cf cellFile
		mustReadJSON(filepath.Join(dataRoot, "cells", c.ID+".json"), &cf)
		cp := append([]rod(nil), cf.Rods...)
		rodsByCell[c.ID] = cp
	}

	if pol.GhostMode == "include" {
		var gh ghostAdditions
		mustReadJSON(filepath.Join(dataRoot, "ancillary", "ghost_rods.json"), &gh)
		for _, add := range gh.Additions {
			rodsByCell[add.CellID] = append(rodsByCell[add.CellID], add.Rods...)
		}
	}

	ignored := 0
	applied := []incidentEvent{}

	for _, ev := range sortEvents(log.Events) {
		kind, _ := ev["kind"].(string)
		day := 0
		if dv, ok := ev["day"].(float64); ok {
			day = int(dv)
		}
		eid, eidOK := ev["event_id"].(string)
		cid, cidOK := ev["cell_id"].(string)

		eligible := false
		switch kind {
		case "strip_rods":
			rids, ok := ev["rod_ids"].([]any)
			if !ok || len(rids) == 0 {
				break
			}
			if !eidOK || !cidOK {
				break
			}
			if _, ok := cellBounds[cid]; !ok {
				break
			}
			if floorDay <= day && day <= pool.CurrentDay {
				eligible = true
			}
		case "nudge_rods":
			if !eidOK || !cidOK {
				break
			}
			if _, ok := cellBounds[cid]; !ok {
				break
			}
			if _, ok := ev["delta"].(float64); !ok {
				break
			}
			if floorDay <= day && day <= pool.CurrentDay {
				eligible = true
			}
		default:
			// ignore
		}

		if !eligible {
			ignored++
			continue
		}

		switch kind {
		case "strip_rods":
			ridsAny := ev["rod_ids"].([]any)
			rm := map[string]struct{}{}
			for _, x := range ridsAny {
				rm[x.(string)] = struct{}{}
			}
			cur := rodsByCell[cid]
			nw := make([]rod, 0, len(cur))
			for _, r := range cur {
				if _, hit := rm[r.RodID]; !hit {
					nw = append(nw, r)
				}
			}
			rodsByCell[cid] = nw
		case "nudge_rods":
			delta := int(ev["delta"].(float64))
			bc := cellBounds[cid]
			cur := rodsByCell[cid]
			nw := make([]rod, 0, len(cur))
			for _, r := range cur {
				a2 := r.A + delta
				b2 := r.B + delta
				if a2 < bc.Lo {
					sh := bc.Lo - a2
					a2 += sh
					b2 += sh
				}
				if b2 > bc.Hi {
					sh := b2 - bc.Hi
					a2 -= sh
					b2 -= sh
				}
				if a2 < bc.Lo || b2 > bc.Hi || a2 >= b2 {
					continue
				}
				nw = append(nw, rod{RodID: r.RodID, A: a2, B: b2})
			}
			rodsByCell[cid] = nw
		}

		applied = append(applied, incidentEvent{
			"day":      day,
			"delta":    ev["delta"],
			"event_id": eid,
			"kind":     kind,
			"rod_ids":  ev["rod_ids"],
			"cell_id":  cid,
		})
	}

	// Normalize applied entries: omit nil fields for cleaner canonical? tests hash full file.
	// Clean applied maps: remove null keys
	cleanApplied := make([]any, 0, len(applied))
	for _, ev := range applied {
		m := map[string]any{}
		keys := []string{"cell_id", "day", "delta", "event_id", "kind", "rod_ids"}
		for _, k := range keys {
			if v, ok := ev[k]; ok && v != nil {
				m[k] = v
			}
		}
		cleanApplied = append(cleanApplied, m)
	}

	// cluster voids
	type seg struct {
		a, b int
	}
	unionLen := func(segs []seg) int64 {
		if len(segs) == 0 {
			return 0
		}
		sort.Slice(segs, func(i, j int) bool {
			if segs[i].a != segs[j].a {
				return segs[i].a < segs[j].a
			}
			return segs[i].b < segs[j].b
		})
		curA, curB := segs[0].a, segs[0].b
		var total int64
		for _, s := range segs[1:] {
			if s.a <= curB {
				if s.b > curB {
					curB = s.b
				}
			} else {
				total += int64(curB - curA)
				curA, curB = s.a, s.b
			}
		}
		total += int64(curB - curA)
		return total
	}

	clustersOut := []any{}
	var sumWeighted int64
	var sumSpan int64

	for _, cl := range pol.Clusters {
		spanLo := int(^uint(0) >> 1)
		spanHi := 0
		for _, id := range cl.CellIDs {
			bc := cellBounds[id]
			if bc.Lo < spanLo {
				spanLo = bc.Lo
			}
			if bc.Hi > spanHi {
				spanHi = bc.Hi
			}
		}
		spanLen := spanHi - spanLo
		segs := []seg{}
		segCount := 0
		for _, id := range cl.CellIDs {
			for _, r := range rodsByCell[id] {
				sa := r.A
				if sa < spanLo {
					sa = spanLo
				}
				sb := r.B
				if sb > spanHi {
					sb = spanHi
				}
				if sa < sb {
					segs = append(segs, seg{sa, sb})
					segCount++
				}
			}
		}
		occ := unionLen(segs)
		voidPpm := 0
		if spanLen > 0 {
			rem := spanLen - int(occ)
			if rem < 0 {
				rem = 0
			}
			voidPpm = int((int64(rem) * 1_000_000) / int64(spanLen))
		}
		sumWeighted += int64(voidPpm * spanLen)
		sumSpan += int64(spanLen)

		clustersOut = append(clustersOut, map[string]any{
			"name":           cl.Name,
			"occupied_len":   int(occ),
			"segments_used":  segCount,
			"span_hi":        spanHi,
			"span_len":       spanLen,
			"span_lo":        spanLo,
			"void_ppm":       voidPpm,
		})
	}

	weighted := 0
	if sumSpan > 0 {
		weighted = int(sumWeighted / sumSpan)
	}

	// cell snapshots sorted by cell_id ascending
	cellIDs := make([]string, 0, len(layout.Cells))
	for _, lc := range layout.Cells {
		cellIDs = append(cellIDs, lc.ID)
	}
	sort.Strings(cellIDs)
	cellsOut := []any{}
	for _, id := range cellIDs {
		lc := cellBounds[id]
		rs := rodsByCell[id]
		sort.Slice(rs, func(i, j int) bool { return rs[i].RodID < rs[j].RodID })
		rodsAny := make([]any, 0, len(rs))
		for _, r := range rs {
			rodsAny = append(rodsAny, map[string]any{"a": r.A, "b": r.B, "rod_id": r.RodID})
		}
		cellsOut = append(cellsOut, map[string]any{
			"cell_id": id,
			"hi":      lc.Hi,
			"lo":      lc.Lo,
			"rods":    rodsAny,
		})
	}

	clusterPayload := map[string]any{"clusters": clustersOut}
	cellPayload := map[string]any{"cells": cellsOut}
	trailPayload := map[string]any{
		"applied": cleanApplied,
		"ignored": ignored,
	}
	summaryPayload := map[string]any{
		"applied_incidents":     len(applied),
		"clusters":              len(pol.Clusters),
		"ghost_mode_used":       pol.GhostMode,
		"ignored_incidents":     ignored,
		"weighted_void_ppm":     weighted,
	}

	writeFile(filepath.Join(auditRoot, "cluster_voids.json"), canonicalMarshal(clusterPayload))
	writeFile(filepath.Join(auditRoot, "cell_snapshots.json"), canonicalMarshal(cellPayload))
	writeFile(filepath.Join(auditRoot, "incident_trail.json"), canonicalMarshal(trailPayload))
	writeFile(filepath.Join(auditRoot, "summary.json"), canonicalMarshal(summaryPayload))

	fmt.Fprintln(os.Stderr, "rod-pack-void-audit wrote", auditRoot)
}
