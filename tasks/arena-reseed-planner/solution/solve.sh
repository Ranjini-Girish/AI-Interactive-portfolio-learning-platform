#!/bin/bash
set -euo pipefail

cat <<'RS' > /app/planner/src/main.rs
use serde::{Deserialize, Serialize};
use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Deserialize)]
struct Team {
    team_id: String,
    tier: String,
    seed_score: i64,
    home_region: String,
    stamina: i64,
    roster_size: i64,
    preferred_arena_ids: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
struct Arena {
    arena_id: String,
    region: String,
    capacity_band: String,
}

#[derive(Debug, Deserialize)]
struct Policy {
    min_stamina: i64,
    min_roster_size: i64,
    max_matches_per_arena: i64,
    participation_points: i64,
    rivalry_bonus: i64,
    suspended_penalty: i64,
    tier_priority: HashMap<String, i64>,
    rivalry_pairs: Vec<[String; 2]>,
}

#[derive(Debug, Deserialize)]
struct PoolState {
    current_day: i64,
}

#[derive(Debug, Clone, Deserialize)]
struct Incident {
    event_id: String,
    day: i64,
    accepted: bool,
    kind: String,
    team_id: Option<String>,
    arena_id: Option<String>,
    new_stamina: Option<i64>,
}

#[derive(Debug, Serialize)]
struct MatchRow {
    arena_id: Option<String>,
    arena_locked_bypass: bool,
    match_id: String,
    rivalry: bool,
    status: String,
    team_a: String,
    team_b: String,
}

#[derive(Debug, Serialize)]
struct ArenaLoadRow {
    arena_id: String,
    locked: bool,
    overbooked: bool,
    scheduled_count: i64,
}

#[derive(Debug, Serialize)]
struct BenchRow {
    effective_stamina: i64,
    reason: String,
    team_id: String,
}

#[derive(Debug, Serialize)]
struct StandingRow {
    projected_points: i64,
    status: String,
    team_id: String,
}

fn read_json<T: for<'de> Deserialize<'de>>(path: &Path) -> T {
    let content = fs::read_to_string(path).unwrap_or_else(|_| panic!("failed to read {}", path.display()));
    serde_json::from_str(&content).unwrap_or_else(|_| panic!("invalid json {}", path.display()))
}

fn write_json<T: Serialize>(path: &Path, value: &T) {
    let content = serde_json::to_string_pretty(value).expect("serialize failed");
    fs::write(path, content).unwrap_or_else(|_| panic!("failed to write {}", path.display()));
}

fn pair_key(a: &str, b: &str) -> String {
    if a <= b {
        format!("{}|{}", a, b)
    } else {
        format!("{}|{}", b, a)
    }
}

fn capacity_bonus(capacity_band: &str) -> i64 {
    match capacity_band {
        "large" => 2,
        "medium" => 1,
        _ => 0,
    }
}

fn arena_score(arena: &Arena, a: &Team, b: &Team) -> i64 {
    let mut score = 0;
    if arena.region == a.home_region && arena.region == b.home_region {
        score += 2;
    } else if arena.region == a.home_region || arena.region == b.home_region {
        score += 1;
    }
    if a.preferred_arena_ids.iter().any(|x| x == &arena.arena_id)
        || b.preferred_arena_ids.iter().any(|x| x == &arena.arena_id)
    {
        score += 1;
    }
    score + capacity_bonus(&arena.capacity_band)
}

fn main() {
    let data_dir = PathBuf::from(env::var("ARP_DATA_DIR").unwrap_or_else(|_| "/app/league".to_string()));
    let out_dir = PathBuf::from(env::var("ARP_OUTPUT_DIR").unwrap_or_else(|_| "/app/plan".to_string()));
    fs::create_dir_all(&out_dir).expect("failed to create output dir");

    let policy: Policy = read_json(&data_dir.join("policy.json"));
    let pool: PoolState = read_json(&data_dir.join("pool_state.json"));
    let incidents: Vec<Incident> = read_json(&data_dir.join("incident_log.json"));

    let mut teams: Vec<Team> = Vec::new();
    for entry in fs::read_dir(data_dir.join("teams")).expect("missing teams dir") {
        let path = entry.expect("bad teams dir entry").path();
        if path.extension().and_then(|s| s.to_str()) == Some("json") {
            teams.push(read_json(&path));
        }
    }
    teams.sort_by(|a, b| a.team_id.cmp(&b.team_id));

    let mut arenas: Vec<Arena> = Vec::new();
    for entry in fs::read_dir(data_dir.join("arenas")).expect("missing arenas dir") {
        let path = entry.expect("bad arenas dir entry").path();
        if path.extension().and_then(|s| s.to_str()) == Some("json") {
            arenas.push(read_json(&path));
        }
    }
    arenas.sort_by(|a, b| a.arena_id.cmp(&b.arena_id));

    let active_incidents: Vec<Incident> = incidents
        .into_iter()
        .filter(|e| e.accepted && e.day <= pool.current_day)
        .collect();

    let mut suspended: BTreeSet<String> = BTreeSet::new();
    let mut locked_arenas: BTreeSet<String> = BTreeSet::new();
    let mut overrides: HashMap<String, (i64, String, i64)> = HashMap::new();

    for e in &active_incidents {
        match e.kind.as_str() {
            "suspension" => {
                if let Some(team) = &e.team_id {
                    suspended.insert(team.clone());
                }
            }
            "arena_lock" => {
                if let Some(arena) = &e.arena_id {
                    locked_arenas.insert(arena.clone());
                }
            }
            "stamina_override" => {
                if let (Some(team), Some(new_stamina)) = (&e.team_id, e.new_stamina) {
                    match overrides.get(team) {
                        None => {
                            overrides.insert(team.clone(), (e.day, e.event_id.clone(), new_stamina));
                        }
                        Some((prev_day, prev_id, _)) => {
                            if e.day > *prev_day || (e.day == *prev_day && e.event_id < *prev_id) {
                                overrides.insert(team.clone(), (e.day, e.event_id.clone(), new_stamina));
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }

    let mut effective_stamina: HashMap<String, i64> = HashMap::new();
    for team in &teams {
        let base = team.stamina;
        let value = overrides
            .get(&team.team_id)
            .map(|(_, _, s)| *s)
            .unwrap_or(base);
        effective_stamina.insert(team.team_id.clone(), value);
    }

    let mut bench_reason: HashMap<String, String> = HashMap::new();
    let mut active: Vec<Team> = Vec::new();

    for team in &teams {
        let eff = *effective_stamina.get(&team.team_id).unwrap_or(&team.stamina);
        if suspended.contains(&team.team_id) {
            bench_reason.insert(team.team_id.clone(), "suspended".to_string());
            continue;
        }
        if team.roster_size < policy.min_roster_size {
            bench_reason.insert(team.team_id.clone(), "small_roster".to_string());
            continue;
        }
        if eff < policy.min_stamina {
            bench_reason.insert(team.team_id.clone(), "low_stamina".to_string());
            continue;
        }
        active.push(team.clone());
    }

    active.sort_by(|a, b| {
        let a_rank = *policy.tier_priority.get(&a.tier).unwrap_or(&0);
        let b_rank = *policy.tier_priority.get(&b.tier).unwrap_or(&0);
        match b_rank.cmp(&a_rank) {
            Ordering::Equal => match b.seed_score.cmp(&a.seed_score) {
                Ordering::Equal => a.team_id.cmp(&b.team_id),
                other => other,
            },
            other => other,
        }
    });

    let rivalry_set: BTreeSet<String> = policy
        .rivalry_pairs
        .iter()
        .map(|p| pair_key(&p[0], &p[1]))
        .collect();

    let mut arena_counts: HashMap<String, i64> = HashMap::new();
    for arena in &arenas {
        arena_counts.insert(arena.arena_id.clone(), 0);
    }

    let mut match_rows: Vec<MatchRow> = Vec::new();
    let mut projected_points: HashMap<String, i64> = HashMap::new();
    for team in &teams {
        projected_points.insert(team.team_id.clone(), 0);
    }

    let mut rivalry_matches = 0;
    let mut index = 0usize;
    let mut match_num = 1usize;
    while index + 1 < active.len() {
        let a = &active[index];
        let b = &active[index + 1];
        let rivalry = rivalry_set.contains(&pair_key(&a.team_id, &b.team_id));
        if rivalry {
            rivalry_matches += 1;
        }

        let mut best_arena: Option<&Arena> = None;
        let mut best_score: i64 = i64::MIN;

        for arena in &arenas {
            let used = *arena_counts.get(&arena.arena_id).unwrap_or(&0);
            let eligible = if rivalry {
                true
            } else {
                !locked_arenas.contains(&arena.arena_id) && used < policy.max_matches_per_arena
            };
            if !eligible {
                continue;
            }
            let score = arena_score(arena, a, b);
            if best_arena.is_none()
                || score > best_score
                || (score == best_score && arena.arena_id < best_arena.expect("best arena").arena_id)
            {
                best_score = score;
                best_arena = Some(arena);
            }
        }

        let match_id = format!("m{:02}", match_num);
        match_num += 1;

        match best_arena {
            None => {
                match_rows.push(MatchRow {
                    arena_id: None,
                    arena_locked_bypass: false,
                    match_id,
                    rivalry,
                    status: "unassigned".to_string(),
                    team_a: a.team_id.clone(),
                    team_b: b.team_id.clone(),
                });
            }
            Some(arena) => {
                let bypass = rivalry && locked_arenas.contains(&arena.arena_id);
                let current = *arena_counts.get(&arena.arena_id).unwrap_or(&0);
                arena_counts.insert(arena.arena_id.clone(), current + 1);

                let mut base = policy.participation_points;
                if rivalry {
                    base += policy.rivalry_bonus;
                }
                *projected_points.entry(a.team_id.clone()).or_insert(0) += base;
                *projected_points.entry(b.team_id.clone()).or_insert(0) += base;

                match_rows.push(MatchRow {
                    arena_id: Some(arena.arena_id.clone()),
                    arena_locked_bypass: bypass,
                    match_id,
                    rivalry,
                    status: "scheduled".to_string(),
                    team_a: a.team_id.clone(),
                    team_b: b.team_id.clone(),
                });
            }
        }

        index += 2;
    }

    if index < active.len() {
        let odd_team = &active[index];
        bench_reason.insert(odd_team.team_id.clone(), "odd_team_out".to_string());
    }

    for team_id in &suspended {
        *projected_points.entry(team_id.clone()).or_insert(0) += policy.suspended_penalty;
    }

    let mut arena_load: Vec<ArenaLoadRow> = arenas
        .iter()
        .map(|arena| {
            let count = *arena_counts.get(&arena.arena_id).unwrap_or(&0);
            ArenaLoadRow {
                arena_id: arena.arena_id.clone(),
                locked: locked_arenas.contains(&arena.arena_id),
                overbooked: count > policy.max_matches_per_arena,
                scheduled_count: count,
            }
        })
        .collect();
    arena_load.sort_by(|a, b| a.arena_id.cmp(&b.arena_id));

    let mut bench_rows: Vec<BenchRow> = bench_reason
        .iter()
        .map(|(team_id, reason)| BenchRow {
            effective_stamina: *effective_stamina.get(team_id).unwrap_or(&0),
            reason: reason.clone(),
            team_id: team_id.clone(),
        })
        .collect();
    bench_rows.sort_by(|a, b| a.team_id.cmp(&b.team_id));

    let benched_ids: BTreeSet<String> = bench_rows.iter().map(|x| x.team_id.clone()).collect();
    let mut standings: Vec<StandingRow> = teams
        .iter()
        .map(|team| StandingRow {
            projected_points: *projected_points.get(&team.team_id).unwrap_or(&0),
            status: if benched_ids.contains(&team.team_id) {
                "benched".to_string()
            } else {
                "active".to_string()
            },
            team_id: team.team_id.clone(),
        })
        .collect();
    standings.sort_by(|a, b| a.team_id.cmp(&b.team_id));

    let matches_scheduled = match_rows.iter().filter(|m| m.status == "scheduled").count() as i64;
    let matches_unassigned = match_rows.iter().filter(|m| m.status == "unassigned").count() as i64;
    let suspended_count = bench_rows.iter().filter(|b| b.reason == "suspended").count() as i64;
    let overbooked_arenas = arena_load.iter().filter(|a| a.overbooked).count() as i64;

    let mut summary = BTreeMap::new();
    summary.insert("active_teams", active.len() as i64);
    summary.insert("benched_count", bench_rows.len() as i64);
    summary.insert("locked_arenas", locked_arenas.len() as i64);
    summary.insert("matches_scheduled", matches_scheduled);
    summary.insert("matches_unassigned", matches_unassigned);
    summary.insert("overbooked_arenas", overbooked_arenas);
    summary.insert("rivalry_matches", rivalry_matches as i64);
    summary.insert("suspended_count", suspended_count);
    summary.insert("total_teams", teams.len() as i64);

    write_json(&out_dir.join("match_plan.json"), &match_rows);
    write_json(&out_dir.join("arena_load.json"), &arena_load);
    write_json(&out_dir.join("bench_report.json"), &bench_rows);
    write_json(&out_dir.join("standings_projection.json"), &standings);
    write_json(&out_dir.join("summary.json"), &summary);
}
RS

cd /app/planner
cargo run --quiet
