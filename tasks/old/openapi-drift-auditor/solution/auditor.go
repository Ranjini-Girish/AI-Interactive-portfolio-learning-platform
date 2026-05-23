package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type Param struct {
	Name     string `json:"name"`
	Required bool   `json:"required"`
	Type     string `json:"type"`
}

type ResponseField struct {
	Name string `json:"name"`
	Type string `json:"type"`
}

type Endpoint struct {
	EndpointID     string          `json:"endpoint_id"`
	Params         []Param         `json:"params"`
	ResponseFields []ResponseField `json:"response_fields"`
	StatusCodes    []int           `json:"status_codes"`
}

type Service struct {
	AuthMode  string     `json:"auth_mode"`
	Endpoints []Endpoint `json:"endpoints"`
	ServiceID string     `json:"service_id"`
	Tier      string     `json:"tier"`
}

type DirectFieldRead struct {
	ConsumerID string   `json:"consumer_id"`
	EndpointID string   `json:"endpoint_id"`
	Fields     []string `json:"fields"`
	ProducerID string   `json:"producer_id"`
}

type FieldExposure struct {
	EndpointID      string            `json:"endpoint_id"`
	ExposingService string            `json:"exposing_service"`
	FieldMap        map[string]string `json:"field_map"`
	ProducerID      string            `json:"producer_id"`
}

type Dependencies struct {
	DirectFieldReads []DirectFieldRead `json:"direct_field_reads"`
	FieldExposures   []FieldExposure   `json:"field_exposures"`
}

type Event struct {
	Accepted   bool   `json:"accepted"`
	Day        int    `json:"day"`
	EndpointID string `json:"endpoint_id"`
	EventID    string `json:"event_id"`
	Kind       string `json:"kind"`
	ServiceID  string `json:"service_id"`
}

type IncidentLog struct {
	Events []Event `json:"events"`
}

type Policy struct {
	FreezeExtensionPhases  int            `json:"freeze_extension_phases"`
	SupportedIncidentKinds []string       `json:"supported_incident_kinds"`
	TierWeights            map[string]int `json:"tier_weights"`
}

type PoolState struct {
	CurrentDay int `json:"current_day"`
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func die(err error) {
	fmt.Fprintln(os.Stderr, "auditor error:", err)
	os.Exit(1)
}

func mustReadJSON(path string, dst interface{}) {
	b, err := os.ReadFile(path)
	if err != nil {
		die(fmt.Errorf("read %s: %w", path, err))
	}
	if err := json.Unmarshal(b, dst); err != nil {
		die(fmt.Errorf("parse %s: %w", path, err))
	}
}

func writeJSON(path string, obj interface{}) {
	buf := &bytes.Buffer{}
	enc := json.NewEncoder(buf)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	if err := enc.Encode(obj); err != nil {
		die(err)
	}
	if err := os.WriteFile(path, buf.Bytes(), 0o644); err != nil {
		die(err)
	}
}

func loadServicesFromDir(dir string) map[string]Service {
	out := map[string]Service{}
	err := filepath.WalkDir(dir, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || !strings.HasSuffix(p, ".json") {
			return nil
		}
		var s Service
		mustReadJSON(p, &s)
		out[s.ServiceID] = s
		return nil
	})
	if err != nil {
		die(err)
	}
	return out
}

type ChangeKind string

const (
	ChAuthModeChanged           = "auth_mode_changed"
	ChEndpointAdded             = "endpoint_added"
	ChEndpointRemoved           = "endpoint_removed"
	ChParamAddedOptional        = "param_added_optional"
	ChParamAddedRequired        = "param_added_required"
	ChParamRemoved              = "param_removed"
	ChParamRequiredAdded        = "param_required_added"
	ChParamTypeNarrowed         = "param_type_narrowed"
	ChResponseFieldAdded        = "response_field_added"
	ChResponseFieldRemoved      = "response_field_removed"
	ChResponseFieldTypeChanged  = "response_field_type_changed"
	ChStatusCodeClassChange     = "status_code_class_change"
)

type EndpointChange struct {
	EndpointID  string
	ChangeKinds []string
	RemovedFields []string
	RemovedParams []string
}

func diffEndpoint(curSvc, baseSvc *Service, curEP, baseEP *Endpoint) EndpointChange {
	ch := EndpointChange{}
	if curSvc == nil || curEP == nil {
		ch.EndpointID = baseEP.EndpointID
		ch.ChangeKinds = []string{ChEndpointRemoved}
		return ch
	}
	ch.EndpointID = curEP.EndpointID
	if baseSvc == nil || baseEP == nil {
		ch.ChangeKinds = []string{ChEndpointAdded}
		return ch
	}

	kinds := map[string]struct{}{}
	if curSvc.AuthMode != baseSvc.AuthMode {
		kinds[ChAuthModeChanged] = struct{}{}
	}

	curParams := map[string]Param{}
	for _, p := range curEP.Params {
		curParams[p.Name] = p
	}
	baseParams := map[string]Param{}
	for _, p := range baseEP.Params {
		baseParams[p.Name] = p
	}
	for name, cp := range curParams {
		bp, ok := baseParams[name]
		if !ok {
			if cp.Required {
				kinds[ChParamAddedRequired] = struct{}{}
			} else {
				kinds[ChParamAddedOptional] = struct{}{}
			}
			continue
		}
		if !bp.Required && cp.Required {
			kinds[ChParamRequiredAdded] = struct{}{}
		}
		if bp.Type != cp.Type {
			kinds[ChParamTypeNarrowed] = struct{}{}
		}
	}
	for name := range baseParams {
		if _, ok := curParams[name]; !ok {
			kinds[ChParamRemoved] = struct{}{}
			ch.RemovedParams = append(ch.RemovedParams, name)
		}
	}

	curFields := map[string]string{}
	for _, f := range curEP.ResponseFields {
		curFields[f.Name] = f.Type
	}
	baseFields := map[string]string{}
	for _, f := range baseEP.ResponseFields {
		baseFields[f.Name] = f.Type
	}
	for name, ct := range curFields {
		bt, ok := baseFields[name]
		if !ok {
			kinds[ChResponseFieldAdded] = struct{}{}
			continue
		}
		if bt != ct {
			kinds[ChResponseFieldTypeChanged] = struct{}{}
		}
	}
	for name := range baseFields {
		if _, ok := curFields[name]; !ok {
			kinds[ChResponseFieldRemoved] = struct{}{}
			ch.RemovedFields = append(ch.RemovedFields, name)
		}
	}

	curClasses := map[int]struct{}{}
	for _, c := range curEP.StatusCodes {
		curClasses[c/100] = struct{}{}
	}
	baseClasses := map[int]struct{}{}
	for _, c := range baseEP.StatusCodes {
		baseClasses[c/100] = struct{}{}
	}
	if !equalClassSet(curClasses, baseClasses) {
		kinds[ChStatusCodeClassChange] = struct{}{}
	}

	ch.ChangeKinds = []string{}
	for k := range kinds {
		ch.ChangeKinds = append(ch.ChangeKinds, k)
	}
	sort.Strings(ch.ChangeKinds)
	sort.Strings(ch.RemovedFields)
	sort.Strings(ch.RemovedParams)
	return ch
}

func equalClassSet(a, b map[int]struct{}) bool {
	if len(a) != len(b) {
		return false
	}
	for k := range a {
		if _, ok := b[k]; !ok {
			return false
		}
	}
	return true
}

type AcceptedEvents struct {
	ForceBreak     map[string]map[string]bool
	ConsumerFreeze map[string]bool
	AcceptedCount  int
	IgnoredCount   int
}

func resolveEvents(log IncidentLog, policy Policy, currentDay int) AcceptedEvents {
	supported := map[string]bool{}
	for _, k := range policy.SupportedIncidentKinds {
		supported[k] = true
	}
	type key struct {
		Kind, Service, Endpoint string
	}
	groups := map[key][]Event{}
	totalEligible := 0
	for _, e := range log.Events {
		if !e.Accepted || e.Day > currentDay || !supported[e.Kind] {
			continue
		}
		groups[key{e.Kind, e.ServiceID, e.EndpointID}] = append(
			groups[key{e.Kind, e.ServiceID, e.EndpointID}], e)
		totalEligible++
	}
	winners := map[string]Event{}
	for _, evs := range groups {
		sort.Slice(evs, func(i, j int) bool {
			if evs[i].Day != evs[j].Day {
				return evs[i].Day > evs[j].Day
			}
			return evs[i].EventID < evs[j].EventID
		})
		w := evs[0]
		winners[w.EventID] = w
	}
	res := AcceptedEvents{
		ForceBreak:     map[string]map[string]bool{},
		ConsumerFreeze: map[string]bool{},
	}
	for _, w := range winners {
		switch w.Kind {
		case "force_break":
			if res.ForceBreak[w.ServiceID] == nil {
				res.ForceBreak[w.ServiceID] = map[string]bool{}
			}
			res.ForceBreak[w.ServiceID][w.EndpointID] = true
		case "consumer_freeze":
			res.ConsumerFreeze[w.ServiceID] = true
		}
	}
	res.AcceptedCount = len(winners)
	res.IgnoredCount = len(log.Events) - res.AcceptedCount
	return res
}

type ResolvedClassification struct {
	Classification string
	Reason         string
}

func tierStrength(kind, tier string, consumerAware bool) string {
	switch kind {
	case ChAuthModeChanged, ChEndpointRemoved:
		return "breaking"
	case ChEndpointAdded, ChResponseFieldAdded:
		return "non_breaking"
	case ChParamAddedOptional:
		return "minor"
	case ChParamAddedRequired:
		if tier == "gold" {
			return "breaking"
		}
		return "minor"
	case ChParamRequiredAdded, ChParamTypeNarrowed:
		if tier == "gold" || tier == "silver" {
			return "breaking"
		}
		return "minor"
	case ChParamRemoved, ChResponseFieldRemoved, ChResponseFieldTypeChanged:
		if tier == "gold" {
			return "breaking"
		}
		if tier == "silver" {
			if consumerAware {
				return "breaking"
			}
			return "minor"
		}
		return "minor"
	case ChStatusCodeClassChange:
		if tier == "gold" {
			return "breaking"
		}
		return "minor"
	}
	return "minor"
}

func strengthRank(s string) int {
	switch s {
	case "breaking_forced":
		return 4
	case "breaking":
		return 3
	case "minor":
		return 2
	case "non_breaking":
		return 1
	}
	return 0
}

func classifyEndpoint(svc Service, ch EndpointChange, deps Dependencies, fbHit bool) ResolvedClassification {
	if fbHit {
		return ResolvedClassification{"breaking_forced", "forced_event"}
	}
	if len(ch.ChangeKinds) == 0 {
		return ResolvedClassification{"non_breaking", "no_changes"}
	}
	consumerReadsEndpoint := false
	consumerReadsField := map[string]bool{}
	for _, r := range deps.DirectFieldReads {
		if r.ProducerID == svc.ServiceID && r.EndpointID == ch.EndpointID {
			consumerReadsEndpoint = true
			for _, f := range r.Fields {
				consumerReadsField[f] = true
			}
		}
	}

	best := "non_breaking"
	bestKinds := []string{}
	for _, k := range ch.ChangeKinds {
		consumerAware := false
		if k == ChParamRemoved {
			consumerAware = consumerReadsEndpoint
		} else if k == ChResponseFieldRemoved {
			consumerAware = false
			for _, removed := range ch.RemovedFields {
				if consumerReadsField[removed] {
					consumerAware = true
					break
				}
			}
		} else if k == ChResponseFieldTypeChanged {
			consumerAware = false
			curFields := map[string]string{}
			for _, ep := range svc.Endpoints {
				if ep.EndpointID == ch.EndpointID {
					for _, f := range ep.ResponseFields {
						curFields[f.Name] = f.Type
					}
				}
			}
			for fname := range consumerReadsField {
				if _, present := curFields[fname]; !present {
					continue
				}
			}
			consumerAware = consumerReadsEndpoint
		}
		s := tierStrength(k, svc.Tier, consumerAware)
		if strengthRank(s) > strengthRank(best) {
			best = s
			bestKinds = []string{k}
		} else if strengthRank(s) == strengthRank(best) {
			bestKinds = append(bestKinds, k)
		}
	}
	sort.Strings(bestKinds)
	return ResolvedClassification{best, bestKinds[0]}
}

type ConsumerImpactEntry struct {
	ProducerService string
	EndpointID      string
	ImpactType      string
	HopDistance     int
	CauseField      string
}

func sccBlockedSet(deps Dependencies, allServices []string) map[string]bool {
	g := map[string]map[string]bool{}
	for _, s := range allServices {
		g[s] = map[string]bool{}
	}
	for _, r := range deps.DirectFieldReads {
		if g[r.ConsumerID] == nil {
			g[r.ConsumerID] = map[string]bool{}
		}
		g[r.ConsumerID][r.ProducerID] = true
	}
	index := map[string]int{}
	lowlink := map[string]int{}
	onStack := map[string]bool{}
	stack := []string{}
	idx := 0
	sccs := [][]string{}

	var strongConnect func(v string)
	strongConnect = func(v string) {
		index[v] = idx
		lowlink[v] = idx
		idx++
		stack = append(stack, v)
		onStack[v] = true
		neighbors := []string{}
		for n := range g[v] {
			neighbors = append(neighbors, n)
		}
		sort.Strings(neighbors)
		for _, w := range neighbors {
			if _, seen := index[w]; !seen {
				strongConnect(w)
				if lowlink[w] < lowlink[v] {
					lowlink[v] = lowlink[w]
				}
			} else if onStack[w] {
				if index[w] < lowlink[v] {
					lowlink[v] = index[w]
				}
			}
		}
		if lowlink[v] == index[v] {
			scc := []string{}
			for {
				w := stack[len(stack)-1]
				stack = stack[:len(stack)-1]
				onStack[w] = false
				scc = append(scc, w)
				if w == v {
					break
				}
			}
			sccs = append(sccs, scc)
		}
	}
	allSorted := append([]string{}, allServices...)
	sort.Strings(allSorted)
	for _, v := range allSorted {
		if _, seen := index[v]; !seen {
			strongConnect(v)
		}
	}

	blocked := map[string]bool{}
	for _, scc := range sccs {
		if len(scc) > 1 {
			for _, v := range scc {
				blocked[v] = true
			}
			continue
		}
		v := scc[0]
		if g[v][v] {
			blocked[v] = true
		}
	}

	changed := true
	for changed {
		changed = false
		for s := range g {
			if blocked[s] {
				continue
			}
			for p := range g[s] {
				if blocked[p] {
					blocked[s] = true
					changed = true
					break
				}
			}
		}
	}
	return blocked
}

func computeImpacts(
	allServices []string,
	servicesMap map[string]Service,
	classifications map[string]map[string]ResolvedClassification,
	endpointChanges map[string]map[string]EndpointChange,
	deps Dependencies,
	accepted AcceptedEvents,
	blocked map[string]bool,
) map[string][]ConsumerImpactEntry {
	consumersOf := map[string]map[string][]DirectFieldRead{}
	for _, r := range deps.DirectFieldReads {
		if consumersOf[r.ProducerID] == nil {
			consumersOf[r.ProducerID] = map[string][]DirectFieldRead{}
		}
		consumersOf[r.ProducerID][r.EndpointID] = append(
			consumersOf[r.ProducerID][r.EndpointID], r)
	}
	exposuresFrom := map[string]map[string][]FieldExposure{}
	for _, fe := range deps.FieldExposures {
		if exposuresFrom[fe.ProducerID] == nil {
			exposuresFrom[fe.ProducerID] = map[string][]FieldExposure{}
		}
		exposuresFrom[fe.ProducerID][fe.EndpointID] = append(
			exposuresFrom[fe.ProducerID][fe.EndpointID], fe)
	}

	type impactKey struct {
		Consumer, Producer, Endpoint string
	}
	impacts := map[impactKey]ConsumerImpactEntry{}

	addImpact := func(consumer, producer, endpointID, kind string, hop int, cause string) {
		key := impactKey{consumer, producer, endpointID}
		existing, ok := impacts[key]
		if !ok {
			impacts[key] = ConsumerImpactEntry{
				ProducerService: producer,
				EndpointID:      endpointID,
				ImpactType:      kind,
				HopDistance:     hop,
				CauseField:      cause,
			}
			return
		}
		newRank := impactPrecedence(kind)
		oldRank := impactPrecedence(existing.ImpactType)
		if newRank > oldRank {
			existing.ImpactType = kind
			existing.CauseField = cause
		} else if newRank == oldRank {
			if cause != "" && (existing.CauseField == "" || cause < existing.CauseField) {
				existing.CauseField = cause
			}
		}
		if hop > 0 && (existing.HopDistance == 0 || hop < existing.HopDistance) {
			if existing.ImpactType != "cyclic_field_exposure" {
				existing.HopDistance = hop
			}
		}
		if existing.ImpactType == "cyclic_field_exposure" {
			existing.HopDistance = 0
		}
		impacts[key] = existing
	}

	for sid, fbEPs := range accepted.ForceBreak {
		for ep := range fbEPs {
			for _, r := range consumersOf[sid][ep] {
				addImpact(r.ConsumerID, sid, ep, "force_migration_required", 1, "")
			}
		}
	}

	walkChange := func(producerID, endpointID, causeField string, hopBase int, walked map[string]int) {
		var walk func(producerID, endpointID, fieldName, causeField string, hop int, walked map[string]int)
		walk = func(producerID, endpointID, fieldName, causeField string, hop int, walked map[string]int) {
			for _, r := range consumersOf[producerID][endpointID] {
				if blocked[r.ConsumerID] && (blocked[producerID] || producerID == r.ConsumerID) {
					addImpact(r.ConsumerID, producerID, endpointID, "cyclic_field_exposure", 0, causeField)
					continue
				}
				if fieldName != "" {
					found := false
					for _, f := range r.Fields {
						if f == fieldName {
							found = true
							break
						}
					}
					if !found {
						continue
					}
				}
				if hop == 1 {
					addImpact(r.ConsumerID, producerID, endpointID, "affected_direct", 1, causeField)
				} else {
					addImpact(r.ConsumerID, producerID, endpointID, "affected_transitive", hop, causeField)
				}
			}
			if fieldName == "" {
				return
			}
			for _, fe := range exposuresFrom[producerID][endpointID] {
				exposedName, ok := fe.FieldMap[fieldName]
				if !ok {
					continue
				}
				if walked[fe.ExposingService] >= hop+1 && walked[fe.ExposingService] != 0 {
					continue
				}
				walked[fe.ExposingService] = hop + 1
				for _, exposingEP := range servicesMap[fe.ExposingService].Endpoints {
					walk(fe.ExposingService, exposingEP.EndpointID, exposedName, causeField, hop+1, walked)
				}
			}
		}
		walk(producerID, endpointID, causeField, causeField, hopBase, walked)
	}
	_ = walkChange

	for sid, byEp := range classifications {
		for epID, cls := range byEp {
			if cls.Classification != "breaking" {
				continue
			}
			ch := endpointChanges[sid][epID]
			triggerFields := []string{}
			triggerEndpointLevel := false
			for _, k := range ch.ChangeKinds {
				if (k == ChResponseFieldRemoved || k == ChResponseFieldTypeChanged) && tierStrengthFromKind(k, sid, servicesMap, deps, ch) == "breaking" {
					if k == ChResponseFieldRemoved {
						triggerFields = append(triggerFields, ch.RemovedFields...)
					} else {
						curFields := map[string]string{}
						for _, ep := range servicesMap[sid].Endpoints {
							if ep.EndpointID == epID {
								for _, f := range ep.ResponseFields {
									curFields[f.Name] = f.Type
								}
							}
						}
						for _, r := range deps.DirectFieldReads {
							if r.ProducerID == sid && r.EndpointID == epID {
								for _, fname := range r.Fields {
									if _, present := curFields[fname]; present {
										triggerFields = append(triggerFields, fname)
									}
								}
							}
						}
					}
				}
				if k == ChEndpointRemoved || k == ChAuthModeChanged || k == ChStatusCodeClassChange ||
					k == ChParamRemoved || k == ChParamRequiredAdded || k == ChParamAddedRequired || k == ChParamTypeNarrowed {
					if tierStrengthFromKind(k, sid, servicesMap, deps, ch) == "breaking" {
						triggerEndpointLevel = true
					}
				}
			}
			sort.Strings(triggerFields)
			triggerFields = uniqueStrings(triggerFields)
			cycleHere := false
			for _, r := range consumersOf[sid][epID] {
				if blocked[r.ConsumerID] && blocked[sid] {
					cycleHere = true
					addImpact(r.ConsumerID, sid, epID, "cyclic_field_exposure", 0, firstOrEmpty(triggerFields))
				}
			}
			if cycleHere {
				continue
			}
			if triggerEndpointLevel {
				for _, r := range consumersOf[sid][epID] {
					addImpact(r.ConsumerID, sid, epID, "affected_direct", 1, "")
				}
			}
			for _, field := range triggerFields {
				walked := map[string]int{}
				walked[sid] = 0
				walkChange(sid, epID, field, 1, walked)
			}
		}
	}

	for sid, byEP := range accepted.ForceBreak {
		for epID := range byEP {
			for _, r := range consumersOf[sid][epID] {
				addImpact(r.ConsumerID, sid, epID, "force_migration_required", 1, "")
			}
		}
	}

	out := map[string][]ConsumerImpactEntry{}
	for k, v := range impacts {
		out[k.Consumer] = append(out[k.Consumer], v)
	}
	for c := range out {
		sort.Slice(out[c], func(i, j int) bool {
			if out[c][i].ProducerService != out[c][j].ProducerService {
				return out[c][i].ProducerService < out[c][j].ProducerService
			}
			return out[c][i].EndpointID < out[c][j].EndpointID
		})
	}
	return out
}

func tierStrengthFromKind(kind, sid string, services map[string]Service, deps Dependencies, ch EndpointChange) string {
	svc := services[sid]
	consumerReadsEndpoint := false
	consumerFields := map[string]bool{}
	for _, r := range deps.DirectFieldReads {
		if r.ProducerID == sid && r.EndpointID == ch.EndpointID {
			consumerReadsEndpoint = true
			for _, f := range r.Fields {
				consumerFields[f] = true
			}
		}
	}
	consumerAware := false
	if kind == ChParamRemoved {
		consumerAware = consumerReadsEndpoint
	}
	if kind == ChResponseFieldRemoved {
		for _, removed := range ch.RemovedFields {
			if consumerFields[removed] {
				consumerAware = true
				break
			}
		}
	}
	if kind == ChResponseFieldTypeChanged {
		consumerAware = consumerReadsEndpoint
	}
	return tierStrength(kind, svc.Tier, consumerAware)
}

func impactPrecedence(s string) int {
	switch s {
	case "force_migration_required":
		return 4
	case "cyclic_field_exposure":
		return 3
	case "affected_direct":
		return 2
	case "affected_transitive":
		return 1
	}
	return 0
}

func uniqueStrings(in []string) []string {
	seen := map[string]bool{}
	out := []string{}
	for _, s := range in {
		if !seen[s] {
			seen[s] = true
			out = append(out, s)
		}
	}
	return out
}

func firstOrEmpty(s []string) string {
	if len(s) == 0 {
		return ""
	}
	return s[0]
}

func summaryActionFor(tier string, impacts []ConsumerImpactEntry) string {
	hasForce := false
	hasDirect := false
	hasTransitive := false
	hasCyclic := false
	for _, i := range impacts {
		switch i.ImpactType {
		case "force_migration_required":
			hasForce = true
		case "affected_direct":
			hasDirect = true
		case "affected_transitive":
			hasTransitive = true
		case "cyclic_field_exposure":
			hasCyclic = true
		}
	}
	if hasForce {
		return "force_migrate"
	}
	if hasDirect && (tier == "gold" || tier == "silver") {
		return "migrate"
	}
	if hasDirect || hasTransitive || hasCyclic {
		return "monitor"
	}
	return "none"
}

func tierRank(t string) int {
	switch t {
	case "gold":
		return 3
	case "silver":
		return 2
	case "bronze":
		return 1
	}
	return 0
}

func main() {
	registryDir := getenv("ODA_REGISTRY_DIR", "/app/registry")
	auditDir := getenv("ODA_AUDIT_DIR", "/app/audit")
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		die(err)
	}

	var pool PoolState
	mustReadJSON(filepath.Join(registryDir, "pool_state.json"), &pool)
	var policy Policy
	mustReadJSON(filepath.Join(registryDir, "policy", "policy.json"), &policy)
	var deps Dependencies
	mustReadJSON(filepath.Join(registryDir, "consumers", "dependencies.json"), &deps)
	var log IncidentLog
	mustReadJSON(filepath.Join(registryDir, "incidents", "incident_log.json"), &log)

	curServices := loadServicesFromDir(filepath.Join(registryDir, "services"))
	baseServices := loadServicesFromDir(filepath.Join(registryDir, "baselines"))

	allIDs := map[string]bool{}
	for k := range curServices {
		allIDs[k] = true
	}
	for k := range baseServices {
		allIDs[k] = true
	}
	allList := []string{}
	for k := range allIDs {
		allList = append(allList, k)
	}
	sort.Strings(allList)

	accepted := resolveEvents(log, policy, pool.CurrentDay)

	endpointChanges := map[string]map[string]EndpointChange{}
	for _, sid := range allList {
		cur, hasCur := curServices[sid]
		base, hasBase := baseServices[sid]
		eps := map[string]EndpointChange{}
		curEPs := map[string]Endpoint{}
		baseEPs := map[string]Endpoint{}
		if hasCur {
			for _, e := range cur.Endpoints {
				curEPs[e.EndpointID] = e
			}
		}
		if hasBase {
			for _, e := range base.Endpoints {
				baseEPs[e.EndpointID] = e
			}
		}
		seen := map[string]bool{}
		for id, ce := range curEPs {
			seen[id] = true
			be, ok := baseEPs[id]
			if !ok {
				eps[id] = EndpointChange{EndpointID: id, ChangeKinds: []string{ChEndpointAdded}}
				continue
			}
			ceCopy := ce
			beCopy := be
			eps[id] = diffEndpoint(&cur, &base, &ceCopy, &beCopy)
		}
		for id, be := range baseEPs {
			if seen[id] {
				continue
			}
			beCopy := be
			eps[id] = diffEndpoint(nil, &base, nil, &beCopy)
		}
		endpointChanges[sid] = eps
	}

	classifications := map[string]map[string]ResolvedClassification{}
	for _, sid := range allList {
		var svcRef Service
		if v, ok := curServices[sid]; ok {
			svcRef = v
		} else {
			svcRef = baseServices[sid]
		}
		classifications[sid] = map[string]ResolvedClassification{}
		for epID, ch := range endpointChanges[sid] {
			fbHit := accepted.ForceBreak[sid][epID]
			cls := classifyEndpoint(svcRef, ch, deps, fbHit)
			classifications[sid][epID] = cls
		}
	}

	blocked := sccBlockedSet(deps, allList)

	mergedSvc := map[string]Service{}
	for k, v := range baseServices {
		mergedSvc[k] = v
	}
	for k, v := range curServices {
		mergedSvc[k] = v
	}

	impacts := computeImpacts(allList, mergedSvc, classifications, endpointChanges, deps, accepted, blocked)

	consumerSet := map[string]bool{}
	for _, r := range deps.DirectFieldReads {
		consumerSet[r.ConsumerID] = true
	}
	consumerList := []string{}
	for c := range consumerSet {
		consumerList = append(consumerList, c)
	}
	sort.Strings(consumerList)

	consumerOut := []map[string]interface{}{}
	for _, c := range consumerList {
		entries := impacts[c]
		rows := []map[string]interface{}{}
		for _, e := range entries {
			rows = append(rows, map[string]interface{}{
				"cause_field":      e.CauseField,
				"endpoint_id":      e.EndpointID,
				"hop_distance":     e.HopDistance,
				"impact_type":      e.ImpactType,
				"producer_service": e.ProducerService,
			})
		}
		tier := mergedSvc[c].Tier
		consumerOut = append(consumerOut, map[string]interface{}{
			"consumer_id":        c,
			"impacted_endpoints": rows,
			"summary_action":     summaryActionFor(tier, entries),
			"tier":               tier,
		})
	}
	writeJSON(filepath.Join(auditDir, "consumer_impact.json"), map[string]interface{}{
		"consumers": consumerOut,
	})

	affectedConsumerCount := map[string]map[string]map[string]bool{}
	for c, entries := range impacts {
		for _, e := range entries {
			if affectedConsumerCount[e.ProducerService] == nil {
				affectedConsumerCount[e.ProducerService] = map[string]map[string]bool{}
			}
			if affectedConsumerCount[e.ProducerService][e.EndpointID] == nil {
				affectedConsumerCount[e.ProducerService][e.EndpointID] = map[string]bool{}
			}
			affectedConsumerCount[e.ProducerService][e.EndpointID][c] = true
		}
	}

	classOut := []map[string]interface{}{}
	for _, sid := range allList {
		eps := []map[string]interface{}{}
		var svcRef Service
		if v, ok := curServices[sid]; ok {
			svcRef = v
		} else {
			svcRef = baseServices[sid]
		}
		epIDs := []string{}
		for id := range endpointChanges[sid] {
			epIDs = append(epIDs, id)
		}
		sort.Strings(epIDs)
		for _, epID := range epIDs {
			ch := endpointChanges[sid][epID]
			cls := classifications[sid][epID]
			cnt := len(affectedConsumerCount[sid][epID])
			eps = append(eps, map[string]interface{}{
				"affected_consumer_count": cnt,
				"change_kinds":            ch.ChangeKinds,
				"classification":          cls.Classification,
				"endpoint_id":             epID,
				"reason":                  cls.Reason,
			})
		}
		classOut = append(classOut, map[string]interface{}{
			"endpoint_changes": eps,
			"service_id":       sid,
			"tier":             svcRef.Tier,
		})
	}
	writeJSON(filepath.Join(auditDir, "change_classification.json"), map[string]interface{}{
		"services": classOut,
	})

	producers := map[string]map[string]bool{}
	for _, r := range deps.DirectFieldReads {
		if producers[r.ConsumerID] == nil {
			producers[r.ConsumerID] = map[string]bool{}
		}
		producers[r.ConsumerID][r.ProducerID] = true
	}

	topoPhase := map[string]int{}
	var visit func(s string, stack map[string]bool) int
	visit = func(s string, stack map[string]bool) int {
		if v, ok := topoPhase[s]; ok {
			return v
		}
		if stack[s] {
			return 0
		}
		stack[s] = true
		max := -1
		for p := range producers[s] {
			pv := visit(p, stack)
			if pv > max {
				max = pv
			}
		}
		stack[s] = false
		var phase int
		if max == -1 {
			phase = 0
		} else {
			phase = max + 1
		}
		topoPhase[s] = phase
		return phase
	}
	for _, sid := range allList {
		visit(sid, map[string]bool{})
	}

	migOut := []map[string]interface{}{}
	for _, sid := range allList {
		var svcRef Service
		if v, ok := curServices[sid]; ok {
			svcRef = v
		} else {
			svcRef = baseServices[sid]
		}
		var phase int
		var origin string
		switch {
		case len(accepted.ForceBreak[sid]) > 0:
			phase = 0
			origin = "forced_phase_zero"
		case blocked[sid]:
			phase = -1
			origin = "blocked_cycle"
		case accepted.ConsumerFreeze[sid]:
			phase = topoPhase[sid] + policy.FreezeExtensionPhases
			origin = "deferred_freeze"
		default:
			phase = topoPhase[sid]
			origin = "topo"
		}
		migOut = append(migOut, map[string]interface{}{
			"phase":        phase,
			"phase_origin": origin,
			"service_id":   sid,
			"tier":         svcRef.Tier,
		})
	}
	sort.SliceStable(migOut, func(i, j int) bool {
		pi := migOut[i]["phase"].(int)
		pj := migOut[j]["phase"].(int)
		if pi != pj {
			return pi < pj
		}
		ti := tierRank(migOut[i]["tier"].(string))
		tj := tierRank(migOut[j]["tier"].(string))
		if ti != tj {
			return ti > tj
		}
		return migOut[i]["service_id"].(string) < migOut[j]["service_id"].(string)
	})
	writeJSON(filepath.Join(auditDir, "migration_plan.json"), map[string]interface{}{
		"services": migOut,
	})

	riskOut := []map[string]interface{}{}
	classCountTotal := map[string]int{
		"breaking":        0,
		"breaking_forced": 0,
		"minor":           0,
		"non_breaking":    0,
	}
	for _, sid := range allList {
		var svcRef Service
		if v, ok := curServices[sid]; ok {
			svcRef = v
		} else {
			svcRef = baseServices[sid]
		}
		var bk, mn, nb int
		for _, cls := range classifications[sid] {
			classCountTotal[cls.Classification]++
			switch cls.Classification {
			case "breaking", "breaking_forced":
				bk++
			case "minor":
				mn++
			case "non_breaking":
				nb++
			}
		}
		tier := svcRef.Tier
		score := bk*policy.TierWeights[tier] + mn
		acc := 0
		for ep := range endpointChanges[sid] {
			acc += len(affectedConsumerCount[sid][ep])
		}
		distinctConsumers := map[string]bool{}
		for c, entries := range impacts {
			for _, e := range entries {
				if e.ProducerService == sid {
					distinctConsumers[c] = true
				}
			}
		}
		var action, origin string
		switch {
		case len(accepted.ForceBreak[sid]) > 0:
			action = "block"
			origin = "forced_event"
		case bk > 0 && (tier == "gold" || tier == "silver"):
			action = "block"
			origin = "tier_rule"
		case bk > 0 && tier == "bronze":
			action = "warn"
			origin = "tier_rule"
		case mn > 0:
			action = "warn"
			origin = "tier_rule"
		default:
			action = "allow"
			origin = "tier_rule"
		}
		riskOut = append(riskOut, map[string]interface{}{
			"action":                  action,
			"action_origin":           origin,
			"affected_consumer_count": len(distinctConsumers),
			"breaking_count":          bk,
			"minor_count":             mn,
			"non_breaking_count":      nb,
			"risk_score":              score,
			"service_id":              sid,
			"tier":                    tier,
		})
	}
	writeJSON(filepath.Join(auditDir, "risk_assessment.json"), map[string]interface{}{
		"services": riskOut,
	})

	directCount := 0
	transCount := 0
	forceCount := 0
	cyclicCount := 0
	for _, entries := range impacts {
		for _, e := range entries {
			switch e.ImpactType {
			case "affected_direct":
				directCount++
			case "affected_transitive":
				transCount++
			case "force_migration_required":
				forceCount++
			case "cyclic_field_exposure":
				cyclicCount++
			}
		}
	}
	cyclicConsumers := map[string]bool{}
	for c, entries := range impacts {
		for _, e := range entries {
			if e.ImpactType == "cyclic_field_exposure" {
				cyclicConsumers[c] = true
			}
		}
	}
	consumersWithNoImpact := 0
	for _, c := range consumerList {
		if len(impacts[c]) == 0 {
			consumersWithNoImpact++
		}
	}
	endpointChangesTotal := 0
	for _, byEP := range endpointChanges {
		endpointChangesTotal += len(byEP)
	}
	blockCount := 0
	warnCount := 0
	allowCount := 0
	for _, r := range riskOut {
		switch r["action"].(string) {
		case "block":
			blockCount++
		case "warn":
			warnCount++
		case "allow":
			allowCount++
		}
	}
	blockedCount := 0
	for s := range blocked {
		_ = s
		blockedCount++
	}
	deferredCount := 0
	forcePhaseZero := 0
	for _, r := range migOut {
		switch r["phase_origin"].(string) {
		case "deferred_freeze":
			deferredCount++
		case "forced_phase_zero":
			forcePhaseZero++
		}
	}

	summary := map[string]interface{}{
		"accepted_incident_events":        accepted.AcceptedCount,
		"affected_direct_count":           directCount,
		"affected_transitive_count":       transCount,
		"allow_action_services_count":     allowCount,
		"block_action_services_count":     blockCount,
		"blocked_cycle_services_count":    blockedCount,
		"breaking_count":                  classCountTotal["breaking"],
		"breaking_forced_count":           classCountTotal["breaking_forced"],
		"consumers_total":                 len(consumerList),
		"consumers_with_no_impact":        consumersWithNoImpact,
		"cyclic_consumers_count":          len(cyclicConsumers),
		"deferred_services_count":         deferredCount,
		"endpoint_changes_total":          endpointChangesTotal,
		"force_migration_required_count":  forceCount,
		"force_phase_zero_count":          forcePhaseZero,
		"ignored_incident_events":         accepted.IgnoredCount,
		"minor_count":                     classCountTotal["minor"],
		"non_breaking_count":              classCountTotal["non_breaking"],
		"services_total":                  len(allList),
		"warn_action_services_count":      warnCount,
	}
	writeJSON(filepath.Join(auditDir, "summary.json"), summary)
}
