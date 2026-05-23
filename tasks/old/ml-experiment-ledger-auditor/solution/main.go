package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

type pyFloat float64

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func die(err error) {
	fmt.Fprintln(os.Stderr, "ml-ledger-auditor:", err)
	os.Exit(1)
}

func mustReadJSON(path string) map[string]interface{} {
	b, err := os.ReadFile(path)
	if err != nil {
		die(err)
	}
	var m map[string]interface{}
	if err := json.Unmarshal(b, &m); err != nil {
		die(fmt.Errorf("parse %s: %w", path, err))
	}
	return m
}

func loadDir(dataDir, sub string) map[string]map[string]interface{} {
	out := make(map[string]map[string]interface{})
	p := filepath.Join(dataDir, sub)
	ents, err := os.ReadDir(p)
	if err != nil {
		return out
	}
	names := make([]string, 0, len(ents))
	for _, e := range ents {
		if !e.IsDir() && strings.HasSuffix(strings.ToLower(e.Name()), ".json") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		m := mustReadJSON(filepath.Join(p, name))
		id, _ := m["id"].(string)
		if id != "" {
			out[id] = m
		}
	}
	return out
}

func isNonemptyString(x interface{}) bool {
	s, ok := x.(string)
	return ok && s != ""
}

func isIntGE(x interface{}, lo int) bool {
	f, ok := toFloat(x)
	if !ok {
		return false
	}
	if f != math.Trunc(f) {
		return false
	}
	iv := int(f)
	return iv >= lo
}

func toFloat(x interface{}) (float64, bool) {
	switch v := x.(type) {
	case float64:
		return v, true
	case int:
		return float64(v), true
	case int64:
		return float64(v), true
	case json.Number:
		f, err := v.Float64()
		return f, err == nil
	default:
		return 0, false
	}
}

func isNumberIn(x interface{}, lo, hi float64) bool {
	f, ok := toFloat(x)
	if !ok {
		return false
	}
	return f >= lo && f <= hi
}

func formatJSONFloat(x float64) string {
	x = math.Round(x*1e4) / 1e4
	if x == 0 && !math.Signbit(x) {
		return "0.0"
	}
	s := fmt.Sprintf("%.4f", x)
	s = strings.TrimRight(s, "0")
	s = strings.TrimSuffix(s, ".")
	if !strings.Contains(s, ".") {
		return s + ".0"
	}
	return s
}

func quoteString(s string) string {
	b, err := json.Marshal(s)
	if err != nil {
		die(err)
	}
	return string(b)
}

func encodeSorted(w *strings.Builder, v interface{}, pad, indent string) {
	switch t := v.(type) {
	case nil:
		w.WriteString("null")
	case bool:
		if t {
			w.WriteString("true")
		} else {
			w.WriteString("false")
		}
	case string:
		w.WriteString(quoteString(t))
	case int:
		w.WriteString(strconv.Itoa(t))
	case int64:
		w.WriteString(strconv.FormatInt(t, 10))
	case float64:
		w.WriteString(formatJSONFloat(t))
	case pyFloat:
		w.WriteString(formatJSONFloat(float64(t)))
	case []interface{}:
		if len(t) == 0 {
			w.WriteString("[]")
			break
		}
		w.WriteString("[\n")
		for i, el := range t {
			w.WriteString(pad)
			w.WriteString(indent)
			encodeSorted(w, el, pad+indent, indent)
			if i < len(t)-1 {
				w.WriteString(",\n")
			} else {
				w.WriteByte('\n')
			}
		}
		w.WriteString(pad)
		w.WriteByte(']')
	case map[string]interface{}:
		keys := make([]string, 0, len(t))
		for k := range t {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		if len(keys) == 0 {
			w.WriteString("{}")
			break
		}
		w.WriteString("{\n")
		for i, k := range keys {
			w.WriteString(pad)
			w.WriteString(indent)
			w.WriteString(quoteString(k))
			w.WriteString(": ")
			encodeSorted(w, t[k], pad+indent, indent)
			if i < len(keys)-1 {
				w.WriteString(",\n")
			} else {
				w.WriteByte('\n')
			}
		}
		w.WriteString(pad)
		w.WriteByte('}')
	default:
		die(fmt.Errorf("encodeSorted unsupported %T", v))
	}
}

func writeJSON(path string, root map[string]interface{}) error {
	var b strings.Builder
	encodeSorted(&b, root, "", "  ")
	b.WriteByte('\n')
	return os.WriteFile(path, []byte(b.String()), 0o644)
}

var hex64 = regexp.MustCompile(`^[0-9a-f]{64}$`)
var hexPrefix = regexp.MustCompile(`^[0-9a-f]{1,64}$`)

func main() {
	dataDir := getenv("MEL_DATA_DIR", "/app/ledger")
	auditDir := getenv("MEL_AUDIT_DIR", "/app/audit")
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		die(err)
	}

	pool := mustReadJSON(filepath.Join(dataDir, "pool_state.json"))
	gov := mustReadJSON(filepath.Join(dataDir, "governance_config.json"))
	incident := mustReadJSON(filepath.Join(dataDir, "incident_log.json"))

	currentDay := int(toFloatMust(pool["current_day"]))
	ledgerVersion, _ := pool["ledger_version"].(string)
	checkpointScoreFloor := toFloatMust(gov["checkpoint_score_floor"])
	tierRules, _ := gov["tiers"].(map[string]interface{})

	rawDatasets := loadDir(dataDir, "datasets")
	rawRuns := loadDir(dataDir, "runs")
	rawCheckpoints := loadDir(dataDir, "checkpoints")
	rawRegistry := loadDir(dataDir, "registry")

	validDatasets := map[string]map[string]interface{}{}
	for id, d := range rawDatasets {
		if validateDataset(d) {
			validDatasets[id] = d
		}
	}
	invalidDatasetsDropped := len(rawDatasets) - len(validDatasets)

	for _, d := range validDatasets {
		parents, _ := d["lineage_parents"].([]interface{})
		fp := make([]interface{}, 0)
		for _, p := range parents {
			ps, _ := p.(string)
			if _, ok := validDatasets[ps]; ok {
				fp = append(fp, ps)
			}
		}
		d["_filtered_parents"] = fp
	}

	cyclic := map[string]bool{}
	for id := range validDatasets {
		if inTransitiveAncestors(validDatasets, id, id) {
			cyclic[id] = true
		}
	}

	depthCache := map[string]int{}
	var lineageDepth func(string, map[string]bool) int
	lineageDepth = func(did string, computing map[string]bool) int {
		if cyclic[did] {
			return -1
		}
		if v, ok := depthCache[did]; ok {
			return v
		}
		if computing[did] {
			return -1
		}
		computing[did] = true
		defer delete(computing, did)
		d := validDatasets[did]
		parents := filteredParents(d)
		if len(parents) == 0 {
			depthCache[did] = 0
			return 0
		}
		mx := 0
		for _, p := range parents {
			v := lineageDepth(p, computing)
			if v > mx {
				mx = v
			}
		}
		depthCache[did] = 1 + mx
		return depthCache[did]
	}
	for id := range validDatasets {
		lineageDepth(id, map[string]bool{})
	}

	rawComp := map[string][]map[string]interface{}{}
	rawLifts := map[string][]map[string]interface{}{}
	rawRetracts := map[string][]map[string]interface{}{}
	for id := range validDatasets {
		rawComp[id] = nil
		rawLifts[id] = nil
		rawRetracts[id] = nil
	}
	ignored := 0
	var acceptedRevocs []map[string]interface{}
	var pendingReplays []map[string]interface{}

	events, _ := incident["events"].([]interface{})
	for _, evi := range events {
		ev, ok := evi.(map[string]interface{})
		if !ok {
			ignored++
			continue
		}
		kind, _ := ev["kind"].(string)
		dayF, dok := toFloat(ev["day"])
		day := int(dayF)
		if !dok || dayF != float64(day) || day < 0 || day > currentDay {
			ignored++
			continue
		}
		switch kind {
		case "dataset_compromise":
			did, _ := ev["dataset_id"].(string)
			reason, _ := ev["reason"].(string)
			if !isNonemptyString(did) || validDatasets[did] == nil || !isNonemptyString(reason) {
				ignored++
				continue
			}
			rawComp[did] = append(rawComp[did], ev)
		case "compromise_lift":
			did, _ := ev["dataset_id"].(string)
			reason, _ := ev["reason"].(string)
			if !isNonemptyString(did) || validDatasets[did] == nil || !isNonemptyString(reason) {
				ignored++
				continue
			}
			rawLifts[did] = append(rawLifts[did], ev)
		case "compromise_retract":
			did, _ := ev["dataset_id"].(string)
			reason, _ := ev["reason"].(string)
			if !isNonemptyString(did) || validDatasets[did] == nil || !isNonemptyString(reason) {
				ignored++
				continue
			}
			rawRetracts[did] = append(rawRetracts[did], ev)
		case "key_revocation":
			prefix, _ := ev["signature_prefix"].(string)
			effF, eok := toFloat(ev["effective_day"])
			eff := int(effF)
			reason, _ := ev["reason"].(string)
			if !isNonemptyString(prefix) || !hexPrefix.MatchString(prefix) || !eok || effF != float64(eff) || eff < 0 || eff > currentDay || !isNonemptyString(reason) {
				ignored++
				continue
			}
			acceptedRevocs = append(acceptedRevocs, ev)
		case "eval_replay":
			pendingReplays = append(pendingReplays, ev)
		default:
			ignored++
		}
	}

	ownComp := map[string][]map[string]interface{}{}
	for did := range validDatasets {
		comps := rawComp[did]
		lifts := rawLifts[did]
		retracts := rawRetracts[did]
		survivingLifts := make([]map[string]interface{}, 0)
		for _, lift := range lifts {
			ld := int(toFloatMust(lift["day"]))
			bad := false
			for _, retr := range retracts {
				rd := int(toFloatMust(retr["day"]))
				if rd >= ld {
					bad = true
					break
				}
			}
			if !bad {
				survivingLifts = append(survivingLifts, lift)
			}
		}
		surviving := make([]map[string]interface{}, 0)
		for _, c := range comps {
			cd := int(toFloatMust(c["day"]))
			covered := false
			for _, lift := range survivingLifts {
				ld := int(toFloatMust(lift["day"]))
				if ld >= cd {
					covered = true
					break
				}
			}
			if !covered {
				surviving = append(surviving, c)
			}
		}
		ownComp[did] = surviving
	}

	validRuns := map[string]map[string]interface{}{}
	for id, r := range rawRuns {
		if validateRun(r, validDatasets, currentDay) {
			validRuns[id] = r
		}
	}
	for _, r := range rawRuns {
		id, _ := r["id"].(string)
		if validRuns[id] == nil {
			continue
		}
		parent := r["parent_run"]
		if parent != nil {
			ps, ok := parent.(string)
			if ok && ps != "" && validRuns[ps] == nil {
				delete(validRuns, id)
			}
		}
	}
	invalidRunsDropped := len(rawRuns) - len(validRuns)

	acceptedReplays := make([]map[string]interface{}, 0)
	for _, ev := range pendingReplays {
		evID, _ := ev["event_id"].(string)
		runID, _ := ev["run_id"].(string)
		m, mok := toFloat(ev["replayed_eval_metric"])
		if !isNonemptyString(evID) || !isNonemptyString(runID) || validRuns[runID] == nil || !mok || !isNumberIn(ev["replayed_eval_metric"], 0, 1) {
			ignored++
			continue
		}
		_ = m
		acceptedReplays = append(acceptedReplays, ev)
	}

	validCkpts := map[string]map[string]interface{}{}
	for id, c := range rawCheckpoints {
		if validateCheckpoint(c, validRuns) {
			validCkpts[id] = c
		}
	}
	invalidCkptsDropped := len(rawCheckpoints) - len(validCkpts)

	validReg := map[string]map[string]interface{}{}
	for id, e := range rawRegistry {
		if validateRegistry(e, validCkpts) {
			validReg[id] = e
		}
	}
	invalidRegDropped := len(rawRegistry) - len(validReg)

	dsStatus := map[string]string{}
	dsSource := map[string]interface{}{}
	ids := sortedKeys(validDatasets)
	for _, did := range ids {
		if cyclic[did] {
			dsStatus[did] = "cyclic"
			dsSource[did] = nil
			continue
		}
		selfAnc := transitiveAncestorsSet(validDatasets, did)
		selfAnc[did] = struct{}{}
		var offenders []string
		for a := range selfAnc {
			if len(ownComp[a]) > 0 {
				offenders = append(offenders, a)
			}
		}
		if len(offenders) == 0 {
			dsStatus[did] = "clean"
			dsSource[did] = nil
		} else {
			dsStatus[did] = "compromised"
			sort.Slice(offenders, func(i, j int) bool {
				di := depthCache[offenders[i]]
				dj := depthCache[offenders[j]]
				if di != dj {
					return di < dj
				}
				return offenders[i] < offenders[j]
			})
			dsSource[did] = offenders[0]
		}
	}

	runCache := map[string]struct {
		st   string
		reas string
	}{}
	var computeRun func(string, map[string]bool) (string, string)
	computeRun = func(rid string, computing map[string]bool) (string, string) {
		if v, ok := runCache[rid]; ok {
			return v.st, v.reas
		}
		if computing[rid] {
			return "inherited_invalid", "parent_cycle_detected"
		}
		computing[rid] = true
		r := validRuns[rid]
		bd, _ := r["base_dataset"].(string)
		cs := dsStatus[bd]
		if cs == "compromised" {
			src, _ := dsSource[bd].(string)
			reas := "tainted_via_" + src
			runCache[rid] = struct{ st, reas string }{st: "tainted_run", reas: reas}
			delete(computing, rid)
			return "tainted_run", reas
		}
		if cs == "cyclic" {
			reas := "tainted_via_" + bd
			runCache[rid] = struct{ st, reas string }{st: "tainted_run", reas: reas}
			delete(computing, rid)
			return "tainted_run", reas
		}
		offenders := make([]struct{ id, st string }, 0)
		seen := map[string]bool{}
		cur := r["parent_run"]
		for cur != nil {
			cid, ok := cur.(string)
			if !ok || cid == "" || validRuns[cid] == nil || seen[cid] {
				break
			}
			seen[cid] = true
			ancSt, _ := computeRun(cid, computing)
			if ancSt == "aborted" || ancSt == "failed" || ancSt == "inherited_invalid" || ancSt == "tainted_run" || ancSt == "replay_mismatch" || ancSt == "runtime_exceeded" {
				offenders = append(offenders, struct{ id, st string }{cid, ancSt})
			}
			cur = validRuns[cid]["parent_run"]
		}
		if len(offenders) > 0 {
			sort.Slice(offenders, func(i, j int) bool { return offenders[i].id < offenders[j].id })
			sm := offenders[0]
			reas := "parent_" + sm.st + "_" + sm.id
			runCache[rid] = struct{ st, reas string }{st: "inherited_invalid", reas: reas}
			delete(computing, rid)
			return "inherited_invalid", reas
		}
		tier, _ := r["declared_tier_target"].(string)
		tierCfg := tierRules[tier].(map[string]interface{})
		runtimeBudget := int(toFloatMust(tierCfg["runtime_budget_minutes"]))
		rtObs := int(toFloatMust(r["runtime_minutes_observed"]))
		if rtObs > runtimeBudget {
			reas := fmt.Sprintf("runtime_exceeded_observed_%d_budget_%d", rtObs, runtimeBudget)
			runCache[rid] = struct{ st, reas string }{st: "runtime_exceeded", reas: reas}
			delete(computing, rid)
			return "runtime_exceeded", reas
		}
		replays := filterReplayEvents(acceptedReplays, rid)
		if len(replays) > 0 {
			sort.Slice(replays, func(i, j int) bool {
				di := int(toFloatMust(replays[i]["day"]))
				dj := int(toFloatMust(replays[j]["day"]))
				if di != dj {
					return di > dj
				}
				eidi, _ := replays[i]["event_id"].(string)
				eidj, _ := replays[j]["event_id"].(string)
				return eidi < eidj
			})
			latest := replays[0]
			tol := toFloatMust(tierCfg["replay_tolerance"])
			repM := toFloatMust(latest["replayed_eval_metric"])
			claimed := toFloatMust(r["claimed_eval_metric"])
			if math.Abs(repM-claimed) > tol {
				reas := fmt.Sprintf("replay_mismatch_replayed_%s_claimed_%s",
					formatReasonFloat(repM), formatReasonFloat(claimed))
				runCache[rid] = struct{ st, reas string }{st: "replay_mismatch", reas: reas}
				delete(computing, rid)
				return "replay_mismatch", reas
			}
		}
		sd, _ := r["status_declared"].(string)
		var reas string
		switch sd {
		case "succeeded":
			reas = "ok"
		case "failed":
			reas = "declared_failed"
		case "aborted":
			reas = "declared_aborted"
		default:
			reas = ""
		}
		runCache[rid] = struct{ st, reas string }{st: sd, reas: reas}
		delete(computing, rid)
		return sd, reas
	}

	runStatusMap := map[string]struct{ st, reas string }{}
	for rid := range validRuns {
		st, reas := computeRun(rid, map[string]bool{})
		runStatusMap[rid] = struct{ st, reas string }{st, reas}
	}

	ckptDisp := map[string]struct{ disp, reas string }{}
	for _, cid := range sortedKeys(validCkpts) {
		c := validCkpts[cid]
		rid, _ := c["run_id"].(string)
		parentRun := validRuns[rid]
		parentSt := runStatusMap[rid].st
		parentReas := runStatusMap[rid].reas
		_ = parentReas
		if parentSt == "tainted_run" {
			base, _ := parentRun["base_dataset"].(string)
			var taintID string
			if dsStatus[base] == "compromised" {
				taintID, _ = dsSource[base].(string)
			} else {
				taintID = base
			}
			ckptDisp[cid] = struct{ disp, reas string }{disp: "quarantine_tainted", reas: "tainted_via_" + taintID}
			continue
		}
		sig, _ := c["signature_hash"].(string)
		var prefixes []string
		for _, ev := range acceptedRevocs {
			pref, _ := ev["signature_prefix"].(string)
			eff := int(toFloatMust(ev["effective_day"]))
			started := int(toFloatMust(parentRun["started_day"]))
			if strings.HasPrefix(sig, pref) && eff <= started {
				prefixes = append(prefixes, pref)
			}
		}
		if len(prefixes) > 0 {
			sort.Strings(prefixes)
			sm := prefixes[0]
			ckptDisp[cid] = struct{ disp, reas string }{disp: "quarantine_revoked_key", reas: "revoked_prefix_" + sm}
			continue
		}
		if parentSt == "failed" || parentSt == "aborted" || parentSt == "inherited_invalid" || parentSt == "replay_mismatch" || parentSt == "runtime_exceeded" {
			ckptDisp[cid] = struct{ disp, reas string }{disp: "quarantine_unstable_run", reas: "parent_" + parentSt}
			continue
		}
		evs := toFloatMust(c["eval_score"])
		if evs < checkpointScoreFloor {
			ckptDisp[cid] = struct{ disp, reas string }{disp: "quarantine_lowscore", reas: "below_floor_" + formatReasonFloat(evs)}
			continue
		}
		ckptDisp[cid] = struct{ disp, reas string }{disp: "keep", reas: "ok"}
	}

	regDec := map[string]struct{ dec, reas string }{}
	for _, eid := range sortedKeys(validReg) {
		e := validReg[eid]
		candidate, _ := e["candidate_checkpoint"].(string)
		ckpt := validCkpts[candidate]
		run := validRuns[ckpt["run_id"].(string)]
		disp := ckptDisp[candidate].disp
		tier, _ := e["target_tier"].(string)
		rule := tierRules[tier].(map[string]interface{})
		cid := candidate
		switch disp {
		case "quarantine_tainted":
			regDec[eid] = struct{ dec, reas string }{dec: "force_rejected_compromise", reas: "force_rejected_compromise_via_" + cid}
		case "quarantine_revoked_key":
			regDec[eid] = struct{ dec, reas string }{dec: "rejected_revoked_signature", reas: "rejected_revoked_signature_via_" + cid}
		case "quarantine_unstable_run":
			regDec[eid] = struct{ dec, reas string }{dec: "rejected_unstable_candidate", reas: "rejected_unstable_candidate_via_" + cid}
		case "quarantine_lowscore":
			regDec[eid] = struct{ dec, reas string }{dec: "rejected_lowscore_candidate", reas: "rejected_lowscore_candidate_via_" + cid}
		default:
			gr, _ := e["governance_review_status"].(string)
			if gr == "rejected" {
				regDec[eid] = struct{ dec, reas string }{dec: "rejected_review", reas: "rejected_review_rejected"}
			} else if gr == "pending" {
				regDec[eid] = struct{ dec, reas string }{dec: "rejected_review_pending", reas: "rejected_review_pending_pending"}
			} else if toBool(rule["requires_clean_dataset_lineage"]) && validDatasets[run["base_dataset"].(string)]["tier"].(string) == "raw" {
				regDec[eid] = struct{ dec, reas string }{dec: "rejected_raw_base_tier", reas: "rejected_raw_base_tier_via_" + cid}
			} else if int(toFloatMust(run["retry_count_observed"])) > int(toFloatMust(rule["max_retry_count_allowed"])) {
				regDec[eid] = struct{ dec, reas string }{
					dec:  "rejected_retry_cap",
					reas: fmt.Sprintf("rejected_retry_cap_observed_%d_max_%d", int(toFloatMust(run["retry_count_observed"])), int(toFloatMust(rule["max_retry_count_allowed"]))),
				}
			} else if depthCache[run["base_dataset"].(string)] < int(toFloatMust(rule["min_lineage_depth"])) {
				od := depthCache[run["base_dataset"].(string)]
				regDec[eid] = struct{ dec, reas string }{
					dec:  "rejected_lineage_floor",
					reas: fmt.Sprintf("rejected_lineage_floor_observed_%d_min_%d", od, int(toFloatMust(rule["min_lineage_depth"]))),
				}
			} else if toFloatMust(run["claimed_eval_metric"]) < toFloatMust(rule["min_eval_floor"]) {
				regDec[eid] = struct{ dec, reas string }{
					dec:  "rejected_eval_floor",
					reas: fmt.Sprintf("rejected_eval_floor_observed_%s_floor_%s", formatReasonFloat(toFloatMust(run["claimed_eval_metric"])), formatReasonFloat(toFloatMust(rule["min_eval_floor"]))),
				}
			} else if currentDay-int(toFloatMust(run["started_day"])) < int(toFloatMust(rule["min_audit_age_days"])) {
				age := currentDay - int(toFloatMust(run["started_day"]))
				regDec[eid] = struct{ dec, reas string }{
					dec:  "rejected_audit_pending",
					reas: fmt.Sprintf("rejected_audit_pending_age_%d_min_%d", age, int(toFloatMust(rule["min_audit_age_days"]))),
				}
			} else {
				regDec[eid] = struct{ dec, reas string }{dec: "promoted", reas: "ok"}
			}
		}
	}

	runsOut := make([]interface{}, 0)
	for _, rid := range sortedKeys(validRuns) {
		r := validRuns[rid]
		st := runStatusMap[rid].st
		reas := runStatusMap[rid].reas
		rep := latestReplay(acceptedReplays, rid)
		row := map[string]interface{}{
			"base_dataset":         r["base_dataset"],
			"claimed_eval_metric":  pyFloat(math.Round(toFloatMust(r["claimed_eval_metric"])*1e4) / 1e4),
			"declared_tier_target": r["declared_tier_target"],
			"id":                   rid,
			"owner":                r["owner"],
			"reason":               reas,
			"status":               st,
		}
		if rep == nil {
			row["replay_metric"] = nil
		} else {
			row["replay_metric"] = pyFloat(math.Round(toFloatMust(rep["replayed_eval_metric"])*1e4) / 1e4)
		}
		runsOut = append(runsOut, row)
	}

	datasetsOut := make([]interface{}, 0)
	for _, did := range sortedKeys(validDatasets) {
		d := validDatasets[did]
		var depth int
		var downstream []interface{}
		if cyclic[did] {
			depth = -1
			downstream = []interface{}{}
		} else {
			depth = depthCache[did]
			desc := descendantsSet(validDatasets, cyclic, did)
			drids := make([]string, 0)
			for rrid, rr := range validRuns {
				bd, _ := rr["base_dataset"].(string)
				if desc[bd] {
					drids = append(drids, rrid)
				}
			}
			sort.Strings(drids)
			for _, x := range drids {
				downstream = append(downstream, x)
			}
		}
		row := map[string]interface{}{
			"compromise_source": dsSource[did],
			"compromise_status": dsStatus[did],
			"downstream_runs":   downstream,
			"id":                did,
			"lineage_depth":     depth,
			"tier":              d["tier"],
		}
		datasetsOut = append(datasetsOut, row)
	}

	checkpointsOut := make([]interface{}, 0)
	for _, cid := range sortedKeys(validCkpts) {
		c := validCkpts[cid]
		d := ckptDisp[cid]
		evs := math.Round(toFloatMust(c["eval_score"])*1e4) / 1e4
		sz := 0
		if d.disp == "keep" {
			sz = int(toFloatMust(c["file_size_mb"]))
		}
		checkpointsOut = append(checkpointsOut, map[string]interface{}{
			"disposition":  d.disp,
			"eval_score":   pyFloat(evs),
			"id":           cid,
			"reason":       d.reas,
			"run_id":       c["run_id"],
			"size_mb_kept": sz,
		})
	}

	modelsOut := make([]interface{}, 0)
	for _, eid := range sortedKeys(validReg) {
		e := validReg[eid]
		rd := regDec[eid]
		tier, _ := e["target_tier"].(string)
		mf := math.Round(toFloatMust(tierRules[tier].(map[string]interface{})["min_eval_floor"])*1e4) / 1e4
		modelsOut = append(modelsOut, map[string]interface{}{
			"applied_eval_floor":   pyFloat(mf),
			"candidate_checkpoint": e["candidate_checkpoint"],
			"decision":             rd.dec,
			"id":                   eid,
			"reason":               rd.reas,
			"target_tier":          tier,
		})
	}

	byRun := map[string]interface{}{
		"aborted": 0, "failed": 0, "inherited_invalid": 0, "replay_mismatch": 0,
		"runtime_exceeded": 0, "succeeded": 0, "tainted_run": 0,
	}
	for _, v := range runStatusMap {
		byRun[v.st] = byRun[v.st].(int) + 1
	}

	byComp := map[string]interface{}{"clean": 0, "compromised": 0, "cyclic": 0}
	for _, cs := range dsStatus {
		byComp[cs] = byComp[cs].(int) + 1
	}

	byDisp := map[string]interface{}{
		"keep": 0, "quarantine_lowscore": 0, "quarantine_unstable_run": 0,
		"quarantine_revoked_key": 0, "quarantine_tainted": 0,
	}
	for _, v := range ckptDisp {
		byDisp[v.disp] = byDisp[v.disp].(int) + 1
	}

	byDec := map[string]interface{}{
		"force_rejected_compromise": 0, "promoted": 0, "rejected_audit_pending": 0,
		"rejected_eval_floor": 0, "rejected_lineage_floor": 0, "rejected_raw_base_tier": 0,
		"rejected_retry_cap": 0, "rejected_review": 0, "rejected_review_pending": 0,
		"rejected_lowscore_candidate": 0, "rejected_unstable_candidate": 0, "rejected_revoked_signature": 0,
	}
	for _, v := range regDec {
		byDec[v.dec] = byDec[v.dec].(int) + 1
	}

	var compromised []interface{}
	for _, rid := range sortedKeys(validRuns) {
		if runStatusMap[rid].st == "tainted_run" {
			compromised = append(compromised, rid)
		}
	}

	totals := map[string]interface{}{
		"checkpoints":                      len(validCkpts),
		"datasets":                         len(validDatasets),
		"ignored_incident_events":          ignored,
		"invalid_checkpoints_dropped":      invalidCkptsDropped,
		"invalid_datasets_dropped":         invalidDatasetsDropped,
		"invalid_registry_entries_dropped": invalidRegDropped,
		"invalid_runs_dropped":             invalidRunsDropped,
		"registry_entries":                 len(validReg),
		"runs":                             len(validRuns),
	}

	summary := map[string]interface{}{
		"by_compromise_status": byComp,
		"by_decision":          byDec,
		"by_disposition":       byDisp,
		"by_run_status":        byRun,
		"compromised_run_ids":  compromised,
		"current_day":          currentDay,
		"ledger_version":       ledgerVersion,
		"totals":               totals,
	}

	if err := writeJSON(filepath.Join(auditDir, "run_status.json"), map[string]interface{}{"runs": runsOut}); err != nil {
		die(err)
	}
	if err := writeJSON(filepath.Join(auditDir, "lineage_graph.json"), map[string]interface{}{"datasets": datasetsOut}); err != nil {
		die(err)
	}
	if err := writeJSON(filepath.Join(auditDir, "checkpoint_disposition.json"), map[string]interface{}{"checkpoints": checkpointsOut}); err != nil {
		die(err)
	}
	if err := writeJSON(filepath.Join(auditDir, "registry_promotion.json"), map[string]interface{}{"models": modelsOut}); err != nil {
		die(err)
	}
	if err := writeJSON(filepath.Join(auditDir, "summary.json"), summary); err != nil {
		die(err)
	}
}

func toBool(x interface{}) bool {
	b, ok := x.(bool)
	return ok && b
}

func formatReasonFloat(x float64) string {
	return fmt.Sprintf("%.4f", x)
}

func filterReplayEvents(ev []map[string]interface{}, rid string) []map[string]interface{} {
	var out []map[string]interface{}
	for _, e := range ev {
		if e["run_id"] == rid {
			out = append(out, e)
		}
	}
	return out
}

func latestReplay(ev []map[string]interface{}, rid string) map[string]interface{} {
	rs := filterReplayEvents(ev, rid)
	if len(rs) == 0 {
		return nil
	}
	sort.Slice(rs, func(i, j int) bool {
		di := int(toFloatMust(rs[i]["day"]))
		dj := int(toFloatMust(rs[j]["day"]))
		if di != dj {
			return di > dj
		}
		eidi, _ := rs[i]["event_id"].(string)
		eidj, _ := rs[j]["event_id"].(string)
		return eidi < eidj
	})
	return rs[0]
}

func descendantsSet(valid map[string]map[string]interface{}, cyclic map[string]bool, root string) map[string]bool {
	out := map[string]bool{}
	stack := []string{root}
	for len(stack) > 0 {
		cur := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if out[cur] || cyclic[cur] {
			continue
		}
		out[cur] = true
		for did, d := range valid {
			if cyclic[did] {
				continue
			}
			for _, p := range filteredParents(d) {
				if p == cur && !out[did] {
					stack = append(stack, did)
				}
			}
		}
	}
	return out
}

func transitiveAncestorsSet(valid map[string]map[string]interface{}, start string) map[string]struct{} {
	seen := map[string]struct{}{}
	stack := append([]string(nil), filteredParents(valid[start])...)
	for len(stack) > 0 {
		cur := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if _, ok := seen[cur]; ok {
			continue
		}
		seen[cur] = struct{}{}
		if valid[cur] != nil {
			stack = append(stack, filteredParents(valid[cur])...)
		}
	}
	return seen
}

func inTransitiveAncestors(valid map[string]map[string]interface{}, start, target string) bool {
	stack := append([]string(nil), filteredParents(valid[start])...)
	seen := map[string]bool{}
	for len(stack) > 0 {
		cur := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if cur == target {
			return true
		}
		if seen[cur] {
			continue
		}
		seen[cur] = true
		if valid[cur] != nil {
			stack = append(stack, filteredParents(valid[cur])...)
		}
	}
	return false
}

func filteredParents(d map[string]interface{}) []string {
	fp, _ := d["_filtered_parents"].([]interface{})
	out := make([]string, 0, len(fp))
	for _, x := range fp {
		s, _ := x.(string)
		out = append(out, s)
	}
	return out
}

func sortedKeys[M ~map[string]V, V any](m M) []string {
	ks := make([]string, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	sort.Strings(ks)
	return ks
}

func toFloatMust(x interface{}) float64 {
	f, ok := toFloat(x)
	if !ok {
		die(fmt.Errorf("expected number, got %T", x))
	}
	return f
}

func validateDataset(d map[string]interface{}) bool {
	if !isNonemptyString(d["id"]) {
		return false
	}
	tier, _ := d["tier"].(string)
	if tier != "raw" && tier != "curated" && tier != "gold" {
		return false
	}
	parents, ok := d["lineage_parents"].([]interface{})
	if !ok {
		return false
	}
	for _, p := range parents {
		if !isNonemptyString(p) {
			return false
		}
	}
	return true
}

func validateRun(r map[string]interface{}, vd map[string]map[string]interface{}, currentDay int) bool {
	if !isNonemptyString(r["id"]) || !isNonemptyString(r["owner"]) {
		return false
	}
	if !isIntGE(r["started_day"], 0) || int(toFloatMust(r["started_day"])) > currentDay {
		return false
	}
	bd, _ := r["base_dataset"].(string)
	if !isNonemptyString(bd) || vd[bd] == nil {
		return false
	}
	tgt, _ := r["declared_tier_target"].(string)
	if tgt != "research" && tgt != "staging" && tgt != "prod" {
		return false
	}
	sd, _ := r["status_declared"].(string)
	if sd != "succeeded" && sd != "failed" && sd != "aborted" {
		return false
	}
	if !isNumberIn(r["claimed_eval_metric"], 0, 1) {
		return false
	}
	if !isIntGE(r["runtime_minutes_observed"], 0) || !isIntGE(r["retry_count_observed"], 0) {
		return false
	}
	pr := r["parent_run"]
	if pr != nil {
		ps, ok := pr.(string)
		if !ok || ps == "" || ps == r["id"] {
			return false
		}
	}
	return true
}

func validateCheckpoint(c map[string]interface{}, vr map[string]map[string]interface{}) bool {
	if !isNonemptyString(c["id"]) {
		return false
	}
	rid, _ := c["run_id"].(string)
	if vr[rid] == nil {
		return false
	}
	if !isIntGE(c["step"], 0) || !isNumberIn(c["eval_score"], 0, 1) {
		return false
	}
	sig, _ := c["signature_hash"].(string)
	if !isNonemptyString(sig) || !hex64.MatchString(sig) {
		return false
	}
	if !isIntGE(c["file_size_mb"], 0) {
		return false
	}
	return true
}

func validateRegistry(e map[string]interface{}, vc map[string]map[string]interface{}) bool {
	if !isNonemptyString(e["id"]) {
		return false
	}
	cp, _ := e["candidate_checkpoint"].(string)
	if vc[cp] == nil {
		return false
	}
	tt, _ := e["target_tier"].(string)
	if tt != "research" && tt != "staging" && tt != "prod" {
		return false
	}
	gr, _ := e["governance_review_status"].(string)
	if gr != "approved" && gr != "pending" && gr != "rejected" {
		return false
	}
	return true
}
