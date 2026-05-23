#!/bin/bash
set -euo pipefail

export PATH="/usr/local/go/bin:${PATH}"

SRC_DIR="${PET_SRC_DIR:-/app/src}"
BIN_DIR="${PET_BIN_DIR:-/app/bin}"
AUDIT_DIR="${PET_AUDIT_DIR:-/app/audit}"

mkdir -p "$SRC_DIR" "$BIN_DIR" "$AUDIT_DIR"
rm -f "$AUDIT_DIR"/*.json

cat > "$SRC_DIR/go.mod" <<'GOMOD'
module petaudit

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
	"strconv"
)

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func readJSON(path string, out any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, out); err != nil {
		panic(err)
	}
}

func writeCanon(path string, obj any) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(obj); err != nil {
		panic(err)
	}
	b := buf.Bytes()
	if len(b) > 0 && b[len(b)-1] != '\n' {
		b = append(b, '\n')
	}
	if err := os.WriteFile(path, b, 0o644); err != nil {
		panic(err)
	}
}

func abs(x int) int {
	if x < 0 {
		return -x
	}
	return x
}

type Manifest struct {
	RaceFiles  []string `json:"race_files"`
	TempoFiles []string `json:"tempo_files"`
	GridFiles  []string `json:"grid_files"`
}

type PoolState struct {
	AuditEpoch string `json:"audit_epoch"`
}

type Caps struct {
	DefaultUnderpromotionCap int            `json:"default_underpromotion_cap"`
	RankOverrides            map[string]int `json:"rank_overrides"`
	IllegalComboMultiplier   int            `json:"illegal_combo_multiplier"`
}

type TieTable struct {
	TiebreakTable map[string]map[string]string `json:"tiebreak_table"`
}

type TempoPolicy struct {
	WindowSize        int   `json:"window_size"`
	ExposedRemainders []int `json:"exposed_remainders"`
	CarryThreshold    int   `json:"carry_threshold"`
}

type Incident struct {
	IncidentID  string   `json:"incident_id"`
	Severity    int      `json:"severity"`
	Action      string   `json:"action"`
	PositionIDs []string `json:"position_ids"`
}

type IncidentLog struct {
	Incidents           []Incident `json:"incidents"`
	FreezeSeverityFloor int        `json:"freeze_severity_floor"`
}

type Row struct {
	PositionID         string `json:"position_id"`
	WhiteRank          int    `json:"white_rank"`
	BlackRank          int    `json:"black_rank"`
	WhiteFile          int    `json:"white_file"`
	BlackFile          int    `json:"black_file"`
	SideToMove         string `json:"side_to_move"`
	TempoMoves         int    `json:"tempo_moves"`
	UnderpromotionRisk int    `json:"underpromotion_risk"`
}

func loadRow(dataDir, rel string) Row {
	var r Row
	readJSON(filepath.Join(dataDir, rel), &r)
	if r.WhiteRank == 0 && r.BlackRank == 0 {
		r.WhiteRank, r.BlackRank = 4, 4
	}
	return r
}

func cellKey(r Row) string {
	fd := abs(r.WhiteFile-r.BlackFile) % 5
	return fmt.Sprintf("f%d_m%d", fd, r.TempoMoves%2)
}

func intInSlice(x int, xs []int) bool {
	for _, v := range xs {
		if v == x {
			return true
		}
	}
	return false
}

func main() {
	dataDir := env("PET_DATA_DIR", "/app/pawn_endgame")
	outDir := env("PET_AUDIT_DIR", "/app/audit")
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		panic(err)
	}

	var manifest Manifest
	readJSON(filepath.Join(dataDir, "manifest.json"), &manifest)
	var pool PoolState
	readJSON(filepath.Join(dataDir, "pool_state.json"), &pool)
	var caps Caps
	readJSON(filepath.Join(dataDir, "policy", "caps.json"), &caps)
	var tie TieTable
	readJSON(filepath.Join(dataDir, "policy", "opposition_tiebreak.json"), &tie)
	var tp TempoPolicy
	readJSON(filepath.Join(dataDir, "policy", "tempo_policy.json"), &tp)
	var ilog IncidentLog
	readJSON(filepath.Join(dataDir, "incidents", "incident_log.json"), &ilog)

	frozen := map[string]struct{}{}
	for _, inc := range ilog.Incidents {
		if inc.Severity >= ilog.FreezeSeverityFloor && inc.Action == "freeze_illegal" {
			for _, pid := range inc.PositionIDs {
				frozen[pid] = struct{}{}
			}
		}
	}

	raceRows := make([]Row, 0, len(manifest.RaceFiles))
	for _, rel := range manifest.RaceFiles {
		raceRows = append(raceRows, loadRow(dataDir, rel))
	}
	tempoRows := make([]Row, 0, len(manifest.TempoFiles))
	for _, rel := range manifest.TempoFiles {
		tempoRows = append(tempoRows, loadRow(dataDir, rel))
	}
	gridRows := make([]Row, 0, len(manifest.GridFiles))
	for _, rel := range manifest.GridFiles {
		gridRows = append(gridRows, loadRow(dataDir, rel))
	}

	races := []map[string]any{}
	for _, r := range raceRows {
		if _, fr := frozen[r.PositionID]; fr {
			races = append(races, map[string]any{
				"outcome":           "frozen",
				"plies_to_decisive": 0,
				"position_id":       r.PositionID,
				"reason_codes":      []any{"incident_freeze"},
			})
			continue
		}
		W := 8 - r.WhiteRank
		B := r.BlackRank - 1
		adjW := W
		if r.SideToMove == "w" {
			adjW--
		}
		adjB := B
		if r.SideToMove == "b" {
			adjB--
		}
		var outcome string
		var plies int
		var reasons []any
		if adjW < adjB {
			outcome = "white_wins"
			plies = adjW + adjB + r.TempoMoves
			reasons = []any{"distance_decisive"}
		} else if adjB < adjW {
			outcome = "black_wins"
			plies = adjW + adjB + r.TempoMoves
			reasons = []any{"distance_decisive"}
		} else {
			ck := cellKey(r)
			trow, ok := tie.TiebreakTable[ck]
			mk := r.SideToMove
			if !ok {
				outcome = "draw"
			} else {
				outcome = trow[mk]
			}
			plies = 2*adjW + abs(r.WhiteFile-r.BlackFile) + r.TempoMoves
			reasons = []any{"opposition_tiebreak"}
		}
		races = append(races, map[string]any{
			"outcome":           outcome,
			"plies_to_decisive": plies,
			"position_id":       r.PositionID,
			"reason_codes":      reasons,
		})
	}
	sort.Slice(races, func(i, j int) bool {
		return races[i]["position_id"].(string) < races[j]["position_id"].(string)
	})

	windows := []map[string]any{}
	for _, r := range tempoRows {
		if _, fr := frozen[r.PositionID]; fr {
			windows = append(windows, map[string]any{
				"carry_pressure": false,
				"class":          "frozen",
				"position_id":    r.PositionID,
				"remainder":      0,
				"window_index":   -1,
			})
			continue
		}
		W := tp.WindowSize
		rem := r.TempoMoves % W
		wi := r.TempoMoves / W
		cl := "safe"
		if intInSlice(rem, tp.ExposedRemainders) {
			cl = "exposed"
		}
		windows = append(windows, map[string]any{
			"carry_pressure": r.TempoMoves >= tp.CarryThreshold,
			"class":          cl,
			"position_id":    r.PositionID,
			"remainder":      rem,
			"window_index":   wi,
		})
	}
	sort.Slice(windows, func(i, j int) bool {
		return windows[i]["position_id"].(string) < windows[j]["position_id"].(string)
	})

	capRows := append(append([]Row{}, raceRows...), tempoRows...)
	evals := []map[string]any{}
	for _, r := range capRows {
		if _, fr := frozen[r.PositionID]; fr {
			evals = append(evals, map[string]any{
				"cap_band":      "frozen",
				"effective_cap": -1,
				"position_id":   r.PositionID,
			})
			continue
		}
		wr := strconv.Itoa(r.WhiteRank)
		cap := caps.DefaultUnderpromotionCap
		if v, ok := caps.RankOverrides[wr]; ok {
			cap = v
		}
		dem := r.UnderpromotionRisk + ((r.WhiteRank + r.BlackRank) % 5)
		mult := caps.IllegalComboMultiplier
		if mult < 1 {
			mult = 1
		}
		band := "within_cap"
		if dem > cap {
			if dem <= cap*mult {
				band = "exceeds_cap"
			} else {
				band = "beyond_policy"
			}
		}
		evals = append(evals, map[string]any{
			"cap_band":      band,
			"effective_cap": cap,
			"position_id":   r.PositionID,
		})
	}
	sort.Slice(evals, func(i, j int) bool {
		return evals[i]["position_id"].(string) < evals[j]["position_id"].(string)
	})

	cellMembers := map[string]map[string]struct{}{}
	allForGrid := append(append([]Row{}, raceRows...), tempoRows...)
	allForGrid = append(allForGrid, gridRows...)
	for _, r := range allForGrid {
		if _, fr := frozen[r.PositionID]; fr {
			continue
		}
		ck := cellKey(r)
		if cellMembers[ck] == nil {
			cellMembers[ck] = map[string]struct{}{}
		}
		cellMembers[ck][r.PositionID] = struct{}{}
	}
	keys := make([]string, 0, len(cellMembers))
	for k := range cellMembers {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	cells := []map[string]any{}
	for _, ck := range keys {
		mem := make([]string, 0, len(cellMembers[ck]))
		for id := range cellMembers[ck] {
			mem = append(mem, id)
		}
		sort.Strings(mem)
		vw, vb := "draw", "draw"
		if trow, ok := tie.TiebreakTable[ck]; ok {
			vw = trow["w"]
			vb = trow["b"]
		}
		cells = append(cells, map[string]any{
			"cell_key":                ck,
			"member_positions":        toAnySlice(mem),
			"verdict_if_black_moves":  vb,
			"verdict_if_white_moves":  vw,
		})
	}

	countKeys := []string{
		"caps_beyond", "caps_exceeds", "caps_frozen", "caps_within",
		"grid_cells",
		"races_black_wins", "races_draw", "races_frozen", "races_total", "races_white_wins",
		"tempo_exposed", "tempo_frozen", "tempo_safe",
	}
	counts := map[string]int{}
	for _, k := range countKeys {
		counts[k] = 0
	}
	counts["races_total"] = len(races)
	for _, rc := range races {
		switch rc["outcome"].(string) {
		case "frozen":
			counts["races_frozen"]++
		case "white_wins":
			counts["races_white_wins"]++
		case "black_wins":
			counts["races_black_wins"]++
		case "draw":
			counts["races_draw"]++
		}
	}
	for _, w := range windows {
		switch w["class"].(string) {
		case "exposed":
			counts["tempo_exposed"]++
		case "safe":
			counts["tempo_safe"]++
		case "frozen":
			counts["tempo_frozen"]++
		}
	}
	counts["grid_cells"] = len(cells)
	for _, e := range evals {
		switch e["cap_band"].(string) {
		case "within_cap":
			counts["caps_within"]++
		case "exceeds_cap":
			counts["caps_exceeds"]++
		case "beyond_policy":
			counts["caps_beyond"]++
		case "frozen":
			counts["caps_frozen"]++
		}
	}
	frozenList := make([]string, 0, len(frozen))
	for id := range frozen {
		frozenList = append(frozenList, id)
	}
	sort.Strings(frozenList)

	actCount := map[string]any{}
	for _, inc := range ilog.Incidents {
		k := inc.Action
		c := 0
		if v, ok := actCount[k]; ok {
			c = v.(int)
		}
		actCount[k] = c + 1
	}

	countsAny := map[string]any{}
	for k, v := range counts {
		countsAny[k] = v
	}

	summary := map[string]any{
		"audit_epoch":         pool.AuditEpoch,
		"counts":              countsAny,
		"frozen_position_ids": toAnySlice(frozenList),
		"incident_actions":    actCount,
	}

	writeCanon(filepath.Join(outDir, "passed_pawn_races.json"), map[string]any{"races": toAnySliceMaps(races)})
	writeCanon(filepath.Join(outDir, "opposition_grid.json"), map[string]any{"cells": toAnySliceMaps(cells)})
	writeCanon(filepath.Join(outDir, "tempo_loss_windows.json"), map[string]any{"windows": toAnySliceMaps(windows)})
	writeCanon(filepath.Join(outDir, "underpromotion_caps.json"), map[string]any{"evaluations": toAnySliceMaps(evals)})
	writeCanon(filepath.Join(outDir, "summary.json"), summary)
}

func toAnySlice(s []string) []any {
	out := make([]any, len(s))
	for i := range s {
		out[i] = s[i]
	}
	return out
}

func toAnySliceMaps(m []map[string]any) []any {
	out := make([]any, len(m))
	for i := range m {
		out[i] = m[i]
	}
	return out
}

GOEOF

cd "$SRC_DIR"
go build -o "$BIN_DIR/pawnaudit" .
"$BIN_DIR/pawnaudit"
