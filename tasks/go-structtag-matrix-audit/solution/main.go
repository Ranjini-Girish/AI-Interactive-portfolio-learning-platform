// Reference implementation for the struct-tag matrix audit task.
package main

import (
	"encoding/json"
	"fmt"
	"maps"
	"os"
	"path/filepath"
	"slices"
	"strings"
)

func main() {
	reg := getenv("GTA_REGISTRY_DIR", "/app/registry")
	out := getenv("GTA_AUDIT_DIR", "/app/audit")
	if err := run(reg, out); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func getenv(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

type fieldRef struct {
	pkgID, structID, fieldID, goName string
	tags                             map[string]any
}

func run(regDir, outDir string) error {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	pool, err := readJSONObj(filepath.Join(regDir, "pool_state.json"))
	if err != nil {
		return err
	}
	policy, err := readJSONObj(filepath.Join(regDir, "policy", "policy.json"))
	if err != nil {
		return err
	}
	incRoot, err := readJSONObj(filepath.Join(regDir, "incidents", "incident_log.json"))
	if err != nil {
		return err
	}
	currentDay := int(pool["current_day"].(float64))
	rawSup := policy["supported_incident_kinds"].([]any)
	supported := make([]string, len(rawSup))
	for i := range rawSup {
		supported[i] = rawSup[i].(string)
	}
	slices.Sort(supported)

	var fields []fieldRef
	pkgDir := filepath.Join(regDir, "packages")
	ents, err := os.ReadDir(pkgDir)
	if err != nil {
		return err
	}
	for _, e := range ents {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		p, err := readJSONObj(filepath.Join(pkgDir, e.Name()))
		if err != nil {
			return err
		}
		pkgID := p["package_id"].(string)
		structs := p["structs"].([]any)
		for _, si := range structs {
			st := si.(map[string]any)
			sid := st["struct_id"].(string)
			for _, fi := range st["fields"].([]any) {
				f := fi.(map[string]any)
				tags := map[string]any{}
				if raw, ok := f["tags"].(map[string]any); ok {
					maps.Copy(tags, raw)
				}
				fields = append(fields, fieldRef{
					pkgID: pkgID, structID: sid,
					fieldID: f["field_id"].(string), goName: f["go_name"].(string),
					tags: tags,
				})
			}
		}
	}
	slices.SortFunc(fields, func(a, b fieldRef) int {
		if c := strings.Compare(a.pkgID, b.pkgID); c != 0 {
			return c
		}
		if c := strings.Compare(a.structID, b.structID); c != 0 {
			return c
		}
		return strings.Compare(a.fieldID, b.fieldID)
	})

	type parsed struct {
		status               string
		ignored              bool
		jsonPrimary          string
		bsonPrimary          string
		jsonFlags            []string
		normJSON, normBSON   map[string]any
		namingSkew           bool
		parseErrJSON         bool
		parseErrBSON         bool
	}

	parseTag := func(kind, raw string) (primary string, flags []string, ok bool, status string) {
		raw = strings.TrimSpace(raw)
		if raw == "" {
			return "", nil, false, "invalid_empty_" + kind + "_name"
		}
		parts := splitCommaRespect(raw)
		if len(parts) == 0 {
			return "", nil, false, "invalid_empty_" + kind + "_name"
		}
		primary = strings.TrimSpace(parts[0])
		if primary == "" {
			return "", nil, false, "invalid_empty_" + kind + "_name"
		}
		for _, p := range parts[1:] {
			p = strings.TrimSpace(p)
			fl := strings.ToLower(p)
			if kind == "json" {
				if fl != "omitempty" && fl != "string" {
					return primary, nil, false, "invalid_unknown_json_flag"
				}
			} else {
				if fl != "omitempty" {
					return primary, nil, false, "invalid_unknown_bson_flag"
				}
			}
			flags = append(flags, fl)
		}
		slices.Sort(flags)
		return primary, flags, true, "ok"
	}

	parsedBy := make([]parsed, len(fields))
	for i, fr := range fields {
		p := parsed{status: "ok"}
		jraw, jok := fr.tags["json"].(string)
		if !jok {
			p.status = "missing_json_tag"
			p.parseErrJSON = true
			parsedBy[i] = p
			continue
		}
		jp, jf, jok2, jst := parseTag("json", jraw)
		if !jok2 {
			p.status = jst
			p.parseErrJSON = true
			parsedBy[i] = p
			continue
		}
		p.jsonPrimary = jp
		p.jsonFlags = jf
		p.normJSON = map[string]any{"primary": jp, "flags": strSliceAny(jf)}
		if jp == "-" {
			p.ignored = true
		}
		if braw, bok := fr.tags["bson"].(string); bok {
			bp, bf, bok2, bst := parseTag("bson", braw)
			if !bok2 {
				p.status = bst
				p.parseErrBSON = true
				parsedBy[i] = p
				continue
			}
			p.bsonPrimary = bp
			p.normBSON = map[string]any{"primary": bp, "flags": strSliceAny(bf)}
			if !p.ignored && jp != "-" && bp != "-" && jp != bp {
				p.namingSkew = true
			}
		}
		parsedBy[i] = p
	}

	collisionMembers := map[int]bool{}
	key := func(pkg, st, name string) string {
		return pkg + "\x00" + st + "\x00" + name
	}
	groupMembers := map[string][]int{}
	for i, fr := range fields {
		p := parsedBy[i]
		if p.ignored || p.parseErrJSON || p.status != "ok" {
			continue
		}
		if p.jsonPrimary == "" || p.jsonPrimary == "-" {
			continue
		}
		k := key(fr.pkgID, fr.structID, p.jsonPrimary)
		groupMembers[k] = append(groupMembers[k], i)
	}
	for _, ids := range groupMembers {
		if len(ids) > 1 {
			for _, id := range ids {
				collisionMembers[id] = true
			}
		}
	}

	events := incRoot["events"].([]any)
	type ev struct {
		id, kind, pkg string
		day            int
		accepted       bool
	}
	var all []ev
	for _, ei := range events {
		e := ei.(map[string]any)
		all = append(all, ev{
			id: e["event_id"].(string), kind: e["kind"].(string),
			pkg: e["package_id"].(string), day: int(e["day"].(float64)),
			accepted: e["accepted"].(bool),
		})
	}
	slices.SortFunc(all, func(a, b ev) int {
		if c := strings.Compare(a.id, b.id); c != 0 {
			return c
		}
		return 0
	})

	ignoredReason := map[string]string{}
	winners := map[string]ev{}
	groupKey := func(kind, pkg string) string { return kind + "\x00" + pkg }

	var eligible []ev
	for _, e := range all {
		if !e.accepted {
			ignoredReason[e.id] = "not_accepted"
			continue
		}
		if e.day > currentDay {
			ignoredReason[e.id] = "future_day"
			continue
		}
		if !slices.Contains(supported, e.kind) {
			ignoredReason[e.id] = "unsupported_kind"
			continue
		}
		eligible = append(eligible, e)
	}
	byGroup := map[string][]ev{}
	for _, e := range eligible {
		gk := groupKey(e.kind, e.pkg)
		byGroup[gk] = append(byGroup[gk], e)
	}
	better := func(a, b ev) bool {
		if a.day != b.day {
			return a.day > b.day
		}
		return a.id < b.id
	}
	for _, lst := range byGroup {
		w := lst[0]
		for _, e := range lst[1:] {
			if better(e, w) {
				w = e
			}
		}
		winners[groupKey(w.kind, w.pkg)] = w
		for _, e := range lst {
			if e.id != w.id {
				ignoredReason[e.id] = "superseded"
			}
		}
	}

	waiverPkgs := map[string]bool{}
	lockPkgs := map[string]bool{}
	var acceptedList []map[string]any
	for _, w := range winners {
		acceptedList = append(acceptedList, map[string]any{
			"day": w.day, "event_id": w.id, "kind": w.kind, "package_id": w.pkg,
		})
		switch w.kind {
		case "naming_waiver":
			waiverPkgs[w.pkg] = true
		case "integrity_lock":
			lockPkgs[w.pkg] = true
		}
	}
	slices.SortFunc(acceptedList, func(a, b map[string]any) int {
		return strings.Compare(a["event_id"].(string), b["event_id"].(string))
	})

	var ignoredIDs []string
	for id := range ignoredReason {
		ignoredIDs = append(ignoredIDs, id)
	}
	slices.Sort(ignoredIDs)

	fieldSeverity := func(i int) string {
		fr := fields[i]
		p := parsedBy[i]
		if lockPkgs[fr.pkgID] {
			return "blocked"
		}
		if p.status != "ok" || p.parseErrBSON {
			return "error"
		}
		if collisionMembers[i] {
			return "error"
		}
		if p.namingSkew {
			if waiverPkgs[fr.pkgID] {
				return "info"
			}
			return "warn"
		}
		return "ok"
	}

	var matrix []map[string]any
	for i, fr := range fields {
		p := parsedBy[i]
		entry := map[string]any{
			"field_id": fr.fieldID, "go_name": fr.goName, "naming_skew": p.namingSkew,
			"package_id": fr.pkgID, "parse_status": p.status, "struct_id": fr.structID,
			"serialization_ignored": p.ignored,
			"tags_normalized": map[string]any{
				"bson": p.normBSON, "json": p.normJSON,
			},
			"tags_raw": anyMap(fr.tags),
		}
		if p.normJSON == nil {
			entry["tags_normalized"] = map[string]any{"bson": p.normBSON, "json": nil}
		}
		if p.normBSON == nil {
			tn := entry["tags_normalized"].(map[string]any)
			tn["bson"] = nil
		}
		sev := fieldSeverity(i)
		entry["effective_severity"] = sev
		_ = sev
		matrix = append(matrix, entry)
	}

	var groups []map[string]any
	for k, ids := range groupMembers {
		if len(ids) < 2 {
			continue
		}
		parts := strings.Split(k, "\x00")
		fids := make([]string, 0, len(ids))
		for _, ii := range ids {
			fids = append(fids, fields[ii].fieldID)
		}
		slices.Sort(fids)
		groups = append(groups, map[string]any{
			"field_ids": fids, "json_name": parts[2], "package_id": parts[0], "struct_id": parts[1],
		})
	}
	slices.SortFunc(groups, func(a, b map[string]any) int {
		if c := strings.Compare(a["package_id"].(string), b["package_id"].(string)); c != 0 {
			return c
		}
		if c := strings.Compare(a["struct_id"].(string), b["struct_id"].(string)); c != 0 {
			return c
		}
		return strings.Compare(a["json_name"].(string), b["json_name"].(string))
	})

	pkgIDs := map[string]bool{}
	for _, fr := range fields {
		pkgIDs[fr.pkgID] = true
	}
	var pkgList []string
	for p := range pkgIDs {
		pkgList = append(pkgList, p)
	}
	slices.Sort(pkgList)

	var roll []map[string]any
	for _, pid := range pkgList {
		counts := map[string]int{"error": 0, "info": 0, "ok": 0, "warn": 0}
		highest := "ok"
		order := []string{"ok", "info", "warn", "error", "blocked"}
		rank := func(s string) int { return slices.Index(order, s) }

		for i, fr := range fields {
			if fr.pkgID != pid {
				continue
			}
			sev := fieldSeverity(i)
			if sev == "blocked" {
				continue
			}
			counts[sev]++
			if rank(sev) > rank(highest) {
				highest = sev
			}
		}
		forced := lockPkgs[pid]
		final := highest
		if forced {
			final = "blocked"
		}
		roll = append(roll, map[string]any{
			"counts": map[string]any{
				"error": counts["error"], "info": counts["info"],
				"ok": counts["ok"], "warn": counts["warn"],
			},
			"forced_by_incident": forced, "highest_severity": final, "package_id": pid,
		})
	}

	incidentObj := map[string]any{
		"accepted_events": acceptedList, "ignored_event_ids": strSliceAny(ignoredIDs),
	}

	structCount := map[string]bool{}
	for _, fr := range fields {
		structCount[fr.pkgID+"\x00"+fr.structID] = true
	}

	summary := summaryCounts(fields, structCount, groups, acceptedList, ignoredIDs, matrix, roll)

	if err := writeJSON(filepath.Join(outDir, "tag_parse_matrix.json"), map[string]any{"entries": matrix}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(outDir, "json_name_collisions.json"), map[string]any{"groups": groups}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(outDir, "package_rollups.json"), map[string]any{"packages": roll}); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(outDir, "incident_resolution.json"), incidentObj); err != nil {
		return err
	}
	if err := writeJSON(filepath.Join(outDir, "summary.json"), summary); err != nil {
		return err
	}
	return nil
}

func summaryCounts(fields []fieldRef, structCount map[string]bool, groups []map[string]any, accepted []map[string]any, ignoredIDs []string, matrix, roll []map[string]any) map[string]any {
	parseErr := 0
	skew := 0
	waived := 0
	for _, row := range matrix {
		st := row["parse_status"].(string)
		if st != "ok" {
			parseErr++
		}
		if row["naming_skew"].(bool) {
			skew++
			if row["effective_severity"].(string) == "info" {
				waived++
			}
		}
	}
	blocked := 0
	for _, r := range roll {
		if r["highest_severity"].(string) == "blocked" {
			blocked++
		}
	}
	keys := []string{
		"accepted_incident_events", "blocked_packages", "collision_groups",
		"fields_missing_json_tag", "fields_total", "ignored_incident_events",
		"naming_skew_fields", "packages_total", "parse_error_fields",
		"structs_total", "waived_naming_skew_fields",
	}
	out := map[string]any{}
	for _, k := range keys {
		switch k {
		case "accepted_incident_events":
			out[k] = len(accepted)
		case "ignored_incident_events":
			out[k] = len(ignoredIDs)
		case "packages_total":
			pkg := map[string]bool{}
			for _, f := range fields {
				pkg[f.pkgID] = true
			}
			out[k] = len(pkg)
		case "structs_total":
			out[k] = len(structCount)
		case "fields_total":
			out[k] = len(fields)
		case "collision_groups":
			out[k] = len(groups)
		case "parse_error_fields":
			out[k] = parseErr
		case "naming_skew_fields":
			out[k] = skew
		case "waived_naming_skew_fields":
			out[k] = waived
		case "blocked_packages":
			out[k] = blocked
		case "fields_missing_json_tag":
			c := 0
			for _, row := range matrix {
				if row["parse_status"].(string) == "missing_json_tag" {
					c++
				}
			}
			out[k] = c
		}
	}
	return out
}

func writeJSON(path string, v map[string]any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(b, '\n'), 0o644)
}

func readJSONObj(path string) (map[string]any, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		return nil, err
	}
	return m, nil
}

func splitCommaRespect(s string) []string {
	var out []string
	var cur strings.Builder
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c == ',' {
			out = append(out, cur.String())
			cur.Reset()
			continue
		}
		cur.WriteByte(c)
	}
	out = append(out, cur.String())
	return out
}

func strSliceAny(s []string) []any {
	r := make([]any, len(s))
	for i := range s {
		r[i] = s[i]
	}
	return r
}

func anyMap(m map[string]any) map[string]any {
	if m == nil {
		return map[string]any{}
	}
	out := map[string]any{}
	maps.Copy(out, m)
	return out
}

