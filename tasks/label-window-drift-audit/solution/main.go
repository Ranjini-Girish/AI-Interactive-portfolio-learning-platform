package main

import (
  "encoding/json"
  "fmt"
  "os"
  "path/filepath"
  "sort"
)

type Policy struct { Supported []string `json:"supported_event_kinds"`; CreditDecay int `json:"credit_decay_bps_per_hop"`; FreezeHops int `json:"freeze_propagation_hops"`; TierRules map[string]TierRule `json:"tier_rules"` }
type TierRule struct { DriftWarn int `json:"drift_warn_bps"`; DriftBlock int `json:"drift_block_bps"`; ConflictBlock int `json:"conflict_block_bps"`; MinClean int `json:"min_clean_windows"`; MinScore int `json:"min_score_bps"` }
type Pool struct { CurrentDay int `json:"current_day"` }
type Dataset struct { DatasetID, Tier, Owner string; Baseline int; Parents []string }
type Window struct { WindowID, DatasetID string; DayStart, DayEnd, LabelsTotal, Positives, Conflicts, ReviewerRejects int; DependsOn []string; SourceModelID string }
type Model struct { ModelID, DatasetID string; CandidateWindows []string; Score int; DeclaredStage string }
type Event struct { EventID, Kind, TargetType, TargetID string; Day int; Accepted bool; Amount int }

type rawDataset struct { DatasetID string `json:"dataset_id"`; Tier string `json:"tier"`; Owner string `json:"owner"`; Baseline int `json:"baseline_positive_bps"`; Parents []string `json:"parents"` }
type rawWindow struct { WindowID string `json:"window_id"`; DatasetID string `json:"dataset_id"`; DayStart int `json:"day_start"`; DayEnd int `json:"day_end"`; LabelsTotal int `json:"labels_total"`; Positives int `json:"positives"`; Conflicts int `json:"conflicts"`; ReviewerRejects int `json:"reviewer_rejects"`; DependsOn []string `json:"depends_on"`; SourceModelID string `json:"source_model_id"` }
type rawModel struct { ModelID string `json:"model_id"`; DatasetID string `json:"dataset_id"`; CandidateWindows []string `json:"candidate_windows"`; Score int `json:"score_bps"`; DeclaredStage string `json:"declared_stage"` }
type rawEvent struct { EventID string `json:"event_id"`; Kind string `json:"kind"`; TargetType string `json:"target_type"`; TargetID string `json:"target_id"`; Day int `json:"day"`; Accepted bool `json:"accepted"`; Amount int `json:"amount_bps"` }
type incidentFile struct { Events []rawEvent `json:"events"` }

func mustRead(path string, v any) { b, err := os.ReadFile(path); if err != nil { panic(err) }; if err := json.Unmarshal(b, v); err != nil { panic(err) } }
func sortedKeys[M ~map[string]V, V any](m M) []string { ks:=make([]string,0,len(m)); for k:=range m { ks=append(ks,k) }; sort.Strings(ks); return ks }
func writeJSON(dir, name string, v any) { b, err := json.MarshalIndent(v, "", "  "); if err != nil { panic(err) }; b=append(b,'\n'); if err:=os.WriteFile(filepath.Join(dir,name), b, 0644); err != nil { panic(err) } }

func main() {
  data := os.Getenv("LWD_DATA_DIR"); if data=="" { data="/app/labelops" }
  out := os.Getenv("LWD_AUDIT_DIR"); if out=="" { out="/app/audit" }
  if err:=os.MkdirAll(out,0755); err!=nil { panic(err) }
  var pool Pool; mustRead(filepath.Join(data,"pool_state.json"), &pool)
  var policy Policy; mustRead(filepath.Join(data,"policy.json"), &policy)
  ds := map[string]Dataset{}; dpaths,_ := filepath.Glob(filepath.Join(data,"datasets","*.json")); for _,p := range dpaths { var r rawDataset; mustRead(p,&r); ds[r.DatasetID]=Dataset{r.DatasetID,r.Tier,r.Owner,r.Baseline,r.Parents} }
  ws := map[string]Window{}; wpaths,_ := filepath.Glob(filepath.Join(data,"windows","*.json")); for _,p := range wpaths { var r rawWindow; mustRead(p,&r); ws[r.WindowID]=Window{r.WindowID,r.DatasetID,r.DayStart,r.DayEnd,r.LabelsTotal,r.Positives,r.Conflicts,r.ReviewerRejects,r.DependsOn,r.SourceModelID} }
  ms := map[string]Model{}; mpaths,_ := filepath.Glob(filepath.Join(data,"models","*.json")); for _,p := range mpaths { var r rawModel; mustRead(p,&r); ms[r.ModelID]=Model{r.ModelID,r.DatasetID,r.CandidateWindows,r.Score,r.DeclaredStage} }
  var inf incidentFile; mustRead(filepath.Join(data,"incidents.json"), &inf)
  supported:=map[string]bool{}; for _,k:=range policy.Supported { supported[k]=true }
  targetExists := func(e rawEvent) bool { if e.TargetType=="dataset" { _,ok:=ds[e.TargetID]; return ok }; if e.TargetType=="window" { _,ok:=ws[e.TargetID]; return ok }; if e.TargetType=="model" { _,ok:=ms[e.TargetID]; return ok }; return false }
  type traceRow struct { EventID string `json:"event_id"`; Kind string `json:"kind"`; TargetID string `json:"target_id"`; TargetType string `json:"target_type"`; Decision string `json:"decision"`; Reason string `json:"reason"` }
  trace:=[]traceRow{}; groups:=map[string][]rawEvent{}; accepted:=[]rawEvent{}
  for _,e:=range inf.Events { reason:="accepted"; if !supported[e.Kind] { reason="unsupported_kind" } else if e.Day>pool.CurrentDay { reason="future_event" } else if !e.Accepted { reason="rejected_event" } else if !targetExists(e) { reason="missing_target" }; if reason=="accepted" { key:=e.Kind+"\x00"+e.TargetType+"\x00"+e.TargetID; groups[key]=append(groups[key],e) } else { trace=append(trace, traceRow{e.EventID,e.Kind,e.TargetID,e.TargetType,"ignored",reason}) } }
  for _,rows:=range groups { sort.Slice(rows, func(i,j int) bool { if rows[i].Day!=rows[j].Day { return rows[i].Day>rows[j].Day }; return rows[i].EventID<rows[j].EventID }); keep:=rows[0]; accepted=append(accepted,keep); trace=append(trace, traceRow{keep.EventID,keep.Kind,keep.TargetID,keep.TargetType,"accepted","accepted"}); for _,e:=range rows[1:] { trace=append(trace, traceRow{e.EventID,e.Kind,e.TargetID,e.TargetType,"ignored","superseded_event"}) } }
  sort.Slice(trace, func(i,j int) bool { return trace[i].EventID<trace[j].EventID })
  parents:=map[string][]string{}; children:=map[string][]string{}; for k,d:=range ds { parents[k]=d.Parents; children[k]=[]string{} }; for k,ps:=range parents { for _,p:=range ps { if _,ok:=children[p]; ok { children[p]=append(children[p],k) } } }; for k:=range children { sort.Strings(children[k]) }
  type lineageRow struct { DatasetID string `json:"dataset_id"`; Tier string `json:"tier"`; Owner string `json:"owner"`; LineageStatus string `json:"lineage_status"`; ParentDepth int `json:"parent_depth"`; CompromiseSources []string `json:"compromise_sources"` }
  lineage:=map[string]lineageRow{}
  var walk func(string, map[string]bool) (int,bool,bool)
  walk = func(x string, stack map[string]bool) (int,bool,bool) { if stack[x] { return -1,true,false }; ns:=map[string]bool{}; for k,v:=range stack { ns[k]=v }; ns[x]=true; maxd:=0; missing:=false; for _,p:=range parents[x] { if _,ok:=ds[p]; !ok { missing=true; continue }; dep,cy,mis:=walk(p,ns); if cy { return -1,true,false }; if mis { missing=true }; if dep+1>maxd { maxd=dep+1 } }; return maxd,false,missing }
  for _,k:=range sortedKeys(ds) { d:=ds[k]; dep,cy,mis:=walk(k,map[string]bool{}); st:="clean"; if cy { st="cyclic"; dep=-1 } else if mis { st="missing_parent"; dep=-1 }; lineage[k]=lineageRow{k,d.Tier,d.Owner,st,dep,[]string{}} }
  seed:=map[string]string{}; for _,e:=range accepted { if e.Kind=="label_source_compromise" { seed[e.TargetID]=e.EventID } }
  comp:=map[string]bool{}; q:=[]string{}; for k:=range seed { comp[k]=true; q=append(q,k) }; sort.Strings(q); for len(q)>0 { x:=q[0]; q=q[1:]; for _,c:=range children[x] { if !comp[c] { comp[c]=true; q=append(q,c) } } }
  var collectSrc func(string, map[string]bool) []string
  collectSrc = func(x string, seen map[string]bool) []string { if seen[x] { return nil }; seen[x]=true; out:=[]string{}; if ev,ok:=seed[x]; ok { out=append(out,ev) }; for _,p:=range parents[x] { if _,ok:=ds[p]; ok { out=append(out, collectSrc(p,seen)...)} }; sort.Strings(out); r:=[]string{}; last:=""; for _,v:=range out { if v!=last { r=append(r,v); last=v } }; return r }
  for k:=range comp { row:=lineage[k]; if row.LineageStatus=="clean" { row.LineageStatus="compromised" }; row.CompromiseSources=collectSrc(k,map[string]bool{}); lineage[k]=row }
  childw:=map[string][]string{}; for k:=range ws { childw[k]=[]string{} }; for k,w:=range ws { for _,p:=range w.DependsOn { if _,ok:=childw[p]; ok { childw[p]=append(childw[p],k) } } }; for k:=range childw { sort.Strings(childw[k]) }
  cycleNodes:=map[string]bool{}; done:=map[string]bool{}; var visit func(string, []string); visit=func(n string, stack []string) { for i,x:=range stack { if x==n { for _,v:=range stack[i:] { cycleNodes[v]=true }; return } }; if done[n] { return }; for _,p:=range ws[n].DependsOn { if _,ok:=ws[p]; ok { visit(p, append(stack,n)) } }; done[n]=true }; for _,k:=range sortedKeys(ws) { visit(k, []string{}) }
  credits:=map[string]int{}; creditEvent:=map[string]string{}; freezes:=map[string][2]string{}
  for _,e:=range accepted { if e.Kind=="relabel_credit" { type item struct{ id string; hop int }; qq:=[]item{{e.TargetID,0}}; seen:=map[string]bool{}; for len(qq)>0 { it:=qq[0]; qq=qq[1:]; if seen[it.id] { continue }; seen[it.id]=true; val:=e.Amount - it.hop*policy.CreditDecay; if val>0 { old,ok:=credits[it.id]; if !ok || val>old || (val==old && e.EventID<creditEvent[it.id]) { credits[it.id]=val; creditEvent[it.id]=e.EventID }; for _,c:=range childw[it.id] { qq=append(qq,item{c,it.hop+1}) } } } }; if e.Kind=="window_freeze" { type item struct{ id string; hop int }; qq:=[]item{{e.TargetID,0}}; seen:=map[string]bool{}; for len(qq)>0 { it:=qq[0]; qq=qq[1:]; if seen[it.id] { continue }; seen[it.id]=true; if it.hop<=policy.FreezeHops { freezes[it.id]=[2]string{fmt.Sprint(it.hop),e.EventID}; for _,c:=range childw[it.id] { qq=append(qq,item{c,it.hop+1}) } } } } }
  type winRow struct { WindowID string `json:"window_id"`; DatasetID string `json:"dataset_id"`; Tier string `json:"tier"`; ObservedPositiveBps int `json:"observed_positive_bps"`; RawDriftBps int `json:"raw_drift_bps"`; EffectiveCreditBps int `json:"effective_credit_bps"`; CreditEventID *string `json:"credit_event_id"`; AdjustedDriftBps int `json:"adjusted_drift_bps"`; ConflictBps int `json:"conflict_bps"`; Status string `json:"status"`; Reasons []string `json:"reasons"` }
  windowRows:=[]winRow{}; statusByWindow:=map[string]string{}
  for _,k:=range sortedKeys(ws) { w:=ws[k]; d:=ds[w.DatasetID]; tier:=policy.TierRules[d.Tier]; obs:=w.Positives*10000/w.LabelsTotal; raw:=obs-d.Baseline; if raw<0 { raw=-raw }; cred:=credits[k]; adj:=raw-cred; if adj<0 { adj=0 }; conf:=(w.Conflicts+w.ReviewerRejects)*10000/w.LabelsTotal; lstat:=lineage[w.DatasetID].LineageStatus; status:="clean"; reasons:=[]string{}; if lstat=="cyclic" || lstat=="missing_parent" { status="invalid_lineage"; reasons=append(reasons,lstat) } else if lstat=="compromised" { status="compromised"; reasons=append(reasons,"dataset_compromise") } else if cycleNodes[k] { status="invalid_dependency"; reasons=append(reasons,"dependency_cycle") } else if fr,ok:=freezes[k]; ok && fr[0]=="0" { status="frozen"; reasons=append(reasons,fr[1]) } else if fr,ok:=freezes[k]; ok { status="frozen_dependency"; reasons=append(reasons,fr[1]) } else if adj>=tier.DriftBlock || conf>=tier.ConflictBlock { status="drift_blocked"; reasons=append(reasons,"drift_or_conflict_limit") } else if adj>=tier.DriftWarn { status="drift_warning"; reasons=append(reasons,"drift_warning") } else { reasons=append(reasons,"within_limits") }; var cep *string; if ev,ok:=creditEvent[k]; ok { s:=ev; cep=&s }; row:=winRow{k,w.DatasetID,d.Tier,obs,raw,cred,cep,adj,conf,status,reasons}; windowRows=append(windowRows,row); statusByWindow[k]=status }
  countWin:=map[string]int{}; for _,r:=range windowRows { countWin[r.Status]++ }
  datasetRows:=[]lineageRow{}; for _,k:=range sortedKeys(lineage) { datasetRows=append(datasetRows,lineage[k]) }
  countDS:=map[string]int{}; compromised:=[]string{}; for _,r:=range datasetRows { countDS[r.LineageStatus]++; if r.LineageStatus=="compromised" { compromised=append(compromised,r.DatasetID) } }
  hold:=map[string]string{}; for _,e:=range accepted { if e.Kind=="model_hold" { hold[e.TargetID]=e.EventID } }
  type modelRow struct { ModelID string `json:"model_id"`; DatasetID string `json:"dataset_id"`; DeclaredStage string `json:"declared_stage"`; ScoreBps int `json:"score_bps"`; EligibleWindows []string `json:"eligible_windows"`; EligibleWindowCount int `json:"eligible_window_count"`; Status string `json:"status"`; Reasons []string `json:"reasons"` }
  modelRows:=[]modelRow{}; countModel:=map[string]int{}
  for _,mid:=range sortedKeys(ms) { m:=ms[mid]; lstat:=lineage[m.DatasetID].LineageStatus; tier:=policy.TierRules[ds[m.DatasetID].Tier]; elig:=[]string{}; for _,w:=range m.CandidateWindows { if statusByWindow[w]=="clean" || statusByWindow[w]=="drift_warning" { elig=append(elig,w) } }; status:=""; reasons:=[]string{}; if lstat=="cyclic" || lstat=="missing_parent" { status="quarantine_lineage"; reasons=append(reasons,lstat) } else if lstat=="compromised" { status="quarantine_compromise"; reasons=append(reasons,"dataset_compromise") } else if ev,ok:=hold[mid]; ok { status="hold"; reasons=append(reasons,ev) } else if len(elig)>=tier.MinClean && m.Score>=tier.MinScore { status="promote"; reasons=append(reasons,"meets_requirements") } else if len(elig)<tier.MinClean { status="insufficient_windows"; reasons=append(reasons,"not_enough_clean_windows") } else { status="below_score"; reasons=append(reasons,"score_below_minimum") }; countModel[status]++; modelRows=append(modelRows, modelRow{mid,m.DatasetID,m.DeclaredStage,m.Score,elig,len(elig),status,reasons}) }
  acceptedCount:=0; ignoredCount:=0; for _,r:=range trace { if r.Decision=="accepted" { acceptedCount++ } else { ignoredCount++ } }
  blocked:=0; for _,r:=range windowRows { if r.Status!="clean" && r.Status!="drift_warning" { blocked++ } }
  writeJSON(out,"window_drift.json", map[string]any{"windows":windowRows,"status_counts":countWin})
  writeJSON(out,"dataset_lineage.json", map[string]any{"datasets":datasetRows,"compromised_datasets":compromised,"lineage_status_counts":countDS})
  writeJSON(out,"model_readiness.json", map[string]any{"models":modelRows,"readiness_counts":countModel})
  writeJSON(out,"incident_trace.json", map[string]any{"events":trace,"accepted_event_count":acceptedCount,"ignored_event_count":ignoredCount})
  writeJSON(out,"summary.json", map[string]any{"current_day":pool.CurrentDay,"total_windows":len(windowRows),"blocked_window_count":blocked,"dataset_status_counts":countDS,"model_status_counts":countModel,"ignored_incident_events":ignoredCount})
}
