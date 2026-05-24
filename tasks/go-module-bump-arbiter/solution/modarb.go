package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

// ----------------------------------------------------------------------------
// Input types
// ----------------------------------------------------------------------------

type Workspace struct {
	WorkspaceID                  string   `json:"workspace_id"`
	Modules                      []string `json:"modules"`
	ReplaceDirectiveQuorum       int      `json:"replace_directive_quorum"`
	SeverityBlockThreshold       string   `json:"severity_block_threshold"`
	VulncheckReachabilityRequired bool    `json:"vulncheck_reachability_required"`
}

type Policy struct {
	SeverityRank           map[string]int `json:"severity_rank"`
	SupportedIncidentKinds []string       `json:"supported_incident_kinds"`
	RetractGraceDays       int            `json:"retract_grace_days"`
}

type Require struct {
	DepPath             string   `json:"dep_path"`
	MinVersion          string   `json:"min_version"`
	ReachabilitySymbols []string `json:"reachability_symbols"`
}

type Replace struct {
	FromPath  string `json:"from_path"`
	ToPath    string `json:"to_path"`
	ToVersion string `json:"to_version"`
}

type Exclude struct {
	DepPath string `json:"dep_path"`
	Version string `json:"version"`
}

type Module struct {
	ModulePath    string    `json:"module_path"`
	GoVersionMin  string    `json:"go_version_min"`
	Requires      []Require `json:"requires"`
	Replaces      []Replace `json:"replaces"`
	Excludes      []Exclude `json:"excludes"`
	Tools         []string  `json:"tools"`
}

type RegistryVersion struct {
	Version         string   `json:"version"`
	MinGoVersion    string   `json:"min_go_version"`
	Retracted       bool     `json:"retracted"`
	RetractReason   *string  `json:"retract_reason"`
	AffectedSymbols []string `json:"affected_symbols"`
	Pseudo          bool     `json:"pseudo"`
	VulnAdvisories  []string `json:"vuln_advisories"`
}

type Registry struct {
	DepPath  string            `json:"dep_path"`
	Versions []RegistryVersion `json:"versions"`
}

type Advisory struct {
	AdvisoryID       string   `json:"advisory_id"`
	DepPath          string   `json:"dep_path"`
	Severity         string   `json:"severity"`
	AffectedVersions []string `json:"affected_versions"`
	FixedIn          *string  `json:"fixed_in"`
	AffectedSymbols  []string `json:"affected_symbols"`
}

type rawEvent struct {
	EventID            string   `json:"event_id"`
	Day                int      `json:"day"`
	Kind               string   `json:"kind"`
	Accepted           bool     `json:"accepted"`
	DepPath            string   `json:"dep_path,omitempty"`
	Version            string   `json:"version,omitempty"`
	OverrideAdvisories []string `json:"override_advisories,omitempty"`
	FromPath           string   `json:"from_path,omitempty"`
	ToPath             string   `json:"to_path,omitempty"`
	ToVersion          string   `json:"to_version,omitempty"`
	EffectiveDay       *int     `json:"effective_day,omitempty"`
	CycleModules       []string `json:"cycle_modules,omitempty"`
}

type IncidentLog struct {
	Events []rawEvent `json:"events"`
}

type PoolState struct {
	CurrentDay int `json:"current_day"`
}

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

func die(err error) {
	fmt.Fprintln(os.Stderr, "modarb error:", err)
	os.Exit(1)
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func mustReadJSON(path string, dst any) {
	b, err := os.ReadFile(path)
	if err != nil {
		die(fmt.Errorf("read %s: %w", path, err))
	}
	if err := json.Unmarshal(b, dst); err != nil {
		die(fmt.Errorf("parse %s: %w", path, err))
	}
}

// compareVersion returns -1/0/+1 for the canonical version comparator.
//   vX.Y.Z without pre-release > vX.Y.Z-<pre>
//   (X, Y, Z) integer-compared; ASCII-compared pre-release.
func compareVersion(a, b string) int {
	if a == b {
		return 0
	}
	aMain, aPre := splitPre(a)
	bMain, bPre := splitPre(b)
	for i := 0; i < 3; i++ {
		ai, bi := triple(aMain, i), triple(bMain, i)
		if ai != bi {
			if ai < bi {
				return -1
			}
			return 1
		}
	}
	if aPre == bPre {
		return 0
	}
	if aPre == "" {
		return 1
	}
	if bPre == "" {
		return -1
	}
	if aPre < bPre {
		return -1
	}
	return 1
}

func splitPre(v string) (string, string) {
	v = strings.TrimPrefix(v, "v")
	if i := strings.Index(v, "-"); i >= 0 {
		return v[:i], v[i+1:]
	}
	return v, ""
}

func triple(main string, idx int) int {
	parts := strings.Split(main, ".")
	if idx >= len(parts) {
		return 0
	}
	n, err := strconv.Atoi(parts[idx])
	if err != nil {
		return 0
	}
	return n
}

func sortVersionsAsc(vs []RegistryVersion) []RegistryVersion {
	out := append([]RegistryVersion(nil), vs...)
	sort.Slice(out, func(i, j int) bool {
		return compareVersion(out[i].Version, out[j].Version) < 0
	})
	return out
}

func maxVersion(vs []string) string {
	best := ""
	for _, v := range vs {
		if best == "" || compareVersion(v, best) > 0 {
			best = v
		}
	}
	return best
}

// pathToFileStem converts a dep path like "golang.org/x/net" into the registry
// filename stem "golang.org__x__net".
func pathToFileStem(p string) string {
	return strings.ReplaceAll(p, "/", "__")
}

// ----------------------------------------------------------------------------
// Loaders
// ----------------------------------------------------------------------------

type World struct {
	Workspace  Workspace
	Policy     Policy
	PoolState  PoolState
	Modules    map[string]Module
	Registry   map[string]Registry // dep_path -> Registry
	Advisories map[string]Advisory // advisory_id -> Advisory
	Incidents  IncidentLog
	ModgraphDir string
}

func loadWorld(modgraphDir string) World {
	w := World{
		Modules:     map[string]Module{},
		Registry:    map[string]Registry{},
		Advisories:  map[string]Advisory{},
		ModgraphDir: modgraphDir,
	}
	mustReadJSON(filepath.Join(modgraphDir, "workspace_manifest.json"), &w.Workspace)
	mustReadJSON(filepath.Join(modgraphDir, "governance", "policy.json"), &w.Policy)
	mustReadJSON(filepath.Join(modgraphDir, "pool_state.json"), &w.PoolState)
	mustReadJSON(filepath.Join(modgraphDir, "incident_log.json"), &w.Incidents)

	modDir := filepath.Join(modgraphDir, "modules")
	entries, err := os.ReadDir(modDir)
	if err != nil {
		die(fmt.Errorf("read modules dir: %w", err))
	}
	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		var m Module
		mustReadJSON(filepath.Join(modDir, e.Name()), &m)
		w.Modules[m.ModulePath] = m
	}

	regDir := filepath.Join(modgraphDir, "registry")
	regEntries, err := os.ReadDir(regDir)
	if err != nil {
		die(fmt.Errorf("read registry dir: %w", err))
	}
	for _, e := range regEntries {
		if !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		var r Registry
		mustReadJSON(filepath.Join(regDir, e.Name()), &r)
		w.Registry[r.DepPath] = r
	}

	advDir := filepath.Join(modgraphDir, "advisories")
	advEntries, err := os.ReadDir(advDir)
	if err != nil {
		die(fmt.Errorf("read advisories dir: %w", err))
	}
	for _, e := range advEntries {
		if !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		var a Advisory
		mustReadJSON(filepath.Join(advDir, e.Name()), &a)
		w.Advisories[a.AdvisoryID] = a
	}

	return w
}

// ----------------------------------------------------------------------------
// Incident filtering
// ----------------------------------------------------------------------------

type Incidents struct {
	ForcePin            map[string]rawEvent
	ReplaceWorkspace    map[string]rawEvent
	RetractEmergency    map[string]map[string]rawEvent // dep_path -> version -> event
	CycleEvents         []rawEvent
	CycleModulesSet     map[string]bool
	AcceptedCount       int
	IgnoredCount        int
}

func filterIncidents(w World) Incidents {
	out := Incidents{
		ForcePin:         map[string]rawEvent{},
		ReplaceWorkspace: map[string]rawEvent{},
		RetractEmergency: map[string]map[string]rawEvent{},
		CycleModulesSet:  map[string]bool{},
	}

	moduleSet := map[string]bool{}
	for _, m := range w.Workspace.Modules {
		moduleSet[m] = true
	}
	supportedKinds := map[string]bool{}
	for _, k := range w.Policy.SupportedIncidentKinds {
		supportedKinds[k] = true
	}

	events := append([]rawEvent(nil), w.Incidents.Events...)
	sort.SliceStable(events, func(i, j int) bool {
		if events[i].Day != events[j].Day {
			return events[i].Day < events[j].Day
		}
		return events[i].EventID < events[j].EventID
	})

	for _, ev := range events {
		if !ev.Accepted || ev.Day > w.PoolState.CurrentDay || !supportedKinds[ev.Kind] {
			out.IgnoredCount++
			continue
		}
		switch ev.Kind {
		case "force_pin":
			reg, ok := w.Registry[ev.DepPath]
			if !ok {
				out.IgnoredCount++
				continue
			}
			found := false
			for _, v := range reg.Versions {
				if v.Version == ev.Version {
					found = true
					break
				}
			}
			if !found {
				out.IgnoredCount++
				continue
			}
			out.ForcePin[ev.DepPath] = ev
			out.AcceptedCount++

		case "replace_workspace_wide":
			reg, ok := w.Registry[ev.ToPath]
			if !ok {
				out.IgnoredCount++
				continue
			}
			found := false
			for _, v := range reg.Versions {
				if v.Version == ev.ToVersion {
					found = true
					break
				}
			}
			if !found {
				out.IgnoredCount++
				continue
			}
			out.ReplaceWorkspace[ev.FromPath] = ev
			out.AcceptedCount++

		case "retract_emergency":
			if ev.EffectiveDay == nil {
				out.IgnoredCount++
				continue
			}
			if *ev.EffectiveDay > w.PoolState.CurrentDay {
				out.IgnoredCount++
				continue
			}
			reg, ok := w.Registry[ev.DepPath]
			if !ok {
				out.IgnoredCount++
				continue
			}
			found := false
			for _, v := range reg.Versions {
				if v.Version == ev.Version {
					found = true
					break
				}
			}
			if !found {
				out.IgnoredCount++
				continue
			}
			if out.RetractEmergency[ev.DepPath] == nil {
				out.RetractEmergency[ev.DepPath] = map[string]rawEvent{}
			}
			out.RetractEmergency[ev.DepPath][ev.Version] = ev
			out.AcceptedCount++

		case "module_graph_cycle":
			if len(ev.CycleModules) < 2 {
				out.IgnoredCount++
				continue
			}
			allKnown := true
			for _, name := range ev.CycleModules {
				if !moduleSet[name] {
					allKnown = false
					break
				}
			}
			if !allKnown {
				out.IgnoredCount++
				continue
			}
			out.CycleEvents = append(out.CycleEvents, ev)
			for _, name := range ev.CycleModules {
				out.CycleModulesSet[name] = true
			}
			out.AcceptedCount++

		default:
			out.IgnoredCount++
		}
	}

	return out
}

// ----------------------------------------------------------------------------
// Phase A: replace-directive audit
// ----------------------------------------------------------------------------

type ReplaceRow struct {
	FromPath        string
	ModuleName      string
	Status          string
	EffectiveTarget *Replace
	SourceEventID   string
}

type WorkspaceTarget struct {
	ToPath        string
	ToVersion     string
	SourceEventID string
}

type PhaseAResult struct {
	Rows      []ReplaceRow
	Workspace map[string]WorkspaceTarget // from_path -> active workspace target
}

type rawReplaceEntry struct {
	ModuleName string
	Replace    Replace
}

func phaseA(w World, inc Incidents) PhaseAResult {
	groups := map[string][]rawReplaceEntry{}
	for _, modName := range w.Workspace.Modules {
		m, ok := w.Modules[modName]
		if !ok {
			continue
		}
		for _, r := range m.Replaces {
			groups[r.FromPath] = append(groups[r.FromPath], rawReplaceEntry{
				ModuleName: modName,
				Replace:    r,
			})
		}
	}

	result := PhaseAResult{
		Workspace: map[string]WorkspaceTarget{},
	}

	for fromPath, entries := range groups {
		if ev, hasIncident := inc.ReplaceWorkspace[fromPath]; hasIncident {
			target := &Replace{
				FromPath:  fromPath,
				ToPath:    ev.ToPath,
				ToVersion: ev.ToVersion,
			}
			for _, e := range entries {
				result.Rows = append(result.Rows, ReplaceRow{
					FromPath:        fromPath,
					ModuleName:      e.ModuleName,
					Status:          "overridden_incident",
					EffectiveTarget: target,
					SourceEventID:   ev.EventID,
				})
			}
			result.Workspace[fromPath] = WorkspaceTarget{
				ToPath:        ev.ToPath,
				ToVersion:     ev.ToVersion,
				SourceEventID: ev.EventID,
			}
			continue
		}

		var validEntries []rawReplaceEntry
		var missingRows []ReplaceRow
		for _, e := range entries {
			if _, ok := w.Registry[e.Replace.ToPath]; !ok {
				missingRows = append(missingRows, ReplaceRow{
					FromPath:        fromPath,
					ModuleName:      e.ModuleName,
					Status:          "block_target_missing",
					EffectiveTarget: nil,
					SourceEventID:   "",
				})
				continue
			}
			validEntries = append(validEntries, e)
		}
		result.Rows = append(result.Rows, missingRows...)

		if len(validEntries) == 0 {
			continue
		}

		tupleKey := func(r Replace) string {
			return r.ToPath + " " + r.ToVersion
		}
		distinct := map[string]rawReplaceEntry{}
		for _, e := range validEntries {
			distinct[tupleKey(e.Replace)] = e
		}

		if len(distinct) == 1 {
			only := validEntries[0].Replace
			target := &Replace{FromPath: fromPath, ToPath: only.ToPath, ToVersion: only.ToVersion}
			if len(validEntries) >= w.Workspace.ReplaceDirectiveQuorum {
				for _, e := range validEntries {
					result.Rows = append(result.Rows, ReplaceRow{
						FromPath:        fromPath,
						ModuleName:      e.ModuleName,
						Status:          "applied_workspace",
						EffectiveTarget: target,
					})
				}
				result.Workspace[fromPath] = WorkspaceTarget{
					ToPath:    only.ToPath,
					ToVersion: only.ToVersion,
				}
			} else {
				for _, e := range validEntries {
					result.Rows = append(result.Rows, ReplaceRow{
						FromPath:        fromPath,
						ModuleName:      e.ModuleName,
						Status:          "quorum_failed",
						EffectiveTarget: nil,
					})
				}
			}
			continue
		}

		var winner Replace
		first := true
		for _, e := range validEntries {
			cand := e.Replace
			if first {
				winner = cand
				first = false
				continue
			}
			cmp := compareVersion(cand.ToVersion, winner.ToVersion)
			if cmp > 0 {
				winner = cand
			} else if cmp == 0 && cand.ToPath < winner.ToPath {
				winner = cand
			}
		}
		winTarget := &Replace{FromPath: fromPath, ToPath: winner.ToPath, ToVersion: winner.ToVersion}
		for _, e := range validEntries {
			if e.Replace.ToPath == winner.ToPath && e.Replace.ToVersion == winner.ToVersion {
				result.Rows = append(result.Rows, ReplaceRow{
					FromPath:        fromPath,
					ModuleName:      e.ModuleName,
					Status:          "applied_workspace",
					EffectiveTarget: winTarget,
				})
			} else {
				result.Rows = append(result.Rows, ReplaceRow{
					FromPath:        fromPath,
					ModuleName:      e.ModuleName,
					Status:          "conflict_divergent_targets",
					EffectiveTarget: nil,
				})
			}
		}
		result.Workspace[fromPath] = WorkspaceTarget{
			ToPath:    winner.ToPath,
			ToVersion: winner.ToVersion,
		}
	}

	sort.SliceStable(result.Rows, func(i, j int) bool {
		if result.Rows[i].FromPath != result.Rows[j].FromPath {
			return result.Rows[i].FromPath < result.Rows[j].FromPath
		}
		return result.Rows[i].ModuleName < result.Rows[j].ModuleName
	})
	return result
}

// ----------------------------------------------------------------------------
// Phase B: MVS with exclusion / retract / cycle gates
// ----------------------------------------------------------------------------

type ResolutionRow struct {
	DepPath         string
	ResolvedPath    string
	ResolvedVersion *string
	Action          string
	SourceEventID   *string
}

func phaseB(w World, inc Incidents, phaseAOut PhaseAResult) []ResolutionRow {
	depRequirers := map[string]map[string]Require{}
	for _, modName := range w.Workspace.Modules {
		m, ok := w.Modules[modName]
		if !ok {
			continue
		}
		for _, r := range m.Requires {
			if depRequirers[r.DepPath] == nil {
				depRequirers[r.DepPath] = map[string]Require{}
			}
			depRequirers[r.DepPath][modName] = r
		}
	}

	var firstCycle string
	if len(inc.CycleEvents) > 0 {
		firstCycle = inc.CycleEvents[0].EventID
	}

	depPaths := make([]string, 0, len(depRequirers))
	for d := range depRequirers {
		depPaths = append(depPaths, d)
	}
	sort.Strings(depPaths)

	var rows []ResolutionRow

	for _, dep := range depPaths {
		requirers := depRequirers[dep]
		effective := map[string]Require{}
		for modName, req := range requirers {
			if !inc.CycleModulesSet[modName] {
				effective[modName] = req
			}
		}

		if len(effective) == 0 {
			ev := firstCycle
			rows = append(rows, ResolutionRow{
				DepPath:       dep,
				ResolvedPath:  dep,
				Action:        "block_cycle",
				SourceEventID: &ev,
			})
			continue
		}

		if fp, ok := inc.ForcePin[dep]; ok {
			ver := fp.Version
			eid := fp.EventID
			rows = append(rows, ResolutionRow{
				DepPath:         dep,
				ResolvedPath:    dep,
				ResolvedVersion: &ver,
				Action:          "forced_pin",
				SourceEventID:   &eid,
			})
			continue
		}

		if target, ok := phaseAOut.Workspace[dep]; ok {
			ver := target.ToVersion
			var sourceID *string
			if target.SourceEventID != "" {
				eid := target.SourceEventID
				sourceID = &eid
			}
			rows = append(rows, ResolutionRow{
				DepPath:         dep,
				ResolvedPath:    target.ToPath,
				ResolvedVersion: &ver,
				Action:          "workspace_replace",
				SourceEventID:   sourceID,
			})
			continue
		}

		var candidates []string
		for _, req := range effective {
			candidates = append(candidates, req.MinVersion)
		}
		candidate := maxVersion(candidates)

		reg, ok := w.Registry[dep]
		if !ok {
			rows = append(rows, ResolutionRow{
				DepPath:      dep,
				ResolvedPath: dep,
				Action:       "block_no_version",
			})
			continue
		}
		sorted := sortVersionsAsc(reg.Versions)

		excludedSet := map[string]bool{}
		for modName := range effective {
			m := w.Modules[modName]
			for _, ex := range m.Excludes {
				if ex.DepPath == dep {
					excludedSet[ex.Version] = true
				}
			}
		}
		emergencyRetracted := map[string]rawEvent{}
		if er, ok := inc.RetractEmergency[dep]; ok {
			for v, ev := range er {
				emergencyRetracted[v] = ev
			}
		}

		walkedOverExclude := false
		walkedOverRetract := false
		var chosen *RegistryVersion
		var emergencyEvent *rawEvent

		for i := range sorted {
			v := sorted[i]
			if compareVersion(v.Version, candidate) < 0 {
				continue
			}
			if excludedSet[v.Version] {
				walkedOverExclude = true
				continue
			}
			if v.Retracted {
				walkedOverRetract = true
				continue
			}
			if ev, has := emergencyRetracted[v.Version]; has {
				walkedOverRetract = true
				ev := ev
				emergencyEvent = &ev
				continue
			}
			chosen = &v
			break
		}

		if chosen == nil {
			rows = append(rows, ResolutionRow{
				DepPath:      dep,
				ResolvedPath: dep,
				Action:       "block_no_version",
			})
			continue
		}

		ver := chosen.Version
		var action string
		var sourceID *string
		switch {
		case walkedOverExclude:
			action = "mvs_walk_excluded"
		case walkedOverRetract:
			action = "mvs_walk_retracted"
			if emergencyEvent != nil {
				eid := emergencyEvent.EventID
				sourceID = &eid
			}
		default:
			action = "mvs_select"
		}

		rows = append(rows, ResolutionRow{
			DepPath:         dep,
			ResolvedPath:    dep,
			ResolvedVersion: &ver,
			Action:          action,
			SourceEventID:   sourceID,
		})
	}

	return rows
}

// ----------------------------------------------------------------------------
// Phase C: vulnerability triage
// ----------------------------------------------------------------------------

type AdvisoryRow struct {
	AdvisoryID            string
	CoveredPostResolution bool
	DepPath               string
	PostResolutionVersion *string
	Severity              string
	Status                string
}

func phaseC(w World, inc Incidents, resolutions []ResolutionRow) []AdvisoryRow {
	byDep := map[string]ResolutionRow{}
	for _, r := range resolutions {
		byDep[r.DepPath] = r
	}

	severityBlocks := func(sev string) bool {
		return w.Policy.SeverityRank[sev] >= w.Policy.SeverityRank[w.Workspace.SeverityBlockThreshold]
	}

	requirerReach := map[string]map[string]bool{}
	for _, modName := range w.Workspace.Modules {
		m, ok := w.Modules[modName]
		if !ok {
			continue
		}
		for _, r := range m.Requires {
			if requirerReach[r.DepPath] == nil {
				requirerReach[r.DepPath] = map[string]bool{}
			}
			for _, s := range r.ReachabilitySymbols {
				requirerReach[r.DepPath][s] = true
			}
		}
	}

	var rows []AdvisoryRow
	for _, adv := range w.Advisories {
		row := AdvisoryRow{
			AdvisoryID: adv.AdvisoryID,
			DepPath:    adv.DepPath,
			Severity:   adv.Severity,
		}
		res, depResolved := byDep[adv.DepPath]
		if !depResolved {
			row.Status = "mitigated_bumped"
			row.CoveredPostResolution = false
			row.PostResolutionVersion = nil
			rows = append(rows, row)
			continue
		}

		row.PostResolutionVersion = res.ResolvedVersion

		covered := false
		if res.ResolvedPath == adv.DepPath && res.ResolvedVersion != nil {
			for _, v := range adv.AffectedVersions {
				if v == *res.ResolvedVersion {
					covered = true
					break
				}
			}
		}
		row.CoveredPostResolution = covered

		if fp, ok := inc.ForcePin[adv.DepPath]; ok {
			for _, oid := range fp.OverrideAdvisories {
				if oid == adv.AdvisoryID {
					row.Status = "overridden"
					rows = append(rows, row)
					goto next
				}
			}
		}

		if res.ResolvedPath != adv.DepPath && !covered {
			row.Status = "mitigated_by_replace"
			rows = append(rows, row)
			continue
		}

		if !covered {
			row.Status = "mitigated_bumped"
			rows = append(rows, row)
			continue
		}

		if res.Action == "forced_pin" {
			row.Status = "unmitigated_pinned"
			rows = append(rows, row)
			continue
		}

		if w.Workspace.VulncheckReachabilityRequired && !severityBlocks(adv.Severity) {
			symbols := requirerReach[adv.DepPath]
			intersect := false
			for _, s := range adv.AffectedSymbols {
				if symbols[s] {
					intersect = true
					break
				}
			}
			if !intersect {
				row.Status = "unreachable"
				rows = append(rows, row)
				continue
			}
		}

		row.Status = "still_open_frozen"
		rows = append(rows, row)
	next:
	}

	sort.SliceStable(rows, func(i, j int) bool {
		return rows[i].AdvisoryID < rows[j].AdvisoryID
	})
	return rows
}

// ----------------------------------------------------------------------------
// Phase D: cycle and retract report
// ----------------------------------------------------------------------------

type BlockedVersion struct {
	DepPath string
	Reason  string
	Version string
}

type ModuleView struct {
	ModuleName      string
	InCycle         bool
	BlockedVersions []BlockedVersion
}

type ToolImpactRow struct {
	DepPath    string
	ModuleName string
	ToolStatus string
}

type CycleRow struct {
	CycleModules []string
	EventID      string
}

type PhaseDResult struct {
	Cycles      []CycleRow
	ModuleView  []ModuleView
	ToolImpacts []ToolImpactRow
}

func phaseD(w World, inc Incidents) PhaseDResult {
	out := PhaseDResult{}

	for _, ev := range inc.CycleEvents {
		members := append([]string(nil), ev.CycleModules...)
		sort.Strings(members)
		out.Cycles = append(out.Cycles, CycleRow{
			CycleModules: members,
			EventID:      ev.EventID,
		})
	}
	sort.SliceStable(out.Cycles, func(i, j int) bool {
		return out.Cycles[i].EventID < out.Cycles[j].EventID
	})

	for _, modName := range w.Workspace.Modules {
		view := ModuleView{
			ModuleName: modName,
			InCycle:    inc.CycleModulesSet[modName],
		}
		m, ok := w.Modules[modName]
		if !ok {
			out.ModuleView = append(out.ModuleView, view)
			continue
		}
		for _, ex := range m.Excludes {
			view.BlockedVersions = append(view.BlockedVersions, BlockedVersion{
				DepPath: ex.DepPath,
				Reason:  "exclude_directive",
				Version: ex.Version,
			})
		}
		reqDeps := map[string]bool{}
		for _, r := range m.Requires {
			reqDeps[r.DepPath] = true
		}
		for dep := range reqDeps {
			reg, ok := w.Registry[dep]
			if !ok {
				continue
			}
			for _, v := range reg.Versions {
				if v.Retracted {
					view.BlockedVersions = append(view.BlockedVersions, BlockedVersion{
						DepPath: dep,
						Reason:  "retracted_intrinsic",
						Version: v.Version,
					})
				}
			}
			if er, ok := inc.RetractEmergency[dep]; ok {
				for ver := range er {
					view.BlockedVersions = append(view.BlockedVersions, BlockedVersion{
						DepPath: dep,
						Reason:  "retracted_emergency",
						Version: ver,
					})
				}
			}
		}
		sort.SliceStable(view.BlockedVersions, func(i, j int) bool {
			a, b := view.BlockedVersions[i], view.BlockedVersions[j]
			if a.DepPath != b.DepPath {
				return a.DepPath < b.DepPath
			}
			if a.Version != b.Version {
				return a.Version < b.Version
			}
			return a.Reason < b.Reason
		})
		out.ModuleView = append(out.ModuleView, view)
	}
	sort.SliceStable(out.ModuleView, func(i, j int) bool {
		return out.ModuleView[i].ModuleName < out.ModuleView[j].ModuleName
	})

	for _, modName := range w.Workspace.Modules {
		m, ok := w.Modules[modName]
		if !ok {
			continue
		}
		reqDeps := map[string]bool{}
		for _, r := range m.Requires {
			reqDeps[r.DepPath] = true
		}
		for _, tool := range m.Tools {
			status := "tool_only"
			if reqDeps[tool] {
				status = "shared_with_requires"
			}
			out.ToolImpacts = append(out.ToolImpacts, ToolImpactRow{
				DepPath:    tool,
				ModuleName: modName,
				ToolStatus: status,
			})
		}
	}
	sort.SliceStable(out.ToolImpacts, func(i, j int) bool {
		if out.ToolImpacts[i].ModuleName != out.ToolImpacts[j].ModuleName {
			return out.ToolImpacts[i].ModuleName < out.ToolImpacts[j].ModuleName
		}
		return out.ToolImpacts[i].DepPath < out.ToolImpacts[j].DepPath
	})

	return out
}

// ----------------------------------------------------------------------------
// Phase E: summary
// ----------------------------------------------------------------------------

func phaseE(w World, inc Incidents, phaseAOut PhaseAResult, resolutions []ResolutionRow, advisories []AdvisoryRow, phaseDOut PhaseDResult) map[string]int {
	summary := map[string]int{
		"accepted_incident_events":         inc.AcceptedCount,
		"advisories_total":                 len(advisories),
		"advisories_unmitigated_pinned":    0,
		"advisories_unreachable":           0,
		"cycle_modules_total":              len(inc.CycleModulesSet),
		"deps_blocked_no_version":          0,
		"deps_forced_pin":                  0,
		"deps_total":                       len(resolutions),
		"deps_workspace_replaced":          0,
		"ignored_incident_events":          inc.IgnoredCount,
		"modules_total":                    len(w.Workspace.Modules),
		"replace_rows_applied_workspace":   0,
		"replace_rows_overridden_incident": 0,
		"tool_only_rows":                   0,
	}
	for _, r := range resolutions {
		switch r.Action {
		case "block_no_version":
			summary["deps_blocked_no_version"]++
		case "forced_pin":
			summary["deps_forced_pin"]++
		case "workspace_replace":
			summary["deps_workspace_replaced"]++
		}
	}
	for _, a := range advisories {
		switch a.Status {
		case "unmitigated_pinned":
			summary["advisories_unmitigated_pinned"]++
		case "unreachable":
			summary["advisories_unreachable"]++
		}
	}
	for _, r := range phaseAOut.Rows {
		switch r.Status {
		case "applied_workspace":
			summary["replace_rows_applied_workspace"]++
		case "overridden_incident":
			summary["replace_rows_overridden_incident"]++
		}
	}
	for _, t := range phaseDOut.ToolImpacts {
		if t.ToolStatus == "tool_only" {
			summary["tool_only_rows"]++
		}
	}
	return summary
}

// ----------------------------------------------------------------------------
// JSON emission (canonical: 2-space indent, sorted keys, no HTML escaping)
// ----------------------------------------------------------------------------

func writeJSON(path string, v any) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		die(fmt.Errorf("encode %s: %w", path, err))
	}
	if err := os.WriteFile(path, buf.Bytes(), 0o644); err != nil {
		die(fmt.Errorf("write %s: %w", path, err))
	}
}

func resolutionToJSON(rows []ResolutionRow) any {
	deps := make([]map[string]any, 0, len(rows))
	for _, r := range rows {
		entry := map[string]any{
			"action":           r.Action,
			"dep_path":         r.DepPath,
			"resolved_path":    r.ResolvedPath,
			"resolved_version": maybeString(r.ResolvedVersion),
			"source_event_id":  maybeString(r.SourceEventID),
		}
		deps = append(deps, entry)
	}
	return map[string]any{"deps": deps}
}

func replaceAuditToJSON(rows []ReplaceRow) any {
	out := make([]map[string]any, 0, len(rows))
	for _, r := range rows {
		var target any
		if r.EffectiveTarget != nil {
			target = map[string]any{
				"to_path":    r.EffectiveTarget.ToPath,
				"to_version": r.EffectiveTarget.ToVersion,
			}
		} else {
			target = nil
		}
		var src any
		if r.SourceEventID != "" {
			src = r.SourceEventID
		} else {
			src = nil
		}
		out = append(out, map[string]any{
			"effective_target": target,
			"from_path":        r.FromPath,
			"module_name":      r.ModuleName,
			"source_event_id":  src,
			"status":           r.Status,
		})
	}
	return map[string]any{"rows": out}
}

func advisoriesToJSON(rows []AdvisoryRow) any {
	out := make([]map[string]any, 0, len(rows))
	for _, r := range rows {
		entry := map[string]any{
			"advisory_id":             r.AdvisoryID,
			"covered_post_resolution": r.CoveredPostResolution,
			"dep_path":                r.DepPath,
			"post_resolution_version": maybeString(r.PostResolutionVersion),
			"severity":                r.Severity,
			"status":                  r.Status,
		}
		out = append(out, entry)
	}
	return map[string]any{"advisories": out}
}

func phaseDToJSON(p PhaseDResult) any {
	cycles := make([]map[string]any, 0, len(p.Cycles))
	for _, c := range p.Cycles {
		cycles = append(cycles, map[string]any{
			"cycle_modules": c.CycleModules,
			"event_id":      c.EventID,
		})
	}
	mv := make([]map[string]any, 0, len(p.ModuleView))
	for _, m := range p.ModuleView {
		bv := make([]map[string]any, 0, len(m.BlockedVersions))
		for _, b := range m.BlockedVersions {
			bv = append(bv, map[string]any{
				"dep_path": b.DepPath,
				"reason":   b.Reason,
				"version":  b.Version,
			})
		}
		mv = append(mv, map[string]any{
			"blocked_versions": bv,
			"in_cycle":         m.InCycle,
			"module_name":      m.ModuleName,
		})
	}
	ti := make([]map[string]any, 0, len(p.ToolImpacts))
	for _, t := range p.ToolImpacts {
		ti = append(ti, map[string]any{
			"dep_path":    t.DepPath,
			"module_name": t.ModuleName,
			"tool_status": t.ToolStatus,
		})
	}
	return map[string]any{
		"cycles":       cycles,
		"module_view":  mv,
		"tool_impacts": ti,
	}
}

func maybeString(s *string) any {
	if s == nil {
		return nil
	}
	return *s
}

// ----------------------------------------------------------------------------
// Main
// ----------------------------------------------------------------------------

func main() {
	modgraphDir := getenv("GMBA_MODGRAPH_DIR", "/app/modgraph")
	decisionsDir := getenv("GMBA_DECISIONS_DIR", "/app/decisions")

	if err := os.MkdirAll(decisionsDir, 0o755); err != nil {
		die(fmt.Errorf("create decisions dir: %w", err))
	}

	w := loadWorld(modgraphDir)
	inc := filterIncidents(w)
	phaseAOut := phaseA(w, inc)
	resolutions := phaseB(w, inc, phaseAOut)
	advisories := phaseC(w, inc, resolutions)
	phaseDOut := phaseD(w, inc)
	summary := phaseE(w, inc, phaseAOut, resolutions, advisories, phaseDOut)

	writeJSON(filepath.Join(decisionsDir, "version_resolution.json"), resolutionToJSON(resolutions))
	writeJSON(filepath.Join(decisionsDir, "replace_directive_audit.json"), replaceAuditToJSON(phaseAOut.Rows))
	writeJSON(filepath.Join(decisionsDir, "vulnerability_exposure.json"), advisoriesToJSON(advisories))
	writeJSON(filepath.Join(decisionsDir, "cycle_and_retract_report.json"), phaseDToJSON(phaseDOut))
	writeJSON(filepath.Join(decisionsDir, "summary.json"), summary)
}
