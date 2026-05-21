package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
)

type policyDoc struct {
	AuditDay      int     `json:"audit_day"`
	BinRing       int     `json:"bin_ring"`
	WrapDelta     int     `json:"wrap_delta"`
	AmpFloor      float64 `json:"amp_floor"`
	DeepNullLt    float64 `json:"deep_null_lt"`
	SoftNullLt    float64 `json:"soft_null_lt"`
	DefaultRegion string  `json:"default_region"`
}

type poolDoc struct {
	Drain map[string]float64 `json:"drain"`
}

type regionRow struct {
	ID         string `json:"id"`
	PathPrefix string `json:"path_prefix"`
}

type layoutDoc struct {
	Regions []regionRow `json:"regions"`
}

type incidentDoc struct {
	Events []struct {
		Day     int             `json:"day"`
		Kind    string          `json:"kind"`
		Payload json.RawMessage `json:"payload"`
	} `json:"events"`
}

type itemDoc struct {
	ID          string  `json:"id"`
	BinIndex    int     `json:"bin_index"`
	Magnitude   float64 `json:"magnitude"`
	PhaseDeg    int     `json:"phase_deg"`
	Tier        string  `json:"tier"`
	RegionPath  string  `json:"region_path"`
	Lineage     string  `json:"lineage"`
}

type anchorDoc struct {
	Scales map[string]float64 `json:"scales"`
}

func readJSON(path string, dst any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, dst); err != nil {
		panic(fmt.Sprintf("%s: %v", path, err))
	}
}

func circDist(a, b, ring int) int {
	if ring <= 0 {
		return 0
	}
	x := (a - b) % ring
	if x < 0 {
		x += ring
	}
	y := ring - x
	if x < y {
		return x
	}
	return y
}

type dsu struct {
	p []int
}

func newDSU(n int) *dsu {
	p := make([]int, n)
	for i := range p {
		p[i] = i
	}
	return &dsu{p: p}
}

func (d *dsu) find(x int) int {
	if d.p[x] != x {
		d.p[x] = d.find(d.p[x])
	}
	return d.p[x]
}

func (d *dsu) union(a, b int) {
	ra, rb := d.find(a), d.find(b)
	if ra == rb {
		return
	}
	if ra < rb {
		d.p[rb] = ra
	} else {
		d.p[ra] = rb
	}
}

func round6(x float64) float64 {
	s := fmt.Sprintf("%.6f", x)
	v, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return x
	}
	return v
}

func encodeCanonical(buf *bytes.Buffer, v any) {
	enc(buf, v, 0)
}

func enc(buf *bytes.Buffer, v any, depth int) {
	switch t := v.(type) {
	case nil:
		buf.WriteString("null")
	case int:
		buf.WriteString(strconv.Itoa(t))
	case int64:
		buf.WriteString(strconv.FormatInt(t, 10))
	case bool:
		if t {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
	case float64:
		if math.IsNaN(t) || math.IsInf(t, 0) {
			panic("non-finite float")
		}
		buf.WriteString(strconv.FormatFloat(round6(t), 'f', -1, 64))
	case json.Number:
		buf.WriteString(string(t))
	case string:
		b, _ := json.Marshal(t)
		buf.Write(b)
	case []any:
		buf.WriteByte('[')
		for i, e := range t {
			if i > 0 {
				buf.WriteByte(',')
			}
			enc(buf, e, depth)
		}
		buf.WriteByte(']')
	case map[string]any:
		buf.WriteByte('{')
		keys := make([]string, 0, len(t))
		for k := range t {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		for i, k := range keys {
			if i > 0 {
				buf.WriteByte(',')
			}
			b, _ := json.Marshal(k)
			buf.Write(b)
			buf.WriteByte(':')
			enc(buf, t[k], depth+1)
		}
		buf.WriteByte('}')
	default:
		panic(fmt.Sprintf("unsupported type %T", v))
	}
}

func writeCanonical(path string, root map[string]any) {
	var buf bytes.Buffer
	encodeCanonical(&buf, root)
	buf.WriteByte('\n')
	if err := os.WriteFile(path, buf.Bytes(), 0o644); err != nil {
		panic(err)
	}
}

func loadItems(dir string) []itemDoc {
	ents, err := os.ReadDir(filepath.Join(dir, "items"))
	if err != nil {
		panic(err)
	}
	var names []string
	for _, e := range ents {
		if e.IsDir() {
			continue
		}
		names = append(names, e.Name())
	}
	sort.Strings(names)
	var out []itemDoc
	for _, n := range names {
		var it itemDoc
		readJSON(filepath.Join(dir, "items", n), &it)
		out = append(out, it)
	}
	return out
}

func matchRegion(regions []regionRow, regionPath string, def string) string {
	type row struct {
		id string
		p  string
		l  int
	}
	var rows []row
	for _, r := range regions {
		rows = append(rows, row{id: r.ID, p: r.PathPrefix, l: len(r.PathPrefix)})
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].l != rows[j].l {
			return rows[i].l > rows[j].l
		}
		return rows[i].id < rows[j].id
	})
	for _, r := range rows {
		if len(regionPath) >= r.l && regionPath[:r.l] == r.p {
			return r.id
		}
	}
	return def
}

func anchorProduct(a, b anchorDoc, rid string) float64 {
	pa := 1.0
	pb := 1.0
	if a.Scales != nil {
		if v, ok := a.Scales[rid]; ok {
			pa = v
		}
	}
	if b.Scales != nil {
		if v, ok := b.Scales[rid]; ok {
			pb = v
		}
	}
	return pa * pb
}

func main() {
	data := os.Getenv("PNL_DATA_DIR")
	if data == "" {
		data = "/app/pnl_lab"
	}
	outDir := os.Getenv("PNL_AUDIT_DIR")
	if outDir == "" {
		outDir = "/app/audit"
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		panic(err)
	}

	var pol policyDoc
	readJSON(filepath.Join(data, "policy.json"), &pol)
	var pool poolDoc
	readJSON(filepath.Join(data, "pool_state.json"), &pool)
	var layout layoutDoc
	readJSON(filepath.Join(data, "domain_layout.json"), &layout)
	var inc incidentDoc
	readJSON(filepath.Join(data, "incident_log.json"), &inc)
	var a anchorDoc
	readJSON(filepath.Join(data, "anchors", "a.json"), &a)
	var b anchorDoc
	readJSON(filepath.Join(data, "anchors", "b.json"), &b)

	drain := map[string]float64{}
	for k, v := range pool.Drain {
		drain[k] = v
	}
	suppressed := map[string]struct{}{}
	quarantine := map[string]struct{}{}

	type ev struct {
		day   int
		idx   int
		kind  string
		raw   json.RawMessage
	}
	var events []ev
	for i, e := range inc.Events {
		if e.Day > pol.AuditDay {
			continue
		}
		events = append(events, ev{day: e.Day, idx: i, kind: e.Kind, raw: e.Payload})
	}
	sort.Slice(events, func(i, j int) bool {
		if events[i].day != events[j].day {
			return events[i].day < events[j].day
		}
		return events[i].idx < events[j].idx
	})

	for _, e := range events {
		switch e.kind {
		case "suppress_items":
			var p struct {
				ItemIDs []string `json:"item_ids"`
			}
			if err := json.Unmarshal(e.raw, &p); err != nil {
				panic(err)
			}
			for _, id := range p.ItemIDs {
				suppressed[id] = struct{}{}
			}
		case "quarantine_lineage":
			var p struct {
				Lineage string `json:"lineage"`
			}
			if err := json.Unmarshal(e.raw, &p); err != nil {
				panic(err)
			}
			quarantine[p.Lineage] = struct{}{}
		case "tier_drain":
			var p struct {
				Tiers map[string]float64 `json:"tiers"`
			}
			if err := json.Unmarshal(e.raw, &p); err != nil {
				panic(err)
			}
			for k, v := range p.Tiers {
				drain[k] = v
			}
		default:
			panic(fmt.Sprintf("unknown incident kind %q", e.kind))
		}
	}

	R := pol.BinRing
	if R <= 0 {
		panic("bin_ring must be positive")
	}
	dsuU := newDSU(R)
	for i := 0; i < R; i++ {
		for j := i + 1; j < R; j++ {
			if circDist(i, j, R) <= pol.WrapDelta {
				dsuU.union(i, j)
			}
		}
	}

	items := loadItems(data)
	binToItems := map[int][]string{}
	for _, it := range items {
		b := it.BinIndex % R
		if b < 0 {
			b += R
		}
		binToItems[b] = append(binToItems[b], it.ID)
	}
	for b := range binToItems {
		sort.Strings(binToItems[b])
	}

	compBins := map[int][]int{}
	for b := 0; b < R; b++ {
		r := dsuU.find(b)
		compBins[r] = append(compBins[r], b)
	}
	var roots []int
	for r := range compBins {
		roots = append(roots, r)
	}
	sort.Ints(roots)

	var edges []any
	for i := 0; i < R; i++ {
		for j := i + 1; j < R; j++ {
			if dsuU.find(i) != dsuU.find(j) {
				continue
			}
			if circDist(i, j, R) <= pol.WrapDelta {
				edges = append(edges, map[string]any{"bin_hi": j, "bin_lo": i})
			}
		}
	}
	bg := map[string]any{
		"bin_ring": R,
		"edges":    edges,
	}
	writeCanonical(filepath.Join(outDir, "bin_graph.json"), bg)

	var comps []any
	contributorsUsed := map[string]struct{}{}
	for _, root := range roots {
		bins := compBins[root]
		sort.Ints(bins)
		anchorBin := bins[0]

		var contributors []string
		for _, b := range bins {
			for _, id := range binToItems[b] {
				if _, ok := suppressed[id]; ok {
					continue
				}
				var it *itemDoc
				for k := range items {
					if items[k].ID == id {
						it = &items[k]
						break
					}
				}
				if it == nil {
					continue
				}
				if _, ok := quarantine[it.Lineage]; ok {
					continue
				}
				contributors = append(contributors, id)
			}
		}
		sort.Strings(contributors)

		var re, im float64
		for _, id := range contributors {
			var it itemDoc
			for _, x := range items {
				if x.ID == id {
					it = x
					break
				}
			}
			rid := matchRegion(layout.Regions, it.RegionPath, pol.DefaultRegion)
			ap := anchorProduct(a, b, rid)
			dv := 0.0
			if v, ok := drain[it.Tier]; ok {
				dv = v
			}
			if dv < 0 {
				dv = 0
			}
			if dv > 1 {
				dv = 1
			}
			mag := it.Magnitude * ap * (1.0 - dv)
			if mag < pol.AmpFloor {
				mag = pol.AmpFloor
			}
			th := float64(normDeg(it.PhaseDeg)) * math.Pi / 180.0
			re += mag * math.Cos(th)
			im += mag * math.Sin(th)
			contributorsUsed[id] = struct{}{}
		}

		re = canonFloat(re)
		im = canonFloat(im)

		cls := "vacant"
		rms := 0.0
		if len(contributors) > 0 {
			rms = math.Hypot(re, im)
			rms = canonFloat(rms)
			if rms < pol.DeepNullLt {
				cls = "deep_null"
			} else if rms < pol.SoftNullLt {
				cls = "soft_null"
			} else {
				cls = "energized"
			}
		}

		row := map[string]any{
			"anchor_bin":     anchorBin,
			"bins":           intsToAny(bins),
			"class":          cls,
			"contributors":   strsToAny(contributors),
			"phasor":         map[string]any{"im": canonFloat(im), "re": canonFloat(re)},
			"rms_mag":        canonFloat(rms),
			"root_bin":       root,
			"suppressed_ids": strsToAny(collectSuppressedInBins(bins, binToItems, suppressed)),
		}
		comps = append(comps, row)
	}

	sort.Slice(comps, func(i, j int) bool {
		ci := comps[i].(map[string]any)
		cj := comps[j].(map[string]any)
		ai := ci["anchor_bin"].(int)
		aj := cj["anchor_bin"].(int)
		if ai != aj {
			return ai < aj
		}
		return ci["root_bin"].(int) < cj["root_bin"].(int)
	})

	nm := map[string]any{"components": comps}
	writeCanonical(filepath.Join(outDir, "null_manifest.json"), nm)

	counts := map[string]int{}
	for _, c := range comps {
		row := c.(map[string]any)
		cls := row["class"].(string)
		counts[cls]++
	}
	sm := map[string]any{
		"audit_day":               pol.AuditDay,
		"bin_ring":                R,
		"components_energized":    counts["energized"],
		"components_total":        len(comps),
		"components_vacant":       counts["vacant"],
		"deep_null_components":    counts["deep_null"],
		"items_total":             len(items),
		"quarantined_lineages":    len(quarantine),
		"soft_null_components":    counts["soft_null"],
		"suppressed_items":        len(suppressed),
		"unique_contributors":     len(contributorsUsed),
		"wrap_delta":              pol.WrapDelta,
	}
	writeCanonical(filepath.Join(outDir, "summary.json"), sm)
}

func intsToAny(xs []int) []any {
	out := make([]any, len(xs))
	for i, v := range xs {
		out[i] = v
	}
	return out
}

func strsToAny(xs []string) []any {
	out := make([]any, len(xs))
	for i, v := range xs {
		out[i] = v
	}
	return out
}

func normDeg(deg int) int {
	d := deg % 360
	if d < 0 {
		d += 360
	}
	return d
}

func canonFloat(x float64) float64 {
	v := round6(x)
	if v == 0 {
		return 0
	}
	return v
}

func collectSuppressedInBins(bins []int, binToItems map[int][]string, suppressed map[string]struct{}) []string {
	var out []string
	seen := map[string]struct{}{}
	for _, b := range bins {
		for _, id := range binToItems[b] {
			if _, ok := suppressed[id]; !ok {
				continue
			}
			if _, ok := seen[id]; ok {
				continue
			}
			seen[id] = struct{}{}
			out = append(out, id)
		}
	}
	sort.Strings(out)
	return out
}
