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
	RingOrder []string `json:"ring_order"`
}

type indexFile struct {
	SegmentFiles []string `json:"segment_files"`
}

type policy struct {
	SchemaVersion  int `json:"schema_version"`
	EvaluationDay  int `json:"evaluation_day"`
	Quorum         int `json:"quorum"`
	WindingModulus int `json:"winding_modulus"`
	AnchorWeight   int `json:"anchor_weight"`
}

type poolState struct {
	TierCap map[string]int `json:"tier_cap"`
}

type incidentWindow struct {
	UntilDay int      `json:"until_day"`
	Tiers    []string `json:"tiers"`
	Relax    int      `json:"relax"`
}

type incidentLog struct {
	Windows []incidentWindow `json:"windows"`
}

type anchor struct {
	SegStart string `json:"seg_start"`
	SegEnd   string `json:"seg_end"`
}

type segment struct {
	SegmentID string `json:"segment_id"`
	Tier      string `json:"tier"`
	Witness   int    `json:"witness"`
	Flux      int    `json:"flux"`
}

func main() {
	dataDir := os.Getenv("RWQ_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/rwq_lab"
	}
	auditDir := os.Getenv("RWQ_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		panic(err)
	}

	layout := mustReadJSON[domainLayout](filepath.Join(dataDir, "domain_layout.json"))
	idx := mustReadJSON[indexFile](filepath.Join(dataDir, "index.json"))
	pol := mustReadJSON[policy](filepath.Join(dataDir, "policy.json"))
	pool := mustReadJSON[poolState](filepath.Join(dataDir, "pool_state.json"))
	inc := mustReadJSON[incidentLog](filepath.Join(dataDir, "incident_log.json"))
	anLo := mustReadJSON[anchor](filepath.Join(dataDir, "anchors", "lo.json"))
	anHi := mustReadJSON[anchor](filepath.Join(dataDir, "anchors", "hi.json"))

	if pol.WindingModulus < 2 || pol.Quorum < 0 || pol.AnchorWeight < 0 {
		panic("invalid policy")
	}

	pos := map[string]int{}
	for i, id := range layout.RingOrder {
		pos[id] = i
	}
	n := len(layout.RingOrder)

	segments := map[string]segment{}
	for _, rel := range idx.SegmentFiles {
		s := mustReadJSON[segment](filepath.Join(dataDir, rel))
		if s.SegmentID == "" {
			panic("empty segment_id")
		}
		segments[s.SegmentID] = s
	}
	for _, id := range layout.RingOrder {
		if _, ok := segments[id]; !ok {
			panic("missing segment for ring id " + id)
		}
	}
	if len(segments) != len(layout.RingOrder) {
		panic("segment count mismatch")
	}

	sumFlux := 0
	for _, id := range layout.RingOrder {
		sumFlux += segments[id].Flux
	}
	mod := pol.WindingModulus
	windingOk := ((sumFlux%mod)+mod)%mod == 0

	anchorHits := map[string]int{}
	for _, id := range layout.RingOrder {
		anchorHits[id] = 0
	}
	for _, a := range []anchor{anLo, anHi} {
		cover := cyclicCover(pos, n, a.SegStart, a.SegEnd)
		for _, id := range cover {
			anchorHits[id]++
		}
	}

	effectiveWitness := map[string]int{}
	effectiveQuorum := map[string]int{}
	for _, id := range layout.RingOrder {
		s := segments[id]
		effectiveWitness[id] = s.Witness + pol.AnchorWeight*anchorHits[id]
		bestRelax := 0
		for _, w := range inc.Windows {
			if pol.EvaluationDay > w.UntilDay {
				continue
			}
			for _, t := range w.Tiers {
				if t == s.Tier && w.Relax > bestRelax {
					bestRelax = w.Relax
				}
			}
		}
		eq := pol.Quorum - bestRelax
		if eq < 0 {
			eq = 0
		}
		effectiveQuorum[id] = eq
	}

	verdict := map[string]string{}
	if !windingOk {
		for _, id := range layout.RingOrder {
			verdict[id] = "winding_violation"
		}
	} else {
		for _, id := range layout.RingOrder {
			if effectiveWitness[id] >= effectiveQuorum[id] {
				verdict[id] = "quorum_ok"
			} else {
				verdict[id] = "quorum_starved"
			}
		}
		tierNames := make([]string, 0, len(pool.TierCap))
		for t := range pool.TierCap {
			tierNames = append(tierNames, t)
		}
		sort.Strings(tierNames)
		for _, tier := range tierNames {
			capv, ok := pool.TierCap[tier]
			if !ok {
				continue
			}
			for {
				sum := 0
				cands := make([]string, 0)
				for _, id := range layout.RingOrder {
					if segments[id].Tier != tier {
						continue
					}
					if verdict[id] != "quorum_ok" {
						continue
					}
					sum += effectiveWitness[id]
					cands = append(cands, id)
				}
				if sum <= capv || len(cands) == 0 {
					break
				}
				victim := ""
				bestPos := -1
				for _, id := range cands {
					if p := pos[id]; p > bestPos {
						bestPos = p
						victim = id
					}
				}
				if victim == "" {
					break
				}
				verdict[victim] = "tier_trimmed"
			}
		}
		for _, id := range layout.RingOrder {
			if verdict[id] == "quorum_ok" {
				verdict[id] = "passed"
			}
		}
	}

	diagnostics := []map[string]any{}
	for _, id := range layout.RingOrder {
		v := verdict[id]
		switch v {
		case "winding_violation":
			diagnostics = append(diagnostics, map[string]any{"code": "WINDING", "segment_id": id})
		case "quorum_starved":
			diagnostics = append(diagnostics, map[string]any{"code": "QUORUM", "segment_id": id})
		case "tier_trimmed":
			diagnostics = append(diagnostics, map[string]any{"code": "TRIM", "segment_id": id})
		}
	}
	sort.Slice(diagnostics, func(i, j int) bool {
		a, b := diagnostics[i], diagnostics[j]
		sa := a["segment_id"].(string)
		sb := b["segment_id"].(string)
		if sa != sb {
			return sa < sb
		}
		return a["code"].(string) < b["code"].(string)
	})

	passed := 0
	starved := 0
	trimmed := 0
	wv := 0
	for _, id := range layout.RingOrder {
		switch verdict[id] {
		case "passed":
			passed++
		case "quorum_starved":
			starved++
		case "tier_trimmed":
			trimmed++
		case "winding_violation":
			wv++
		}
	}

	summary := map[string]any{
		"diagnostics_total":       len(diagnostics),
		"passed_count":            passed,
		"quorum_starved_count":    starved,
		"schema_version":          pol.SchemaVersion,
		"segments_total":          len(layout.RingOrder),
		"tier_trimmed_count":      trimmed,
		"winding_ok":              windingOk,
		"winding_violation_count": wv,
	}

	rows := make([]any, 0, len(layout.RingOrder))
	for _, id := range layout.RingOrder {
		s := segments[id]
		rows = append(rows, map[string]any{
			"effective_quorum":  effectiveQuorum[id],
			"effective_witness": effectiveWitness[id],
			"segment_id":        id,
			"tier":              s.Tier,
			"verdict":           verdict[id],
		})
	}

	diagAny := make([]any, len(diagnostics))
	for i, d := range diagnostics {
		diagAny[i] = d
	}

	segOut := map[string]any{
		"diagnostics":    diagAny,
		"schema_version": pol.SchemaVersion,
		"segments":       rows,
	}

	mustWriteJSON(filepath.Join(auditDir, "summary.json"), summary)
	mustWriteJSON(filepath.Join(auditDir, "segment_verdicts.json"), segOut)
}

func cyclicCover(pos map[string]int, n int, start, end string) []string {
	a := pos[start]
	b := pos[end]
	out := make([]string, 0, n)
	if a <= b {
		for i := a; i <= b; i++ {
			out = append(out, ringID(pos, n, i))
		}
		return out
	}
	for i := a; i < n; i++ {
		out = append(out, ringID(pos, n, i))
	}
	for i := 0; i <= b; i++ {
		out = append(out, ringID(pos, n, i))
	}
	return out
}

func ringID(pos map[string]int, n int, idx int) string {
	for id, p := range pos {
		if p == idx {
			return id
		}
	}
	panic("bad idx")
}

func mustReadJSON[T any](path string) T {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	var v T
	if err := json.Unmarshal(b, &v); err != nil {
		panic(err)
	}
	return v
}

func mustWriteJSON(path string, v any) {
	b, err := marshalMinified(v)
	if err != nil {
		panic(err)
	}
	if err := os.WriteFile(path, append(b, '\n'), 0o644); err != nil {
		panic(err)
	}
}

func marshalMinified(v any) ([]byte, error) {
	var buf bytes.Buffer
	if err := writeMin(&buf, v); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func writeMin(buf *bytes.Buffer, v any) error {
	switch t := v.(type) {
	case nil:
		buf.WriteString("null")
	case bool:
		if t {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
	case float64:
		buf.WriteString(fmt.Sprintf("%.0f", t))
	case int:
		buf.WriteString(fmt.Sprintf("%d", t))
	case int64:
		buf.WriteString(fmt.Sprintf("%d", t))
	case string:
		enc, _ := json.Marshal(t)
		buf.Write(enc)
	case []any:
		buf.WriteByte('[')
		for i, e := range t {
			if i > 0 {
				buf.WriteByte(',')
			}
			if err := writeMin(buf, e); err != nil {
				return err
			}
		}
		buf.WriteByte(']')
	case map[string]any:
		keys := make([]string, 0, len(t))
		for k := range t {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		buf.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				buf.WriteByte(',')
			}
			enc, _ := json.Marshal(k)
			buf.Write(enc)
			buf.WriteByte(':')
			if err := writeMin(buf, t[k]); err != nil {
				return err
			}
		}
		buf.WriteByte('}')
	default:
		return fmt.Errorf("unsupported type %T", v)
	}
	return nil
}
