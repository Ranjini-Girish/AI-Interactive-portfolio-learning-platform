package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

var tierRank = map[string]int{
	"gold":        3,
	"silver":      2,
	"bronze":      1,
	"underfilled": 0,
}

type policy struct {
	LineageGraceDays int            `json:"lineage_grace_days"`
	RowFloors        map[string]int `json:"row_floors"`
	StalenessDays    map[string]int `json:"staleness_days"`
}

type poolState struct {
	CurrentDay int `json:"current_day"`
}

type sliceRec struct {
	Cluster         string  `json:"cluster"`
	DeclaredTier    string  `json:"declared_tier"`
	LastRefreshDay  int     `json:"last_refresh_day"`
	LineageParent   *string `json:"lineage_parent"`
	RowCount        int     `json:"row_count"`
	SliceID         string  `json:"slice_id"`
}

type incidentsDoc struct {
	Notes []json.RawMessage `json:"notes"`
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	data := getenv("FSF_DATA_DIR", "/app/featstore")
	outd := getenv("FSF_AUDIT_DIR", "/app/audit")
	if err := run(data, outd); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func run(dataDir, auditDir string) error {
	polRaw, err := os.ReadFile(filepath.Join(dataDir, "policy.json"))
	if err != nil {
		return err
	}
	var pol policy
	if err := json.Unmarshal(polRaw, &pol); err != nil {
		return err
	}

	psRaw, err := os.ReadFile(filepath.Join(dataDir, "pool_state.json"))
	if err != nil {
		return err
	}
	var ps poolState
	if err := json.Unmarshal(psRaw, &ps); err != nil {
		return err
	}

	slices, err := loadSlices(filepath.Join(dataDir, "slices"))
	if err != nil {
		return err
	}
	sort.Slice(slices, func(i, j int) bool { return slices[i].SliceID < slices[j].SliceID })

	forced := map[string]string{}
	quarantineClusters := map[string]struct{}{}
	if b, err := os.ReadFile(filepath.Join(dataDir, "incidents.json")); err == nil {
		var inc incidentsDoc
		if json.Unmarshal(b, &inc) == nil {
			type forceNote struct {
				Kind       string `json:"kind"`
				SliceID    string `json:"slice_id"`
				ForcedTier string `json:"forced_tier"`
			}
			type compNote struct {
				Kind         string `json:"kind"`
				Cluster      string `json:"cluster"`
				EffectiveDay int    `json:"effective_day"`
			}
			var forceList []forceNote
			for _, raw := range inc.Notes {
				var kindProbe struct {
					Kind string `json:"kind"`
				}
				if json.Unmarshal(raw, &kindProbe) != nil {
					continue
				}
				switch kindProbe.Kind {
				case "force_tier":
					var n forceNote
					if json.Unmarshal(raw, &n) == nil {
						forceList = append(forceList, n)
					}
				case "cluster_compromise":
					var n compNote
					if json.Unmarshal(raw, &n) == nil && n.EffectiveDay <= ps.CurrentDay {
						quarantineClusters[n.Cluster] = struct{}{}
					}
				}
			}
			sort.Slice(forceList, func(i, j int) bool {
				return forceList[i].SliceID < forceList[j].SliceID
			})
			for _, n := range forceList {
				forced[n.SliceID] = n.ForcedTier
			}
		}
	}

	capacityTier := func(rows int) string {
		if rows >= pol.RowFloors["gold"] {
			return "gold"
		}
		if rows >= pol.RowFloors["silver"] {
			return "silver"
		}
		if rows >= pol.RowFloors["bronze"] {
			return "bronze"
		}
		return "underfilled"
	}

	lowerRank := func(a, b string) string {
		if tierRank[a] <= tierRank[b] {
			return a
		}
		return b
	}

	baseTier := func(s sliceRec) string {
		cap := capacityTier(s.RowCount)
		if cap == "underfilled" {
			return "underfilled"
		}
		return lowerRank(s.DeclaredTier, cap)
	}

	effectiveTier := func(s sliceRec) string {
		if ft, ok := forced[s.SliceID]; ok {
			return ft
		}
		return baseTier(s)
	}

	isQuarantined := func(s sliceRec) bool {
		_, ok := quarantineClusters[s.Cluster]
		return ok
	}

	stalenessBudget := func(tier string) int {
		if tier == "underfilled" {
			return pol.StalenessDays["bronze"]
		}
		return pol.StalenessDays[tier]
	}

	freshnessByID := map[string]string{}
	parentFresh := map[string]string{}
	profiles := make([]map[string]any, 0, len(slices))
	underfilledIDs := make([]string, 0)

	for _, s := range slices {
		if capacityTier(s.RowCount) == "underfilled" {
			underfilledIDs = append(underfilledIDs, s.SliceID)
		}
		effTier := effectiveTier(s)
		quarantined := isQuarantined(s)
		effRows := s.RowCount
		var parentID any = nil
		if s.LineageParent != nil {
			parentID = *s.LineageParent
		}

		var fresh string
		if quarantined {
			fresh = "quarantined"
			effRows = 0
		} else {
			age := ps.CurrentDay - s.LastRefreshDay
			stale := age > stalenessBudget(effTier)
			lineageLag := false
			if s.LineageParent != nil {
				pid := *s.LineageParent
				pf := parentFresh[pid]
				if pf != "fresh" {
					lineageLag = true
				} else {
					var parent sliceRec
					found := false
					for _, cand := range slices {
						if cand.SliceID == pid {
							parent = cand
							found = true
							break
						}
					}
					if found && s.LastRefreshDay < parent.LastRefreshDay-pol.LineageGraceDays {
						lineageLag = true
					}
				}
			}
			switch {
			case stale:
				fresh = "stale"
			case lineageLag:
				fresh = "lineage_lag"
			default:
				fresh = "fresh"
			}
		}

		freshnessByID[s.SliceID] = fresh
		parentFresh[s.SliceID] = fresh

		profiles = append(profiles, map[string]any{
			"cluster":             s.Cluster,
			"effective_row_count": effRows,
			"effective_tier":      effTier,
			"freshness":           fresh,
			"last_refresh_day":    s.LastRefreshDay,
			"lineage_parent":      parentID,
			"row_count":           s.RowCount,
			"slice_id":            s.SliceID,
		})
	}

	events := make([]map[string]any, 0)
	for _, s := range slices {
		if freshnessByID[s.SliceID] != "lineage_lag" || s.LineageParent == nil {
			continue
		}
		pid := *s.LineageParent
		var parent sliceRec
		for _, cand := range slices {
			if cand.SliceID == pid {
				parent = cand
				break
			}
		}
		events = append(events, map[string]any{
			"lag_days":          s.LastRefreshDay - parent.LastRefreshDay,
			"parent_freshness":  parentFresh[pid],
			"parent_slice_id":   pid,
			"slice_id":          s.SliceID,
		})
	}
	sort.Slice(events, func(i, j int) bool {
		return fmt.Sprint(events[i]["slice_id"]) < fmt.Sprint(events[j]["slice_id"])
	})

	rollups := map[string]map[string]int{}
	clustersSeen := map[string]struct{}{}
	quarantinedTotal := 0
	staleTotal := 0
	tierCounts := map[string]int{
		"bronze":      0,
		"gold":        0,
		"silver":      0,
		"underfilled": 0,
	}

	for _, s := range slices {
		clustersSeen[s.Cluster] = struct{}{}
		f := freshnessByID[s.SliceID]
		if f == "quarantined" {
			quarantinedTotal++
		}
		if f == "stale" {
			staleTotal++
		}
		if _, ok := rollups[s.Cluster]; !ok {
			rollups[s.Cluster] = map[string]int{
				"fresh":        0,
				"lineage_lag":  0,
				"quarantined":  0,
				"stale":        0,
			}
		}
		rollups[s.Cluster][f]++
		if f != "quarantined" {
			tierCounts[effectiveTier(s)]++
		}
	}

	clusterNames := make([]string, 0, len(rollups))
	for c := range rollups {
		clusterNames = append(clusterNames, c)
	}
	sort.Strings(clusterNames)
	clustersOut := map[string]any{}
	for _, c := range clusterNames {
		row := rollups[c]
		clustersOut[c] = map[string]any{
			"fresh":       row["fresh"],
			"lineage_lag": row["lineage_lag"],
			"quarantined": row["quarantined"],
			"stale":       row["stale"],
		}
	}

	clusterList := make([]string, 0, len(clustersSeen))
	for c := range clustersSeen {
		clusterList = append(clusterList, c)
	}
	sort.Strings(clusterList)

	payloads := map[string]any{
		"capacity_summary.json": map[string]any{
			"tiers": map[string]any{
				"bronze":      tierCounts["bronze"],
				"gold":        tierCounts["gold"],
				"silver":      tierCounts["silver"],
				"underfilled": tierCounts["underfilled"],
			},
			"underfilled_slices": underfilledIDs,
		},
		"cluster_rollups.json": map[string]any{
			"clusters":    clustersOut,
			"current_day": ps.CurrentDay,
		},
		"lineage_events.json": map[string]any{
			"events": events,
		},
		"slice_profiles.json": map[string]any{
			"current_day": ps.CurrentDay,
			"slices":      profiles,
		},
		"summary.json": map[string]any{
			"clusters":          clusterList,
			"current_day":       ps.CurrentDay,
			"quarantined_total": quarantinedTotal,
			"slices_total":      len(slices),
			"stale_total":       staleTotal,
		},
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	for name, payload := range payloads {
		if err := writeJSON(filepath.Join(auditDir, name), payload); err != nil {
			return err
		}
	}
	return nil
}

func writeJSON(path string, v any) error {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(true)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		return err
	}
	return os.WriteFile(path, buf.Bytes(), 0o644)
}

func loadSlices(dir string) ([]sliceRec, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	out := make([]sliceRec, 0)
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var s sliceRec
		if err := json.Unmarshal(b, &s); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no slices")
	}
	return out, nil
}
