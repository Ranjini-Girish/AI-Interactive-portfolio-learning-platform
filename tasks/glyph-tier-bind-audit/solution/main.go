package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func getenv(key, def string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return def
}

func modNonneg(x, m int) int {
	r := x % m
	if r < 0 {
		return r + m
	}
	return r
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
	return append(out, '\n')
}

func writeJSON(path string, v any) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		panic(err)
	}
	if err := os.WriteFile(path, canonicalJSON(v), 0o644); err != nil {
		panic(err)
	}
}

func readJSON(path string, out any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, out); err != nil {
		panic(fmt.Sprintf("%s: %v", path, err))
	}
}

func histRows(hist map[int]int) []map[string]int {
	var bins []int
	for b, t := range hist {
		if t > 0 {
			bins = append(bins, b)
		}
	}
	sort.Ints(bins)
	rows := make([]map[string]int, 0, len(bins))
	for _, b := range bins {
		rows = append(rows, map[string]int{"bin": b, "tally": hist[b]})
	}
	return rows
}

func main() {
	root := getenv("GTB_DATA_DIR", "/app/gtb_lab")
	audit := getenv("GTB_AUDIT_DIR", "/app/audit")

	var policy struct {
		TierStride   int  `json:"tier_stride"`
		MixCoeff     int  `json:"mix_coeff"`
		BlendMod     int  `json:"blend_mod"`
		ChainSpan    int  `json:"chain_span"`
		CooldownMod  int  `json:"cooldown_mod"`
		TierSpill    bool `json:"tier_spill"`
		CooldownEcho bool `json:"cooldown_echo"`
		BindWalk     bool `json:"bind_walk"`
	}
	readJSON(filepath.Join(root, "policy.json"), &policy)

	var pool struct {
		EpochSerial int `json:"epoch_serial"`
		RingMod     int `json:"ring_mod"`
	}
	readJSON(filepath.Join(root, "pool_state.json"), &pool)

	var manifest struct {
		CalTag string `json:"cal_tag"`
		RunTag string `json:"run_tag"`
	}
	readJSON(filepath.Join(root, "manifest.json"), &manifest)

	var epochs struct {
		CurrentEpoch int `json:"current_epoch"`
	}
	readJSON(filepath.Join(root, "epochs.json"), &epochs)

	var bind struct {
		Edges []struct {
			From string `json:"from"`
			To   string `json:"to"`
		} `json:"edges"`
	}
	readJSON(filepath.Join(root, "bind_edges.json"), &bind)

	var north struct {
		LaneBias int `json:"lane_bias"`
	}
	readJSON(filepath.Join(root, "anchors/north.json"), &north)

	var south struct {
		LaneBias int `json:"lane_bias"`
	}
	readJSON(filepath.Join(root, "anchors/south.json"), &south)

	var incidents struct {
		Masks []struct {
			SampleID  string `json:"sample_id"`
			ZeroSlots []int  `json:"zero_slots"`
		} `json:"masks"`
	}
	readJSON(filepath.Join(root, "incident_log.json"), &incidents)

	masks := map[string]map[int]struct{}{}
	for _, row := range incidents.Masks {
		if masks[row.SampleID] == nil {
			masks[row.SampleID] = map[int]struct{}{}
		}
		for _, z := range row.ZeroSlots {
			masks[row.SampleID][z] = struct{}{}
		}
	}

	wLane := policy.TierStride
	wFold := wLane
	if manifest.CalTag != manifest.RunTag {
		wFold = (wLane + 1) / 2
	}
	staleThresh := epochs.CurrentEpoch - 1

	samplePaths, err := filepath.Glob(filepath.Join(root, "samples", "sample_*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(samplePaths)

	samplesOut := map[string][]map[string]int{}
	histMaps := map[string]map[int]int{}
	spillBin := map[string]int{}
	var tailParts []string
	totalGlyphs := 0
	staleTotal := 0

	for _, sp := range samplePaths {
		var doc struct {
			SampleID  string `json:"sample_id"`
			Epoch     int    `json:"epoch"`
			TierShift int    `json:"tier_shift"`
			Glyphs    []int  `json:"glyphs"`
		}
		readJSON(sp, &doc)
		sid := doc.SampleID
		stale := doc.Epoch < staleThresh
		if stale {
			staleTotal++
		}
		glyphs := append([]int(nil), doc.Glyphs...)
		n := len(glyphs)
		if m, ok := masks[sid]; ok {
			for zi := range m {
				if zi >= 0 && zi < n {
					glyphs[zi] =  0
				}
			}
		}
		adj := make([]int, n)
		for i := range glyphs {
			adj[i] = glyphs[i] + modNonneg(north.LaneBias*i+south.LaneBias, wLane)
		}
		skew := modNonneg(modNonneg(pool.EpochSerial, policy.BlendMod)*policy.MixCoeff+doc.TierShift+modNonneg(pool.RingMod, wFold), wFold)
		span := policy.ChainSpan
		if stale {
			span *= 2
		}
		hist := map[int]int{}
		xacc := 0
		for k := 1; k <= n; k++ {
			xacc ^= adj[k-1]
			folded := ((xacc + skew) / wFold) / span
			hist[folded]++
			if policy.CooldownEcho && k%policy.CooldownMod == 0 {
				hist[folded]++
			}
		}
		if policy.TierSpill && len(hist) > 0 && !stale {
			bMax := 0
			for b := range hist {
				if b > bMax {
					bMax = b
				}
			}
			hist[bMax] += modNonneg(north.LaneBias+south.LaneBias+doc.TierShift, wFold)
			spillBin[sid] = bMax
		}
		histMaps[sid] = hist
		samplesOut[sid] = histRows(hist)
		totalGlyphs += n
		tailParts = append(tailParts, fmt.Sprintf("%s:%d", sid, xacc))
	}

	var bindEvents []map[string]any
	bindTotal := 0
	if policy.BindWalk {
		edges := append([]struct{ From, To string }{}, bind.Edges...)
		sort.Slice(edges, func(i, j int) bool {
			if edges[i].From != edges[j].From {
				return edges[i].From < edges[j].From
			}
			return edges[i].To < edges[j].To
		})
		for _, e := range edges {
			b, ok := spillBin[e.To]
			if !ok {
				continue
			}
			h := histMaps[e.From]
			if h == nil {
				h = map[int]int{}
				histMaps[e.From] = h
			}
			h[b]++
			samplesOut[e.From] = histRows(h)
			bindEvents = append(bindEvents, map[string]any{"bin": b, "delta": 1, "from": e.From, "to": e.To})
			bindTotal++
		}
	}

	sort.Strings(tailParts)
	sum := sha256.Sum256([]byte(strings.Join(tailParts, ",")))

	writeJSON(filepath.Join(audit, "tier_bins.json"), map[string]any{"samples": samplesOut})
	writeJSON(filepath.Join(audit, "bind_events.json"), map[string]any{"events": bindEvents})
	writeJSON(filepath.Join(audit, "summary.json"), map[string]any{
		"bind_propagate_total": bindTotal,
		"blend_mod":            policy.BlendMod,
		"chain_span":           policy.ChainSpan,
		"cooldown_echo":        policy.CooldownEcho,
		"cooldown_mod":         policy.CooldownMod,
		"effective_fold_stride": wFold,
		"epoch_serial":         pool.EpochSerial,
		"mix_coeff":            policy.MixCoeff,
		"ring_mod":             pool.RingMod,
		"stale_sample_total":   staleTotal,
		"tier_spill":           policy.TierSpill,
		"tier_stride":          wLane,
		"tail_epoch_sha":       hex.EncodeToString(sum[:]),
		"total_glyphs":         totalGlyphs,
	})
}
