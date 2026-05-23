#!/bin/bash
set -euo pipefail

mkdir -p /app/plan /app/planner/src

cat > /app/planner/Cargo.toml <<'CARGO_END'
[package]
name = "planner"
version = "0.1.0"
edition = "2021"

[dependencies]
serde_json = "1"

[[bin]]
name = "planner"
path = "src/main.rs"

[profile.release]
opt-level = 1
codegen-units = 16
CARGO_END

cat > /app/planner/src/main.rs <<'RUST_END'
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

type Semver = (u32, u32, u32);

fn severity_rank(s: &str) -> i32 {
    match s {
        "low" => 0,
        "medium" => 1,
        "high" => 2,
        "critical" => 3,
        other => panic!("unknown severity: {other}"),
    }
}

fn parse_semver(s: &str) -> Semver {
    let parts: Vec<u32> = s.split('.').map(|p| p.parse::<u32>().unwrap()).collect();
    assert_eq!(parts.len(), 3, "bad semver: {s}");
    (parts[0], parts[1], parts[2])
}

fn parse_range(r: &str) -> (Semver, Semver) {
    let r = r.trim();
    if let Some(rest) = r.strip_prefix('=') {
        let v = parse_semver(rest.trim());
        return (v, (v.0, v.1, v.2 + 1));
    }
    if let Some(rest) = r.strip_prefix('^') {
        let parts: Vec<u32> = rest
            .trim()
            .split('.')
            .map(|p| p.parse::<u32>().unwrap())
            .collect();
        assert_eq!(parts.len(), 2, "bad ^range: {r}");
        let (x, y) = (parts[0], parts[1]);
        let lo = (x, y, 0);
        let hi = if x >= 1 { (x + 1, 0, 0) } else { (0, y + 1, 0) };
        return (lo, hi);
    }
    if let Some(rest) = r.strip_prefix('~') {
        let parts: Vec<u32> = rest
            .trim()
            .split('.')
            .map(|p| p.parse::<u32>().unwrap())
            .collect();
        assert_eq!(parts.len(), 2, "bad ~range: {r}");
        let (x, y) = (parts[0], parts[1]);
        return ((x, y, 0), (x, y + 1, 0));
    }
    let cleaned: String = r.chars().filter(|c| !c.is_whitespace()).collect();
    let mut parts = cleaned.split(',');
    let lo_part = parts.next().expect("range lo").strip_prefix(">=").expect(">= prefix");
    let hi_part = parts.next().expect("range hi").strip_prefix('<').expect("< prefix");
    (parse_semver(lo_part), parse_semver(hi_part))
}

fn in_range(v: Semver, rng: (Semver, Semver)) -> bool {
    v >= rng.0 && v < rng.1
}

fn read_json(path: &Path) -> Value {
    let s = fs::read_to_string(path).unwrap_or_else(|e| panic!("read {}: {}", path.display(), e));
    serde_json::from_str(&s).unwrap_or_else(|e| panic!("parse {}: {}", path.display(), e))
}

fn write_json(path: &Path, v: &Value) {
    let mut s = serde_json::to_string_pretty(v).unwrap();
    s.push('\n');
    fs::write(path, s).unwrap();
}

fn as_str(v: &Value) -> &str {
    v.as_str().unwrap()
}

fn as_bool(v: &Value) -> bool {
    v.as_bool().unwrap()
}

fn as_i64(v: &Value) -> i64 {
    v.as_i64().unwrap()
}

#[derive(Clone, Debug)]
struct VersionInfo {
    ver: Semver,
    ver_str: String,
    msrv: Semver,
    features: BTreeSet<String>,
    default_features: BTreeSet<String>,
    yanked: bool,
}

#[derive(Clone, Debug)]
struct Advisory {
    advisory_id: String,
    crate_name: String,
    severity: String,
    sev_rank: i32,
    range: (Semver, Semver),
    day_published: i64,
}

#[derive(Clone, Debug)]
struct DepDecl {
    workspace: bool,
    version_range: Option<String>,
    features: Vec<String>,
    default_features: bool,
    required_features: Vec<String>,
}

#[derive(Clone, Debug)]
struct Member {
    member_msrv: String,
    deps: BTreeMap<String, DepDecl>,
}

#[derive(Clone, Debug)]
struct CrateDoc {
    versions: Vec<VersionInfo>,
}

#[derive(Clone, Debug)]
struct Event {
    event_id: String,
    day: i64,
    kind: String,
    crate_name: Option<String>,
    member: Option<String>,
    pinned_version: Option<String>,
    advisory_id: Option<String>,
}

fn collect_versions(reg: &Value) -> Vec<VersionInfo> {
    let mut out: Vec<VersionInfo> = reg["versions"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| VersionInfo {
            ver: parse_semver(as_str(&v["version"])),
            ver_str: as_str(&v["version"]).to_string(),
            msrv: parse_semver(as_str(&v["msrv"])),
            features: v["features"]
                .as_array()
                .unwrap()
                .iter()
                .map(|x| as_str(x).to_string())
                .collect(),
            default_features: v["default_features"]
                .as_array()
                .unwrap()
                .iter()
                .map(|x| as_str(x).to_string())
                .collect(),
            yanked: as_bool(&v["yanked"]),
        })
        .collect();
    out.sort_by_key(|x| x.ver);
    out
}

fn parse_event(v: &Value) -> Event {
    Event {
        event_id: v["event_id"].as_str().unwrap_or("").to_string(),
        day: v["day"].as_i64().unwrap_or(i64::MIN),
        kind: v["kind"].as_str().unwrap_or("").to_string(),
        crate_name: v.get("crate").and_then(|x| x.as_str()).map(String::from),
        member: v.get("member").and_then(|x| x.as_str()).map(String::from),
        pinned_version: v
            .get("pinned_version")
            .and_then(|x| x.as_str())
            .map(String::from),
        advisory_id: v.get("advisory_id").and_then(|x| x.as_str()).map(String::from),
    }
}

fn event_scope(e: &Event) -> String {
    match e.kind.as_str() {
        "force_freeze" => format!("force_freeze\x1f{}", e.crate_name.as_deref().unwrap_or("")),
        "forced_bump" => format!(
            "forced_bump\x1f{}\x1f{}",
            e.crate_name.as_deref().unwrap_or(""),
            e.member.as_deref().unwrap_or("")
        ),
        "advisory_override" => format!(
            "advisory_override\x1f{}",
            e.advisory_id.as_deref().unwrap_or("")
        ),
        other => panic!("bad event kind: {other}"),
    }
}

struct PlannerCtx<'a> {
    workspace_msrv: Semver,
    allow_yanked_pinned: bool,
    lock: &'a BTreeMap<String, String>,
    active_advisories_by_crate: &'a BTreeMap<String, Vec<Advisory>>,
    members: &'a BTreeMap<String, Member>,
    workspace_dependencies: &'a BTreeMap<String, String>,
    forced_bump_set: &'a BTreeSet<(String, String)>,
}

impl<'a> PlannerCtx<'a> {
    fn is_blocked(&self, crate_name: &str, v: Semver) -> bool {
        if let Some(adv) = self.active_advisories_by_crate.get(crate_name) {
            adv.iter().any(|a| in_range(v, a.range))
        } else {
            false
        }
    }

    fn blocking_active(&self, crate_name: &str, v: Semver) -> Vec<String> {
        self.active_advisories_by_crate
            .get(crate_name)
            .map(|adv| {
                adv.iter()
                    .filter(|a| in_range(v, a.range))
                    .map(|a| a.advisory_id.clone())
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default()
    }

    fn eligibility_basic(
        &self,
        crate_name: &str,
        vinfo: &VersionInfo,
        eff: (Semver, Semver),
        effective_msrv: Semver,
    ) -> bool {
        if !in_range(vinfo.ver, eff) {
            return false;
        }
        if vinfo.msrv > effective_msrv {
            return false;
        }
        if vinfo.yanked {
            if !self.allow_yanked_pinned {
                return false;
            }
            if self.lock.get(crate_name).map(String::as_str) != Some(&vinfo.ver_str) {
                return false;
            }
        }
        if self.is_blocked(crate_name, vinfo.ver) {
            return false;
        }
        true
    }

    fn effective_msrv_for(&self, member_name: &str, crate_name: &str) -> Semver {
        let dep = self
            .members
            .get(member_name)
            .unwrap()
            .deps
            .get(crate_name)
            .unwrap();
        if dep.workspace {
            self.workspace_msrv
        } else {
            let mm = parse_semver(&self.members.get(member_name).unwrap().member_msrv);
            if mm > self.workspace_msrv {
                mm
            } else {
                self.workspace_msrv
            }
        }
    }

    fn effective_range_for(&self, member_name: &str, crate_name: &str) -> (Semver, Semver) {
        let dep = self
            .members
            .get(member_name)
            .unwrap()
            .deps
            .get(crate_name)
            .unwrap();
        if dep.workspace {
            parse_range(self.workspace_dependencies.get(crate_name).unwrap())
        } else {
            parse_range(dep.version_range.as_deref().unwrap())
        }
    }

    fn sharing_set_for(&self, crate_name: &str) -> Vec<String> {
        let mut out = Vec::new();
        for member_name in self.members.keys() {
            let dep = self.members.get(member_name).unwrap().deps.get(crate_name);
            if let Some(d) = dep {
                if d.workspace
                    && !self
                        .forced_bump_set
                        .contains(&(member_name.clone(), crate_name.to_string()))
                {
                    out.push(member_name.clone());
                }
            }
        }
        out
    }
}

fn shared_default_pref(crate_name: &str, members: &BTreeMap<String, Member>, sharing: &[String]) -> bool {
    sharing
        .iter()
        .any(|m| members.get(m).unwrap().deps.get(crate_name).unwrap().default_features)
}

fn planner_select(
    ctx: &PlannerCtx,
    crate_name: &str,
    eligible: &[VersionInfo],
    sharing_members: &[String],
) -> (Option<VersionInfo>, Vec<String>) {
    if eligible.is_empty() {
        return (None, Vec::new());
    }
    let use_defaults = shared_default_pref(crate_name, ctx.members, sharing_members);

    let mut eligible_desc: Vec<&VersionInfo> = eligible.iter().collect();
    eligible_desc.sort_by(|a, b| b.ver.cmp(&a.ver));

    let mut shared_features: BTreeSet<String> = BTreeSet::new();
    for m in sharing_members {
        for f in &ctx.members.get(m).unwrap().deps.get(crate_name).unwrap().features {
            shared_features.insert(f.clone());
        }
    }

    let requested = |vinfo: &VersionInfo| -> BTreeSet<String> {
        let mut s = shared_features.clone();
        if use_defaults {
            for f in &vinfo.default_features {
                s.insert(f.clone());
            }
        }
        s
    };

    for v in &eligible_desc {
        let req = requested(v);
        if req.iter().all(|f| v.features.contains(f)) {
            return ((*v).clone().into(), Vec::new());
        }
    }

    let mut union_requested: BTreeSet<String> = shared_features.clone();
    if use_defaults {
        let max_v = eligible_desc[0];
        for f in &max_v.default_features {
            union_requested.insert(f.clone());
        }
    }

    let mut dropped: Vec<String> = Vec::new();
    let mut remaining = union_requested;
    loop {
        for v in &eligible_desc {
            if remaining.iter().all(|f| v.features.contains(f)) {
                let mut sorted = dropped.clone();
                sorted.sort();
                return ((*v).clone().into(), sorted);
            }
        }
        let mut not_supported: Vec<String> = Vec::new();
        for f in &remaining {
            if !eligible_desc.iter().any(|v| v.features.contains(f)) {
                not_supported.push(f.clone());
            }
        }
        let pick = if !not_supported.is_empty() {
            not_supported.sort();
            not_supported[0].clone()
        } else {
            remaining.iter().next().unwrap().clone()
        };
        dropped.push(pick.clone());
        remaining.remove(&pick);
        if remaining.is_empty() {
            let mut sorted = dropped.clone();
            sorted.sort();
            return (eligible_desc[0].clone().into(), sorted);
        }
    }
}

fn json_object(pairs: Vec<(&str, Value)>) -> Value {
    let mut m = Map::new();
    for (k, v) in pairs {
        m.insert(k.to_string(), v);
    }
    Value::Object(m)
}

fn classify_planner_action(lock: &BTreeMap<String, String>, crate_name: &str, ci: &VersionInfo) -> String {
    let locked = lock.get(crate_name);
    if locked.is_none() {
        return "hold".to_string();
    }
    let lv = parse_semver(locked.unwrap());
    if ci.ver == lv {
        "hold".to_string()
    } else if ci.ver > lv {
        "bump".to_string()
    } else {
        "downgrade".to_string()
    }
}

fn main() {
    let data_dir = PathBuf::from(env::var("CWB_DATA_DIR").unwrap_or_else(|_| "/app/workspace".into()));
    let plan_dir = PathBuf::from(env::var("CWB_PLAN_DIR").unwrap_or_else(|_| "/app/plan".into()));
    fs::create_dir_all(&plan_dir).unwrap();

    let manifest = read_json(&data_dir.join("workspace_manifest.json"));
    let pool = read_json(&data_dir.join("pool_state.json"));
    let lock_raw = read_json(&data_dir.join("current_lock.json"));
    let lock: BTreeMap<String, String> = lock_raw["locks"]
        .as_object()
        .unwrap()
        .iter()
        .map(|(k, v)| (k.clone(), as_str(v).to_string()))
        .collect();
    let advisories_raw = read_json(&data_dir.join("advisories.json"));
    let incidents_raw = read_json(&data_dir.join("incident_log.json"));

    let workspace_dependencies: BTreeMap<String, String> = manifest["workspace_dependencies"]
        .as_object()
        .unwrap()
        .iter()
        .map(|(k, v)| (k.clone(), as_str(v).to_string()))
        .collect();
    let workspace_msrv = parse_semver(as_str(&manifest["workspace_msrv"]));
    let severity_threshold = severity_rank(as_str(&manifest["severity_block_threshold"]));
    let allow_yanked_pinned = as_bool(&manifest["allow_yanked_pinned"]);
    let current_day = as_i64(&pool["current_day"]);

    let mut members: BTreeMap<String, Member> = BTreeMap::new();
    let mut member_paths: Vec<PathBuf> = fs::read_dir(data_dir.join("members"))
        .unwrap()
        .filter_map(|e| {
            let p = e.ok()?.path();
            if p.extension().and_then(|s| s.to_str()) == Some("json") {
                Some(p)
            } else {
                None
            }
        })
        .collect();
    member_paths.sort();
    for fp in &member_paths {
        let m = read_json(fp);
        let name = as_str(&m["name"]).to_string();
        let member_msrv = as_str(&m["member_msrv"]).to_string();
        let mut deps = BTreeMap::new();
        for (k, v) in m["deps"].as_object().unwrap() {
            deps.insert(
                k.clone(),
                DepDecl {
                    workspace: as_bool(&v["workspace"]),
                    version_range: v["version_range"].as_str().map(String::from),
                    features: v["features"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .map(|x| as_str(x).to_string())
                        .collect(),
                    default_features: as_bool(&v["default_features"]),
                    required_features: v["required_features"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .map(|x| as_str(x).to_string())
                        .collect(),
                },
            );
        }
        members.insert(name, Member { member_msrv, deps });
    }

    let mut registry: BTreeMap<String, CrateDoc> = BTreeMap::new();
    let mut reg_paths: Vec<PathBuf> = fs::read_dir(data_dir.join("registry"))
        .unwrap()
        .filter_map(|e| {
            let p = e.ok()?.path();
            if p.extension().and_then(|s| s.to_str()) == Some("json") {
                Some(p)
            } else {
                None
            }
        })
        .collect();
    reg_paths.sort();
    for fp in &reg_paths {
        let r = read_json(fp);
        let name = as_str(&r["name"]).to_string();
        let versions = collect_versions(&r);
        registry.insert(name, CrateDoc { versions });
    }

    let mut prelim_accepted: Vec<Event> = Vec::new();
    let mut ignored_count: i64 = 0;
    let accepted_kinds: BTreeSet<&str> = ["force_freeze", "forced_bump", "advisory_override"]
        .iter()
        .copied()
        .collect();
    for raw in incidents_raw["events"].as_array().unwrap() {
        let accepted = raw.get("accepted").and_then(|x| x.as_bool());
        if accepted != Some(true) {
            ignored_count += 1;
            continue;
        }
        let day = raw.get("day").and_then(|x| x.as_i64());
        if day.is_none() || day.unwrap() > current_day {
            ignored_count += 1;
            continue;
        }
        let kind = raw.get("kind").and_then(|x| x.as_str()).unwrap_or("");
        if !accepted_kinds.contains(kind) {
            ignored_count += 1;
            continue;
        }
        prelim_accepted.push(parse_event(raw));
    }

    let mut scope_best: BTreeMap<String, Event> = BTreeMap::new();
    for e in &prelim_accepted {
        let key = event_scope(e);
        let take = match scope_best.get(&key) {
            None => true,
            Some(prev) => {
                if e.day > prev.day {
                    true
                } else if e.day == prev.day && e.event_id < prev.event_id {
                    true
                } else {
                    false
                }
            }
        };
        if take {
            scope_best.insert(key, e.clone());
        }
    }
    let accepted_events: Vec<Event> = scope_best.into_values().collect();

    let mut force_freeze_crates: BTreeSet<String> = BTreeSet::new();
    let mut forced_bump_map: BTreeMap<(String, String), Event> = BTreeMap::new();
    let mut overridden_advisory_ids: BTreeSet<String> = BTreeSet::new();
    for e in &accepted_events {
        match e.kind.as_str() {
            "force_freeze" => {
                force_freeze_crates.insert(e.crate_name.clone().unwrap());
            }
            "forced_bump" => {
                forced_bump_map.insert(
                    (e.member.clone().unwrap(), e.crate_name.clone().unwrap()),
                    e.clone(),
                );
            }
            "advisory_override" => {
                overridden_advisory_ids.insert(e.advisory_id.clone().unwrap());
            }
            _ => {}
        }
    }
    let forced_bump_set: BTreeSet<(String, String)> = forced_bump_map.keys().cloned().collect();

    let mut all_advisories_by_id: BTreeMap<String, Advisory> = BTreeMap::new();
    let mut active_advisories_by_crate: BTreeMap<String, Vec<Advisory>> = BTreeMap::new();
    for a in advisories_raw["advisories"].as_array().unwrap() {
        let adv = Advisory {
            advisory_id: as_str(&a["advisory_id"]).to_string(),
            crate_name: as_str(&a["crate"]).to_string(),
            severity: as_str(&a["severity"]).to_string(),
            sev_rank: severity_rank(as_str(&a["severity"])),
            range: parse_range(as_str(&a["affected_range"])),
            day_published: as_i64(&a["day_published"]),
        };
        all_advisories_by_id.insert(adv.advisory_id.clone(), adv.clone());
        let is_overridden = overridden_advisory_ids.contains(&adv.advisory_id);
        if !is_overridden && adv.sev_rank >= severity_threshold {
            active_advisories_by_crate
                .entry(adv.crate_name.clone())
                .or_default()
                .push(adv);
        }
    }

    let ctx = PlannerCtx {
        workspace_msrv,
        allow_yanked_pinned,
        lock: &lock,
        active_advisories_by_crate: &active_advisories_by_crate,
        members: &members,
        workspace_dependencies: &workspace_dependencies,
        forced_bump_set: &forced_bump_set,
    };

    let mut crate_decision: BTreeMap<
        String,
        (Option<VersionInfo>, Vec<String>, Vec<String>, bool, Vec<String>, bool),
    > = BTreeMap::new();

    let mut all_crates_in_deps: BTreeSet<String> = BTreeSet::new();
    for m in members.values() {
        for c in m.deps.keys() {
            all_crates_in_deps.insert(c.clone());
        }
    }

    for crate_name in &all_crates_in_deps {
        if !registry.contains_key(crate_name) {
            continue;
        }
        let versions = &registry.get(crate_name).unwrap().versions;
        if force_freeze_crates.contains(crate_name) {
            let locked_str = lock.get(crate_name).cloned();
            let mut chosen: Option<VersionInfo> = None;
            let mut blocking: Vec<String> = Vec::new();
            let mut freeze_unsafe = false;
            if let Some(ls) = locked_str.as_ref() {
                let lv = parse_semver(ls);
                if let Some(vinfo) = versions.iter().find(|v| v.ver == lv) {
                    chosen = Some(vinfo.clone());
                    blocking = ctx.blocking_active(crate_name, lv);
                    let yanked_unsafe = vinfo.yanked
                        && !(allow_yanked_pinned
                            && lock.get(crate_name).map(String::as_str) == Some(&vinfo.ver_str));
                    if !blocking.is_empty() || yanked_unsafe {
                        freeze_unsafe = true;
                    }
                }
            }
            crate_decision.insert(
                crate_name.clone(),
                (chosen, Vec::new(), Vec::new(), true, blocking, freeze_unsafe),
            );
            continue;
        }

        let sharing_members = ctx.sharing_set_for(crate_name);
        if !sharing_members.is_empty() {
            let eff = parse_range(workspace_dependencies.get(crate_name).unwrap());
            let shared_msrv = workspace_msrv;
            let eligible: Vec<VersionInfo> = versions
                .iter()
                .filter(|v| ctx.eligibility_basic(crate_name, v, eff, shared_msrv))
                .cloned()
                .collect();
            let (chosen, dropped) = planner_select(&ctx, crate_name, &eligible, &sharing_members);
            crate_decision.insert(
                crate_name.clone(),
                (chosen, dropped, sharing_members, false, Vec::new(), false),
            );
        }
    }

    let mut bump_plan_entries: Vec<Value> = Vec::new();
    let mut feature_conflict_events: Vec<Value> = Vec::new();
    let mut advisory_consumers: BTreeMap<
        String,
        Vec<(String, Option<String>, bool, bool)>,
    > = BTreeMap::new();
    for aid in all_advisories_by_id.keys() {
        advisory_consumers.insert(aid.clone(), Vec::new());
    }
    let mut mitigated_versions_by_advisory: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for aid in all_advisories_by_id.keys() {
        mitigated_versions_by_advisory.insert(aid.clone(), BTreeSet::new());
    }
    let mut still_open_frozen: BTreeSet<String> = BTreeSet::new();
    let mut hard_conflict_per_advisory: BTreeSet<String> = BTreeSet::new();

    let mut all_entries: Vec<(String, String)> = Vec::new();
    for member_name in members.keys() {
        for crate_name in members.get(member_name).unwrap().deps.keys() {
            all_entries.push((member_name.clone(), crate_name.clone()));
        }
    }

    for (member_name, crate_name) in &all_entries {
        let dep = members
            .get(member_name)
            .unwrap()
            .deps
            .get(crate_name)
            .unwrap()
            .clone();
        let current_version = lock.get(crate_name).cloned();
        let chosen_info: Option<VersionInfo>;
        let action: String;
        let source: String;
        let sharing: String;

        if force_freeze_crates.contains(crate_name) {
            let dec = crate_decision.get(crate_name).unwrap();
            sharing = if dep.workspace { "shared".to_string() } else { "per_member".to_string() };
            source = "incident_log_force_freeze".to_string();
            chosen_info = dec.0.clone();
            if chosen_info.is_none() {
                action = "block_no_safe_version".to_string();
            } else if dec.5 {
                action = "freeze_unsafe".to_string();
            } else {
                action = "freeze".to_string();
            }
        } else if forced_bump_map.contains_key(&(member_name.clone(), crate_name.clone())) {
            let evt = forced_bump_map
                .get(&(member_name.clone(), crate_name.clone()))
                .unwrap();
            let pinned_str = evt.pinned_version.as_ref().unwrap();
            let pinned_ver = parse_semver(pinned_str);
            let versions = registry
                .get(crate_name)
                .map(|c| c.versions.clone())
                .unwrap_or_default();
            let eff = ctx.effective_range_for(member_name, crate_name);
            sharing = if dep.workspace {
                "forced_per_member".to_string()
            } else {
                "per_member".to_string()
            };
            source = "incident_log_forced_bump".to_string();
            let vinfo = versions.iter().find(|v| v.ver == pinned_ver).cloned();
            let entry_msrv = ctx.effective_msrv_for(member_name, crate_name);
            match vinfo {
                Some(vi) if ctx.eligibility_basic(crate_name, &vi, eff, entry_msrv) => {
                    action = "forced_bump".to_string();
                    chosen_info = Some(vi);
                }
                _ => {
                    action = "block_no_safe_version".to_string();
                    chosen_info = None;
                }
            }
        } else if dep.workspace {
            let dec = crate_decision.get(crate_name);
            sharing = "shared".to_string();
            source = "planner".to_string();
            chosen_info = dec.and_then(|d| d.0.clone());
            action = match chosen_info.as_ref() {
                None => "block_no_safe_version".to_string(),
                Some(ci) => classify_planner_action(&lock, crate_name, ci),
            };
        } else {
            sharing = "per_member".to_string();
            source = "planner".to_string();
            let eff = ctx.effective_range_for(member_name, crate_name);
            let entry_msrv = ctx.effective_msrv_for(member_name, crate_name);
            let versions = registry
                .get(crate_name)
                .map(|c| c.versions.clone())
                .unwrap_or_default();
            let eligible: Vec<VersionInfo> = versions
                .iter()
                .filter(|v| ctx.eligibility_basic(crate_name, v, eff, entry_msrv))
                .cloned()
                .collect();
            let (chosen, _dropped) =
                planner_select(&ctx, crate_name, &eligible, &[member_name.clone()]);
            chosen_info = chosen;
            action = match chosen_info.as_ref() {
                None => "block_no_safe_version".to_string(),
                Some(ci) => classify_planner_action(&lock, crate_name, ci),
            };
        }

        let feature_loss_set: Vec<String> = match chosen_info.as_ref() {
            None => Vec::new(),
            Some(ci) => {
                let mut req: BTreeSet<String> = dep.features.iter().cloned().collect();
                if dep.default_features {
                    for f in &ci.default_features {
                        req.insert(f.clone());
                    }
                }
                let mut miss: Vec<String> =
                    req.into_iter().filter(|f| !ci.features.contains(f)).collect();
                miss.sort();
                miss
            }
        };

        let reason = if action == "block_no_safe_version" {
            "no_eligible_version"
        } else if action == "freeze_unsafe" {
            "freeze_advisory_conflict"
        } else if !feature_loss_set.is_empty() {
            "feature_downgrade"
        } else {
            "satisfied"
        };

        let chosen_version_str: Option<String> = chosen_info.as_ref().map(|ci| ci.ver_str.clone());

        let entry = json_object(vec![
            ("member", Value::String(member_name.clone())),
            ("crate", Value::String(crate_name.clone())),
            (
                "current_version",
                current_version
                    .clone()
                    .map(Value::String)
                    .unwrap_or(Value::Null),
            ),
            (
                "chosen_version",
                chosen_version_str
                    .clone()
                    .map(Value::String)
                    .unwrap_or(Value::Null),
            ),
            ("action", Value::String(action.clone())),
            ("reason", Value::String(reason.to_string())),
            (
                "feature_loss_set",
                Value::Array(
                    feature_loss_set
                        .iter()
                        .cloned()
                        .map(Value::String)
                        .collect(),
                ),
            ),
            ("sharing", Value::String(sharing.clone())),
            ("source", Value::String(source.clone())),
        ]);
        bump_plan_entries.push(entry);

        if !feature_loss_set.is_empty() {
            let required: BTreeSet<String> = dep.required_features.iter().cloned().collect();
            let lost: BTreeSet<String> = feature_loss_set.iter().cloned().collect();
            let hard_conflict = lost.intersection(&required).next().is_some();
            feature_conflict_events.push(json_object(vec![
                ("member", Value::String(member_name.clone())),
                ("crate", Value::String(crate_name.clone())),
                (
                    "lost_features",
                    Value::Array(
                        feature_loss_set
                            .iter()
                            .cloned()
                            .map(Value::String)
                            .collect(),
                    ),
                ),
                ("hard_conflict", Value::Bool(hard_conflict)),
                ("forced_disable", Value::Bool(hard_conflict)),
            ]));
        }

        if let Some(cv) = chosen_version_str.as_ref() {
            let cver = parse_semver(cv);
            for adv in all_advisories_by_id.values() {
                if adv.crate_name != *crate_name {
                    continue;
                }
                advisory_consumers.get_mut(&adv.advisory_id).unwrap().push((
                    member_name.clone(),
                    Some(cv.clone()),
                    in_range(cver, adv.range),
                    {
                        let lost: BTreeSet<String> =
                            feature_loss_set.iter().cloned().collect();
                        let required: BTreeSet<String> =
                            dep.required_features.iter().cloned().collect();
                        !feature_loss_set.is_empty()
                            && lost.intersection(&required).next().is_some()
                    },
                ));
                mitigated_versions_by_advisory
                    .get_mut(&adv.advisory_id)
                    .unwrap()
                    .insert(cv.clone());
                if action == "freeze_unsafe"
                    && adv.sev_rank >= severity_threshold
                    && !overridden_advisory_ids.contains(&adv.advisory_id)
                    && in_range(cver, adv.range)
                {
                    still_open_frozen.insert(adv.advisory_id.clone());
                }
                if adv.sev_rank >= severity_threshold
                    && !overridden_advisory_ids.contains(&adv.advisory_id)
                    && !feature_loss_set.is_empty()
                {
                    let lost: BTreeSet<String> =
                        feature_loss_set.iter().cloned().collect();
                    let required: BTreeSet<String> =
                        dep.required_features.iter().cloned().collect();
                    if lost.intersection(&required).next().is_some() {
                        hard_conflict_per_advisory.insert(adv.advisory_id.clone());
                    }
                }
            }
        } else {
            for adv in all_advisories_by_id.values() {
                if adv.crate_name != *crate_name {
                    continue;
                }
                advisory_consumers.get_mut(&adv.advisory_id).unwrap().push((
                    member_name.clone(),
                    None,
                    false,
                    false,
                ));
            }
        }
    }

    let mut msrv_members_json: Vec<Value> = Vec::new();
    let mut msrv_inconsistent_count: i64 = 0;
    for member_name in members.keys() {
        let m = members.get(member_name).unwrap();
        let mm = parse_semver(&m.member_msrv);
        let (status, exceeded_by) = if mm > workspace_msrv {
            msrv_inconsistent_count += 1;
            let diff = (
                mm.0.saturating_sub(workspace_msrv.0),
                mm.1.saturating_sub(workspace_msrv.1),
                mm.2.saturating_sub(workspace_msrv.2),
            );
            ("inconsistent", format!("{}.{}.{}", diff.0, diff.1, diff.2))
        } else {
            ("compatible", "0.0.0".to_string())
        };

        let mut blocked_pairs: BTreeSet<(String, String)> = BTreeSet::new();
        for crate_name in m.deps.keys() {
            if !registry.contains_key(crate_name) {
                continue;
            }
            let eff = ctx.effective_range_for(member_name, crate_name);
            let entry_msrv = ctx.effective_msrv_for(member_name, crate_name);
            for vinfo in &registry.get(crate_name).unwrap().versions {
                if !in_range(vinfo.ver, eff) {
                    continue;
                }
                if vinfo.msrv > entry_msrv {
                    blocked_pairs.insert((crate_name.clone(), vinfo.ver_str.clone()));
                }
            }
        }

        msrv_members_json.push(json_object(vec![
            ("member", Value::String(member_name.clone())),
            ("member_msrv", Value::String(m.member_msrv.clone())),
            ("status", Value::String(status.to_string())),
            ("exceeded_by", Value::String(exceeded_by)),
            (
                "msrv_blocked_versions_count",
                Value::Number(serde_json::Number::from(blocked_pairs.len() as i64)),
            ),
        ]));
    }

    let mut advisory_out: Vec<Value> = Vec::new();
    for aid in all_advisories_by_id.keys() {
        let a = all_advisories_by_id.get(aid).unwrap();
        let consumers = advisory_consumers.get(aid).unwrap();
        let overridden = overridden_advisory_ids.contains(aid);

        let (status, mitigation): (&str, Option<&str>) = if overridden {
            ("overridden", Some("override"))
        } else if a.sev_rank < severity_threshold {
            ("inactive_low_severity", None)
        } else if still_open_frozen.contains(aid) {
            ("still_open_frozen", Some("frozen"))
        } else if hard_conflict_per_advisory.contains(aid) {
            ("mitigated_by_forced_disable", Some("forced_disable"))
        } else {
            let any_block = consumers.iter().any(|c| c.1.is_none());
            if any_block {
                ("still_open", None)
            } else {
                let in_range_any = consumers.iter().any(|c| c.2);
                if !in_range_any {
                    ("resolved_by_bump", Some("bump"))
                } else {
                    ("still_open", None)
                }
            }
        };
        let mv: Vec<String> = mitigated_versions_by_advisory
            .get(aid)
            .unwrap()
            .iter()
            .cloned()
            .collect();
        let mv_json: Vec<Value> = mv.into_iter().map(Value::String).collect();
        advisory_out.push(json_object(vec![
            ("advisory_id", Value::String(aid.clone())),
            ("crate", Value::String(a.crate_name.clone())),
            ("severity", Value::String(a.severity.clone())),
            ("status", Value::String(status.to_string())),
            (
                "mitigation_method",
                mitigation
                    .map(|s| Value::String(s.to_string()))
                    .unwrap_or(Value::Null),
            ),
            ("mitigated_versions", Value::Array(mv_json)),
            (
                "day_published",
                Value::Number(serde_json::Number::from(a.day_published)),
            ),
        ]));
    }

    let mut action_counts: BTreeMap<String, i64> = BTreeMap::new();
    for e in &bump_plan_entries {
        let key = as_str(&e["action"]).to_string();
        *action_counts.entry(key).or_insert(0) += 1;
    }
    let mut advisory_counts: BTreeMap<String, i64> = BTreeMap::new();
    for a in &advisory_out {
        let key = as_str(&a["status"]).to_string();
        *advisory_counts.entry(key).or_insert(0) += 1;
    }

    let mut shared_crates: BTreeSet<String> = BTreeSet::new();
    let mut per_member_crates: BTreeSet<String> = BTreeSet::new();
    for e in &bump_plan_entries {
        let crate_name = as_str(&e["crate"]).to_string();
        let sharing = as_str(&e["sharing"]);
        match sharing {
            "shared" => {
                shared_crates.insert(crate_name);
            }
            "per_member" | "forced_per_member" => {
                per_member_crates.insert(crate_name);
            }
            _ => {}
        }
    }

    let hard_conflict_count: i64 = feature_conflict_events
        .iter()
        .filter(|e| e["hard_conflict"].as_bool() == Some(true))
        .count() as i64;

    let action_counts_json: Value = {
        let mut m = Map::new();
        for (k, v) in &action_counts {
            m.insert(k.clone(), Value::Number(serde_json::Number::from(*v)));
        }
        Value::Object(m)
    };
    let advisory_counts_json: Value = {
        let mut m = Map::new();
        for (k, v) in &advisory_counts {
            m.insert(k.clone(), Value::Number(serde_json::Number::from(*v)));
        }
        Value::Object(m)
    };

    let summary = json_object(vec![
        (
            "workspace_msrv",
            Value::String(as_str(&manifest["workspace_msrv"]).to_string()),
        ),
        (
            "severity_block_threshold",
            Value::String(as_str(&manifest["severity_block_threshold"]).to_string()),
        ),
        (
            "total_members",
            Value::Number(serde_json::Number::from(members.len() as i64)),
        ),
        (
            "total_crates_in_registry",
            Value::Number(serde_json::Number::from(registry.len() as i64)),
        ),
        (
            "total_entries",
            Value::Number(serde_json::Number::from(bump_plan_entries.len() as i64)),
        ),
        ("action_counts", action_counts_json),
        (
            "shared_crate_count",
            Value::Number(serde_json::Number::from(shared_crates.len() as i64)),
        ),
        (
            "per_member_crate_count",
            Value::Number(serde_json::Number::from(per_member_crates.len() as i64)),
        ),
        (
            "hard_conflict_count",
            Value::Number(serde_json::Number::from(hard_conflict_count)),
        ),
        ("advisory_counts", advisory_counts_json),
        (
            "ignored_incident_events",
            Value::Number(serde_json::Number::from(ignored_count)),
        ),
        (
            "msrv_inconsistent_member_count",
            Value::Number(serde_json::Number::from(msrv_inconsistent_count)),
        ),
    ]);

    write_json(
        &plan_dir.join("bump_plan.json"),
        &json!({ "entries": bump_plan_entries }),
    );
    write_json(
        &plan_dir.join("msrv_compatibility.json"),
        &json!({
            "workspace_msrv": as_str(&manifest["workspace_msrv"]),
            "members": msrv_members_json,
        }),
    );
    write_json(
        &plan_dir.join("feature_conflict_report.json"),
        &json!({ "events": feature_conflict_events }),
    );
    write_json(
        &plan_dir.join("advisory_status.json"),
        &json!({ "advisories": advisory_out }),
    );
    write_json(&plan_dir.join("summary.json"), &summary);
}
RUST_END

cargo build --release --manifest-path /app/planner/Cargo.toml
/app/planner/target/release/planner
