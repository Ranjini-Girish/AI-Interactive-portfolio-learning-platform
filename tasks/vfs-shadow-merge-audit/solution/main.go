package main

import (
	"encoding/json"
	"maps"
	"os"
	"path/filepath"
	"slices"
	"sort"
)

type poolFile struct {
	PoolID               string `json:"pool_id"`
	AnchorEpoch          int64  `json:"anchor_epoch"`
	AsOfEpoch            int64  `json:"as_of_epoch"`
	DayLengthSec         int64  `json:"day_length_sec"`
	ShadowStaleSpanDays  int64  `json:"shadow_stale_span_days"`
}

type tierInfo struct {
	SoftCap       int64   `json:"soft_cap"`
	HardCap       int64   `json:"hard_cap"`
	ShadowWeight  float64 `json:"shadow_weight"`
}

type mountFile struct {
	MountID          string  `json:"mount_id"`
	PoolID           string  `json:"pool_id"`
	Tier             string  `json:"tier"`
	ParentMountID    *string `json:"parent_mount_id"`
	BaseBytes        int64   `json:"base_bytes"`
	ShadowBytes      int64   `json:"shadow_bytes"`
	ShadowDayLo      int64   `json:"shadow_day_lo"`
	ShadowDayHi      int64   `json:"shadow_day_hi"`
	LastTouchPoolDay int64   `json:"last_touch_pool_day"`
	ExportCapBytes   int64   `json:"export_cap_bytes"`
}

type inodeRow struct {
	InodeID       string  `json:"inode_id"`
	HomeMountID   string  `json:"home_mount_id"`
	Bytes         int64   `json:"bytes"`
	BorrowTarget  *string `json:"borrow_target"`
}

type inodeFile struct {
	Rows []inodeRow `json:"rows"`
}

type incidentFile struct {
	IncidentID     string `json:"incident_id"`
	PoolID         string `json:"pool_id"`
	Precedence     int64  `json:"precedence"`
	StartEpoch     int64  `json:"start_epoch"`
	EndEpoch       int64  `json:"end_epoch"`
	ScopeKind      string `json:"scope_kind"`
	ScopeMountID   string `json:"scope_mount_id"`
	FreezeMerge    bool   `json:"freeze_merge"`
}

type snapFile map[string]struct {
	Seq int64 `json:"seq"`
}

func readJSON(path string, v any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, v)
}

func listJSONFiles(root, sub string) []string {
	dir := filepath.Join(root, sub)
	entries, err := os.ReadDir(dir)
	if err != nil {
		panic(err)
	}
	out := make([]string, 0, len(entries))
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		out = append(out, filepath.Join(dir, e.Name()))
	}
	sort.Strings(out)
	return out
}

func main() {
	dataDir := os.Getenv("VFS_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/vfs_shadow"
	}
	auditDir := os.Getenv("VFS_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		panic(err)
	}

	var pool poolFile
	if err := readJSON(filepath.Join(dataDir, "pool.json"), &pool); err != nil {
		panic(err)
	}
	tiers := map[string]tierInfo{}
	if err := readJSON(filepath.Join(dataDir, "tiers.json"), &tiers); err != nil {
		panic(err)
	}

	mounts := map[string]mountFile{}
	for _, path := range listJSONFiles(dataDir, "mounts") {
		var m mountFile
		if e := readJSON(path, &m); e != nil {
			panic(e)
		}
		mounts[m.MountID] = m
	}

	snapSeq := map[string]int64{}
	for _, path := range listJSONFiles(dataDir, "snapshots") {
		var sf snapFile
		if e := readJSON(path, &sf); e != nil {
			panic(e)
		}
		for k, v := range sf {
			snapSeq[k] = v.Seq
		}
	}

	incidents := make([]incidentFile, 0)
	for _, path := range listJSONFiles(dataDir, "incidents") {
		var inc incidentFile
		if e := readJSON(path, &inc); e != nil {
			panic(e)
		}
		incidents = append(incidents, inc)
	}

	inodeRows := make([]inodeRow, 0)
	for _, path := range listJSONFiles(dataDir, "inodes") {
		var f inodeFile
		if e := readJSON(path, &f); e != nil {
			panic(e)
		}
		inodeRows = append(inodeRows, f.Rows...)
	}

	poolDay := int64(0)
	if pool.DayLengthSec > 0 {
		delta := pool.AsOfEpoch - pool.AnchorEpoch
		if delta > 0 {
			poolDay = delta / pool.DayLengthSec
		}
	}

	children := map[string][]string{}
	parentOf := map[string]string{}
	for id, m := range mounts {
		if m.ParentMountID != nil && *m.ParentMountID != "" {
			p := *m.ParentMountID
			children[p] = append(children[p], id)
			parentOf[id] = p
		}
	}
	for p := range children {
		sort.Slice(children[p], func(i, j int) bool {
			a, b := children[p][i], children[p][j]
			sa, sb := snapSeq[a], snapSeq[b]
			if sa != sb {
				return sa < sb
			}
			return a < b
		})
	}

	descendants := map[string]map[string]struct{}{}
	var dfsDesc func(root string) map[string]struct{}
	dfsDesc = func(root string) map[string]struct{} {
		out := map[string]struct{}{root: {}}
		for _, c := range children[root] {
			sub := dfsDesc(c)
			maps.Copy(out, sub)
		}
		return out
	}
	for id := range mounts {
		descendants[id] = dfsDesc(id)
	}

	incidentApplies := func(inc incidentFile, mountID string) bool {
		m := mounts[mountID]
		if inc.PoolID != m.PoolID {
			return false
		}
		if inc.StartEpoch > pool.AsOfEpoch || pool.AsOfEpoch >= inc.EndEpoch {
			return false
		}
		switch inc.ScopeKind {
		case "pool_wide":
			return true
		case "mount":
			return inc.ScopeMountID == mountID
		case "subtree":
			_, ok := descendants[inc.ScopeMountID][mountID]
			return ok
		default:
			return false
		}
	}

	type win struct {
		id          string
		prec        int64
		freezeMerge bool
	}
	winning := map[string]win{}
	for mid := range mounts {
		var best *win
		for _, inc := range incidents {
			if !incidentApplies(inc, mid) {
				continue
			}
			cand := win{id: inc.IncidentID, prec: inc.Precedence, freezeMerge: inc.FreezeMerge}
			if best == nil {
				b := cand
				best = &b
				continue
			}
			if cand.prec > best.prec || (cand.prec == best.prec && cand.id < best.id) {
				b := cand
				best = &b
			}
		}
		if best != nil {
			winning[mid] = *best
		}
	}

	activeIncSet := map[string]struct{}{}
	for _, inc := range incidents {
		for mid := range mounts {
			if incidentApplies(inc, mid) {
				activeIncSet[inc.IncidentID] = struct{}{}
				break
			}
		}
	}

	shadowAdj := map[string]int64{}
	for mid, m := range mounts {
		ti, ok := tiers[m.Tier]
		if !ok {
			panic("missing tier " + m.Tier)
		}
		w := ti.ShadowWeight
		inWin := poolDay >= m.ShadowDayLo && poolDay <= m.ShadowDayHi
		var decay float64 = 1
		lag := poolDay - m.LastTouchPoolDay
		if lag > 0 {
			num := float64(pool.ShadowStaleSpanDays - lag)
			if num < 0 {
				num = 0
			}
			if pool.ShadowStaleSpanDays <= 0 {
				decay = 0
			} else {
				decay = num / float64(pool.ShadowStaleSpanDays)
			}
		}
		adj := int64(0)
		if inWin {
			adj = int64(float64(m.ShadowBytes) * w * decay)
		}
		if wn, ok := winning[mid]; ok && wn.freezeMerge {
			adj = 0
		}
		shadowAdj[mid] = adj
	}

	inodeQuota := map[string]int64{}
	type inodeRep struct {
		billing string
		broken  bool
		acct    int64
	}
	inodeRepMap := map[string]inodeRep{}

	rowByID := map[string]inodeRow{}
	for _, r := range inodeRows {
		rowByID[r.InodeID] = r
	}

	for _, r := range inodeRows {
		visited := map[string]struct{}{}
		cur := r.InodeID
		cycle := false
		for {
			if _, ok := visited[cur]; ok {
				cycle = true
				break
			}
			visited[cur] = struct{}{}
			row, ok := rowByID[cur]
			if !ok {
				cycle = true
				break
			}
			if row.BorrowTarget == nil || *row.BorrowTarget == "" {
				break
			}
			cur = *row.BorrowTarget
		}
		var terminal mountFile
		var termID string
		if cycle {
			termID = r.HomeMountID
			terminal = mounts[termID]
			_ = terminal
			acct := r.Bytes * 2
			inodeQuota[r.HomeMountID] += acct
			inodeRepMap[r.InodeID] = inodeRep{billing: r.HomeMountID, broken: true, acct: acct}
			continue
		}
		// walk again to terminal inode id
		cur = r.InodeID
		for {
			row := rowByID[cur]
			if row.BorrowTarget == nil || *row.BorrowTarget == "" {
				termID = row.HomeMountID
				break
			}
			cur = *row.BorrowTarget
		}
		acct := r.Bytes
		inodeQuota[termID] += acct
		inodeRepMap[r.InodeID] = inodeRep{billing: termID, broken: false, acct: acct}
	}

	merged := map[string]int64{}
	rolled := map[string]int64{}

	var postOrder func(string)
	postOrder = func(mid string) {
		for _, c := range children[mid] {
			postOrder(c)
		}
		m := mounts[mid]
		ps := m.BaseBytes + shadowAdj[mid]
		iq := inodeQuota[mid]
		sum := int64(0)
		for _, c := range children[mid] {
			cm := mounts[c]
			cap := cm.ExportCapBytes
			mv := merged[c]
			if mv < cap {
				sum += mv
			} else {
				sum += cap
			}
		}
		rolled[mid] = sum
		merged[mid] = ps + iq + sum
	}

	roots := []string{}
	for mid := range mounts {
		if _, ok := parentOf[mid]; !ok {
			roots = append(roots, mid)
		}
	}
	sort.Strings(roots)
	for _, r := range roots {
		postOrder(r)
	}

	mountIDs := slices.Collect(maps.Keys(mounts))
	sort.Strings(mountIDs)

	maxTot := int64(-1)
	for _, mid := range mountIDs {
		if merged[mid] > maxTot {
			maxTot = merged[mid]
		}
	}

	violations := []map[string]any{}
	for _, mid := range mountIDs {
		m := mounts[mid]
		ti := tiers[m.Tier]
		if merged[mid] > ti.HardCap {
			violations = append(violations, map[string]any{
				"hard_cap":     ti.HardCap,
				"merged_total": merged[mid],
				"mount_id":     mid,
				"tier":         m.Tier,
			})
		}
	}

	freezeCnt := int64(0)
	for _, mid := range mountIDs {
		if wn, ok := winning[mid]; ok && wn.freezeMerge {
			freezeCnt++
		}
	}

	summary := map[string]any{
		"active_incident_count":     len(activeIncSet),
		"cap_violation_count":       len(violations),
		"freeze_merge_mount_count":  freezeCnt,
		"inode_row_count":           len(inodeRows),
		"max_merged_total":          maxTot,
		"mount_count":               len(mounts),
		"pool_day_index":            poolDay,
	}

	nodes := []map[string]any{}
	for _, mid := range mountIDs {
		m := mounts[mid]
		var pm any = nil
		if m.ParentMountID != nil && *m.ParentMountID != "" {
			pm = *m.ParentMountID
		}
		nodes = append(nodes, map[string]any{
			"inode_quota":     inodeQuota[mid],
			"merged_total":    merged[mid],
			"mount_id":        mid,
			"parent_mount_id": pm,
			"post_shadow":     m.BaseBytes + shadowAdj[mid],
			"rolled_children": rolled[mid],
		})
	}

	freezeMounts := []map[string]any{}
	for _, mid := range mountIDs {
		var wid any = nil
		fm := false
		if wn, ok := winning[mid]; ok {
			wid = wn.id
			fm = wn.freezeMerge
		}
		freezeMounts = append(freezeMounts, map[string]any{
			"freeze_merge":         fm,
			"mount_id":             mid,
			"winning_incident_id":  wid,
		})
	}

	inodeRowsOut := []map[string]any{}
	inodeIDs := slices.Clone(inodeRows)
	sort.Slice(inodeIDs, func(i, j int) bool { return inodeIDs[i].InodeID < inodeIDs[j].InodeID })
	for _, r := range inodeIDs {
		rep := inodeRepMap[r.InodeID]
		inodeRowsOut = append(inodeRowsOut, map[string]any{
			"billing_mount_id": rep.billing,
			"broken":           rep.broken,
			"bytes_accounted":  rep.acct,
			"inode_id":         r.InodeID,
		})
	}

	write := func(name string, payload any) {
		b, err := json.Marshal(payload)
		if err != nil {
			panic(err)
		}
		if err := os.WriteFile(filepath.Join(auditDir, name), b, 0o644); err != nil {
			panic(err)
		}
	}

	write("summary.json", summary)
	write("merge_graph.json", map[string]any{"nodes": nodes})
	write("cap_violations.json", map[string]any{"violations": violations})
	write("inode_report.json", map[string]any{"rows": inodeRowsOut})
	write("freeze_state.json", map[string]any{"mounts": freezeMounts})
}
