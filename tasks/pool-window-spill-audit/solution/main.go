package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type policy struct {
	WindowMs    int `json:"window_ms"`
	PoolCeiling int `json:"pool_ceiling"`
}

type incident struct {
	Kind        string `json:"kind"`
	StartWindow int    `json:"start_window"`
	FromWindow  int    `json:"from_window"`
	Delta       int    `json:"delta"`
}

type incidentsFile struct {
	Incidents []incident `json:"incidents"`
}

type arrival struct {
	ArrivalID   string `json:"arrival_id"`
	PartitionID string `json:"partition_id"`
	TsMs        int64  `json:"ts_ms"`
	Bytes       int    `json:"bytes"`
}

type admission struct {
	Window      int    `json:"window"`
	PartitionID string `json:"partition_id"`
	ArrivalID   string `json:"arrival_id"`
	Bytes       int    `json:"bytes"`
}

type spill struct {
	FromWindow    int    `json:"from_window"`
	ToWindow      int    `json:"to_window"`
	PartitionID   string `json:"partition_id"`
	SourceArrival string `json:"source_arrival"`
	Bytes         int    `json:"bytes"`
}

type drop struct {
	Window        int    `json:"window"`
	PartitionID   string `json:"partition_id"`
	SourceArrival string `json:"source_arrival"`
	Bytes         int    `json:"bytes"`
}

type windowStat struct {
	Window       int `json:"window"`
	EffectiveCap int `json:"effective_cap"`
	Used         int `json:"used"`
}

type summary struct {
	IncidentsApplied []string `json:"incidents_applied"`
	TotalAdmissions  int      `json:"total_admissions"`
	TotalSpillBytes  int      `json:"total_spill_bytes"`
	TotalDropBytes   int      `json:"total_drop_bytes"`
	MaxWindow        int      `json:"max_window"`
}

func must(err error) {
	if err != nil {
		panic(err)
	}
}

func readJSON(path string, v any) {
	raw, err := os.ReadFile(path)
	must(err)
	must(json.Unmarshal(raw, v))
}

func clampCap(v int) int {
	if v < 1 {
		return 1
	}
	return v
}

func effectiveCap(base int, incidents []incident, w int) int {
	c := base
	for _, inc := range incidents {
		switch inc.Kind {
		case "cap_bump":
			if w >= inc.StartWindow {
				c += inc.Delta
			}
		case "cap_shave":
			if w >= inc.StartWindow {
				c -= inc.Delta
			}
		case "noop", "halt_spill":
			continue
		default:
			continue
		}
	}
	return clampCap(c)
}

func haltThreshold(incidents []incident) int {
	th := int(^uint(0) >> 1)
	found := false
	for _, inc := range incidents {
		if inc.Kind != "halt_spill" {
			continue
		}
		found = true
		if inc.FromWindow < th {
			th = inc.FromWindow
		}
	}
	if !found {
		return th
	}
	return th
}

func writeJSON(path string, v any) {
	out, err := json.MarshalIndent(v, "", "  ")
	must(err)
	out = append(out, '\n')
	must(os.WriteFile(path, out, 0o644))
}

func main() {
	dataDir := os.Getenv("PWS_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/poolspill"
	}
	auditDir := os.Getenv("PWS_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	must(os.MkdirAll(auditDir, 0o755))

	var pol policy
	readJSON(filepath.Join(dataDir, "policy.json"), &pol)
	if pol.WindowMs <= 0 || pol.PoolCeiling <= 0 {
		panic("invalid policy")
	}

	var incFile incidentsFile
	readJSON(filepath.Join(dataDir, "incidents.json"), &incFile)

	haltFrom := haltThreshold(incFile.Incidents)

	buckets := map[int][]arrival{}
	maxSeen := 0

	arrivalDir := filepath.Join(dataDir, "arrivals")
	entries, err := os.ReadDir(arrivalDir)
	must(err)
	for _, ent := range entries {
		if ent.IsDir() || !strings.HasSuffix(ent.Name(), ".json") {
			continue
		}
		var a arrival
		readJSON(filepath.Join(arrivalDir, ent.Name()), &a)
		if a.Bytes <= 0 || a.ArrivalID == "" || a.PartitionID == "" || a.TsMs < 0 {
			panic("invalid arrival in " + ent.Name())
		}
		w := int(a.TsMs / int64(pol.WindowMs))
		buckets[w] = append(buckets[w], a)
		if w > maxSeen {
			maxSeen = w
		}
	}

	var admissions []admission
	var spills []spill
	var drops []drop

	changed := true
	for changed {
		changed = false
		for w := 0; w <= maxSeen; w++ {
			xs := buckets[w]
			if len(xs) == 0 {
				continue
			}
			delete(buckets, w)
			sort.Slice(xs, func(i, j int) bool {
				if xs[i].TsMs != xs[j].TsMs {
					return xs[i].TsMs < xs[j].TsMs
				}
				if xs[i].PartitionID != xs[j].PartitionID {
					return xs[i].PartitionID < xs[j].PartitionID
				}
				return xs[i].ArrivalID < xs[j].ArrivalID
			})

			cap := effectiveCap(pol.PoolCeiling, incFile.Incidents, w)
			used := 0
			for _, a := range xs {
				room := cap - used
				if room < 0 {
					room = 0
				}
				take := a.Bytes
				if take > room {
					take = room
				}
				if take > 0 {
					admissions = append(admissions, admission{
						Window:      w,
						PartitionID: a.PartitionID,
						ArrivalID:   a.ArrivalID,
						Bytes:       take,
					})
					used += take
				}
				remain := a.Bytes - take
				if remain == 0 {
					continue
				}
				if w >= haltFrom {
					drops = append(drops, drop{
						Window:        w,
						PartitionID:   a.PartitionID,
						SourceArrival: a.ArrivalID,
						Bytes:         remain,
					})
					changed = true
					continue
				}
				tw := w + 1
				spills = append(spills, spill{
					FromWindow:    w,
					ToWindow:      tw,
					PartitionID:   a.PartitionID,
					SourceArrival: a.ArrivalID,
					Bytes:         remain,
				})
				next := arrival{
					ArrivalID:   fmt.Sprintf("spill#%s#%d", a.ArrivalID, tw),
					PartitionID: a.PartitionID,
					TsMs:        int64(tw * pol.WindowMs),
					Bytes:       remain,
				}
				buckets[tw] = append(buckets[tw], next)
				if tw > maxSeen {
					maxSeen = tw
				}
				changed = true
			}
		}
	}

	sort.Slice(admissions, func(i, j int) bool {
		if admissions[i].Window != admissions[j].Window {
			return admissions[i].Window < admissions[j].Window
		}
		if admissions[i].PartitionID != admissions[j].PartitionID {
			return admissions[i].PartitionID < admissions[j].PartitionID
		}
		if admissions[i].ArrivalID != admissions[j].ArrivalID {
			return admissions[i].ArrivalID < admissions[j].ArrivalID
		}
		return admissions[i].Bytes < admissions[j].Bytes
	})

	sort.Slice(spills, func(i, j int) bool {
		if spills[i].FromWindow != spills[j].FromWindow {
			return spills[i].FromWindow < spills[j].FromWindow
		}
		if spills[i].ToWindow != spills[j].ToWindow {
			return spills[i].ToWindow < spills[j].ToWindow
		}
		if spills[i].PartitionID != spills[j].PartitionID {
			return spills[i].PartitionID < spills[j].PartitionID
		}
		if spills[i].SourceArrival != spills[j].SourceArrival {
			return spills[i].SourceArrival < spills[j].SourceArrival
		}
		return spills[i].Bytes < spills[j].Bytes
	})

	sort.Slice(drops, func(i, j int) bool {
		if drops[i].Window != drops[j].Window {
			return drops[i].Window < drops[j].Window
		}
		if drops[i].PartitionID != drops[j].PartitionID {
			return drops[i].PartitionID < drops[j].PartitionID
		}
		if drops[i].SourceArrival != drops[j].SourceArrival {
			return drops[i].SourceArrival < drops[j].SourceArrival
		}
		return drops[i].Bytes < drops[j].Bytes
	})

	usedPer := map[int]int{}
	for _, a := range admissions {
		usedPer[a.Window] += a.Bytes
	}

	var windows []windowStat
	for w := 0; w <= maxSeen; w++ {
		if _, ok := usedPer[w]; !ok {
			continue
		}
		windows = append(windows, windowStat{
			Window:       w,
			EffectiveCap: effectiveCap(pol.PoolCeiling, incFile.Incidents, w),
			Used:         usedPer[w],
		})
	}
	sort.Slice(windows, func(i, j int) bool { return windows[i].Window < windows[j].Window })

	applied := make([]string, 0, len(incFile.Incidents))
	for _, inc := range incFile.Incidents {
		applied = append(applied, inc.Kind)
	}

	totalAdm := 0
	for _, a := range admissions {
		totalAdm += a.Bytes
	}
	totalSpill := 0
	for _, s := range spills {
		totalSpill += s.Bytes
	}
	totalDrop := 0
	for _, d := range drops {
		totalDrop += d.Bytes
	}

	maxWin := maxSeen
	for _, a := range admissions {
		if a.Window > maxWin {
			maxWin = a.Window
		}
	}
	for _, s := range spills {
		if s.FromWindow > maxWin {
			maxWin = s.FromWindow
		}
		if s.ToWindow > maxWin {
			maxWin = s.ToWindow
		}
	}
	for _, d := range drops {
		if d.Window > maxWin {
			maxWin = d.Window
		}
	}

	sum := summary{
		IncidentsApplied: applied,
		TotalAdmissions:  totalAdm,
		TotalSpillBytes:  totalSpill,
		TotalDropBytes:   totalDrop,
		MaxWindow:        maxWin,
	}

	writeJSON(filepath.Join(auditDir, "admissions.json"), map[string]any{"admissions": admissions})
	writeJSON(filepath.Join(auditDir, "spills.json"), map[string]any{"spills": spills})
	writeJSON(filepath.Join(auditDir, "drops.json"), map[string]any{"drops": drops})
	writeJSON(filepath.Join(auditDir, "windows.json"), map[string]any{"windows": windows})
	writeJSON(filepath.Join(auditDir, "summary.json"), sum)
}
