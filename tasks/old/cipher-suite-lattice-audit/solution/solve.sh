#!/bin/bash
set -euo pipefail

export PATH="/usr/local/go/bin:${PATH}"

DATA_DIR="${CSL_DATA_DIR:-/app/cipher_lattice}"
AUDIT_DIR="${CSL_AUDIT_DIR:-/app/audit}"
WORK="${CSL_BUILD_DIR:-/tmp/cslbuild}"

mkdir -p "$WORK" "$AUDIT_DIR"

cat >"$WORK/go.mod" <<'GOMOD'
module cslaudit

go 1.23
GOMOD

cat >"$WORK/main.go" <<'GOEOF'
package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type suiteRec struct {
	Family       string `json:"family"`
	FsBand       string `json:"fs_band"`
	LatticeRank  int    `json:"lattice_rank"`
	SuiteID      string `json:"suite_id"`
}

type hostFile struct {
	CapRank         int                      `json:"cap_rank"`
	ECH             []map[string]interface{} `json:"ech_client_configs"`
	HostID          string                   `json:"host_id"`
	OfferedSuiteIDs []string                 `json:"offered_suite_ids"`
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func readJSON(path string) map[string]interface{} {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	var m map[string]interface{}
	if err := json.Unmarshal(b, &m); err != nil {
		panic(err)
	}
	return m
}

func writeJSON(path string, v interface{}) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		panic(err)
	}
	out := bytes.TrimSuffix(buf.Bytes(), []byte("\n"))
	out = append(out, '\n')
	if err := os.WriteFile(path, out, 0o644); err != nil {
		panic(err)
	}
}

func strMap(m map[string]interface{}, k string) string {
	v, ok := m[k]
	if !ok || v == nil {
		return ""
	}
	s, _ := v.(string)
	return s
}

func strSliceFromIface(v interface{}) []string {
	arr, ok := v.([]interface{})
	if !ok {
		return nil
	}
	out := make([]string, 0, len(arr))
	for _, it := range arr {
		s, _ := it.(string)
		out = append(out, s)
	}
	return out
}

func intFromIface(v interface{}) int {
	switch t := v.(type) {
	case float64:
		return int(t)
	case json.Number:
		i, _ := t.Int64()
		return int(i)
	default:
		return 0
	}
}

func tierWorsen(tier string, steps int) string {
	for i := 0; i < steps; i++ {
		switch tier {
		case "T1":
			tier = "T2"
		case "T2":
			tier = "T3"
		}
	}
	return tier
}

func containsStr(list []string, s string) bool {
	for _, x := range list {
		if x == s {
			return true
		}
	}
	return false
}

func main() {
	dataRoot := env("CSL_DATA_DIR", "/app/cipher_lattice")
	auditRoot := env("CSL_AUDIT_DIR", "/app/audit")

	policy := readJSON(filepath.Join(dataRoot, "policy.json"))
	pool := readJSON(filepath.Join(dataRoot, "pool_state.json"))
	edgesDoc := readJSON(filepath.Join(dataRoot, "base_lattice", "edges.json"))
	baseEdgesRaw := edgesDoc["edges"].([]interface{})

	cipherPrefix := strMap(policy, "cipher_grease_prefix")
	echLabels := strSliceFromIface(policy["ech_grease_labels"])
	fsMapRaw := policy["fs_band_to_tier"].(map[string]interface{})
	fsMap := map[string]string{}
	for k, v := range fsMapRaw {
		fsMap[k] = v.(string)
	}
	sentinelIDs := strSliceFromIface(policy["sentinel_suite_ids"])
	sentinelFlag := false
	if v, ok := policy["sentinel_trailing_strong_fs"]; ok {
		sentinelFlag, _ = v.(bool)
	}

	var co map[string]interface{}
	if v, ok := policy["fs_co_worsen"]; ok {
		co, _ = v.(map[string]interface{})
	}

	currentSeq := intFromIface(pool["current_seq"])
	auditWindow := strMap(pool, "audit_window")

	incidentRoot := readJSON(filepath.Join(dataRoot, "incidents", "incident_log.json"))
	incEvents := incidentRoot["events"].([]interface{})

	type incRow struct {
		seq     int
		kind    string
		suiteID string
		family  string
		raw     map[string]interface{}
	}
	rows := make([]incRow, 0, len(incEvents))
	for _, it := range incEvents {
		ev := it.(map[string]interface{})
		seq := intFromIface(ev["seq"])
		if seq > currentSeq {
			continue
		}
		rows = append(rows, incRow{
			seq:     seq,
			kind:    ev["kind"].(string),
			suiteID: strMap(ev, "suite_id"),
			family:  strMap(ev, "family"),
			raw:     ev,
		})
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].seq != rows[j].seq {
			return rows[i].seq < rows[j].seq
		}
		if rows[i].kind != rows[j].kind {
			return rows[i].kind < rows[j].kind
		}
		if rows[i].suiteID != rows[j].suiteID {
			return rows[i].suiteID < rows[j].suiteID
		}
		return rows[i].family < rows[j].family
	})

	suites := map[string]suiteRec{}
	_ = filepath.Walk(filepath.Join(dataRoot, "suites"), func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() || !strings.HasSuffix(path, ".json") {
			return err
		}
		b, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		var rec suiteRec
		if err := json.Unmarshal(b, &rec); err != nil {
			return err
		}
		suites[rec.SuiteID] = rec
		return nil
	})

	revoked := map[string]struct{}{}
	trace := make([]map[string]interface{}, 0, len(rows))
	for _, row := range rows {
		switch row.kind {
		case "revoke_suite":
			revoked[row.suiteID] = struct{}{}
		case "revoke_family":
			for sid, rec := range suites {
				if rec.Family == row.family {
					revoked[sid] = struct{}{}
				}
			}
		case "clear_revocation":
			delete(revoked, row.suiteID)
		}
		trace = append(trace, map[string]interface{}{
			"kind":                row.kind,
			"revoked_count_after": len(revoked),
			"seq":                 row.seq,
		})
	}

	revokedList := make([]string, 0, len(revoked))
	for sid := range revoked {
		revokedList = append(revokedList, sid)
	}
	sort.Strings(revokedList)

	coWorsen := false
	guard := ""
	affects := map[string]struct{}{}
	steps := 0
	if co != nil {
		guard = strMap(co, "guard_revoked_family")
		steps = intFromIface(co["steps"])
		for _, it := range co["affects_suite_families"].([]interface{}) {
			affects[it.(string)] = struct{}{}
		}
	}
	if guard != "" {
		for sid := range revoked {
			if suites[sid].Family == guard {
				coWorsen = true
				break
			}
		}
	}

	hostPaths, _ := filepath.Glob(filepath.Join(dataRoot, "hosts", "*.json"))
	sort.Strings(hostPaths)

	type hostSummary struct {
		CapRank                    int    `json:"cap_rank"`
		GreaseStrippedCipher       int    `json:"grease_stripped_cipher"`
		GreaseStrippedECH          int    `json:"grease_stripped_ech"`
		HostID                     string `json:"host_id"`
		RetainedCount              int    `json:"retained_count"`
		StrongestRetainedSuiteID   string `json:"strongest_retained_suite_id"`
	}

	hostSummaries := make([]hostSummary, 0, len(hostPaths))
	findings := make([]map[string]interface{}, 0)

	active := map[string]struct{}{}

	for _, hp := range hostPaths {
		b, err := os.ReadFile(hp)
		if err != nil {
			panic(err)
		}
		var hf hostFile
		if err := json.Unmarshal(b, &hf); err != nil {
			panic(err)
		}

		stripCipher := 0
		stripped := make([]string, 0, len(hf.OfferedSuiteIDs))
		for _, sid := range hf.OfferedSuiteIDs {
			if sid == "" {
				stripCipher++
				continue
			}
			if strings.HasPrefix(sid, cipherPrefix) {
				stripCipher++
				continue
			}
			stripped = append(stripped, sid)
		}

		stripECH := 0
		echKept := make([]map[string]interface{}, 0, len(hf.ECH))
		for _, obj := range hf.ECH {
			lbl, _ := obj["label"].(string)
			if containsStr(echLabels, lbl) {
				stripECH++
				continue
			}
			echKept = append(echKept, obj)
		}
		_ = echKept

		if sentinelFlag {
			for i := 0; i < len(stripped); i++ {
				if !containsStr(sentinelIDs, stripped[i]) {
					continue
				}
				for j := i + 1; j < len(stripped); j++ {
					wid := stripped[j]
					rec, ok := suites[wid]
					if !ok {
						continue
					}
					baseTier := fsMap[rec.FsBand]
					if baseTier == "T1" {
						findings = append(findings, map[string]interface{}{
							"host_id":         hf.HostID,
							"index_sentinel":  i,
							"index_witness":   j,
							"pattern":         "sentinel_before_strong_fs",
							"sentinel":        stripped[i],
							"witness":         wid,
						})
					}
				}
			}
		}

		retained := make([]string, 0)
		bestRank := -1
		bestID := ""
		for _, sid := range stripped {
			rec, ok := suites[sid]
			if !ok {
				continue
			}
			if _, bad := revoked[sid]; bad {
				continue
			}
			if rec.LatticeRank > hf.CapRank {
				continue
			}
			retained = append(retained, sid)
			active[sid] = struct{}{}
			if rec.LatticeRank > bestRank || (rec.LatticeRank == bestRank && (bestID == "" || sid < bestID)) {
				bestRank = rec.LatticeRank
				bestID = sid
			}
		}

		strongest := ""
		if len(retained) > 0 {
			strongest = bestID
		}

		hostSummaries = append(hostSummaries, hostSummary{
			CapRank:                  hf.CapRank,
			GreaseStrippedCipher:     stripCipher,
			GreaseStrippedECH:        stripECH,
			HostID:                   hf.HostID,
			RetainedCount:            len(retained),
			StrongestRetainedSuiteID: strongest,
		})
	}

	sort.Slice(hostSummaries, func(i, j int) bool {
		return hostSummaries[i].HostID < hostSummaries[j].HostID
	})

	sort.Slice(findings, func(i, j int) bool {
		a, b := findings[i], findings[j]
		if a["host_id"].(string) != b["host_id"].(string) {
			return a["host_id"].(string) < b["host_id"].(string)
		}
		if intFromIface(a["index_sentinel"]) != intFromIface(b["index_sentinel"]) {
			return intFromIface(a["index_sentinel"]) < intFromIface(b["index_sentinel"])
		}
		if intFromIface(a["index_witness"]) != intFromIface(b["index_witness"]) {
			return intFromIface(a["index_witness"]) < intFromIface(b["index_witness"])
		}
		if a["sentinel"].(string) != b["sentinel"].(string) {
			return a["sentinel"].(string) < b["sentinel"].(string)
		}
		return a["witness"].(string) < b["witness"].(string)
	})

	activeIDs := make([]string, 0, len(active))
	for sid := range active {
		activeIDs = append(activeIDs, sid)
	}
	sort.Strings(activeIDs)

	nodes := make([]map[string]interface{}, 0, len(activeIDs))
	for _, sid := range activeIDs {
		rec := suites[sid]
		nodes = append(nodes, map[string]interface{}{
			"family":        rec.Family,
			"fs_band":       rec.FsBand,
			"lattice_rank":  rec.LatticeRank,
			"suite_id":      rec.SuiteID,
		})
	}

	edgesOut := make([]map[string]interface{}, 0)
	for _, it := range baseEdgesRaw {
		edge := it.(map[string]interface{})
		weak := edge["weak"].(string)
		strong := edge["strong"].(string)
		if _, ok1 := active[weak]; !ok1 {
			continue
		}
		if _, ok2 := active[strong]; !ok2 {
			continue
		}
		edgesOut = append(edgesOut, map[string]interface{}{
			"strong": strong,
			"weak":   weak,
		})
	}
	sort.Slice(edgesOut, func(i, j int) bool {
		wi := edgesOut[i]["weak"].(string)
		wj := edgesOut[j]["weak"].(string)
		if wi != wj {
			return wi < wj
		}
		return edgesOut[i]["strong"].(string) < edgesOut[j]["strong"].(string)
	})

	merged := map[string]interface{}{
		"edges": edgesOut,
		"meta": map[string]interface{}{
			"active_suite_count": len(activeIDs),
			"audit_window":       auditWindow,
			"edge_count":         len(edgesOut),
		},
		"nodes": nodes,
	}

	fsRows := make([]map[string]interface{}, 0, len(activeIDs))
	for _, sid := range activeIDs {
		rec := suites[sid]
		baseTier := fsMap[rec.FsBand]
		effective := baseTier
		if coWorsen {
			if _, hit := affects[rec.Family]; hit {
				effective = tierWorsen(baseTier, steps)
			}
		}
		fsRows = append(fsRows, map[string]interface{}{
			"base_tier":      baseTier,
			"effective_tier": effective,
			"family":         rec.Family,
			"suite_id":       sid,
		})
	}

	anchorFiles := make([]string, 0)
	_ = filepath.Walk(filepath.Join(dataRoot, "anchors"), func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() || !strings.HasSuffix(path, ".json") {
			return err
		}
		rel, err := filepath.Rel(dataRoot, path)
		if err != nil {
			return err
		}
		anchorFiles = append(anchorFiles, filepath.ToSlash(rel))
		return nil
	})
	sort.Strings(anchorFiles)

	summary := map[string]interface{}{
		"active_suite_count":        len(activeIDs),
		"anchor_files":              anchorFiles,
		"audit_window":              auditWindow,
		"downgrade_finding_count":   len(findings),
		"edge_count":                len(edgesOut),
		"hosts":                     hostSummaries,
		"revoked_suite_count":       len(revokedList),
	}

	downgrade := map[string]interface{}{
		"findings": findings,
	}

	revLattice := map[string]interface{}{
		"revoked_suite_ids": revokedList,
		"trace":             trace,
	}

	fsReport := map[string]interface{}{
		"suites": fsRows,
	}

	writeJSON(filepath.Join(auditRoot, "merged_lattice.json"), merged)
	writeJSON(filepath.Join(auditRoot, "fs_tier_report.json"), fsReport)
	writeJSON(filepath.Join(auditRoot, "downgrade_screen.json"), downgrade)
	writeJSON(filepath.Join(auditRoot, "revocation_lattice.json"), revLattice)
	writeJSON(filepath.Join(auditRoot, "summary.json"), summary)
}
GOEOF

(
	cd "$WORK" && gofmt -w main.go && go run .
)
