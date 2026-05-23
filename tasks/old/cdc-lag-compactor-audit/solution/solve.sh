#!/bin/bash
set -euo pipefail

DATA_DIR="${CDC_DATA_DIR:-/app/cdc}"
OUT_DIR="${CDC_AUDIT_DIR:-/app/audit}"
BIN_PATH="${CDC_BIN_PATH:-/app/bin/cdc-audit}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
export PATH="/usr/local/cargo/bin:$PATH"

cat > "$TMP_DIR/cdc_audit.rs" <<'RUST'
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet, VecDeque};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone)]
struct Policy { min_lag:i64, max_lag:i64, retention:i64, merge_gap:i64, tomb_cap:i64, risk_weight:i64 }
#[derive(Clone)]
struct Stream { tier:String, upstreams:Vec<String> }
#[derive(Clone)]
struct Partition { last_source:i64, last_sink:i64, event_day:i64 }
#[derive(Clone)]
struct Segment { id:String, low:i64, high:i64, bytes:i64, tombstones:i64, family:String, max_event_day:i64 }
#[derive(Clone)]
struct Event { event_id:String, kind:String, stream:String, partition:String, day:i64, value_a:String }
#[derive(Clone)]
struct PartRow { stream:String, partition:String, effective_sink:i64, event_lag:i64, raw_lag:i64, reasons:Vec<String>, status:String }
#[derive(Clone)]
struct GroupRow { stream:String, partition:String, action:String, bytes:i64, high:i64, low:i64, reason:String, segs:Vec<String> }
#[derive(Clone)]
struct RiskRow { stream:String, status:String, risk_score:i64, reasons:Vec<String>, upstream_q:i64 }

fn read_rows(path:&Path)->Vec<Vec<String>>{
    fs::read_to_string(path).unwrap().lines()
        .map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#'))
        .map(|l| l.split('|').map(|s| s.to_string()).collect()).collect()
}
fn esc(s:&str)->String{ let mut out=String::from("\""); for c in s.chars(){ match c{ '"' => out.push_str("\\\""), '\\' => out.push_str("\\\\"), '\n' => out.push_str("\\n"), _ => out.push(c)} } out.push('"'); out }
fn arr_str(v:&Vec<String>)->String{ format!("[{}]", v.iter().map(|s| esc(s)).collect::<Vec<_>>().join(", ")) }
fn counts_json(m:&BTreeMap<String,i64>)->String{ format!("{{{}}}", m.iter().map(|(k,v)| format!("{}: {}", esc(k), v)).collect::<Vec<_>>().join(", ")) }
fn write_json(path:&Path, body:String){ fs::write(path, format!("{}\n", body)).unwrap(); }
fn event_winner(events:Vec<&Event>)->Option<Event>{ let mut items:Vec<Event>=events.into_iter().cloned().collect(); items.sort_by(|a,b| b.day.cmp(&a.day).then(a.event_id.cmp(&b.event_id))); items.into_iter().next() }

fn main(){
    let data=PathBuf::from(env::var("CDC_DATA_DIR").unwrap_or_else(|_| "/app/cdc".to_string()));
    let out=PathBuf::from(env::var("CDC_AUDIT_DIR").unwrap_or_else(|_| "/app/audit".to_string()));
    fs::create_dir_all(&out).unwrap();
    let current_day:i64=read_rows(&data.join("pool_state.tsv"))[0][1].parse().unwrap();
    let mut policy:HashMap<String,Policy>=HashMap::new();
    for r in read_rows(&data.join("policy.tsv")){
        policy.insert(r[0].clone(), Policy{min_lag:r[1].parse().unwrap(),max_lag:r[2].parse().unwrap(),retention:r[3].parse().unwrap(),merge_gap:r[4].parse().unwrap(),tomb_cap:r[5].parse().unwrap(),risk_weight:r[6].parse().unwrap()});
    }
    let mut streams:HashMap<String,Stream>=HashMap::new();
    for r in read_rows(&data.join("streams.tsv")){
        let ups=if r[2]=="-" { vec![] } else { r[2].split(',').map(|s|s.to_string()).collect() };
        streams.insert(r[0].clone(), Stream{tier:r[1].clone(), upstreams:ups});
    }
    let mut parts:HashMap<(String,String),Partition>=HashMap::new();
    for ent in fs::read_dir(data.join("partitions")).unwrap(){
        let path=ent.unwrap().path(); let stream=path.file_stem().unwrap().to_string_lossy().to_string();
        for r in read_rows(&path){ parts.insert((stream.clone(),r[0].clone()), Partition{last_source:r[1].parse().unwrap(),last_sink:r[2].parse().unwrap(),event_day:r[3].parse().unwrap()}); }
    }
    let mut segments:HashMap<(String,String),Vec<Segment>>=HashMap::new();
    for ent in fs::read_dir(data.join("segments")).unwrap(){
        let path=ent.unwrap().path(); let stem=path.file_stem().unwrap().to_string_lossy().to_string();
        let idx=stem.rfind('-').unwrap(); let stream=stem[..idx].to_string(); let part=stem[idx+1..].to_string();
        let mut list=Vec::new();
        for r in read_rows(&path){ list.push(Segment{id:r[0].clone(),low:r[1].parse().unwrap(),high:r[2].parse().unwrap(),bytes:r[3].parse().unwrap(),tombstones:r[4].parse().unwrap(),family:r[5].clone(),max_event_day:r[6].parse().unwrap()}); }
        list.sort_by(|a,b| a.low.cmp(&b.low).then(a.id.cmp(&b.id)));
        segments.insert((stream,part),list);
    }
    let supported:HashSet<&str>=["late_arrival_grace","partition_rewind","compaction_hold","stream_compromise","force_replay","source_pause"].into_iter().collect();
    let concrete:HashSet<&str>=["partition_rewind","compaction_hold","force_replay","source_pause"].into_iter().collect();
    let mut events=Vec::new(); let mut ignored=0i64;
    for r in read_rows(&data.join("incidents.tsv")){
        let day:i64=r[4].parse().unwrap(); let kind=r[1].clone(); let stream=r[2].clone(); let part=r[3].clone();
        let mut valid=r[5]=="true" && day<=current_day && supported.contains(kind.as_str()) && streams.contains_key(&stream);
        if valid && part!="*" && !parts.contains_key(&(stream.clone(),part.clone())){ valid=false; }
        if valid && concrete.contains(kind.as_str()) && part=="*"{ valid=false; }
        if valid { events.push(Event{event_id:r[0].clone(),kind,stream,partition:part,day,value_a:r[6].clone()}); } else { ignored+=1; }
    }
    let mut children:HashMap<String,Vec<String>>=HashMap::new();
    for (s,meta) in &streams{ for u in &meta.upstreams{ children.entry(u.clone()).or_default().push(s.clone()); } }
    let mut direct_q:BTreeSet<String>=BTreeSet::new();
    for e in events.iter().filter(|e| e.kind=="stream_compromise"){ direct_q.insert(e.stream.clone()); }
    let mut quarantined:BTreeSet<String>=direct_q.clone(); let mut inherited:HashMap<String,BTreeSet<String>>=HashMap::new();
    let mut q:VecDeque<(String,String)>=direct_q.iter().map(|s|(s.clone(),s.clone())).collect();
    while let Some((source,stream))=q.pop_front(){ if let Some(kids)=children.get(&stream){ let mut sorted=kids.clone(); sorted.sort(); for child in sorted{ inherited.entry(child.clone()).or_default().insert(source.clone()); if !quarantined.contains(&child){ quarantined.insert(child.clone()); q.push_back((source.clone(),child)); } } } }
    let mut grace:HashMap<String,i64>=HashMap::new();
    let stream_names:Vec<String>=streams.keys().cloned().collect();
    for s in &stream_names{ if let Some(e)=event_winner(events.iter().filter(|e| e.kind=="late_arrival_grace" && e.stream==*s).collect()){ grace.insert(s.clone(), e.value_a.parse().unwrap()); } }
    let mut rewinds:HashMap<(String,String),i64>=HashMap::new(); let mut force:HashSet<(String,String)>=HashSet::new(); let mut pauses:HashSet<(String,String)>=HashSet::new(); let mut holds:HashSet<(String,String)>=HashSet::new();
    let part_keys:Vec<(String,String)>=parts.keys().cloned().collect();
    for (s,p) in &part_keys{
        if let Some(e)=event_winner(events.iter().filter(|e| e.kind=="partition_rewind" && e.stream==*s && e.partition==*p).collect()){ rewinds.insert((s.clone(),p.clone()),e.value_a.parse().unwrap()); }
        if event_winner(events.iter().filter(|e| e.kind=="force_replay" && e.stream==*s && e.partition==*p).collect()).is_some(){ force.insert((s.clone(),p.clone())); }
        if let Some(e)=event_winner(events.iter().filter(|e| e.kind=="source_pause" && e.stream==*s && e.partition==*p).collect()){ let dur:i64=e.value_a.parse().unwrap(); if e.day<=current_day && current_day<=e.day+dur-1{ pauses.insert((s.clone(),p.clone())); } }
        if let Some(e)=event_winner(events.iter().filter(|e| e.kind=="compaction_hold" && e.stream==*s && e.partition==*p).collect()){ let dur:i64=e.value_a.parse().unwrap(); if e.day<=current_day && current_day<=e.day+dur-1{ holds.insert((s.clone(),p.clone())); } }
    }
    let mut part_rows=Vec::new(); let mut by_stream:HashMap<String,Vec<String>>=HashMap::new();
    let mut sorted_parts=part_keys.clone(); sorted_parts.sort();
    for (s,p) in sorted_parts{
        let part=parts.get(&(s.clone(),p.clone())).unwrap(); let pol=policy.get(&streams.get(&s).unwrap().tier).unwrap();
        let eff=std::cmp::min(part.last_sink,*rewinds.get(&(s.clone(),p.clone())).unwrap_or(&part.last_sink));
        let raw=std::cmp::max(0,part.last_source-eff); let evlag=std::cmp::max(0,current_day-part.event_day-*grace.get(&s).unwrap_or(&0));
        let (status,reason)=if quarantined.contains(&s){("quarantined","stream_quarantine")} else if force.contains(&(s.clone(),p.clone())) || rewinds.contains_key(&(s.clone(),p.clone())){("replay_required", if force.contains(&(s.clone(),p.clone())){"force_replay"}else{"rewind"})} else if pauses.contains(&(s.clone(),p.clone())){("paused","source_pause")} else if raw>pol.max_lag || evlag>pol.retention{("stale","lag_threshold")} else if raw>pol.min_lag || evlag>0{("lagging","within_recovery")} else {("caught_up","within_floor")};
        by_stream.entry(s.clone()).or_default().push(status.to_string());
        part_rows.push(PartRow{stream:s,partition:p,effective_sink:eff,event_lag:evlag,raw_lag:raw,reasons:vec![reason.to_string()],status:status.to_string()});
    }
    let mut stream_status:HashMap<String,String>=HashMap::new();
    let mut names:Vec<String>=streams.keys().cloned().collect(); names.sort();
    for s in &names{ let statuses=by_stream.get(s).unwrap(); let st=if quarantined.contains(s){"quarantined"} else if statuses.iter().any(|x| x=="replay_required"||x=="stale"){"replay_required"} else if statuses.iter().any(|x| x=="lagging"||x=="paused"){"degraded"} else {"healthy"}; stream_status.insert(s.clone(),st.to_string()); }
    let mut changed=true; while changed{ changed=false; for s in &names{ let cur=stream_status.get(s).unwrap().clone(); if cur=="quarantined"||cur=="replay_required"{continue;} let meta=streams.get(s).unwrap(); if meta.upstreams.iter().any(|u| { let us=stream_status.get(u).unwrap(); us=="quarantined"||us=="replay_required" }) && cur!="degraded"{ stream_status.insert(s.clone(),"degraded".to_string()); changed=true; } } }
    let mut groups=Vec::new();
    for (s,p) in part_keys.iter().cloned().collect::<BTreeSet<_>>(){
        let pol=policy.get(&streams.get(&s).unwrap().tier).unwrap(); let segs=segments.get(&(s.clone(),p.clone())).unwrap().clone();
        if quarantined.contains(&s) || holds.contains(&(s.clone(),p.clone())){
            let action=if quarantined.contains(&s){"hold_quarantine"}else{"hold_incident"}; let reason=if quarantined.contains(&s){"stream_quarantine"}else{"active_hold"};
            for seg in segs{ groups.push(group(&s,&p,&vec![seg],action,reason)); }
            continue;
        }
        let mut cur:Vec<Segment>=Vec::new();
        for seg in segs{
            if cur.is_empty(){ cur.push(seg); continue; }
            let mut cand=cur.clone(); cand.push(seg.clone()); let gap=seg.low-cur.last().unwrap().high; let same=seg.family==cur.last().unwrap().family; let tomb:i64=cand.iter().map(|x|x.tombstones).sum(); let bytes:i64=cand.iter().map(|x|x.bytes).sum();
            if same && gap<=pol.merge_gap && tomb*100<=bytes*pol.tomb_cap{ cur.push(seg); } else { groups.push(decide(&s,&p,&cur,current_day,pol)); cur=vec![seg]; }
        }
        if !cur.is_empty(){ groups.push(decide(&s,&p,&cur,current_day,pol)); }
    }
    let mut risks=Vec::new();
    for s in &names{
        let pol=policy.get(&streams.get(s).unwrap().tier).unwrap(); let lag:i64=part_rows.iter().filter(|r| r.stream==*s).map(|r|r.raw_lag).sum(); let upstream_q=streams.get(s).unwrap().upstreams.iter().filter(|u| quarantined.contains(*u)).count() as i64;
        let mut score=(lag*pol.risk_weight)/10; let st=stream_status.get(s).unwrap(); let mut reasons=Vec::new();
        if st=="quarantined"{ score+=if direct_q.contains(s){100}else{80}; reasons.push("quarantine".to_string()); }
        if st=="replay_required"{ score+=25; reasons.push("replay".to_string()); }
        if st=="degraded"{ score+=10; reasons.push("degraded".to_string()); }
        if upstream_q>0{ score+=15*upstream_q; reasons.push("upstream_quarantine".to_string()); }
        if reasons.is_empty(){ reasons.push("nominal".to_string()); }
        risks.push(RiskRow{stream:s.clone(),status:st.clone(),risk_score:score,reasons,upstream_q});
    }
    risks.sort_by(|a,b| b.risk_score.cmp(&a.risk_score).then(a.stream.cmp(&b.stream)));
    write_json(&out.join("partition_lag.json"), format!("{{\n  \"partitions\": [{}]\n}}", part_rows.iter().map(part_json).collect::<Vec<_>>().join(", ")));
    write_json(&out.join("compaction_plan.json"), format!("{{\n  \"groups\": [{}]\n}}", groups.iter().map(group_json).collect::<Vec<_>>().join(", ")));
    write_json(&out.join("replay_risk.json"), format!("{{\n  \"streams\": [{}]\n}}", risks.iter().map(risk_json).collect::<Vec<_>>().join(", ")));
    let qrows=names.iter().map(|s|{ let status=if direct_q.contains(s){"direct"}else if quarantined.contains(s){"inherited"}else{"none"}; let from=inherited.get(s).map(|x|x.iter().cloned().collect()).unwrap_or_else(Vec::new); format!("{{\"inherited_from\": {}, \"quarantine_status\": {}, \"stream\": {}}}", arr_str(&from), esc(status), esc(s)) }).collect::<Vec<_>>().join(", ");
    write_json(&out.join("quarantine_graph.json"), format!("{{\n  \"streams\": [{}]\n}}", qrows));
    let mut sc=BTreeMap::new(); for v in stream_status.values(){*sc.entry(v.clone()).or_insert(0)+=1;}
    let mut pc=BTreeMap::new(); for r in &part_rows{*pc.entry(r.status.clone()).or_insert(0)+=1;}
    let mut gc=BTreeMap::new(); for g in &groups{*gc.entry(g.action.clone()).or_insert(0)+=1;}
    let total:i64=risks.iter().map(|r|r.risk_score).sum();
    let summary=format!("{{\n  \"compaction_action_counts\": {},\n  \"ignored_incident_events\": {},\n  \"partition_status_counts\": {},\n  \"stream_status_counts\": {},\n  \"total_replay_risk\": {}\n}}", counts_json(&gc), ignored, counts_json(&pc), counts_json(&sc), total);
    write_json(&out.join("summary.json"), summary);
}
fn group(s:&str,p:&str,segs:&Vec<Segment>,action:&str,reason:&str)->GroupRow{ GroupRow{stream:s.to_string(),partition:p.to_string(),action:action.to_string(),bytes:segs.iter().map(|x|x.bytes).sum(),high:segs.iter().map(|x|x.high).max().unwrap(),low:segs.iter().map(|x|x.low).min().unwrap(),reason:reason.to_string(),segs:segs.iter().map(|x|x.id.clone()).collect()} }
fn decide(s:&str,p:&str,segs:&Vec<Segment>,day:i64,pol:&Policy)->GroupRow{ if segs.len()>=2{group(s,p,segs,"merge","adjacent_eligible")} else if segs[0].max_event_day<=day-pol.retention{group(s,p,segs,"evict","retention_expired")} else {group(s,p,segs,"keep","not_mergeable")} }
fn part_json(r:&PartRow)->String{ format!("{{\"effective_sink_lsn\": {}, \"event_lag_days\": {}, \"partition\": {}, \"raw_lag\": {}, \"reasons\": {}, \"status\": {}, \"stream\": {}}}", r.effective_sink,r.event_lag,esc(&r.partition),r.raw_lag,arr_str(&r.reasons),esc(&r.status),esc(&r.stream)) }
fn group_json(g:&GroupRow)->String{ format!("{{\"action\": {}, \"bytes\": {}, \"output_high_lsn\": {}, \"output_low_lsn\": {}, \"partition\": {}, \"reason\": {}, \"segment_ids\": {}, \"stream\": {}}}", esc(&g.action),g.bytes,g.high,g.low,esc(&g.partition),esc(&g.reason),arr_str(&g.segs),esc(&g.stream)) }
fn risk_json(r:&RiskRow)->String{ format!("{{\"reasons\": {}, \"risk_score\": {}, \"status\": {}, \"stream\": {}, \"upstream_quarantine_count\": {}}}", arr_str(&r.reasons),r.risk_score,esc(&r.status),esc(&r.stream),r.upstream_q) }
RUST

mkdir -p "$(dirname "$BIN_PATH")"
rustc --edition=2021 "$TMP_DIR/cdc_audit.rs" -O -o "$BIN_PATH"
"$BIN_PATH"
