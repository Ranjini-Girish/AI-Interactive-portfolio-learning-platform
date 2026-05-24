package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type policyDoc struct {
	CurrentDay           int            `json:"current_day"`
	IMAnchorMHz          int            `json:"im_anchor_mhz"`
	MinCarrierMHz        int            `json:"min_carrier_mhz"`
	MinSeparationMHz     int            `json:"min_separation_mhz"`
	TierHeadroomDropMHz  map[string]int `json:"tier_headroom_drop_mhz"`
}

type poolDoc struct {
	BandProcessOrder []string       `json:"band_process_order"`
	TierEmitCap      map[string]int `json:"tier_emit_cap"`
}

type incidentEvent struct {
	Accepted    bool   `json:"accepted"`
	Day         int    `json:"day"`
	EventID     string `json:"event_id"`
	Kind        string `json:"kind"`
	TargetSite  string `json:"target_site,omitempty"`
	TargetBand  string `json:"target_band,omitempty"`
	LiftMHz     int    `json:"lift_mhz,omitempty"`
}

type incidentLog struct {
	Events []incidentEvent `json:"events"`
}

type anchorWindow struct {
	GuardCloseMHz int `json:"guard_close_mhz"`
	ReferenceMHz  int `json:"reference_mhz"`
}

type siteFile struct {
	BandTag      string `json:"band_tag"`
	EmissionsMHz []int  `json:"emissions_mhz"`
	SiteID       string `json:"site_id"`
	Tier         string `json:"tier"`
}

type regEntry struct {
	BandTag string `json:"band_tag"`
	MHz     int    `json:"mhz"`
	SiteID  string `json:"site_id"`
	Tier    string `json:"tier"`
}

func main() {
	dataDir := os.Getenv("IMHA_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/imhr_lab"
	}
	outDir := os.Getenv("IMHA_AUDIT_DIR")
	if outDir == "" {
		outDir = "/app/audit"
	}
	if err := run(dataDir, outDir); err != nil {
		fmt.Fprintf(os.Stderr, "imha: %v\n", err)
		os.Exit(1)
	}
}

func run(dataDir, outDir string) error {
	policy, err := readJSON[policyDoc](filepath.Join(dataDir, "policy.json"))
	if err != nil {
		return err
	}
	pool, err := readJSON[poolDoc](filepath.Join(dataDir, "pool_state.json"))
	if err != nil {
		return err
	}
	inc, err := readJSON[incidentLog](filepath.Join(dataDir, "incident_log.json"))
	if err != nil {
		return err
	}
	anchor, err := readJSON[anchorWindow](filepath.Join(dataDir, "anchors", "window.json"))
	if err != nil {
		return err
	}

	sitePaths, err := filepath.Glob(filepath.Join(dataDir, "sites", "*.json"))
	if err != nil {
		return err
	}
	sort.Strings(sitePaths)
	var sites []siteFile
	siteByID := map[string]siteFile{}
	for _, p := range sitePaths {
		sf, err := readJSON[siteFile](p)
		if err != nil {
			return err
		}
		sites = append(sites, *sf)
		siteByID[sf.SiteID] = *sf
	}

	events := filterEvents(inc.Events, policy.CurrentDay)
	sort.Slice(events, func(i, j int) bool {
		if events[i].Day != events[j].Day {
			return events[i].Day < events[j].Day
		}
		return events[i].EventID < events[j].EventID
	})

	frozen := map[string]bool{}
	comp := map[string]bool{}
	bandAdd := map[string]int{}
	allSites := map[string]struct{}{}
	for _, s := range sites {
		allSites[s.SiteID] = struct{}{}
	}
	for _, ev := range events {
		if !ev.Accepted {
			continue
		}
		switch ev.Kind {
		case "site_compromise":
			comp[ev.TargetSite] = true
		case "site_freeze":
			frozen[ev.TargetSite] = true
		case "site_lift":
			frozen[ev.TargetSite] = false
		case "per_band_noise_lift":
			bandAdd[ev.TargetBand] += ev.LiftMHz
		}
	}

	effectiveMin := map[string]int{}
	for _, b := range pool.BandProcessOrder {
		effectiveMin[b] = policy.MinCarrierMHz + bandAdd[b]
	}

	type adjSite struct {
		SiteID       string `json:"site_id"`
		AdjustedMHz  []int  `json:"adjusted_mhz"`
		BandTag      string
		Tier         string
		FrozenSkip   bool
		Compromised  bool
	}
	var adjustedList []adjSite
	var siteIDs []string
	for id := range allSites {
		siteIDs = append(siteIDs, id)
	}
	sort.Strings(siteIDs)

	for _, sid := range siteIDs {
		s := siteByID[sid]
		as := adjSite{SiteID: sid, BandTag: s.BandTag, Tier: s.Tier, FrozenSkip: frozen[sid], Compromised: comp[sid]}
		if comp[sid] {
			as.AdjustedMHz = []int{}
		} else {
			drop := policy.TierHeadroomDropMHz[s.Tier]
			minC := effectiveMin[s.BandTag]
			var adj []int
			raw := append([]int(nil), s.EmissionsMHz...)
			sort.Sort(sort.Reverse(sort.IntSlice(raw)))
			for _, f := range raw {
				v := f - drop
				if v >= minC {
					adj = append(adj, v)
				}
			}
			sort.Sort(sort.Reverse(sort.IntSlice(adj)))
			as.AdjustedMHz = adj
		}
		adjustedList = append(adjustedList, as)
	}
	sort.Slice(adjustedList, func(i, j int) bool {
		return adjustedList[i].SiteID < adjustedList[j].SiteID
	})

	usedTier := map[string]int{}
	for t := range policy.TierHeadroomDropMHz {
		usedTier[t] = 0
	}
	for _, s := range sites {
		if _, ok := usedTier[s.Tier]; !ok {
			usedTier[s.Tier] = 0
		}
	}

	var registry []regEntry
	var admissionOrder []string

	tryAdmit := func(sid string, band string, tier string, mhz int) bool {
		if usedTier[tier] >= pool.TierEmitCap[tier] {
			return false
		}
		for _, r := range registry {
			if r.SiteID == sid && r.MHz == mhz {
				return false
			}
			if r.BandTag != band {
				continue
			}
			abs := mhz - r.MHz
			if abs < 0 {
				abs = -abs
			}
			if abs < policy.MinSeparationMHz {
				return false
			}
		}
		registry = append(registry, regEntry{BandTag: band, MHz: mhz, SiteID: sid, Tier: tier})
		admissionOrder = append(admissionOrder, fmt.Sprintf("%s:%d", sid, mhz))
		usedTier[tier]++
		return true
	}

	adjByID := map[string]adjSite{}
	for _, a := range adjustedList {
		adjByID[a.SiteID] = a
	}

	sweepRounds := 0
	for {
		sweepRounds++
		admitted := 0
		for _, B := range pool.BandProcessOrder {
			for _, sid := range siteIDs {
				a := adjByID[sid]
				if a.Compromised || a.FrozenSkip || a.BandTag != B {
					continue
				}
				s := siteByID[sid]
				for _, mhz := range a.AdjustedMHz {
					if tryAdmit(sid, B, s.Tier, mhz) {
						admitted++
						break
					}
				}
			}
		}
		if admitted == 0 {
			break
		}
	}

	var frozenSkipped []string
	for _, sid := range siteIDs {
		if frozen[sid] {
			frozenSkipped = append(frozenSkipped, sid)
		}
	}
	sort.Strings(frozenSkipped)

	type hitRec struct {
		BandTag  string `json:"band_tag"`
		HitMHz   []int  `json:"hit_mhz"`
		MHzHigh  int    `json:"mhz_high"`
		MHzLow   int    `json:"mhz_low"`
		SiteHigh string `json:"site_high"`
		SiteLow  string `json:"site_low"`
	}
	var hits []hitRec

	for i := 0; i < len(registry); i++ {
		for j := i + 1; j < len(registry); j++ {
			a := registry[i]
			b := registry[j]
			if a.BandTag != b.BandTag || a.SiteID == b.SiteID {
				continue
			}
			p, q := a, b
			if a.SiteID > b.SiteID || (a.SiteID == b.SiteID && a.MHz > b.MHz) {
				p, q = b, a
			}
			lowS, highS, lowF, highF := p.SiteID, q.SiteID, p.MHz, q.MHz
			t1 := 2*lowF - highF
			t2 := lowF + highF - policy.IMAnchorMHz
			targets := map[int]struct{}{}
			for _, t := range []int{t1, t2} {
				for _, r := range registry {
					if r.BandTag != a.BandTag {
						continue
					}
					if r.MHz == t {
						targets[t] = struct{}{}
					}
				}
			}
			if len(targets) == 0 {
				continue
			}
			var hm []int
			for v := range targets {
				hm = append(hm, v)
			}
			sort.Ints(hm)
			hits = append(hits, hitRec{
				BandTag:  a.BandTag,
				HitMHz:   hm,
				MHzHigh:  highF,
				MHzLow:   lowF,
				SiteHigh: highS,
				SiteLow:  lowS,
			})
		}
	}

	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	regObjs := make([]map[string]any, 0, len(registry))
	for _, r := range registry {
		regObjs = append(regObjs, map[string]any{
			"band_tag": r.BandTag,
			"mhz":      r.MHz,
			"site_id":  r.SiteID,
			"tier":     r.Tier,
		})
	}
	tiersUsed := map[string]any{}
	for _, k := range sortedStringKeys(usedTier) {
		tiersUsed[k] = usedTier[k]
	}
	regPayload := map[string]any{
		"admission_order": admissionOrder,
		"registry":        regObjs,
		"tiers_used":      tiersUsed,
	}
	hitObjs := make([]map[string]any, 0, len(hits))
	for _, h := range hits {
		hm := make([]any, len(h.HitMHz))
		for i, v := range h.HitMHz {
			hm[i] = v
		}
		hitObjs = append(hitObjs, map[string]any{
			"band_tag":   h.BandTag,
			"hit_mhz":    hm,
			"mhz_high":   h.MHzHigh,
			"mhz_low":    h.MHzLow,
			"site_high":  h.SiteHigh,
			"site_low":   h.SiteLow,
		})
	}
	hitPayload := map[string]any{
		"anchor_mhz":    anchor.ReferenceMHz,
		"hits":          hitObjs,
		"im_anchor_mhz": policy.IMAnchorMHz,
	}
	sumAdj := make([]map[string]any, 0, len(adjustedList))
	for _, a := range adjustedList {
		if a.Compromised {
			continue
		}
		adj := make([]any, len(a.AdjustedMHz))
		for i, v := range a.AdjustedMHz {
			adj[i] = v
		}
		sumAdj = append(sumAdj, map[string]any{
			"adjusted_mhz": adj,
			"site_id":      a.SiteID,
		})
	}
	summary := map[string]any{
		"adjusted_sites":       sumAdj,
		"bands":                toAnySlice(pool.BandProcessOrder),
		"current_day":          policy.CurrentDay,
		"frozen_skipped_sites": toAnySliceStr(frozenSkipped),
		"hits":                 len(hits),
		"incidents_applied":    len(events),
		"registry_carriers":    len(registry),
		"sweep_rounds":         sweepRounds,
	}
	for _, name := range []struct {
		file string
		val  any
	}{
		{"registry.json", regPayload},
		{"intermod_hits.json", hitPayload},
		{"summary.json", summary},
	} {
		if err := writeCanonicalJSON(filepath.Join(outDir, name.file), name.val); err != nil {
			return err
		}
	}
	return nil
}

func filterEvents(ev []incidentEvent, day int) []incidentEvent {
	var out []incidentEvent
	for _, e := range ev {
		if e.Day <= day {
			out = append(out, e)
		}
	}
	return out
}

func readJSON[T any](path string) (*T, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var v T
	if err := json.Unmarshal(b, &v); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return &v, nil
}

func sortedStringKeys(m map[string]int) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func toAnySlice(s []string) []any {
	out := make([]any, len(s))
	for i, v := range s {
		out[i] = v
	}
	return out
}

func toAnySliceStr(s []string) []any {
	return toAnySlice(s)
}

func writeCanonicalJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}
