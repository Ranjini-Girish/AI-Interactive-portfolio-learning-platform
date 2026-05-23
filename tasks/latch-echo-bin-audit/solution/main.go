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

func mod_nonneg(x, m int) int {
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
	root := getenv("LEB_DATA_DIR", "/app/leb_lab")
	audit := getenv("LEB_AUDIT_DIR", "/app/audit")

	var policy struct {
		BinStride  int  `json:"bin_stride"`
		SkewMix    int  `json:"skew_mix"`
		BlendMod   int  `json:"blend_mod"`
		PairSpan   int  `json:"pair_span"`
		LatchMod   int  `json:"latch_mod"`
		EchoMax    bool `json:"echo_max"`
		LatchEcho  bool `json:"latch_echo"`
	}
	readJSON(filepath.Join(root, "policy.json"), &policy)

	var pool struct {
		LedgerSerial int `json:"ledger_serial"`
		QuorumRing   int `json:"quorum_ring"`
	}
	readJSON(filepath.Join(root, "pool_state.json"), &pool)

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

	w := policy.BinStride
	e, v := east.LaneAdd, west.LaneAdd

	samplePaths, err := filepath.Glob(filepath.Join(root, "samples", "sample_*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(samplePaths)

	samplesOut := map[string][]map[string]int{}
	var tailParts []string
	totalAssignments := 0

	for _, sp := range samplePaths {
		var doc struct {
			SampleID string `json:"sample_id"`
			Latch    int    `json:"latch"`
			Readings []int  `json:"readings"`
		}
		readJSON(sp, &doc)
		sid, latch := doc.SampleID, doc.Latch
		readings := append([]int(nil), doc.Readings...)
		n := len(readings)
		if m, ok := masks[sid]; ok {
			for zi := range m {
				if zi >= 0 && zi < n {
					readings[zi] = 0
				}
			}
		}
		adj := make([]int, n)
		for i := range readings {
			adj[i] = readings[i] + mod_nonneg(e*i+v, w)
		}
		skew := mod_nonneg(mod_nonneg(pool.LedgerSerial, policy.BlendMod)*policy.SkewMix+latch+mod_nonneg(pool.QuorumRing, w), w)
		hist := map[int]int{}
		ssum := 0
		for k := 1; k <= n; k++ {
			ssum += adj[k-1]
			folded := ((ssum + skew) / w) / policy.PairSpan
			hist[folded]++
			if policy.LatchEcho && k%policy.LatchMod == 0 {
				hist[folded]++
			}
		}
		if policy.EchoMax && len(hist) > 0 {
			bMax := 0
			for b := range hist {
				if b > bMax {
					bMax = b
				}
			}
			hist[bMax] += mod_nonneg(e+v+latch, w)
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
		totalAssignments += n
		tailParts = append(tailParts, fmt.Sprintf("%s:%d", sid, ssum))
	}
	sort.Strings(tailParts)
	tailJoined := strings.Join(tailParts, ",")
	sum := sha256.Sum256([]byte(tailJoined))

	writeJSON(filepath.Join(audit, "latch_bins.json"), map[string]any{"samples": samplesOut})
	writeJSON(filepath.Join(audit, "summary.json"), map[string]any{
		"bin_stride":          w,
		"blend_mod":           policy.BlendMod,
		"echo_max":            policy.EchoMax,
		"latch_echo":          policy.LatchEcho,
		"latch_mod":           policy.LatchMod,
		"ledger_serial":       pool.LedgerSerial,
		"pair_span":           policy.PairSpan,
		"quorum_ring":         pool.QuorumRing,
		"skew_mix":            policy.SkewMix,
		"tail_ledger_sha":     hex.EncodeToString(sum[:]),
		"total_assignments":   totalAssignments,
	})
}
