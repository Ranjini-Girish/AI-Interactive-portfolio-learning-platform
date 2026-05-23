package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type Catalog struct {
	Days  []string `json:"days"`
	Rings []string `json:"rings"`
}

type Policy struct {
	IncidentSuppressFloor int `json:"incident_suppress_floor"`
	OverrunSlack          int `json:"overrun_slack"`
	Tiers                 []struct {
		HighWaterMax int    `json:"high_water_max"`
		Label        string `json:"label"`
	} `json:"tiers"`
}

type Incidents struct {
	Days map[string]struct {
		Severity int `json:"severity"`
	} `json:"days"`
}

type SpliceWindow struct {
	ClaimedSpan        int    `json:"claimed_span"`
	ID                 string `json:"id"`
	ReportedWrapParity int    `json:"reported_wrap_parity"`
	TickHi             int    `json:"tick_hi"`
	TickLo             int    `json:"tick_lo"`
}

type Snapshot struct {
	Capacity           int            `json:"capacity"`
	ConsumerTailLo     int            `json:"consumer_tail_lo"`
	ConsumerTotal      int            `json:"consumer_total"`
	HighWater          int            `json:"high_water"`
	InstrumentWrapCons int            `json:"instrument_wrap_cons"`
	InstrumentWrapProd int            `json:"instrument_wrap_prod"`
	ProducerTotal      int            `json:"producer_total"`
	SpliceWindows      []SpliceWindow `json:"splice_windows"`
}

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func readJSON(path string, out any) {
	b, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read %s: %v\n", path, err)
		os.Exit(1)
	}
	if err := json.Unmarshal(b, out); err != nil {
		fmt.Fprintf(os.Stderr, "parse %s: %v\n", path, err)
		os.Exit(1)
	}
}

func writeJSON(path string, v any) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(true)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		fmt.Fprintf(os.Stderr, "encode %s: %v\n", path, err)
		os.Exit(1)
	}
	out := bytes.TrimSuffix(buf.Bytes(), []byte("\n"))
	if err := os.WriteFile(path, out, 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "write %s: %v\n", path, err)
		os.Exit(1)
	}
}

func suppressedDays(inc Incidents, floor int) []string {
	var out []string
	for day, row := range inc.Days {
		if row.Severity >= floor {
			out = append(out, day)
		}
	}
	sort.Strings(out)
	return out
}

func isSuppressed(day string, sup map[string]bool) bool {
	return sup[day]
}

func tierLabel(hw int, pol Policy) string {
	for _, t := range pol.Tiers {
		if hw <= t.HighWaterMax {
			return t.Label
		}
	}
	return pol.Tiers[len(pol.Tiers)-1].Label
}

func spliceStatus(snap Snapshot, sw SpliceWindow) string {
	tickDelta := sw.TickHi - sw.TickLo
	if sw.ClaimedSpan != tickDelta {
		return "span_mismatch"
	}
	tailMod := snap.ConsumerTotal % snap.Capacity
	if (snap.ConsumerTailLo % snap.Capacity) != tailMod {
		return "tail_desync"
	}
	parityCalc := (((snap.ConsumerTotal % snap.Capacity) + sw.ClaimedSpan) / snap.Capacity) % 2
	if (sw.ReportedWrapParity & 1) != parityCalc {
		return "parity_drift"
	}
	return "ok"
}

func overrunStatus(occ int, cap int, slack int) string {
	if occ < 0 || occ > cap+slack {
		return "overrun"
	}
	if occ > cap {
		return "slack"
	}
	return "nominal"
}

func wrapParityStatus(snap Snapshot, slack int) (expectedXOR int, parityBit int, status string) {
	predProd := snap.ProducerTotal / snap.Capacity
	predCons := snap.ConsumerTotal / snap.Capacity
	expectedXOR = (predProd ^ predCons) & 1
	parityBit = (snap.InstrumentWrapProd ^ snap.InstrumentWrapCons) & 1
	occ := snap.ProducerTotal - snap.ConsumerTotal
	if occ < 0 || occ > snap.Capacity+slack {
		return expectedXOR, parityBit, "anomaly"
	}
	if expectedXOR == parityBit {
		return expectedXOR, parityBit, "match"
	}
	return expectedXOR, parityBit, "mismatch"
}

func main() {
	root := getenv("RSP_DATA_DIR", "/app/ring_splice")
	outDir := getenv("RSP_AUDIT_DIR", "/app/audit")

	var cat Catalog
	var pol Policy
	var inc Incidents
	readJSON(filepath.Join(root, "catalog.json"), &cat)
	readJSON(filepath.Join(root, "policy.json"), &pol)
	readJSON(filepath.Join(root, "incidents.json"), &inc)

	supList := suppressedDays(inc, pol.IncidentSuppressFloor)
	supSet := map[string]bool{}
	for _, d := range supList {
		supSet[d] = true
	}

	severity := map[string]int{}
	for _, d := range supList {
		severity[d] = inc.Days[d].Severity
	}

	incidentOut := map[string]any{
		"policy_floor":    pol.IncidentSuppressFloor,
		"severity":        severity,
		"suppressed_days": supList,
	}
	writeJSON(filepath.Join(outDir, "incident_suppression.json"), incidentOut)

	var spliceEntries []map[string]any
	var overrunRows []map[string]any
	var wrapRows []map[string]any
	var tierRows []map[string]any

	days := append([]string(nil), cat.Days...)
	sort.Strings(days)
	rings := append([]string(nil), cat.Rings...)
	sort.Strings(rings)

	for _, day := range days {
		if isSuppressed(day, supSet) {
			continue
		}
		for _, ring := range rings {
			p := filepath.Join(root, "snapshots", day, ring+".json")
			var snap Snapshot
			readJSON(p, &snap)

			occ := snap.ProducerTotal - snap.ConsumerTotal
			overrunRows = append(overrunRows, map[string]any{
				"day":       day,
				"occupancy": occ,
				"ring":      ring,
				"status":    overrunStatus(occ, snap.Capacity, pol.OverrunSlack),
			})

			exp, bit, wstat := wrapParityStatus(snap, pol.OverrunSlack)
			wrapRows = append(wrapRows, map[string]any{
				"day":          day,
				"expected_xor": exp,
				"parity_bit":   bit,
				"ring":         ring,
				"status":       wstat,
			})

			tierRows = append(tierRows, map[string]any{
				"day":        day,
				"high_water": snap.HighWater,
				"ring":       ring,
				"tier":       tierLabel(snap.HighWater, pol),
			})

			for _, sw := range snap.SpliceWindows {
				spliceEntries = append(spliceEntries, map[string]any{
					"day":    day,
					"id":     sw.ID,
					"ring":   ring,
					"status": spliceStatus(snap, sw),
				})
			}
		}
	}

	sort.Slice(spliceEntries, func(i, j int) bool {
		di := spliceEntries[i]["day"].(string)
		dj := spliceEntries[j]["day"].(string)
		if di != dj {
			return di < dj
		}
		ri := spliceEntries[i]["ring"].(string)
		rj := spliceEntries[j]["ring"].(string)
		if ri != rj {
			return ri < rj
		}
		return spliceEntries[i]["id"].(string) < spliceEntries[j]["id"].(string)
	})

	sort.Slice(overrunRows, func(i, j int) bool {
		di := overrunRows[i]["day"].(string)
		dj := overrunRows[j]["day"].(string)
		if di != dj {
			return di < dj
		}
		return overrunRows[i]["ring"].(string) < overrunRows[j]["ring"].(string)
	})

	sort.Slice(wrapRows, func(i, j int) bool {
		di := wrapRows[i]["day"].(string)
		dj := wrapRows[j]["day"].(string)
		if di != dj {
			return di < dj
		}
		return wrapRows[i]["ring"].(string) < wrapRows[j]["ring"].(string)
	})

	sort.Slice(tierRows, func(i, j int) bool {
		di := tierRows[i]["day"].(string)
		dj := tierRows[j]["day"].(string)
		if di != dj {
			return di < dj
		}
		return tierRows[i]["ring"].(string) < tierRows[j]["ring"].(string)
	})

	writeJSON(filepath.Join(outDir, "splice_inventory.json"), map[string]any{"entries": spliceEntries})
	writeJSON(filepath.Join(outDir, "overrun_ledger.json"), map[string]any{"rows": overrunRows})
	writeJSON(filepath.Join(outDir, "wrap_parity_report.json"), map[string]any{"rows": wrapRows})
	writeJSON(filepath.Join(outDir, "watermark_tier_matrix.json"), map[string]any{"rows": tierRows})
}
