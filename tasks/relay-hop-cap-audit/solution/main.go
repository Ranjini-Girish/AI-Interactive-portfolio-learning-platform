package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type Policy struct {
	CarryMax  int      `json:"carry_max"`
	Epochs    []int    `json:"epochs"`
	HopsOrder []string `json:"hops_order"`
}

type Incident struct {
	Kind  string `json:"kind"`
	Epoch int    `json:"epoch"`
	HopID string `json:"hop_id,omitempty"`
	Delta int    `json:"delta,omitempty"`
}

type IncidentsFile struct {
	Incidents []Incident `json:"incidents"`
}

type HopFile struct {
	HopID   string `json:"hop_id"`
	BaseCap int    `json:"base_cap"`
}

type FlowFile struct {
	FlowID string `json:"flow_id"`
	Epoch  int    `json:"epoch"`
	HopID  string `json:"hop_id"`
	Bytes  int    `json:"bytes"`
}

type Admission struct {
	Bytes   int    `json:"bytes"`
	Epoch   int    `json:"epoch"`
	FlowID  string `json:"flow_id"`
	HopID   string `json:"hop_id"`
}

type Denial struct {
	Available int    `json:"available"`
	Epoch     int    `json:"epoch"`
	FlowID    string `json:"flow_id"`
	HopID     string `json:"hop_id"`
	Requested int    `json:"requested"`
}

type LedgerRow struct {
	CapCore  int    `json:"cap_core"`
	CarryIn  int    `json:"carry_in"`
	CarryOut int    `json:"carry_out"`
	Epoch    int    `json:"epoch"`
	HopID    string `json:"hop_id"`
	Used     int    `json:"used"`
}

type Summary struct {
	IncidentsApplied   []string `json:"incidents_applied"`
	MaxEpoch           int      `json:"max_epoch"`
	TotalAdmissions    int      `json:"total_admissions"`
	TotalAdmittedBytes int      `json:"total_admitted_bytes"`
	TotalDenials       int      `json:"total_denials"`
	TotalDeniedBytes   int      `json:"total_denied_bytes"`
}

func readJSON(path string, dst any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, dst)
}

func writeJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}

func sortedGlob(dir, pattern string) ([]string, error) {
	matches, err := filepath.Glob(filepath.Join(dir, pattern))
	if err != nil {
		return nil, err
	}
	sort.Strings(matches)
	return matches, nil
}

func main() {
	dataDir := os.Getenv("RHC_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/relayhop"
	}
	auditDir := os.Getenv("RHC_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		panic(err)
	}

	var pol Policy
	if err := readJSON(filepath.Join(dataDir, "policy.json"), &pol); err != nil {
		panic(err)
	}
	var incFile IncidentsFile
	if err := readJSON(filepath.Join(dataDir, "incidents.json"), &incFile); err != nil {
		panic(err)
	}

	hopPaths, err := sortedGlob(filepath.Join(dataDir, "hops"), "*.json")
	if err != nil {
		panic(err)
	}
	base := map[string]int{}
	for _, p := range hopPaths {
		var hf HopFile
		if err := readJSON(p, &hf); err != nil {
			panic(err)
		}
		base[hf.HopID] = hf.BaseCap
	}

	flowPaths, err := sortedGlob(filepath.Join(dataDir, "flows"), "*.json")
	if err != nil {
		panic(err)
	}
	var flows []FlowFile
	for _, p := range flowPaths {
		var ff FlowFile
		if err := readJSON(p, &ff); err != nil {
			panic(err)
		}
		flows = append(flows, ff)
	}

	epochSet := map[int]struct{}{}
	for _, e := range pol.Epochs {
		epochSet[e] = struct{}{}
	}
	for _, f := range flows {
		if _, ok := epochSet[f.Epoch]; !ok {
			panic(fmt.Errorf("flow %s epoch %d not in policy.epochs", f.FlowID, f.Epoch))
		}
		if _, ok := base[f.HopID]; !ok {
			panic(fmt.Errorf("unknown hop %s", f.HopID))
		}
	}

	deltaAcc := map[string]int{}
	halted := map[string]bool{}
	carry := map[string]int{}
	hopSet := map[string]struct{}{}
	for _, h := range pol.HopsOrder {
		hopSet[h] = struct{}{}
	}
	if len(hopSet) != len(pol.HopsOrder) {
		panic(fmt.Errorf("hops_order contains duplicates"))
	}
	if len(hopSet) != len(base) {
		panic(fmt.Errorf("hops_order must list every hop fixture exactly once"))
	}
	for h := range base {
		if _, ok := hopSet[h]; !ok {
			panic(fmt.Errorf("hop %s missing from hops_order", h))
		}
	}
	for _, h := range pol.HopsOrder {
		deltaAcc[h] = 0
		halted[h] = false
		carry[h] = 0
	}

	var admissions []Admission
	var denials []Denial
	var ledgers []LedgerRow

	capCore := func(h string) int {
		if halted[h] {
			return 0
		}
		v := base[h] + deltaAcc[h]
		if v < 1 {
			v = 1
		}
		return v
	}

	for _, e := range pol.Epochs {
		for _, inc := range incFile.Incidents {
			if inc.Epoch != e {
				continue
			}
			switch inc.Kind {
			case "noop":
			case "cap_add":
				deltaAcc[inc.HopID] += inc.Delta
			case "halt_hop":
				halted[inc.HopID] = true
				carry[inc.HopID] = 0
			case "resume_hop":
				halted[inc.HopID] = false
				carry[inc.HopID] = 0
			default:
				panic(fmt.Errorf("unknown incident kind %q", inc.Kind))
			}
		}

		cin := map[string]int{}
		for _, h := range pol.HopsOrder {
			cin[h] = carry[h]
		}

		used := map[string]int{}
		for _, h := range pol.HopsOrder {
			used[h] = 0
		}

		budget := func(h string) int {
			return capCore(h) + cin[h]
		}

		var epochFlows []FlowFile
		for _, f := range flows {
			if f.Epoch == e {
				epochFlows = append(epochFlows, f)
			}
		}
		sort.Slice(epochFlows, func(i, j int) bool {
			if epochFlows[i].HopID != epochFlows[j].HopID {
				return epochFlows[i].HopID < epochFlows[j].HopID
			}
			return epochFlows[i].FlowID < epochFlows[j].FlowID
		})

		for _, f := range epochFlows {
			h := f.HopID
			b := f.Bytes
			avail := budget(h) - used[h]
			if avail < 0 {
				avail = 0
			}
			if b <= avail {
				used[h] += b
				admissions = append(admissions, Admission{
					Bytes:  b,
					Epoch:  e,
					FlowID: f.FlowID,
					HopID:  h,
				})
			} else {
				denials = append(denials, Denial{
					Available: avail,
					Epoch:     e,
					FlowID:    f.FlowID,
					HopID:     h,
					Requested: b,
				})
			}
		}

		for _, h := range pol.HopsOrder {
			cc := capCore(h)
			bud := cc + cin[h]
			u := used[h]
			rem := bud - u
			cout := min(pol.CarryMax, max(0, rem))
			if halted[h] {
				cout = 0
			}
			ledgers = append(ledgers, LedgerRow{
				CapCore:  cc,
				CarryIn:  cin[h],
				CarryOut: cout,
				Epoch:    e,
				HopID:    h,
				Used:     u,
			})
			carry[h] = cout
		}
	}

	sort.Slice(admissions, func(i, j int) bool {
		if admissions[i].Epoch != admissions[j].Epoch {
			return admissions[i].Epoch < admissions[j].Epoch
		}
		if admissions[i].HopID != admissions[j].HopID {
			return admissions[i].HopID < admissions[j].HopID
		}
		return admissions[i].FlowID < admissions[j].FlowID
	})
	sort.Slice(denials, func(i, j int) bool {
		if denials[i].Epoch != denials[j].Epoch {
			return denials[i].Epoch < denials[j].Epoch
		}
		if denials[i].HopID != denials[j].HopID {
			return denials[i].HopID < denials[j].HopID
		}
		return denials[i].FlowID < denials[j].FlowID
	})
	sort.Slice(ledgers, func(i, j int) bool {
		if ledgers[i].Epoch != ledgers[j].Epoch {
			return ledgers[i].Epoch < ledgers[j].Epoch
		}
		return ledgers[i].HopID < ledgers[j].HopID
	})

	applied := make([]string, 0, len(incFile.Incidents))
	for _, inc := range incFile.Incidents {
		applied = append(applied, inc.Kind)
	}

	maxEp := 0
	for _, inc := range incFile.Incidents {
		if inc.Epoch > maxEp {
			maxEp = inc.Epoch
		}
	}
	for _, a := range admissions {
		if a.Epoch > maxEp {
			maxEp = a.Epoch
		}
	}
	for _, d := range denials {
		if d.Epoch > maxEp {
			maxEp = d.Epoch
		}
	}

	totAdm := 0
	totAdmBytes := 0
	for _, a := range admissions {
		totAdm++
		totAdmBytes += a.Bytes
	}
	totDen := len(denials)
	totDenBytes := 0
	for _, d := range denials {
		totDenBytes += d.Requested
	}

	summary := Summary{
		IncidentsApplied:   applied,
		MaxEpoch:           maxEp,
		TotalAdmissions:    totAdm,
		TotalAdmittedBytes: totAdmBytes,
		TotalDenials:       totDen,
		TotalDeniedBytes:   totDenBytes,
	}

	if err := writeJSON(filepath.Join(auditDir, "admissions.json"), map[string]any{
		"admissions": admissions,
	}); err != nil {
		panic(err)
	}
	if err := writeJSON(filepath.Join(auditDir, "denials.json"), map[string]any{
		"denials": denials,
	}); err != nil {
		panic(err)
	}
	if err := writeJSON(filepath.Join(auditDir, "carry_ledgers.json"), map[string]any{
		"rows": ledgers,
	}); err != nil {
		panic(err)
	}
	if err := writeJSON(filepath.Join(auditDir, "summary.json"), summary); err != nil {
		panic(err)
	}
}
