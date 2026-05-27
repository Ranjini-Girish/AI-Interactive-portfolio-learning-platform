package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
)

type policyDoc struct {
	AuditDay  int               `json:"audit_day"`
	TierOrder []string          `json:"tier_order"`
	TierCaps  map[string]int    `json:"tier_caps"`
}

type eventsDoc struct {
	TierDerates  []derate `json:"tier_derates"`
	ItemFreezes  []freeze `json:"item_freezes"`
}

type derate struct {
	Tier      string `json:"tier"`
	FactorBp  int    `json:"factor_bp"`
	StartDay  int    `json:"start_day"`
	EndDay    int    `json:"end_day"`
}

type freeze struct {
	ItemID   string `json:"item_id"`
	StartDay int    `json:"start_day"`
	EndDay   int    `json:"end_day"`
}

type itemDoc struct {
	ItemID string `json:"item_id"`
	Tier   string `json:"tier"`
	Demand int    `json:"demand"`
}

type row struct {
	ItemID    string `json:"item_id"`
	Tier      string `json:"tier"`
	Status    string `json:"status"`
	Demand    int    `json:"demand"`
	Allocated int    `json:"allocated"`
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func tierKey(tier string, order []string) (int, string) {
	for i, t := range order {
		if t == tier {
			return i, tier
		}
	}
	return len(order), tier
}

func writeJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(b, '\n'), 0o644)
}

func main() {
	data := env("QUOTA_DATA_DIR", "/app/quota_lab")
	audit := env("QUOTA_AUDIT_DIR", "/app/audit")
	_ = os.MkdirAll(audit, 0o755)

	var pol policyDoc
	loadJSON(filepath.Join(data, "policy.json"), &pol)
	var ev eventsDoc
	loadJSON(filepath.Join(data, "events.json"), &ev)

	caps := map[string]int{}
	for k, v := range pol.TierCaps {
		caps[k] = v
	}
	for _, d := range ev.TierDerates {
		if d.StartDay <= pol.AuditDay && pol.AuditDay <= d.EndDay {
			if c, ok := caps[d.Tier]; ok {
				caps[d.Tier] = c * d.FactorBp / 10000
			}
		}
	}
	frozen := map[string]bool{}
	for _, f := range ev.ItemFreezes {
		if f.StartDay <= pol.AuditDay && pol.AuditDay <= f.EndDay {
			frozen[f.ItemID] = true
		}
	}

	var items []itemDoc
	matches, _ := filepath.Glob(filepath.Join(data, "items", "*.json"))
	sort.Strings(matches)
	for _, p := range matches {
		var it itemDoc
		loadJSON(p, &it)
		items = append(items, it)
	}
	sort.Slice(items, func(i, j int) bool {
		ri, _ := tierKey(items[i].Tier, pol.TierOrder)
		rj, _ := tierKey(items[j].Tier, pol.TierOrder)
		if ri != rj {
			return ri < rj
		}
		return items[i].ItemID < items[j].ItemID
	})

	tierRem := map[string]int{}
	for k, v := range caps {
		tierRem[k] = v
	}
	var rows []row
	sc := map[string]int{"frozen": 0, "ok": 0, "shortfall": 0}
	for _, it := range items {
		if frozen[it.ItemID] {
			rows = append(rows, row{it.ItemID, it.Tier, "frozen", it.Demand, 0})
			sc["frozen"]++
			continue
		}
		left := tierRem[it.Tier]
		alloc := it.Demand
		if alloc > left {
			alloc = left
		}
		tierRem[it.Tier] = left - alloc
		st := "ok"
		if alloc != it.Demand {
			st = "shortfall"
		}
		sc[st]++
		rows = append(rows, row{it.ItemID, it.Tier, st, it.Demand, alloc})
	}
	touched := []string{}
	seen := map[string]bool{}
	for _, r := range rows {
		if r.Allocated > 0 && !seen[r.Tier] {
			seen[r.Tier] = true
			touched = append(touched, r.Tier)
		}
	}
	sort.Strings(touched)
	summary := map[string]any{
		"audit_day":       pol.AuditDay,
		"items_processed": len(items),
		"frozen_items":    sc["frozen"],
		"status_counts":   sc,
		"tiers_touched":   touched,
	}
	_ = writeJSON(filepath.Join(audit, "allocations.json"), map[string]any{"items": rows})
	_ = writeJSON(filepath.Join(audit, "summary.json"), summary)
}

func loadJSON(path string, v any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, v); err != nil {
		panic(err)
	}
}
