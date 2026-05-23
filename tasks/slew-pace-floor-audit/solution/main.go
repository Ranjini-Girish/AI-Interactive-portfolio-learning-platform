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

func main() {
	root := getenv("SPA_DATA_DIR", "/app/pace_lab")
	audit := getenv("SPA_AUDIT_DIR", "/app/audit")

	var policy struct {
		FloorWindow int  `json:"floor_window"`
		SlewStride  int  `json:"slew_stride"`
		FoldDiv     int  `json:"fold_div"`
		PaceMod     int  `json:"pace_mod"`
		MixCoeff    int  `json:"mix_coeff"`
		BlendMod    int  `json:"blend_mod"`
		CapSpill    bool `json:"cap_spill"`
		PaceEcho    bool `json:"pace_echo"`
	}
	readJSON(filepath.Join(root, "policy.json"), &policy)

	var pool struct {
		LedgerEpoch int `json:"ledger_epoch"`
		RingSlot    int `json:"ring_slot"`
	}
	readJSON(filepath.Join(root, "pool_state.json"), &pool)

	var north struct {
		LaneAdd int `json:"lane_add"`
	}
	readJSON(filepath.Join(root, "anchors/north.json"), &north)

	var south struct {
		LaneAdd int `json:"lane_add"`
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

	s := policy.SlewStride
	samplePaths, err := filepath.Glob(filepath.Join(root, "samples", "sample_*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(samplePaths)

	samplesOut := map[string][]map[string]int{}
	var tailParts []string
	totalValues := 0

	for _, sp := range samplePaths {
		var doc struct {
			SampleID string `json:"sample_id"`
			EpochTag int    `json:"epoch_tag"`
			Values   []int  `json:"values"`
		}
		readJSON(sp, &doc)
		sid := doc.SampleID
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
			adj[i] = values[i] + modNonneg(north.LaneAdd*i+south.LaneAdd, s)
		}
		skew := modNonneg(modNonneg(pool.LedgerEpoch, policy.BlendMod)*policy.MixCoeff+doc.EpochTag+modNonneg(pool.RingSlot, s), s)
		hist := map[int]int{}
		window := make([]int, 0, policy.FloorWindow)
		var runningMax *int
		for k := 1; k <= n; k++ {
			window = append(window, adj[k-1])
			if len(window) > policy.FloorWindow {
				window = window[1:]
			}
			mk := window[0]
			for _, v := range window[1:] {
				if v < mk {
					mk = v
				}
			}
			if runningMax == nil || mk > *runningMax {
				v := mk
				runningMax = &v
			}
			folded := ((mk + skew) / s) / policy.FoldDiv
			hist[folded]++
			if policy.PaceEcho && k%policy.PaceMod == 0 {
				hist[folded]++
			}
			if policy.PaceEcho && runningMax != nil && *runningMax == mk {
				hist[folded]++
			}
		}
		if policy.CapSpill && len(hist) > 0 {
			bMax := 0
			for b := range hist {
				if b > bMax {
					bMax = b
				}
			}
			hist[bMax] += modNonneg(pool.LedgerEpoch+doc.EpochTag, s)
		}
		var bins []int
		for b := range hist {
			if hist[b] > 0 {
				bins = append(bins, b)
			}
		}
		sort.Ints(bins)
		rows := make([]map[string]int, 0, len(bins))
		for _, b := range bins {
			rows = append(rows, map[string]int{"bin": b, "tally": hist[b]})
		}
		samplesOut[sid] = rows
		totalValues += n
		rm := 0
		if runningMax != nil {
			rm = *runningMax
		}
		tailParts = append(tailParts, fmt.Sprintf("%s:%d", sid, rm))
	}
	sort.Strings(tailParts)
	sum := sha256.Sum256([]byte(strings.Join(tailParts, ",")))

	writeJSON(filepath.Join(audit, "floor_bins.json"), map[string]any{"samples": samplesOut})
	writeJSON(filepath.Join(audit, "summary.json"), map[string]any{
		"blend_mod":      policy.BlendMod,
		"cap_spill":      policy.CapSpill,
		"floor_window":   policy.FloorWindow,
		"fold_div":       policy.FoldDiv,
		"ledger_epoch":   pool.LedgerEpoch,
		"mix_coeff":      policy.MixCoeff,
		"pace_echo":      policy.PaceEcho,
		"pace_mod":       policy.PaceMod,
		"ring_slot":      pool.RingSlot,
		"slew_stride":    s,
		"tail_floor_sha": hex.EncodeToString(sum[:]),
		"total_values":   totalValues,
	})
}
