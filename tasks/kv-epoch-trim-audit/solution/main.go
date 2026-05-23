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
	root := getenv("KET_DATA_DIR", "/app/ket_lab")
	audit := getenv("KET_AUDIT_DIR", "/app/audit")

	var policy struct {
		TrimWindow  int  `json:"trim_window"`
		EpochStride int  `json:"epoch_stride"`
		FoldDiv     int  `json:"fold_div"`
		HalveMod    int  `json:"halve_mod"`
		MixCoeff    int  `json:"mix_coeff"`
		BlendMod    int  `json:"blend_mod"`
		EpochSpill  bool `json:"epoch_spill"`
		TrimEcho    bool `json:"trim_echo"`
		LinkWalk    bool `json:"link_walk"`
	}
	readJSON(filepath.Join(root, "policy.json"), &policy)

	var pool struct {
		LedgerEpoch int `json:"ledger_epoch"`
		RingSlot    int `json:"ring_slot"`
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

	var links struct {
		Edges []struct {
			From string `json:"from"`
			To   string `json:"to"`
		} `json:"edges"`
	}
	readJSON(filepath.Join(root, "spill_links.json"), &links)

	var east struct {
		LaneAdd int `json:"lane_add"`
	}
	readJSON(filepath.Join(root, "anchors/east.json"), &east)

	var west struct {
		LaneAdd int `json:"lane_add"`
	}
	readJSON(filepath.Join(root, "anchors/west.json"), &west)

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

	sLane := policy.EpochStride
	sFold := sLane
	if manifest.CalTag != manifest.RunTag {
		sFold = (sLane + 1) / 2
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
	totalValues := 0
	staleTotal := 0

	for _, sp := range samplePaths {
		var doc struct {
			SampleID  string `json:"sample_id"`
			Epoch     int    `json:"epoch"`
			EpochTag  int    `json:"epoch_tag"`
			Values    []int  `json:"values"`
		}
		readJSON(sp, &doc)
		sid := doc.SampleID
		stale := doc.Epoch < staleThresh
		if stale {
			staleTotal++
		}
		values := append([]int(nil), doc.Values...)
		n := len(values)
		if m, ok := masks[sid]; ok {
			for zi := range m {
				if zi >= 0 && zi < n {
					values[zi] = 0
				}
			}
		}
		adj := make([]int, n)
		for i := range values {
			adj[i] = values[i] + modNonneg(east.LaneAdd*i+west.LaneAdd, sLane)
		}
		skew := modNonneg(modNonneg(pool.LedgerEpoch, policy.BlendMod)*policy.MixCoeff+doc.EpochTag+modNonneg(pool.RingSlot, sFold), sFold)
		hist := map[int]int{}
		window := make([]int, 0, policy.TrimWindow)
		var runningExtreme *int
		for k := 1; k <= n; k++ {
			window = append(window, adj[k-1])
			if len(window) > policy.TrimWindow {
				window = window[1:]
			}
			mk := window[0]
			if stale {
				for _, v := range window[1:] {
					if v < mk {
						mk = v
					}
				}
				if runningExtreme == nil || mk > *runningExtreme {
					v := mk
					runningExtreme = &v
				}
			} else {
				for _, v := range window[1:] {
					if v > mk {
						mk = v
					}
				}
				if runningExtreme == nil || mk < *runningExtreme {
					v := mk
					runningExtreme = &v
				}
			}
			folded := ((mk + skew) / sFold) / policy.FoldDiv
			hist[folded]++
			if policy.TrimEcho && k%policy.HalveMod == 0 {
				hist[folded]++
			}
			if policy.TrimEcho && runningExtreme != nil && mk == *runningExtreme {
				hist[folded]++
			}
		}
		if policy.EpochSpill && len(hist) > 0 && !stale {
			bMin := 0
			for b := range hist {
				if b < bMin {
					bMin = b
				}
			}
			hist[bMin] += modNonneg(pool.LedgerEpoch+doc.EpochTag, sFold)
			spillBin[sid] = bMin
		}
		histMaps[sid] = hist
		samplesOut[sid] = histRows(hist)
		totalValues += n
		rm := 0
		if runningExtreme != nil {
			rm = *runningExtreme
		}
		tailParts = append(tailParts, fmt.Sprintf("%s:%d", sid, rm))
	}

	var spillEvents []map[string]any
	spillTotal := 0
	if policy.LinkWalk {
		edges := append([]struct{ From, To string }{}, links.Edges...)
		sort.Slice(edges, func(i, j int) bool {
			if edges[i].From != edges[j].From {
				return edges[i].From < edges[j].From
			}
			return edges[i].To < edges[j].To
		})
		for _, e := range edges {
			b, ok := spillBin[e.From]
			if !ok {
				continue
			}
			h := histMaps[e.To]
			if h == nil {
				h = map[int]int{}
				histMaps[e.To] = h
			}
			h[b]++
			samplesOut[e.To] = histRows(h)
			spillEvents = append(spillEvents, map[string]any{"bin": b, "delta": 1, "from": e.From, "to": e.To})
			spillTotal++
		}
	}

	sort.Strings(tailParts)
	sum := sha256.Sum256([]byte(strings.Join(tailParts, ",")))

	writeJSON(filepath.Join(audit, "trim_bins.json"), map[string]any{"samples": samplesOut})
	writeJSON(filepath.Join(audit, "spill_events.json"), map[string]any{"events": spillEvents})
	writeJSON(filepath.Join(audit, "summary.json"), map[string]any{
		"blend_mod":              policy.BlendMod,
		"effective_fold_stride":  sFold,
		"epoch_spill":            policy.EpochSpill,
		"epoch_stride":           sLane,
		"fold_div":               policy.FoldDiv,
		"halve_mod":              policy.HalveMod,
		"ledger_epoch":           pool.LedgerEpoch,
		"mix_coeff":              policy.MixCoeff,
		"ring_slot":              pool.RingSlot,
		"spill_propagate_total":  spillTotal,
		"stale_sample_total":     staleTotal,
		"tail_trim_sha":          hex.EncodeToString(sum[:]),
		"total_values":           totalValues,
		"trim_echo":              policy.TrimEcho,
		"trim_window":            policy.TrimWindow,
	})
}
