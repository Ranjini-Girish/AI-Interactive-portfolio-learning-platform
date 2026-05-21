package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type policyFile struct {
	AlignSlack      int       `json:"align_slack"`
	AnchorsPath     string    `json:"anchors_path"`
	IncidentLogPath string    `json:"incident_log_path"`
	LanesGlob       string    `json:"lanes_glob"`
	PerLaneCost     int       `json:"per_lane_cost"`
	PoolStatePath   string    `json:"pool_state_path"`
	StrideSignFold  bool      `json:"stride_sign_fold"`
	Window          windowObj `json:"window"`
}

type windowObj struct {
	EndDay   int `json:"end_day"`
	StartDay int `json:"start_day"`
}

type anchorsFile struct {
	Window windowObj `json:"window"`
}

type poolFile struct {
	Tokens int `json:"tokens"`
}

type incident struct {
	LaneID     string `json:"lane_id"`
	ThroughDay int    `json:"through_day"`
}

type incidentFile struct {
	Incidents []incident `json:"incidents"`
}

type laneFile struct {
	DayEnd     int    `json:"day_end"`
	DayStart   int    `json:"day_start"`
	LaneID     string `json:"lane_id"`
	TickBase   int    `json:"tick_base"`
	TickStride int    `json:"tick_stride"`
	Tier       string `json:"tier"`
}

type clusterOut struct {
	ClusterID int            `json:"cluster_id"`
	LaneIDs   []string       `json:"lane_ids"`
	PoolDraw  int            `json:"pool_draw"`
	Status    string         `json:"status"`
	Ticks     map[string]int `json:"ticks"`
}

type drawEvt struct {
	After     int `json:"after"`
	Amount    int `json:"amount"`
	Before    int `json:"before"`
	ClusterID int `json:"cluster_id"`
}

type poolLedgerOut struct {
	ClosingTokens int       `json:"closing_tokens"`
	Draws         []drawEvt `json:"draws"`
	OpeningTokens int       `json:"opening_tokens"`
}

type summaryOut struct {
	ClosingTokens         int       `json:"closing_tokens"`
	ClusterCount            int       `json:"cluster_count"`
	EffectiveWindow         windowObj `json:"effective_window"`
	LaneCountInWindow       int       `json:"lane_count_in_window"`
	OpeningTokens           int       `json:"opening_tokens"`
	PoolDeferredClusters    int       `json:"pool_deferred_clusters"`
	PoolSatisfiedClusters   int       `json:"pool_satisfied_clusters"`
	QuarantinedClusters     int       `json:"quarantined_clusters"`
	StrideSignFoldApplied   bool      `json:"stride_sign_fold_applied"`
	TiersTouched            []string  `json:"tiers_touched"`
}

func readJSON(path string, dst any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.DisallowUnknownFields()
	return dec.Decode(dst)
}

func specJSONBytes(v any) ([]byte, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(true)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		return nil, err
	}
	out := buf.Bytes()
	if len(out) == 0 {
		return nil, errors.New("empty json")
	}
	if out[len(out)-1] != '\n' {
		out = append(out, '\n')
	}
	return out, nil
}

func writeSpecJSON(path string, v any) error {
	b, err := specJSONBytes(v)
	if err != nil {
		return err
	}
	return os.WriteFile(path, b, 0o644)
}

func intersectWindow(a, b windowObj) (windowObj, error) {
	s := a.StartDay
	if b.StartDay > s {
		s = b.StartDay
	}
	e := a.EndDay
	if b.EndDay < e {
		e = b.EndDay
	}
	if s > e {
		return windowObj{}, fmt.Errorf("window intersection empty")
	}
	return windowObj{StartDay: s, EndDay: e}, nil
}

func absInt(x int) int {
	if x < 0 {
		return -x
	}
	return x
}

func main() {
	dataDir := os.Getenv("TAW_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/taw_lab"
	}
	auditDir := os.Getenv("TAW_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	switch len(os.Args) {
	case 1:
	case 3:
		dataDir = os.Args[1]
		auditDir = os.Args[2]
	default:
		fmt.Fprintln(os.Stderr, "expected zero extra args or lab_dir audit_dir")
		os.Exit(1)
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	var pol policyFile
	if err := readJSON(filepath.Join(dataDir, "policy.json"), &pol); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if pol.AlignSlack < 0 || pol.PerLaneCost <= 0 {
		fmt.Fprintln(os.Stderr, "invalid policy bounds")
		os.Exit(1)
	}
	if pol.Window.StartDay > pol.Window.EndDay {
		fmt.Fprintln(os.Stderr, "invalid policy window")
		os.Exit(1)
	}

	ap := filepath.Join(dataDir, filepath.Clean(strings.ReplaceAll(pol.AnchorsPath, "\\", "/")))
	if strings.Contains(pol.AnchorsPath, "..") {
		fmt.Fprintln(os.Stderr, "invalid anchors path")
		os.Exit(1)
	}
	var anchors anchorsFile
	if err := readJSON(ap, &anchors); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if anchors.Window.StartDay > anchors.Window.EndDay {
		fmt.Fprintln(os.Stderr, "invalid anchors window")
		os.Exit(1)
	}

	eff, err := intersectWindow(pol.Window, anchors.Window)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	var pool poolFile
	pp := filepath.Join(dataDir, filepath.Clean(strings.ReplaceAll(pol.PoolStatePath, "\\", "/")))
	if strings.Contains(pol.PoolStatePath, "..") {
		fmt.Fprintln(os.Stderr, "invalid pool path")
		os.Exit(1)
	}
	if err := readJSON(pp, &pool); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	var inc incidentFile
	ip := filepath.Join(dataDir, filepath.Clean(strings.ReplaceAll(pol.IncidentLogPath, "\\", "/")))
	if strings.Contains(pol.IncidentLogPath, "..") {
		fmt.Fprintln(os.Stderr, "invalid incident path")
		os.Exit(1)
	}
	if err := readJSON(ip, &inc); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	globPath := filepath.Join(dataDir, filepath.Clean(strings.ReplaceAll(pol.LanesGlob, "\\", "/")))
	if strings.Contains(pol.LanesGlob, "..") {
		fmt.Fprintln(os.Stderr, "invalid lanes glob")
		os.Exit(1)
	}
	matches, err := filepath.Glob(globPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	sort.Strings(matches)

	quarantine := map[string]struct{}{}
	for _, it := range inc.Incidents {
		if it.ThroughDay >= eff.StartDay {
			quarantine[it.LaneID] = struct{}{}
		}
	}

	type laneRec struct {
		id         string
		dayStart   int
		dayEnd     int
		tickBase   int
		tickStride int
		tier       string
		tickEff    int
		inWindow   bool
	}

	var lanes []laneRec
	for _, p := range matches {
		var lf laneFile
		if err := readJSON(p, &lf); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		if lf.DayStart > lf.DayEnd {
			fmt.Fprintln(os.Stderr, "lane day range invalid")
			os.Exit(1)
		}
		stride := lf.TickStride
		if pol.StrideSignFold {
			stride = absInt(stride)
		}
		es := lf.DayStart
		if eff.StartDay > es {
			es = eff.StartDay
		}
		ee := lf.DayEnd
		if eff.EndDay < ee {
			ee = eff.EndDay
		}
		inWin := es <= ee
		tickEff := 0
		if inWin {
			tickEff = lf.TickBase + stride*(ee-lf.DayStart)
		}
		lanes = append(lanes, laneRec{
			id: lf.LaneID, dayStart: lf.DayStart, dayEnd: lf.DayEnd,
			tickBase: lf.TickBase, tickStride: stride, tier: lf.Tier,
			tickEff: tickEff, inWindow: inWin,
		})
	}
	sort.Slice(lanes, func(i, j int) bool { return lanes[i].id < lanes[j].id })

	var activeIdx []int
	for i, ln := range lanes {
		if ln.inWindow {
			activeIdx = append(activeIdx, i)
		}
	}

	var free []laneRec
	for _, i := range activeIdx {
		ln := lanes[i]
		if _, q := quarantine[ln.id]; q {
			continue
		}
		free = append(free, ln)
	}

	parent := make([]int, len(free))
	for i := range parent {
		parent[i] = i
	}
	var find func(int) int
	find = func(a int) int {
		if parent[a] != a {
			parent[a] = find(parent[a])
		}
		return parent[a]
	}
	union := func(a, b int) {
		ra, rb := find(a), find(b)
		if ra == rb {
			return
		}
		if ra < rb {
			parent[rb] = ra
		} else {
			parent[ra] = rb
		}
	}
	for i := 0; i < len(free); i++ {
		for j := i + 1; j < len(free); j++ {
			if absInt(free[i].tickEff-free[j].tickEff) <= pol.AlignSlack {
				union(i, j)
			}
		}
	}

	compRoots := map[int][]laneRec{}
	for i, ln := range free {
		r := find(i)
		compRoots[r] = append(compRoots[r], ln)
	}
	var comps [][]laneRec
	for _, grp := range compRoots {
		sort.Slice(grp, func(i, j int) bool {
			if grp[i].tickEff != grp[j].tickEff {
				return grp[i].tickEff < grp[j].tickEff
			}
			return grp[i].id < grp[j].id
		})
		comps = append(comps, grp)
	}
	sort.Slice(comps, func(i, j int) bool {
		return comps[i][0].id < comps[j][0].id
	})

	var qLanes []laneRec
	for _, i := range activeIdx {
		ln := lanes[i]
		if _, ok := quarantine[ln.id]; ok {
			qLanes = append(qLanes, ln)
		}
	}
	sort.Slice(qLanes, func(i, j int) bool { return qLanes[i].id < qLanes[j].id })

	var clusters []clusterOut
	cid := 0
	for _, ln := range qLanes {
		clusters = append(clusters, clusterOut{
			ClusterID: cid,
			LaneIDs:   []string{ln.id},
			PoolDraw:  0,
			Status:    "quarantined",
			Ticks:     map[string]int{ln.id: ln.tickEff},
		})
		cid++
	}
	for _, grp := range comps {
		ids := make([]string, 0, len(grp))
		tm := map[string]int{}
		for _, ln := range grp {
			ids = append(ids, ln.id)
			tm[ln.id] = ln.tickEff
		}
		clusters = append(clusters, clusterOut{
			ClusterID: cid,
			LaneIDs:   ids,
			PoolDraw:  0,
			Status:    "pending",
			Ticks:     tm,
		})
		cid++
	}

	tokens := pool.Tokens
	opening := tokens
	var draws []drawEvt
	sat := 0
	def := 0
	qu := len(qLanes)

	for i := range clusters {
		if clusters[i].Status == "quarantined" {
			continue
		}
		cost := pol.PerLaneCost * len(clusters[i].LaneIDs)
		if tokens >= cost {
			before := tokens
			tokens -= cost
			draws = append(draws, drawEvt{
				After: tokens, Amount: cost, Before: before, ClusterID: clusters[i].ClusterID,
			})
			clusters[i].PoolDraw = cost
			clusters[i].Status = "pool_satisfied"
			sat++
		} else {
			clusters[i].PoolDraw = 0
			clusters[i].Status = "pool_deferred"
			def++
		}
	}

	tierSet := map[string]struct{}{}
	for _, i := range activeIdx {
		tierSet[lanes[i].tier] = struct{}{}
	}
	tiers := make([]string, 0, len(tierSet))
	for t := range tierSet {
		tiers = append(tiers, t)
	}
	sort.Strings(tiers)

	summary := summaryOut{
		ClosingTokens:         tokens,
		ClusterCount:          len(clusters),
		EffectiveWindow:       eff,
		LaneCountInWindow:     len(activeIdx),
		OpeningTokens:         opening,
		PoolDeferredClusters:  def,
		PoolSatisfiedClusters: sat,
		QuarantinedClusters:   qu,
		StrideSignFoldApplied: pol.StrideSignFold,
		TiersTouched:          tiers,
	}

	ledger := poolLedgerOut{
		ClosingTokens: tokens,
		Draws:         draws,
		OpeningTokens: opening,
	}

	if err := writeSpecJSON(filepath.Join(auditDir, "clusters.json"), map[string]any{
		"clusters": clusters,
	}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := writeSpecJSON(filepath.Join(auditDir, "pool_ledger.json"), ledger); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := writeSpecJSON(filepath.Join(auditDir, "summary.json"), summary); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
