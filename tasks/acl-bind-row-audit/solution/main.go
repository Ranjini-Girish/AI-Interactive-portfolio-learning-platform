package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
)

type poolState struct {
	CurrentStep int `json:"current_step"`
}

type incidentEvent map[string]any

type incidentLog struct {
	Events []incidentEvent `json:"events"`
}

type grantFile struct {
	Subject  string `json:"subject"`
	ObjectID string `json:"object_id"`
	Rights   int64  `json:"rights"`
}

type objectOut struct {
	CombinedRights int      `json:"combined_rights"`
	ID               string   `json:"id"`
	Subjects         []string `json:"subjects"`
}

type report struct {
	Objects []objectOut    `json:"objects"`
	Summary map[string]int `json:"summary"`
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

func canonicalJSON(v any) []byte {
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

func intFromAny(v any) (int, bool) {
	switch x := v.(type) {
	case float64:
		return int(x), true
	case json.Number:
		i, err := strconv.Atoi(string(x))
		return i, err == nil
	case string:
		i, err := strconv.Atoi(x)
		return i, err == nil
	default:
		return 0, false
	}
}

func int64FromAny(v any) (int64, bool) {
	switch x := v.(type) {
	case float64:
		return int64(x), true
	case json.Number:
		i, err := strconv.ParseInt(string(x), 10, 64)
		return i, err == nil
	case string:
		i, err := strconv.ParseInt(x, 10, 64)
		return i, err == nil
	default:
		return 0, false
	}
}

func strFromAny(v any) (string, bool) {
	s, ok := v.(string)
	return s, ok
}

func sortEvents(ev []incidentEvent) []incidentEvent {
	out := append([]incidentEvent(nil), ev...)
	sort.SliceStable(out, func(i, j int) bool {
		ai, _ := intFromAny(out[i]["apply_step"])
		aj, _ := intFromAny(out[j]["apply_step"])
		if ai != aj {
			return ai < aj
		}
		si, _ := strFromAny(out[i]["event_id"])
		sj, _ := strFromAny(out[j]["event_id"])
		return si < sj
	})
	return out
}

var grantFileRe = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]*\.json$`)

func u32(v int64) uint32 {
	return uint32(v & 0xffffffff)
}

func main() {
	dataRoot := os.Getenv("ABR_DATA_DIR")
	if dataRoot == "" {
		dataRoot = "/app/abr_lab"
	}
	auditRoot := os.Getenv("ABR_AUDIT_DIR")
	if auditRoot == "" {
		auditRoot = "/app/abr_audit"
	}

	var pool poolState
	mustReadJSON(filepath.Join(dataRoot, "pool_state.json"), &pool)
	var log incidentLog
	mustReadJSON(filepath.Join(dataRoot, "incident_log.json"), &log)

	matches, err := filepath.Glob(filepath.Join(dataRoot, "grants", "*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(matches)
	var paths []string
	for _, p := range matches {
		if grantFileRe.MatchString(filepath.Base(p)) {
			paths = append(paths, p)
		}
	}

	var rows []struct {
		subject  string
		objectID string
		rights   uint32
	}
	for _, p := range paths {
		var gf grantFile
		mustReadJSON(p, &gf)
		rows = append(rows, struct {
			subject  string
			objectID string
			rights   uint32
		}{gf.Subject, gf.ObjectID, u32(gf.Rights)})
	}
	rowsLoaded := len(rows)

	sorted := sortEvents(log.Events)
	eventsSeen := len(sorted)
	unknown := 0
	for _, ev := range sorted {
		st, ok := intFromAny(ev["apply_step"])
		if !ok || st > pool.CurrentStep {
			continue
		}
		kind, _ := strFromAny(ev["kind"])
		switch kind {
		case "noop":
		case "revoke_bits":
			oid, ok := strFromAny(ev["object_id"])
			if !ok {
				continue
			}
			mk, ok := int64FromAny(ev["mask"])
			if !ok {
				continue
			}
			mask := u32(mk)
			for i := range rows {
				if rows[i].objectID != oid {
					continue
				}
				rows[i].rights = rows[i].rights &^ mask
			}
		default:
			unknown++
		}
	}

	group := map[string]struct {
		comb uint32
		subm map[string]struct{}
	}{}
	for _, r := range rows {
		g := group[r.objectID]
		g.comb |= r.rights
		if g.subm == nil {
			g.subm = map[string]struct{}{}
		}
		g.subm[r.subject] = struct{}{}
		group[r.objectID] = g
	}

	ids := make([]string, 0, len(group))
	for id := range group {
		ids = append(ids, id)
	}
	sort.Strings(ids)

	var objects []objectOut
	for _, id := range ids {
		g := group[id]
		subs := make([]string, 0, len(g.subm))
		for s := range g.subm {
			subs = append(subs, s)
		}
		sort.Strings(subs)
		objects = append(objects, objectOut{
			CombinedRights: int(g.comb),
			ID:             id,
			Subjects:       subs,
		})
	}

	rep := report{
		Objects: objects,
		Summary: map[string]int{
			"events_seen":           eventsSeen,
			"objects_considered":    len(objects),
			"rows_loaded":           rowsLoaded,
			"unknown_event_kinds":   unknown,
		},
	}
	writeFile(filepath.Join(auditRoot, "report.json"), canonicalJSON(rep))
}
