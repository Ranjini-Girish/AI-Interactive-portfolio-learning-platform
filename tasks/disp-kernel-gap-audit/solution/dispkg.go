package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
)

type knot struct {
	Lambda int `json:"lambda_q"`
	N      int `json:"n_q"`
}

type sample struct {
	SampleID string `json:"sample_id"`
	LambdaQ  int    `json:"lambda_q"`
	NMeas    int    `json:"n_meas_q"`
	PhaseQ   int    `json:"phase_q"`
	BandID   string `json:"band_id"`
}

type trackFile struct {
	Samples []sample `json:"samples"`
}

type catTrack struct {
	TrackID string `json:"track_id"`
	Path    string `json:"path"`
}

type catalog struct {
	Tracks []catTrack `json:"tracks"`
}

type event map[string]any

type incidents struct {
	Events []event `json:"events"`
}

func sha256File(path string) (string, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	h := sha256.Sum256(b)
	return fmt.Sprintf("%x", h), nil
}

func readJSON(path string, out any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.UseNumber()
	return dec.Decode(out)
}

func asInt(v any) int {
	switch t := v.(type) {
	case json.Number:
		i, _ := t.Int64()
		return int(i)
	case float64:
		return int(t)
	case int:
		return t
	case string:
		i, _ := strconv.Atoi(t)
		return i
	default:
		return 0
	}
}

func asBool(v any) bool {
	b, ok := v.(bool)
	return ok && b
}

func interpN(ks []knot, L int, diags map[string]struct{}) int {
	if len(ks) == 0 {
		return 0
	}
	for _, k := range ks {
		if k.Lambda == L {
			return k.N
		}
	}
	if L < ks[0].Lambda {
		diags["extrap_low"] = struct{}{}
		return ks[0].N
	}
	last := ks[len(ks)-1]
	if L > last.Lambda {
		diags["extrap_high"] = struct{}{}
		return last.N
	}
	for i := 0; i < len(ks)-1; i++ {
		l0, n0 := ks[i].Lambda, ks[i].N
		l1, n1 := ks[i+1].Lambda, ks[i+1].N
		if l0 < L && L < l1 {
			step := (n1 - n0) * (L - l0) / (l1 - l0)
			return n0 + step
		}
	}
	return last.N
}

func sortedKeys(m map[string]struct{}) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func canonJSON(v any) ([]byte, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(true)
	if err := enc.Encode(v); err != nil {
		return nil, err
	}
	b := buf.Bytes()
	if len(b) > 0 && b[len(b)-1] == '\n' {
		b = b[:len(b)-1]
	}
	return append(b, '\n'), nil
}

func main() {
	dataDir := os.Getenv("DISPK_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/disp_kernel_lab"
	}
	auditDir := os.Getenv("DISPK_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		panic(err)
	}

	var policy map[string]any
	if err := readJSON(filepath.Join(dataDir, "policy.json"), &policy); err != nil {
		panic(err)
	}
	var knotsWrap struct {
		Knots []knot `json:"knots"`
	}
	if err := readJSON(filepath.Join(dataDir, "knots.json"), &knotsWrap); err != nil {
		panic(err)
	}
	var cat catalog
	if err := readJSON(filepath.Join(dataDir, "catalog.json"), &cat); err != nil {
		panic(err)
	}
	var inc incidents
	if err := readJSON(filepath.Join(dataDir, "incidents.json"), &inc); err != nil {
		panic(err)
	}
	var pool map[string]any
	if err := readJSON(filepath.Join(dataDir, "pool_state.json"), &pool); err != nil {
		panic(err)
	}

	day := asInt(policy["current_day"])
	base := asInt(policy["base"])
	init := asInt(policy["init"])
	mod := asInt(policy["modulus"])
	jump := asInt(policy["phase_jump_q"])
	collapse, _ := policy["collapse_lambda"].(bool)
	bandBias := map[string]int{}
	if bb, ok := policy["band_bias"].(map[string]any); ok {
		for k, v := range bb {
			bandBias[k] = asInt(v)
		}
	}

	var capPtr *int
	if v, ok := pool["terminal_sum_cap"]; ok && v != nil {
		c := asInt(v)
		capPtr = &c
	}

	type pair struct{ tid, sid string }
	suppressed := map[pair]struct{}{}
	bandInc := map[string]int{}
	compromised := map[string]struct{}{}

	for _, ev := range inc.Events {
		kind, _ := ev["kind"].(string)
		switch kind {
		case "suppress_sample":
			sd, ed := asInt(ev["start_day"]), asInt(ev["end_day"])
			if sd <= day && day <= ed {
				suppressed[pair{ev["track_id"].(string), ev["sample_id"].(string)}] = struct{}{}
			}
		case "bias_band":
			sd, ed := asInt(ev["start_day"]), asInt(ev["end_day"])
			if sd <= day && day <= ed {
				bid := ev["band_id"].(string)
				bandInc[bid] = bandInc[bid] + asInt(ev["bias_q"])
			}
		case "compromise_track":
			if asBool(ev["accepted"]) && day >= asInt(ev["day"]) {
				compromised[ev["track_id"].(string)] = struct{}{}
			}
		}
	}

	sort.Slice(cat.Tracks, func(i, j int) bool {
		return cat.Tracks[i].TrackID < cat.Tracks[j].TrackID
	})

	totalCataloged := 0
	rollups := make([]map[string]any, 0, len(cat.Tracks))
	rawDigest := map[string]int{}

	for _, tr := range cat.Tracks {
		tid := tr.TrackID
		var tf trackFile
		if err := readJSON(filepath.Join(dataDir, tr.Path), &tf); err != nil {
			panic(err)
		}
		totalCataloged += len(tf.Samples)

		if _, q := compromised[tid]; q {
			rollups = append(rollups, map[string]any{
				"diagnostics":      []string{"track_compromised"},
				"gap_mix_steps":    0,
				"samples_kept":     0,
				"status":           "quarantined",
				"terminal_digest":  0,
				"track_id":         tid,
			})
			continue
		}

		kept := make([]sample, 0, len(tf.Samples))
		for _, s := range tf.Samples {
			if _, bad := suppressed[pair{tid, s.SampleID}]; bad {
				continue
			}
			kept = append(kept, s)
		}

		diags := map[string]struct{}{}
		if collapse {
			byLam := map[int][]sample{}
			for _, s := range kept {
				byLam[s.LambdaQ] = append(byLam[s.LambdaQ], s)
			}
			merged := make([]sample, 0, len(byLam))
			lams := make([]int, 0, len(byLam))
			for lam := range byLam {
				lams = append(lams, lam)
			}
			sort.Ints(lams)
			for _, lam := range lams {
				grp := byLam[lam]
				sort.Slice(grp, func(i, j int) bool { return grp[i].SampleID < grp[j].SampleID })
				merged = append(merged, grp[0])
				if len(grp) > 1 {
					diags["lambda_collapsed"] = struct{}{}
				}
			}
			kept = merged
		}

		sort.Slice(kept, func(i, j int) bool {
			if kept[i].LambdaQ != kept[j].LambdaQ {
				return kept[i].LambdaQ < kept[j].LambdaQ
			}
			return kept[i].SampleID < kept[j].SampleID
		})

		for i := 0; i < len(kept)-1; i++ {
			d := kept[i+1].PhaseQ - kept[i].PhaseQ
			if d < 0 {
				d = -d
			}
			if d > jump {
				diags["phase_discontinuity"] = struct{}{}
				break
			}
		}

		h := init % mod
		for _, s := range kept {
			local := map[string]struct{}{}
			nI := interpN(knotsWrap.Knots, s.LambdaQ, local)
			for k := range local {
				diags[k] = struct{}{}
			}
			signed := s.NMeas - nI
			if _, ok := bandBias[s.BandID]; ok {
				signed += bandBias[s.BandID]
			} else {
				diags["unknown_band"] = struct{}{}
			}
			signed += bandInc[s.BandID]
			gap := signed
			if gap < 0 {
				gap = -gap
			}
			h = (h*base + gap) % mod
		}

		rawDigest[tid] = h
		dlist := sortedKeys(diags)
		rollups = append(rollups, map[string]any{
			"diagnostics":     dlist,
			"gap_mix_steps":   len(kept),
			"samples_kept":    len(kept),
			"status":          "ok",
			"terminal_digest": h,
			"track_id":        tid,
		})
	}

	sumRaw := 0
	for _, r := range rollups {
		if r["status"] == "ok" {
			sumRaw += asInt(r["terminal_digest"])
		}
	}
	capApplied := false
	var scaledSum any = nil
	if capPtr != nil && sumRaw > *capPtr {
		capApplied = true
		ss := 0
		c := *capPtr
		for i := range rollups {
			if rollups[i]["status"] != "ok" {
				continue
			}
			tid := rollups[i]["track_id"].(string)
			raw := rawDigest[tid]
			nv := 0
			if sumRaw > 0 {
				nv = (raw * c) / sumRaw
			}
			rollups[i]["terminal_digest"] = nv
			ss += nv
		}
		scaledSum = ss
	} else {
		for i := range rollups {
			if rollups[i]["status"] == "ok" {
				tid := rollups[i]["track_id"].(string)
				rollups[i]["terminal_digest"] = rawDigest[tid]
			}
		}
	}

	nQuar := 0
	keptTotal := 0
	for _, r := range rollups {
		if r["status"] == "quarantined" {
			nQuar++
		}
		keptTotal += asInt(r["samples_kept"])
	}

	meta := map[string]any{
		"base":               base,
		"catalog_sha256":     must(sha256File(filepath.Join(dataDir, "catalog.json"))),
		"current_day":        day,
		"incidents_sha256":   must(sha256File(filepath.Join(dataDir, "incidents.json"))),
		"init":               init,
		"knots_sha256":       must(sha256File(filepath.Join(dataDir, "knots.json"))),
		"modulus":            mod,
		"policy_sha256":      must(sha256File(filepath.Join(dataDir, "policy.json"))),
		"pool_sha256":        must(sha256File(filepath.Join(dataDir, "pool_state.json"))),
	}
	summary := map[string]any{
		"cap_applied":               capApplied,
		"quarantined_tracks":        nQuar,
		"scaled_sum":                scaledSum,
		"total_samples_cataloged":   totalCataloged,
		"total_samples_kept":        keptTotal,
		"tracks":                    len(rollups),
	}
	out := map[string]any{
		"meta":           meta,
		"summary":        summary,
		"track_rollups":  rollups,
	}
	bout, err := canonJSON(out)
	if err != nil {
		panic(err)
	}
	outPath := filepath.Join(auditDir, "disp_gap.json")
	if err := os.WriteFile(outPath, bout, 0o644); err != nil {
		panic(err)
	}
}

func must(s string, e error) string {
	if e != nil {
		panic(e)
	}
	return s
}
