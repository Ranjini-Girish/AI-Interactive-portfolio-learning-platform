#!/bin/bash
set -euo pipefail

mkdir -p "${DAG_PLAN_DIR:-/app/plan}"
PLANNER_DIR="${DAG_PLANNER_DIR:-/app/planner}"
export PATH="/usr/local/cargo/bin:${PATH}"
if [ -f "${HOME}/.cargo/env" ]; then
  source "${HOME}/.cargo/env"
fi

cat > "${PLANNER_DIR}/src/main.rs" <<'RS_EOF'
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{Map, Number, Value};

const ALLOWED_INCIDENT_KINDS: [&str; 3] = [
    "job_quarantine",
    "sla_breach_grace",
    "resource_pool_freeze",
];

#[derive(Clone)]
struct JobRecord {
    name: String,
    phase: i64,
    rc: String,
    rt: i64,
    retry: i64,
    base_p: i64,
    status: String,
    ep: i64,
    start: Option<i64>,
    end: Option<i64>,
}

fn data_dir() -> PathBuf {
    env::var("DAG_DATA_DIR")
        .unwrap_or_else(|_| "/app/pipelines".to_string())
        .into()
}

fn out_dir() -> PathBuf {
    env::var("DAG_PLAN_DIR")
        .unwrap_or_else(|_| "/app/plan".to_string())
        .into()
}

fn read_json(path: &Path) -> Value {
    let text = fs::read_to_string(path).unwrap_or_else(|e| panic!("read {}: {}", path.display(), e));
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("parse {}: {}", path.display(), e))
}

fn write_json(path: &Path, value: &Value) {
    let mut text = serde_json::to_string_pretty(value).expect("serialize json");
    text.push('\n');
    fs::write(path, text).unwrap_or_else(|e| panic!("write {}: {}", path.display(), e));
}

fn get_str<'a>(obj: &'a Value, key: &str) -> &'a str {
    obj.get(key)
        .and_then(Value::as_str)
        .unwrap_or_else(|| panic!("missing string key {}", key))
}

fn get_i64(obj: &Value, key: &str) -> i64 {
    obj.get(key)
        .and_then(Value::as_i64)
        .unwrap_or_else(|| panic!("missing int key {}", key))
}

fn optional_string_array(obj: &Value, key: &str) -> Vec<String> {
    obj.get(key)
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(Value::as_str)
                .map(ToString::to_string)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default()
}

fn find_cycle_jobs(jobs: &[Value]) -> BTreeSet<String> {
    let mut name_to_idx: BTreeMap<String, usize> = BTreeMap::new();
    for (idx, j) in jobs.iter().enumerate() {
        name_to_idx.insert(get_str(j, "name").to_string(), idx);
    }
    let n = jobs.len();
    let mut graph = vec![Vec::<usize>::new(); n];
    let mut self_loops = BTreeSet::<String>::new();
    for j in jobs {
        let jname = get_str(j, "name");
        for dep in optional_string_array(j, "depends_on") {
            if dep == jname {
                self_loops.insert(jname.to_string());
            } else if let Some(dep_idx) = name_to_idx.get(&dep) {
                let src = *name_to_idx.get(jname).expect("job in map");
                graph[src].push(*dep_idx);
            }
        }
    }
    let mut index: usize = 0;
    let mut stack = Vec::<usize>::new();
    let mut on_stack = vec![false; n];
    let mut indices = vec![-1_i64; n];
    let mut lowlink = vec![0_i64; n];
    let mut cycle_jobs = self_loops;

    fn strongconnect(
        v: usize,
        index: &mut usize,
        stack: &mut Vec<usize>,
        on_stack: &mut [bool],
        indices: &mut [i64],
        lowlink: &mut [i64],
        graph: &[Vec<usize>],
        jobs: &[Value],
        cycle_jobs: &mut BTreeSet<String>,
    ) {
        indices[v] = *index as i64;
        lowlink[v] = *index as i64;
        *index += 1;
        stack.push(v);
        on_stack[v] = true;
        for &w in &graph[v] {
            if indices[w] == -1 {
                strongconnect(
                    w, index, stack, on_stack, indices, lowlink, graph, jobs, cycle_jobs,
                );
                if lowlink[w] < lowlink[v] {
                    lowlink[v] = lowlink[w];
                }
            } else if on_stack[w] && indices[w] < lowlink[v] {
                lowlink[v] = indices[w];
            }
        }
        if lowlink[v] == indices[v] {
            let mut scc = Vec::<usize>::new();
            loop {
                let w = stack.pop().expect("tarjan stack underflow");
                on_stack[w] = false;
                scc.push(w);
                if w == v {
                    break;
                }
            }
            if scc.len() >= 2 {
                for w in scc {
                    cycle_jobs.insert(get_str(&jobs[w], "name").to_string());
                }
            }
        }
    }

    for v in 0..n {
        if indices[v] == -1 {
            strongconnect(
                v,
                &mut index,
                &mut stack,
                &mut on_stack,
                &mut indices,
                &mut lowlink,
                &graph,
                jobs,
                &mut cycle_jobs,
            );
        }
    }
    cycle_jobs
}

fn topological_phases(jobs: &[Value], cycle_present: bool) -> BTreeMap<String, i64> {
    if cycle_present {
        let mut out = BTreeMap::new();
        for j in jobs {
            out.insert(get_str(j, "name").to_string(), 0);
        }
        return out;
    }
    let mut name_to_job = BTreeMap::<String, Value>::new();
    for j in jobs {
        name_to_job.insert(get_str(j, "name").to_string(), j.clone());
    }

    fn compute(
        name: &str,
        phase: &mut BTreeMap<String, i64>,
        stack: &mut BTreeSet<String>,
        name_to_job: &BTreeMap<String, Value>,
    ) -> i64 {
        if let Some(v) = phase.get(name) {
            return *v;
        }
        if stack.contains(name) {
            return 0;
        }
        stack.insert(name.to_string());
        let deps = optional_string_array(name_to_job.get(name).expect("job exists"), "depends_on");
        let p = if deps.is_empty() {
            0
        } else {
            let mut vals = Vec::<i64>::new();
            for d in deps {
                if name_to_job.contains_key(&d) {
                    vals.push(compute(&d, phase, stack, name_to_job));
                }
            }
            1 + vals.into_iter().max().expect("at least one valid dependency")
        };
        stack.remove(name);
        phase.insert(name.to_string(), p);
        p
    }

    let mut phase = BTreeMap::<String, i64>::new();
    for j in jobs {
        let n = get_str(j, "name");
        compute(n, &mut phase, &mut BTreeSet::new(), &name_to_job);
    }
    phase
}

fn compute_initial_job_status(
    jobs: &[Value],
    has_cycle: bool,
    is_quarantined: bool,
    freeze_active_resources: &BTreeSet<String>,
) -> BTreeMap<String, String> {
    let mut statuses = BTreeMap::<String, String>::new();
    for j in jobs {
        let name = get_str(j, "name").to_string();
        let rc = get_str(j, "resource_class");
        let s = if has_cycle {
            "blocked_cycle"
        } else if is_quarantined {
            "blocked_quarantine"
        } else if freeze_active_resources.contains(rc) {
            "blocked_resource_freeze"
        } else {
            "scheduled"
        };
        statuses.insert(name, s.to_string());
    }
    if !has_cycle && !is_quarantined {
        let mut name_to_decl = BTreeMap::<String, Value>::new();
        for j in jobs {
            name_to_decl.insert(get_str(j, "name").to_string(), j.clone());
        }
        loop {
            let mut changed = false;
            let snapshot = statuses.clone();
            for j in jobs {
                let name = get_str(j, "name").to_string();
                let cur = statuses.get(&name).cloned().unwrap_or_default();
                if cur == "blocked_cycle"
                    || cur == "blocked_quarantine"
                    || cur == "blocked_resource_freeze"
                {
                    continue;
                }
                let deps = optional_string_array(name_to_decl.get(&name).expect("decl"), "depends_on");
                let mut blocked = false;
                for d in deps {
                    if snapshot.get(&d).map(String::as_str) == Some("blocked_resource_freeze") {
                        blocked = true;
                        break;
                    }
                }
                if blocked {
                    statuses.insert(name, "blocked_resource_freeze".to_string());
                    changed = true;
                }
            }
            if !changed {
                break;
            }
        }
    }
    statuses
}

#[derive(Clone)]
struct WaveEntry {
    wave_index: i64,
    duration: i64,
    members: Vec<String>,
}

fn build_phase_class_waves(
    jobs: &[Value],
    phases: &BTreeMap<String, i64>,
    statuses: &BTreeMap<String, String>,
    pen: i64,
    impaired_slots: &BTreeMap<String, i64>,
) -> BTreeMap<(i64, String), Vec<WaveEntry>> {
    let mut buckets: BTreeMap<(i64, String), Vec<(i64, String)>> = BTreeMap::new();
    for j in jobs {
        let name = get_str(j, "name").to_string();
        if statuses.get(&name).map(String::as_str) == Some("blocked_resource_freeze") {
            continue;
        }
        let phase = *phases.get(&name).expect("phase");
        let rc = get_str(j, "resource_class").to_string();
        let rt = get_i64(j, "runtime_minutes");
        let retry = get_i64(j, "retry_count");
        let eff = rt + retry * pen;
        buckets.entry((phase, rc)).or_default().push((eff, name));
    }
    let mut out: BTreeMap<(i64, String), Vec<WaveEntry>> = BTreeMap::new();
    for ((phase, rc), mut entries) in buckets {
        entries.sort_by(|a, b| {
            if a.0 != b.0 {
                b.0.cmp(&a.0)
            } else {
                a.1.cmp(&b.1)
            }
        });
        let s = *impaired_slots.get(&rc).expect("impaired slot value") as usize;
        if s == 0 {
            panic!("zero impaired slots for resource_class {}", rc);
        }
        let mut waves = Vec::<WaveEntry>::new();
        let mut idx: i64 = 0;
        let mut i = 0usize;
        while i < entries.len() {
            let end = std::cmp::min(i + s, entries.len());
            let chunk = &entries[i..end];
            let dur = chunk.iter().map(|(e, _)| *e).max().expect("wave non-empty");
            let members = chunk.iter().map(|(_, n)| n.clone()).collect::<Vec<_>>();
            waves.push(WaveEntry {
                wave_index: idx,
                duration: dur,
                members,
            });
            idx += 1;
            i = end;
        }
        out.insert((phase, rc), waves);
    }
    out
}

fn impaired_slots_for_status(
    pstatus: &str,
    slots: &BTreeMap<String, i64>,
    carve_out: &BTreeMap<String, i64>,
) -> BTreeMap<String, i64> {
    let mut out = BTreeMap::<String, i64>::new();
    for (rc, &s) in slots.iter() {
        let v = if pstatus == "degraded" || pstatus == "partial_resource_block" {
            let c = carve_out.get(rc).copied().unwrap_or(0);
            std::cmp::max(1, s - c)
        } else {
            s
        };
        out.insert(rc.clone(), v);
    }
    out
}

fn main() {
    let data = data_dir();
    let out = out_dir();
    fs::create_dir_all(&out).expect("create output dir");

    let pool = read_json(&data.join("pool_state.json"));
    let current_day = get_i64(&pool, "current_day");
    let sched_ver = get_str(&pool, "scheduler_version").to_string();

    let cluster = read_json(&data.join("cluster.json"));
    let slots: BTreeMap<String, i64> = cluster
        .get("slots_per_resource_class")
        .and_then(Value::as_object)
        .expect("slots_per_resource_class object")
        .iter()
        .map(|(k, v)| (k.clone(), v.as_i64().expect("slot count int")))
        .collect();
    let carve_out: BTreeMap<String, i64> = cluster
        .get("impaired_slot_carve_out_per_class")
        .and_then(Value::as_object)
        .expect("impaired_slot_carve_out_per_class object")
        .iter()
        .map(|(k, v)| (k.clone(), v.as_i64().expect("carve-out int")))
        .collect();
    let tier_mod: BTreeMap<String, i64> = cluster
        .get("tier_priority_modifier_int")
        .and_then(Value::as_object)
        .expect("tier_priority_modifier_int object")
        .iter()
        .map(|(k, v)| (k.clone(), v.as_i64().expect("tier modifier int")))
        .collect();
    let retry_penalty: BTreeMap<String, i64> = cluster
        .get("retry_penalty_minutes_per_tier")
        .and_then(Value::as_object)
        .expect("retry_penalty_minutes_per_tier object")
        .iter()
        .map(|(k, v)| (k.clone(), v.as_i64().expect("retry penalty int")))
        .collect();
    let partial_sla_mult: BTreeMap<String, i64> = cluster
        .get("partial_block_sla_multiplier_pct_per_tier")
        .and_then(Value::as_object)
        .expect("partial_block_sla_multiplier_pct_per_tier object")
        .iter()
        .map(|(k, v)| (k.clone(), v.as_i64().expect("partial block sla multiplier int")))
        .collect();
    let sla_debit_per_upstream = cluster
        .get("degraded_sla_debit_per_upstream_quarantine")
        .and_then(Value::as_i64)
        .expect("degraded_sla_debit_per_upstream_quarantine int");
    let wave_debit = cluster
        .get("wave_pressure_debit_per_burst")
        .and_then(Value::as_i64)
        .expect("wave_pressure_debit_per_burst int");
    let chain_debit = cluster
        .get("critical_chain_debit_per_link")
        .and_then(Value::as_i64)
        .expect("critical_chain_debit_per_link int");

    let consumers_doc = read_json(&data.join("consumers.json"));
    let edges = consumers_doc
        .get("edges")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    let pipelines_dir = data.join("pipelines");
    let mut pipeline_names = fs::read_dir(&pipelines_dir)
        .unwrap_or_else(|e| panic!("read_dir {}: {}", pipelines_dir.display(), e))
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir())
        .map(|e| e.file_name().to_string_lossy().to_string())
        .collect::<Vec<_>>();
    pipeline_names.sort();

    let mut manifests = BTreeMap::<String, Value>::new();
    let mut jobs_by_pipe = BTreeMap::<String, Vec<Value>>::new();
    for p in &pipeline_names {
        let manifest = read_json(&pipelines_dir.join(p).join("manifest.json"));
        manifests.insert(p.clone(), manifest);
        let jobs_dir = pipelines_dir.join(p).join("jobs");
        let mut job_paths = fs::read_dir(&jobs_dir)
            .unwrap_or_else(|e| panic!("read_dir {}: {}", jobs_dir.display(), e))
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .filter(|path| path.extension().and_then(|s| s.to_str()) == Some("json"))
            .collect::<Vec<_>>();
        job_paths.sort();
        let jobs = job_paths.iter().map(|p| read_json(p)).collect::<Vec<_>>();
        jobs_by_pipe.insert(p.clone(), jobs);
    }

    let log = read_json(&data.join("incident_log.json"));
    let events = log
        .get("events")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    let known_pipes = pipeline_names.iter().cloned().collect::<BTreeSet<_>>();
    let known_rc = slots.keys().cloned().collect::<BTreeSet<_>>();

    let mut accepted_events = Vec::<Value>::new();
    let mut ignored: i64 = 0;
    for ev in events {
        let kind = ev.get("kind").and_then(Value::as_str).unwrap_or("");
        let day = ev.get("day").and_then(Value::as_i64);
        if !ALLOWED_INCIDENT_KINDS.contains(&kind) {
            ignored += 1;
            continue;
        }
        let day = match day {
            Some(d) => d,
            None => {
                ignored += 1;
                continue;
            }
        };
        if day > current_day {
            ignored += 1;
            continue;
        }
        if kind == "job_quarantine" {
            let pipe = ev.get("pipeline").and_then(Value::as_str).unwrap_or("");
            let job = ev.get("job").and_then(Value::as_str).unwrap_or("");
            let reason = ev.get("reason").and_then(Value::as_str).unwrap_or("");
            if !known_pipes.contains(pipe) || reason.is_empty() {
                ignored += 1;
                continue;
            }
            let job_names = jobs_by_pipe
                .get(pipe)
                .expect("jobs for known pipeline")
                .iter()
                .map(|j| get_str(j, "name").to_string())
                .collect::<BTreeSet<_>>();
            if !job_names.contains(job) {
                ignored += 1;
                continue;
            }
        } else if kind == "sla_breach_grace" {
            let pipe = ev.get("pipeline").and_then(Value::as_str).unwrap_or("");
            let ext = ev.get("extension_minutes").and_then(Value::as_i64);
            if !known_pipes.contains(pipe) || ext.is_none() || ext.unwrap() < 0 {
                ignored += 1;
                continue;
            }
        } else if kind == "resource_pool_freeze" {
            let rc = ev.get("resource_class").and_then(Value::as_str).unwrap_or("");
            let dur = ev.get("duration_days").and_then(Value::as_i64);
            if !known_rc.contains(rc) || dur.is_none() || dur.unwrap() <= 0 {
                ignored += 1;
                continue;
            }
        }
        accepted_events.push(ev);
    }

    let mut quarantine_events_by_pipe = BTreeMap::<String, Vec<String>>::new();
    let mut sla_grace_by_pipe = BTreeMap::<String, i64>::new();
    let mut freeze_active_resources = BTreeSet::<String>::new();
    for ev in &accepted_events {
        let kind = get_str(ev, "kind");
        if kind == "job_quarantine" {
            let pipe = get_str(ev, "pipeline").to_string();
            let job = get_str(ev, "job").to_string();
            quarantine_events_by_pipe.entry(pipe).or_default().push(job);
        } else if kind == "sla_breach_grace" {
            let pipe = get_str(ev, "pipeline").to_string();
            let ext = get_i64(ev, "extension_minutes");
            *sla_grace_by_pipe.entry(pipe).or_insert(0) += ext;
        } else if kind == "resource_pool_freeze" {
            let start = get_i64(ev, "day");
            let dur = get_i64(ev, "duration_days");
            let end = start + dur - 1;
            if start <= current_day && current_day <= end {
                freeze_active_resources.insert(get_str(ev, "resource_class").to_string());
            }
        }
    }

    let quarantined_pipes = quarantine_events_by_pipe
        .keys()
        .cloned()
        .collect::<BTreeSet<_>>();

    let mut consumer_to_producers = BTreeMap::<String, BTreeSet<String>>::new();
    let mut producer_to_consumers = BTreeMap::<String, BTreeSet<String>>::new();
    for edge in edges {
        let producer = edge.get("producer").and_then(Value::as_str).unwrap_or("");
        let consumer = edge.get("consumer").and_then(Value::as_str).unwrap_or("");
        if known_pipes.contains(producer) && known_pipes.contains(consumer) {
            consumer_to_producers
                .entry(consumer.to_string())
                .or_default()
                .insert(producer.to_string());
            producer_to_consumers
                .entry(producer.to_string())
                .or_default()
                .insert(consumer.to_string());
        }
    }

    let mut cycle_jobs_by_pipe = BTreeMap::<String, BTreeSet<String>>::new();
    for p in &pipeline_names {
        cycle_jobs_by_pipe.insert(p.clone(), find_cycle_jobs(jobs_by_pipe.get(p).expect("jobs")));
    }

    let mut initial_job_status_by_pipe = BTreeMap::<String, BTreeMap<String, String>>::new();
    let mut partial_resource_block_set = BTreeSet::<String>::new();
    for p in &pipeline_names {
        let jobs = jobs_by_pipe.get(p).expect("jobs");
        let has_cycle = !cycle_jobs_by_pipe.get(p).expect("cycle map").is_empty();
        let is_q = quarantined_pipes.contains(p);
        let statuses = compute_initial_job_status(jobs, has_cycle, is_q, &freeze_active_resources);
        if !has_cycle && !is_q && statuses.values().any(|v| v.as_str() == "blocked_resource_freeze") {
            partial_resource_block_set.insert(p.clone());
        }
        initial_job_status_by_pipe.insert(p.clone(), statuses);
    }

    let mut cascade_seeds = quarantined_pipes.clone();
    for p in &partial_resource_block_set {
        cascade_seeds.insert(p.clone());
    }
    let mut degraded_set = BTreeSet::<String>::new();
    let mut visited = cascade_seeds.clone();
    let mut queue = VecDeque::<String>::new();
    for s in &cascade_seeds {
        queue.push_back(s.clone());
    }
    while let Some(cur) = queue.pop_front() {
        let downs = producer_to_consumers.get(&cur).cloned().unwrap_or_default();
        for c in downs {
            if !quarantined_pipes.contains(&c) {
                degraded_set.insert(c.clone());
            }
            if !visited.contains(&c) {
                visited.insert(c.clone());
                queue.push_back(c);
            }
        }
    }

    let upstream_quarantined = |pipe: &str| -> Vec<String> {
        let mut out = BTreeSet::<String>::new();
        let mut seen = BTreeSet::<String>::new();
        let mut stack = vec![pipe.to_string()];
        while let Some(cur) = stack.pop() {
            for prod in consumer_to_producers
                .get(&cur)
                .cloned()
                .unwrap_or_default()
            {
                if seen.contains(&prod) {
                    continue;
                }
                seen.insert(prod.clone());
                if quarantined_pipes.contains(&prod) {
                    out.insert(prod.clone());
                }
                stack.push(prod);
            }
        }
        out.into_iter().collect()
    };

    let transitive_producers = |pipe: &str| -> BTreeSet<String> {
        let mut out = BTreeSet::<String>::new();
        let mut stack = vec![pipe.to_string()];
        while let Some(cur) = stack.pop() {
            for prod in consumer_to_producers
                .get(&cur)
                .cloned()
                .unwrap_or_default()
            {
                if out.insert(prod.clone()) {
                    stack.push(prod);
                }
            }
        }
        out
    };

    let mut pstatus_by_pipe = BTreeMap::<String, String>::new();
    for pipe in &pipeline_names {
        let has_cycle = !cycle_jobs_by_pipe.get(pipe).expect("cycle map").is_empty();
        let is_q = quarantined_pipes.contains(pipe);
        let in_degraded = degraded_set.contains(pipe);
        let in_partial = partial_resource_block_set.contains(pipe);
        let s = if has_cycle {
            "blocked_cycle"
        } else if is_q {
            "blocked_quarantine"
        } else if in_degraded {
            "degraded"
        } else if in_partial {
            "partial_resource_block"
        } else {
            "scheduled"
        };
        pstatus_by_pipe.insert(pipe.clone(), s.to_string());
    }

    let non_blocked = |p: &str| -> bool {
        let s = pstatus_by_pipe.get(p).map(String::as_str).unwrap_or("");
        s == "scheduled" || s == "degraded" || s == "partial_resource_block"
    };

    let mut chain_depth_by_pipe = BTreeMap::<String, i64>::new();
    {
        let mut consumer_topo: Vec<String> = Vec::new();
        let mut consumer_indeg: BTreeMap<String, i64> = BTreeMap::new();
        for p in &pipeline_names {
            consumer_indeg.insert(p.clone(), 0);
        }
        for p in &pipeline_names {
            let downs = producer_to_consumers.get(p).cloned().unwrap_or_default();
            for d in &downs {
                *consumer_indeg.get_mut(d).expect("indeg") += 1;
            }
        }
        let mut ready: Vec<String> = consumer_indeg
            .iter()
            .filter(|(_, &v)| v == 0)
            .map(|(k, _)| k.clone())
            .collect();
        ready.sort();
        let mut q: VecDeque<String> = VecDeque::from(ready);
        while let Some(cur) = q.pop_front() {
            consumer_topo.push(cur.clone());
            let downs = producer_to_consumers.get(&cur).cloned().unwrap_or_default();
            let mut next_ready = Vec::<String>::new();
            for d in downs {
                if let Some(v) = consumer_indeg.get_mut(&d) {
                    *v -= 1;
                    if *v == 0 {
                        next_ready.push(d);
                    }
                }
            }
            next_ready.sort();
            for r in next_ready {
                q.push_back(r);
            }
        }
        for pipe in consumer_topo.iter().rev() {
            if !non_blocked(pipe) {
                chain_depth_by_pipe.insert(pipe.clone(), 0);
                continue;
            }
            let downs = producer_to_consumers.get(pipe).cloned().unwrap_or_default();
            let mut best: i64 = 0;
            let mut found_consumer = false;
            for d in downs {
                if non_blocked(&d) {
                    found_consumer = true;
                    let cd = *chain_depth_by_pipe.get(&d).unwrap_or(&0);
                    if 1 + cd > best {
                        best = 1 + cd;
                    }
                }
            }
            chain_depth_by_pipe.insert(pipe.clone(), if found_consumer { best } else { 0 });
        }
    }

    let mut topo_order = Vec::<String>::new();
    {
        let mut indeg = BTreeMap::<String, i64>::new();
        for p in &pipeline_names {
            indeg.insert(p.clone(), 0);
        }
        for p in &pipeline_names {
            let producers = consumer_to_producers.get(p).cloned().unwrap_or_default();
            *indeg.get_mut(p).expect("indeg entry") = producers.len() as i64;
        }
        let mut ready: Vec<String> = indeg
            .iter()
            .filter(|(_, &v)| v == 0)
            .map(|(k, _)| k.clone())
            .collect();
        ready.sort();
        let mut q: VecDeque<String> = VecDeque::from(ready);
        while let Some(cur) = q.pop_front() {
            topo_order.push(cur.clone());
            let downs = producer_to_consumers.get(&cur).cloned().unwrap_or_default();
            let mut next_ready = Vec::<String>::new();
            for d in downs {
                if let Some(v) = indeg.get_mut(&d) {
                    *v -= 1;
                    if *v == 0 {
                        next_ready.push(d);
                    }
                }
            }
            next_ready.sort();
            for r in next_ready {
                q.push_back(r);
            }
        }
    }

    let mut total_by_pipe = BTreeMap::<String, i64>::new();
    let mut offset_by_pipe = BTreeMap::<String, i64>::new();
    let mut phase_runtimes_by_pipe = BTreeMap::<String, BTreeMap<i64, i64>>::new();
    let mut job_status_by_pipe = BTreeMap::<String, BTreeMap<String, String>>::new();
    let mut phases_by_pipe = BTreeMap::<String, BTreeMap<String, i64>>::new();
    let mut burst_by_pipe = BTreeMap::<String, i64>::new();
    let mut waves_by_pipe = BTreeMap::<String, BTreeMap<(i64, String), Vec<WaveEntry>>>::new();

    for pipe in &topo_order {
        let jobs = jobs_by_pipe.get(pipe).expect("jobs");
        let pstatus = pstatus_by_pipe.get(pipe).cloned().expect("pstatus");
        let cycle_jobs = cycle_jobs_by_pipe.get(pipe).expect("cycle map");
        let has_cycle = !cycle_jobs.is_empty();
        let phases = topological_phases(jobs, has_cycle);
        phases_by_pipe.insert(pipe.clone(), phases.clone());

        let initial_statuses = initial_job_status_by_pipe
            .get(pipe)
            .expect("initial statuses")
            .clone();
        let mut statuses = initial_statuses.clone();
        for (_, s) in statuses.iter_mut() {
            if pstatus == "degraded" && s == "scheduled" {
                *s = "degraded".to_string();
            }
        }
        job_status_by_pipe.insert(pipe.clone(), statuses.clone());

        let tier = get_str(manifests.get(pipe).expect("manifest"), "tier").to_string();
        let pen = *retry_penalty.get(&tier).expect("retry penalty for tier");

        let pipe_impaired = impaired_slots_for_status(&pstatus, &slots, &carve_out);
        let waves_map = if pstatus == "blocked_cycle" || pstatus == "blocked_quarantine" {
            BTreeMap::new()
        } else {
            build_phase_class_waves(jobs, &phases, &statuses, pen, &pipe_impaired)
        };

        let mut burst = 0_i64;
        if pstatus != "blocked_cycle" && pstatus != "blocked_quarantine" {
            let mut counts: BTreeMap<(i64, String), i64> = BTreeMap::new();
            for j in jobs {
                let name = get_str(j, "name").to_string();
                if statuses.get(&name).map(String::as_str) == Some("blocked_resource_freeze") {
                    continue;
                }
                let phase = *phases.get(&name).expect("phase");
                let rc = get_str(j, "resource_class").to_string();
                *counts.entry((phase, rc)).or_insert(0) += 1;
            }
            for ((_, rc), n) in counts.iter() {
                let cap = *slots.get(rc).expect("slot value");
                if *n > cap {
                    burst += 1;
                }
            }
        }
        let mut phase_runtimes = BTreeMap::<i64, i64>::new();
        for ((phase, _rc), waves) in waves_map.iter() {
            let class_total: i64 = waves.iter().map(|w| w.duration).sum();
            let cur = *phase_runtimes.get(phase).unwrap_or(&0);
            if class_total > cur {
                phase_runtimes.insert(*phase, class_total);
            }
        }
        burst_by_pipe.insert(pipe.clone(), burst);
        phase_runtimes_by_pipe.insert(pipe.clone(), phase_runtimes.clone());
        waves_by_pipe.insert(pipe.clone(), waves_map);

        let offset: i64 = if pstatus == "degraded" || pstatus == "partial_resource_block" {
            let producers = transitive_producers(pipe);
            let mut best: i64 = 0;
            for prod in &producers {
                let ps = pstatus_by_pipe.get(prod).cloned().unwrap_or_default();
                if ps == "scheduled" || ps == "degraded" || ps == "partial_resource_block" {
                    let t = *total_by_pipe.get(prod).unwrap_or(&0);
                    if t > best {
                        best = t;
                    }
                }
            }
            best
        } else {
            0
        };
        offset_by_pipe.insert(pipe.clone(), offset);

        let total: i64 = if pstatus == "blocked_cycle" || pstatus == "blocked_quarantine" {
            0
        } else {
            offset + phase_runtimes.values().sum::<i64>()
        };
        total_by_pipe.insert(pipe.clone(), total);
    }

    let mut pipeline_records = Vec::<Value>::new();
    let mut cycle_records = Vec::<Value>::new();
    let mut quarantine_records = Vec::<Value>::new();
    let mut wave_records = Vec::<Value>::new();
    let mut by_pipeline_status = BTreeMap::<String, i64>::from([
        ("blocked_cycle".to_string(), 0),
        ("blocked_quarantine".to_string(), 0),
        ("degraded".to_string(), 0),
        ("partial_resource_block".to_string(), 0),
        ("scheduled".to_string(), 0),
    ]);
    let mut by_job_status = BTreeMap::<String, i64>::from([
        ("blocked_cycle".to_string(), 0),
        ("blocked_quarantine".to_string(), 0),
        ("blocked_resource_freeze".to_string(), 0),
        ("degraded".to_string(), 0),
        ("scheduled".to_string(), 0),
    ]);
    let mut sla_violations = Vec::<String>::new();
    let mut total_jobs: i64 = 0;
    let mut minutes_demanded_by_rc = BTreeMap::<String, i64>::new();
    let mut minutes_blocked_by_rc = BTreeMap::<String, i64>::new();
    let mut burst_total: i64 = 0;

    for pipe in &pipeline_names {
        let manifest = manifests.get(pipe).expect("manifest");
        let jobs = jobs_by_pipe.get(pipe).expect("jobs");
        total_jobs += jobs.len() as i64;
        let tier = get_str(manifest, "tier").to_string();
        let cycle_jobs = cycle_jobs_by_pipe.get(pipe).expect("cycle map");
        let has_cycle = !cycle_jobs.is_empty();

        cycle_records.push({
            let mut m = Map::new();
            m.insert("name".to_string(), Value::String(pipe.clone()));
            m.insert("has_cycle".to_string(), Value::Bool(has_cycle));
            m.insert(
                "cycle_jobs".to_string(),
                Value::Array(cycle_jobs.iter().cloned().map(Value::String).collect()),
            );
            Value::Object(m)
        });

        let pstatus = pstatus_by_pipe.get(pipe).cloned().expect("pstatus");
        let is_q = quarantined_pipes.contains(pipe);
        let in_degraded = degraded_set.contains(pipe);

        let phases = phases_by_pipe.get(pipe).cloned().expect("phases");
        let statuses = job_status_by_pipe.get(pipe).cloned().expect("statuses");
        let phase_runtimes = phase_runtimes_by_pipe.get(pipe).cloned().expect("phase rt");
        let offset = *offset_by_pipe.get(pipe).unwrap_or(&0);
        let total_runtime = *total_by_pipe.get(pipe).unwrap_or(&0);
        let waves_map = waves_by_pipe.get(pipe).cloned().unwrap_or_default();
        let burst = *burst_by_pipe.get(pipe).unwrap_or(&0);
        burst_total += burst;
        let chain_depth = *chain_depth_by_pipe.get(pipe).unwrap_or(&0);

        let mut per_job = Vec::<JobRecord>::new();
        for j in jobs {
            let name = get_str(j, "name").to_string();
            let rc = get_str(j, "resource_class").to_string();
            let base_p = get_i64(j, "base_priority");
            let rt = get_i64(j, "runtime_minutes");
            let retry = get_i64(j, "retry_count");
            let phase = *phases.get(&name).expect("phase");
            let s = statuses.get(&name).cloned().unwrap_or_else(|| "scheduled".to_string());
            per_job.push(JobRecord {
                name,
                phase,
                rc,
                rt,
                retry,
                base_p,
                status: s,
                ep: 0,
                start: None,
                end: None,
            });
        }

        let tier_int = *tier_mod.get(&tier).expect("tier modifier");
        for jrec in &mut per_job {
            let mut ep = jrec.base_p * tier_int;
            if pstatus == "degraded" {
                ep += 100;
            }
            jrec.ep = ep;
        }

        if pstatus == "blocked_cycle" || pstatus == "blocked_quarantine" {
            for jrec in &mut per_job {
                jrec.start = None;
                jrec.end = None;
            }
        } else {
            let pen = *retry_penalty.get(&tier).expect("retry penalty for tier");
            let mut all_phases: BTreeSet<i64> = phases.values().cloned().collect();
            for ((ph, _rc), _) in waves_map.iter() {
                all_phases.insert(*ph);
            }
            let mut ordered_phases: Vec<i64> = all_phases.into_iter().collect();
            ordered_phases.sort();
            let mut phase_starts = BTreeMap::<i64, i64>::new();
            let mut cumulative = offset;
            for ph in &ordered_phases {
                phase_starts.insert(*ph, cumulative);
                cumulative += *phase_runtimes.get(ph).unwrap_or(&0);
            }
            for jrec in &mut per_job {
                if jrec.status == "blocked_resource_freeze" {
                    jrec.start = None;
                    jrec.end = None;
                    continue;
                }
                let waves = waves_map
                    .get(&(jrec.phase, jrec.rc.clone()))
                    .expect("waves for (phase, rc)");
                let mut wave_idx_opt: Option<usize> = None;
                for (i, w) in waves.iter().enumerate() {
                    if w.members.iter().any(|n| n == &jrec.name) {
                        wave_idx_opt = Some(i);
                        break;
                    }
                }
                let wave_idx = wave_idx_opt.expect("non-frozen job in some wave");
                let mut wave_offset = 0_i64;
                for k in 0..wave_idx {
                    wave_offset += waves[k].duration;
                }
                let phase_start = *phase_starts.get(&jrec.phase).expect("phase start");
                let start = phase_start + wave_offset;
                let eff = jrec.rt + jrec.retry * pen;
                jrec.start = Some(start);
                jrec.end = Some(start + eff);
            }
        }

        let up_q = if pstatus == "degraded" {
            upstream_quarantined(pipe)
        } else {
            Vec::new()
        };
        let base_sla = if pstatus == "blocked_quarantine" {
            0
        } else {
            get_i64(manifest, "sla_hours") * 60 + sla_grace_by_pipe.get(pipe).cloned().unwrap_or(0)
        };
        let pre_sla = if pstatus == "degraded" {
            std::cmp::max(0, base_sla - sla_debit_per_upstream * up_q.len() as i64)
        } else if pstatus == "partial_resource_block" {
            let mult = *partial_sla_mult.get(&tier).expect("partial block sla mult");
            (base_sla * mult) / 100
        } else {
            base_sla
        };
        let burst_sla = if pstatus == "blocked_cycle" || pstatus == "blocked_quarantine" {
            pre_sla
        } else {
            std::cmp::max(0, pre_sla - wave_debit * burst)
        };
        let eff_sla = if pstatus == "blocked_cycle" || pstatus == "blocked_quarantine" {
            burst_sla
        } else {
            std::cmp::max(0, burst_sla - chain_debit * chain_depth)
        };
        let sla_met = if pstatus == "blocked_cycle" || pstatus == "blocked_quarantine" {
            true
        } else {
            total_runtime <= eff_sla
        };
        if !sla_met {
            sla_violations.push(pipe.clone());
        }

        per_job.sort_by(|a, b| (a.phase, a.ep, &a.name).cmp(&(b.phase, b.ep, &b.name)));

        let jobs_out = per_job
            .iter()
            .map(|jrec| {
                let mut m = Map::new();
                m.insert("name".to_string(), Value::String(jrec.name.clone()));
                m.insert("phase".to_string(), Value::Number(Number::from(jrec.phase)));
                m.insert(
                    "effective_priority".to_string(),
                    Value::Number(Number::from(jrec.ep)),
                );
                m.insert(
                    "resource_class".to_string(),
                    Value::String(jrec.rc.clone()),
                );
                m.insert(
                    "runtime_minutes".to_string(),
                    Value::Number(Number::from(jrec.rt)),
                );
                m.insert(
                    "start_minute".to_string(),
                    jrec.start.map_or(Value::Null, |v| Value::Number(Number::from(v))),
                );
                m.insert(
                    "end_minute".to_string(),
                    jrec.end.map_or(Value::Null, |v| Value::Number(Number::from(v))),
                );
                m.insert("status".to_string(), Value::String(jrec.status.clone()));
                Value::Object(m)
            })
            .collect::<Vec<_>>();

        pipeline_records.push({
            let mut m = Map::new();
            m.insert("name".to_string(), Value::String(pipe.clone()));
            m.insert("tier".to_string(), Value::String(tier.clone()));
            m.insert("pipeline_status".to_string(), Value::String(pstatus.clone()));
            m.insert(
                "upstream_offset_minutes".to_string(),
                Value::Number(Number::from(offset)),
            );
            m.insert(
                "effective_sla_minutes".to_string(),
                Value::Number(Number::from(eff_sla)),
            );
            m.insert(
                "total_runtime_minutes".to_string(),
                Value::Number(Number::from(total_runtime)),
            );
            m.insert("sla_met".to_string(), Value::Bool(sla_met));
            m.insert("jobs".to_string(), Value::Array(jobs_out));
            Value::Object(m)
        });

        if pstatus != "blocked_cycle" && pstatus != "blocked_quarantine" {
            let mut phases_obj = BTreeMap::<i64, BTreeMap<String, &Vec<WaveEntry>>>::new();
            for ((ph, rc), waves) in waves_map.iter() {
                phases_obj.entry(*ph).or_default().insert(rc.clone(), waves);
            }
            let mut phase_arr = Vec::<Value>::new();
            for (ph, rcs) in phases_obj.iter() {
                let mut rc_arr = Vec::<Value>::new();
                for (rc, waves) in rcs.iter() {
                    let mut wave_arr = Vec::<Value>::new();
                    for w in waves.iter() {
                        let mut sorted_members = w.members.clone();
                        sorted_members.sort();
                        let mut wm = Map::new();
                        wm.insert(
                            "wave_index".to_string(),
                            Value::Number(Number::from(w.wave_index)),
                        );
                        wm.insert(
                            "duration_minutes".to_string(),
                            Value::Number(Number::from(w.duration)),
                        );
                        wm.insert(
                            "jobs".to_string(),
                            Value::Array(sorted_members.into_iter().map(Value::String).collect()),
                        );
                        wave_arr.push(Value::Object(wm));
                    }
                    let mut rcm = Map::new();
                    rcm.insert("resource_class".to_string(), Value::String(rc.clone()));
                    rcm.insert("waves".to_string(), Value::Array(wave_arr));
                    rc_arr.push(Value::Object(rcm));
                }
                let mut pm = Map::new();
                pm.insert("phase".to_string(), Value::Number(Number::from(*ph)));
                pm.insert("resource_classes".to_string(), Value::Array(rc_arr));
                phase_arr.push(Value::Object(pm));
            }
            let mut wm = Map::new();
            wm.insert("name".to_string(), Value::String(pipe.clone()));
            wm.insert(
                "burst_pressure".to_string(),
                Value::Number(Number::from(burst)),
            );
            wm.insert("phases".to_string(), Value::Array(phase_arr));
            wave_records.push(Value::Object(wm));
        }

        *by_pipeline_status.entry(pstatus.clone()).or_insert(0) += 1;
        for jrec in &per_job {
            *by_job_status.entry(jrec.status.clone()).or_insert(0) += 1;
        }

        if pstatus != "blocked_cycle" && pstatus != "blocked_quarantine" {
            for jrec in &per_job {
                *minutes_demanded_by_rc.entry(jrec.rc.clone()).or_insert(0) += jrec.rt;
                if jrec.status == "blocked_resource_freeze" {
                    *minutes_blocked_by_rc.entry(jrec.rc.clone()).or_insert(0) += jrec.rt;
                }
            }
        }

        let qstate = if is_q {
            "quarantined"
        } else if in_degraded {
            "degraded"
        } else {
            "normal"
        };
        let mut q_jobs = quarantine_events_by_pipe.get(pipe).cloned().unwrap_or_default();
        q_jobs.sort();

        quarantine_records.push({
            let mut m = Map::new();
            m.insert("name".to_string(), Value::String(pipe.clone()));
            m.insert(
                "quarantine_state".to_string(),
                Value::String(qstate.to_string()),
            );
            m.insert(
                "quarantined_jobs".to_string(),
                Value::Array(q_jobs.into_iter().map(Value::String).collect()),
            );
            m.insert(
                "upstream_quarantined".to_string(),
                Value::Array(up_q.iter().cloned().map(Value::String).collect()),
            );
            Value::Object(m)
        });
    }

    pipeline_records.sort_by(|a, b| a["name"].as_str().cmp(&b["name"].as_str()));
    cycle_records.sort_by(|a, b| a["name"].as_str().cmp(&b["name"].as_str()));
    quarantine_records.sort_by(|a, b| a["name"].as_str().cmp(&b["name"].as_str()));
    wave_records.sort_by(|a, b| a["name"].as_str().cmp(&b["name"].as_str()));
    sla_violations.sort();

    let mut schedule_doc = Map::new();
    schedule_doc.insert("pipelines".to_string(), Value::Array(pipeline_records));
    write_json(&out.join("schedule_plan.json"), &Value::Object(schedule_doc));

    let mut cycle_doc = Map::new();
    cycle_doc.insert("pipelines".to_string(), Value::Array(cycle_records));
    write_json(&out.join("cycle_report.json"), &Value::Object(cycle_doc));

    let mut quarantine_doc = Map::new();
    quarantine_doc.insert("pipelines".to_string(), Value::Array(quarantine_records));
    write_json(
        &out.join("quarantine_status.json"),
        &Value::Object(quarantine_doc),
    );

    let mut wave_doc = Map::new();
    wave_doc.insert("pipelines".to_string(), Value::Array(wave_records));
    write_json(&out.join("wave_plan.json"), &Value::Object(wave_doc));

    let mut rc_records = Vec::<Value>::new();
    for rc in slots.keys() {
        let mut m = Map::new();
        m.insert("resource_class".to_string(), Value::String(rc.clone()));
        m.insert(
            "slots_total".to_string(),
            Value::Number(Number::from(*slots.get(rc).expect("slot value"))),
        );
        m.insert(
            "minutes_demanded".to_string(),
            Value::Number(Number::from(*minutes_demanded_by_rc.get(rc).unwrap_or(&0))),
        );
        m.insert(
            "minutes_blocked_by_freeze".to_string(),
            Value::Number(Number::from(*minutes_blocked_by_rc.get(rc).unwrap_or(&0))),
        );
        m.insert(
            "active_freeze".to_string(),
            Value::Bool(freeze_active_resources.contains(rc)),
        );
        rc_records.push(Value::Object(m));
    }
    let mut rc_doc = Map::new();
    rc_doc.insert("by_resource_class".to_string(), Value::Array(rc_records));
    write_json(&out.join("resource_utilization.json"), &Value::Object(rc_doc));

    let mut summary = Map::new();
    summary.insert(
        "current_day".to_string(),
        Value::Number(Number::from(current_day)),
    );
    summary.insert("scheduler_version".to_string(), Value::String(sched_ver));
    summary.insert(
        "total_pipelines".to_string(),
        Value::Number(Number::from(pipeline_names.len() as i64)),
    );
    summary.insert(
        "total_jobs".to_string(),
        Value::Number(Number::from(total_jobs)),
    );
    summary.insert(
        "ignored_incident_events".to_string(),
        Value::Number(Number::from(ignored)),
    );
    let mut by_pipeline_status_obj = Map::new();
    for (k, v) in by_pipeline_status {
        by_pipeline_status_obj.insert(k, Value::Number(Number::from(v)));
    }
    summary.insert(
        "by_pipeline_status".to_string(),
        Value::Object(by_pipeline_status_obj),
    );
    let mut by_job_status_obj = Map::new();
    for (k, v) in by_job_status {
        by_job_status_obj.insert(k, Value::Number(Number::from(v)));
    }
    summary.insert("by_job_status".to_string(), Value::Object(by_job_status_obj));
    summary.insert(
        "sla_violations".to_string(),
        Value::Array(sla_violations.into_iter().map(Value::String).collect()),
    );
    summary.insert(
        "burst_pressure_total".to_string(),
        Value::Number(Number::from(burst_total)),
    );
    write_json(&out.join("summary.json"), &Value::Object(summary));
}
RS_EOF

cd "${PLANNER_DIR}"
cargo build --release --locked
"${PLANNER_DIR}/target/release/planner"
