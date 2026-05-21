package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
)

type policy struct {
	HotUtil       int     `json:"hot_util"`
	MedianK       int     `json:"median_k"`
	MergeGapTol   int     `json:"merge_gap_tol"`
	ReliefDelta   int     `json:"relief_delta"`
	DepthCap      float64 `json:"depth_cap"`
	DepthPerQD    float64 `json:"depth_per_qd"`
}

type device struct {
	DeviceID   string `json:"device_id"`
	QueueDepth int    `json:"queue_depth"`
}

type incidents struct {
	Spans []span `json:"spans"`
}

type span struct {
	Kind     string `json:"kind"`
	StartT   int    `json:"start_t"`
	EndT     int    `json:"end_t"`
	DeviceID string `json:"device_id,omitempty"`
}

type loadFile struct {
	DeviceID string      `json:"device_id"`
	Ticks    []tickEntry `json:"ticks"`
}

type tickEntry struct {
	T    int `json:"t"`
	Util int `json:"util"`
}

type report struct {
	Summary summary   `json:"summary"`
	Devices []devOut  `json:"devices"`
}

type summary struct {
	DevicesScanned           int `json:"devices_scanned"`
	TotalHotTicks            int `json:"total_hot_ticks"`
	TotalWindows             int `json:"total_windows"`
	VerdictHot               int `json:"verdict_hot"`
	VerdictWarm              int `json:"verdict_warm"`
	VerdictCool              int `json:"verdict_cool"`
	FreezeSuppressedTicks    int `json:"freeze_suppressed_ticks"`
	ReliefActiveTicks        int `json:"relief_active_ticks"`
}

type devOut struct {
	DeviceID   string `json:"device_id"`
	HotWindows [][]int `json:"hot_windows"`
	Verdict    string `json:"verdict"`
}

func main() {
	dataDir := os.Getenv("IOC_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/ioc_lab"
	}
	auditDir := os.Getenv("IOC_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := run(dataDir, auditDir); err != nil {
		fmt.Fprintf(os.Stderr, "%v\n", err)
		os.Exit(1)
	}
}

func run(dataDir, auditDir string) error {
	policyPath := filepath.Join(dataDir, "policy.json")
	devicesPath := filepath.Join(dataDir, "devices.json")
	incPath := filepath.Join(dataDir, "incidents.json")

	polCfg, err := readJSON[policy](policyPath)
	if err != nil {
		return err
	}
	pol := *polCfg
	devList, err := readJSON[[]device](devicesPath)
	if err != nil {
		return err
	}
	inc, err := readJSON[incidents](incPath)
	if err != nil {
		return err
	}

	h := pol.MedianK / 2
	if pol.MedianK%2 == 0 || pol.MedianK < 1 {
		return fmt.Errorf("median_k must be a positive odd integer")
	}

	depthByDevice := map[string]int{}
	for _, d := range *devList {
		depthByDevice[d.DeviceID] = d.QueueDepth
	}

	matches, err := filepath.Glob(filepath.Join(dataDir, "loads", "*.json"))
	if err != nil {
		return err
	}
	sort.Strings(matches)

	samples := map[string]map[int]int{}
	for _, path := range matches {
		lf, err := readJSON[loadFile](path)
		if err != nil {
			return err
		}
		id := lf.DeviceID
		if samples[id] == nil {
			samples[id] = map[int]int{}
		}
		for _, te := range lf.Ticks {
			samples[id][te.T] = te.Util
		}
	}

	freezeActive := func(t int) bool {
		for _, sp := range inc.Spans {
			if sp.Kind != "freeze" {
				continue
			}
			if t >= sp.StartT && t <= sp.EndT {
				return true
			}
		}
		return false
	}
	embargoActive := func(dev string, t int) bool {
		for _, sp := range inc.Spans {
			if sp.Kind != "embargo" || sp.DeviceID != dev {
				continue
			}
			if t >= sp.StartT && t <= sp.EndT {
				return true
			}
		}
		return false
	}
	reliefActive := func(dev string, t int) bool {
		for _, sp := range inc.Spans {
			if sp.Kind != "credit_relief" || sp.DeviceID != dev {
				continue
			}
			if t >= sp.StartT && t <= sp.EndT {
				return true
			}
		}
		return false
	}

	thresholdFor := func(dev string) int {
		qd := depthByDevice[dev]
		f := 1.0 + float64(qd)*pol.DepthPerQD
		if f > pol.DepthCap {
			f = pol.DepthCap
		}
		return int(math.Ceil(float64(pol.HotUtil) * f))
	}

	medianInt := func(vals []int) int {
		if len(vals) == 0 {
			return 0
		}
		cp := append([]int(nil), vals...)
		sort.Ints(cp)
		n := len(cp)
		mid := n / 2
		if n%2 == 1 {
			return cp[mid]
		}
		return (cp[mid-1] + cp[mid]) / 2
	}

	smoothed := func(dev string, t int) int {
		m := samples[dev]
		if m == nil {
			return 0
		}
		var vals []int
		for dt := -h; dt <= h; dt++ {
			if u, ok := m[t+dt]; ok {
				vals = append(vals, u)
			}
		}
		return medianInt(vals)
	}

	wouldHot := func(dev string, t int) bool {
		if embargoActive(dev, t) {
			return false
		}
		u := smoothed(dev, t)
		if u == 0 && len(samples[dev]) == 0 {
			return false
		}
		th := thresholdFor(dev)
		if reliefActive(dev, t) {
			th -= pol.ReliefDelta
			if th < 0 {
				th = 0
			}
		}
		return u >= th
	}

	isHot := func(dev string, t int) bool {
		if freezeActive(t) {
			return false
		}
		return wouldHot(dev, t)
	}

	freezeSuppressed := 0
	reliefTicks := 0
	for _, d := range *devList {
		dev := d.DeviceID
		m := samples[dev]
		if len(m) == 0 {
			continue
		}
		ts := make([]int, 0, len(m))
		for t := range m {
			ts = append(ts, t)
		}
		sort.Ints(ts)
		minT, maxT := ts[0], ts[len(ts)-1]
		for t := minT; t <= maxT; t++ {
			if reliefActive(dev, t) {
				reliefTicks++
			}
			if freezeActive(t) && wouldHot(dev, t) {
				freezeSuppressed++
			}
		}
	}

	totalHot := 0
	totalWindows := 0
	vHot, vWarm, vCool := 0, 0, 0

	outDevs := make([]devOut, 0, len(*devList))
	for _, d := range *devList {
		dev := d.DeviceID
		m := samples[dev]
		var hotTicks []int
		if len(m) > 0 {
			ts := make([]int, 0, len(m))
			for t := range m {
				ts = append(ts, t)
			}
			sort.Ints(ts)
			minT, maxT := ts[0], ts[len(ts)-1]
			for t := minT; t <= maxT; t++ {
				if isHot(dev, t) {
					hotTicks = append(hotTicks, t)
					totalHot++
				}
			}
		}
		windows := mergeConsecutive(hotTicks, pol.MergeGapTol)
		if windows == nil {
			windows = [][]int{}
		}
		totalWindows += len(windows)
		verdict := "cool"
		if len(hotTicks) > 0 {
			verdict = "warm"
			for _, w := range windows {
				if w[1]-w[0]+1 >= 3 {
					verdict = "hot"
					break
				}
			}
		}
		switch verdict {
		case "hot":
			vHot++
		case "warm":
			vWarm++
		default:
			vCool++
		}
		outDevs = append(outDevs, devOut{
			DeviceID:   dev,
			HotWindows: windows,
			Verdict:    verdict,
		})
	}

	sort.Slice(outDevs, func(i, j int) bool {
		return outDevs[i].DeviceID < outDevs[j].DeviceID
	})

	rep := report{
		Summary: summary{
			DevicesScanned:        len(*devList),
			TotalHotTicks:         totalHot,
			TotalWindows:          totalWindows,
			VerdictHot:            vHot,
			VerdictWarm:           vWarm,
			VerdictCool:           vCool,
			FreezeSuppressedTicks: freezeSuppressed,
			ReliefActiveTicks:     reliefTicks,
		},
		Devices: outDevs,
	}

	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		return err
	}
	path := filepath.Join(auditDir, "report.json")
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(true)
	if err := enc.Encode(rep); err != nil {
		return err
	}
	return nil
}

func mergeConsecutive(ticks []int, tol int) [][]int {
	if len(ticks) == 0 {
		return nil
	}
	sort.Ints(ticks)
	var out [][]int
	curS, curE := ticks[0], ticks[0]
	for i := 1; i < len(ticks); i++ {
		t := ticks[i]
		if t <= curE+1+tol {
			if t > curE {
				curE = t
			}
			continue
		}
		out = append(out, []int{curS, curE})
		curS, curE = t, t
	}
	out = append(out, []int{curS, curE})
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
