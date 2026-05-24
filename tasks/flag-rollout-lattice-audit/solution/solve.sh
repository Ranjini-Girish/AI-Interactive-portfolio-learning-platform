#!/bin/bash
set -euo pipefail
APP_DIR=${FRLA_APP_DIR:-/app}
mkdir -p "$APP_DIR/rollout/src"
cat > "$APP_DIR/rollout/src/main.ts" <<'TSEOF'
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

type AnyRow = Record<string, any>;

const args = process.argv.slice(2);
function arg(name: string, fallback: string): string {
  const idx = args.indexOf(name);
  if (idx >= 0 && idx + 1 < args.length) return args[idx + 1];
  return fallback;
}

const DATA = arg("--input", process.env.FRLA_FLAGS_DIR ?? "/app/flags");
const OUT = arg("--output", process.env.FRLA_AUDIT_DIR ?? "/app/audit");

function load(path: string): any {
  return JSON.parse(readFileSync(path, "utf8"));
}

function writeJson(name: string, value: any) {
  writeFileSync(join(OUT, name), JSON.stringify(sortValue(value), null, 2) + "\n");
}

function sortValue(value: any): any {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === "object") {
    const out: AnyRow = {};
    for (const key of Object.keys(value).sort()) out[key] = sortValue(value[key]);
    return out;
  }
  return value;
}

const policy = load(join(DATA, "policy.json"));
const pool = load(join(DATA, "pool_state.json"));
const dependencies = load(join(DATA, "dependencies.json"));
const segments: AnyRow = {};
for (const file of readdirSync(join(DATA, "segments")).sort()) {
  const row = load(join(DATA, "segments", file));
  segments[row.segment_id] = row;
}
const flags: AnyRow = {};
for (const file of readdirSync(join(DATA, "flags")).sort()) {
  const row = load(join(DATA, "flags", file));
  flags[row.flag_id] = row;
}
const incidents = load(join(DATA, "incidents", "incident_log.json")).events;
const exposures: AnyRow[] = [];
for (const file of readdirSync(join(DATA, "exposures")).sort()) {
  for (const row of load(join(DATA, "exposures", file)).records) exposures.push(row);
}

function descendants(start: string): string[] {
  const out: string[] = [];
  const stack = [start];
  while (stack.length) {
    const cur = stack.pop() as string;
    out.push(cur);
    const children = Object.keys(segments).filter((sid) => segments[sid].parent_id === cur).sort();
    for (const child of children.reverse()) stack.push(child);
  }
  return out;
}

function ancestors(start: string): string[] {
  const out: string[] = [];
  let cur: string | null = start;
  while (cur !== null) {
    out.push(cur);
    cur = segments[cur].parent_id;
  }
  return out;
}

const currentDay = pool.current_day;
const accepted: AnyRow[] = [];
const ignored: AnyRow[] = [];
for (const row of [...incidents].sort((a, b) => a.day - b.day || a.event_id.localeCompare(b.event_id))) {
  let reason: string | null = null;
  if (!row.valid) reason = "invalid";
  else if (row.day > currentDay) reason = "future_day";
  else if (!policy.supported_incidents.includes(row.kind)) reason = "unsupported_kind";
  if (reason) ignored.push({ event_id: row.event_id, kind: row.kind, reason });
  else accepted.push(row);
}

const budgetDelta: AnyRow = Object.fromEntries(Object.keys(flags).map((f) => [f, 0]));
const killed = new Set<string>();
const forcedActive = new Set<string>();
const locks: AnyRow = {};
const compromised = new Set<string>();
const waivers = new Set<string>();
const applied: AnyRow[] = [];
for (const row of accepted) {
  const clean: AnyRow = {};
  for (const key of Object.keys(row).sort()) if (key !== "valid") clean[key] = row[key];
  applied.push(clean);
  if (row.kind === "budget_grant") budgetDelta[row.flag_id] += row.delta_pct;
  if (row.kind === "kill_switch") killed.add(row.flag_id);
  if (row.kind === "force_state" && row.state === "active") forcedActive.add(row.flag_id);
  if (row.kind === "segment_lock") {
    const until = row.day + row.duration_days - 1 + policy.tiers.gold.lock_grace_days;
    for (const sid of descendants(row.segment_id)) locks[sid] = Math.max(locks[sid] ?? -1, until);
  }
  if (row.kind === "segment_compromise") for (const sid of descendants(row.segment_id)) compromised.add(sid);
  if (row.kind === "dependency_waiver" && row.day + row.duration_days - 1 >= currentDay) waivers.add(`${row.flag_id}\0${row.depends_on}`);
}

const activeEdges = dependencies.edges.filter((e: AnyRow) => !waivers.has(`${e.flag_id}\0${e.depends_on}`));
const byFlag: AnyRow = Object.fromEntries(Object.keys(flags).map((f) => [f, activeEdges.filter((e: AnyRow) => e.flag_id === f).map((e: AnyRow) => e.depends_on).sort()]));
const visiting = new Set<string>();
const memo: AnyRow = {};
const cycleNodes = new Set<string>();
function wave(fid: string): number | null {
  if (Object.prototype.hasOwnProperty.call(memo, fid)) return memo[fid];
  if (visiting.has(fid)) {
    for (const n of visiting) cycleNodes.add(n);
    return null;
  }
  visiting.add(fid);
  const vals: number[] = [];
  for (const dep of byFlag[fid]) {
    const val = wave(dep);
    if (val === null) cycleNodes.add(fid);
    else vals.push(val);
  }
  visiting.delete(fid);
  memo[fid] = cycleNodes.has(fid) ? null : vals.length ? Math.max(...vals) + 1 : 0;
  return memo[fid];
}
for (const fid of Object.keys(flags).sort()) wave(fid);

const rollouts: AnyRow[] = [];
const allowedByFlag: AnyRow = Object.fromEntries(Object.keys(flags).map((f) => [f, 0]));
for (const fid of Object.keys(flags).sort()) {
  const flag = flags[fid];
  for (const sid of Object.keys(segments).sort()) {
    const candidates = flag.overrides
      .map((ov: AnyRow, idx: number) => ({ ov, idx }))
      .filter((x: AnyRow) => ancestors(sid).includes(x.ov.segment_id))
      .sort((a: AnyRow, b: AnyRow) => b.ov.priority - a.ov.priority || a.idx - b.idx || a.ov.segment_id.localeCompare(b.ov.segment_id));
    let pct = flag.default_pct;
    let source = "default";
    if (candidates.length) {
      pct = candidates[0].ov.pct;
      source = candidates[0].ov.segment_id;
    }
    const reasons = new Set<string>();
    let state = "active";
    if (cycleNodes.has(fid) || byFlag[fid].some((dep: string) => killed.has(dep))) {
      state = "blocked_dependency";
      pct = 0;
      reasons.add("dependency_block");
    }
    if ((locks[sid] ?? -1) >= currentDay) {
      if (state === "active") state = "locked";
      pct = 0;
      reasons.add("segment_lock");
    }
    const cap = policy.tiers[flag.tier].max_pct;
    if (pct > cap) {
      pct = cap;
      reasons.add("tier_cap");
    }
    if (forcedActive.has(fid) && (state === "blocked_dependency" || state === "locked")) {
      state = "active";
      reasons.add("force_state_active");
    }
    if (killed.has(fid)) {
      state = "killed";
      pct = 0;
      reasons.add("kill_switch");
    }
    if (compromised.has(sid)) {
      state = "quarantined";
      pct = 0;
      reasons.add("segment_compromise");
    }
    allowedByFlag[fid] += Math.floor((segments[sid].size * pct) / 100);
    rollouts.push({ flag_id: fid, segment_id: sid, effective_pct: pct, state, source_segment: source, reasons: [...reasons].sort() });
  }
}

const observed: AnyRow = Object.fromEntries(Object.keys(flags).map((f) => [f, 0]));
for (const row of exposures) observed[row.flag_id] += row.users;
const totalPop = Object.values(segments).reduce((acc: number, s: any) => acc + s.size, 0);
const budgetRows = Object.keys(flags).sort().map((fid) => {
  const flag = flags[fid];
  const budgetPct = policy.tiers[flag.tier].default_budget_pct + budgetDelta[fid];
  const allowedUsers = Math.min(Math.floor((totalPop * budgetPct) / 100), allowedByFlag[fid]);
  let status = "within_budget";
  if (killed.has(fid)) status = "killed";
  else if (exposures.some((r) => r.flag_id === fid && compromised.has(r.segment_id))) status = "quarantine_exposure";
  else if (observed[fid] > allowedUsers) status = "over_budget";
  return { flag_id: fid, observed_users: observed[fid], allowed_users: allowedUsers, budget_pct: budgetPct, budget_delta_pct: budgetDelta[fid], status };
});

const waveRows = Object.keys(flags).sort().map((fid) => {
  if (cycleNodes.has(fid)) return { flag_id: fid, wave: null, dependency_status: "cycle_blocked", blocked_by: byFlag[fid].slice().sort() };
  const killedDeps = byFlag[fid].filter((dep: string) => killed.has(dep)).sort();
  if (killedDeps.length) return { flag_id: fid, wave: null, dependency_status: "upstream_killed", blocked_by: killedDeps };
  return { flag_id: fid, wave: memo[fid], dependency_status: "ready", blocked_by: [] };
});

mkdirSync(OUT, { recursive: true });
writeJson("rollout_matrix.json", { rollouts });
writeJson("exposure_budget.json", { flags: budgetRows });
writeJson("dependency_waves.json", { flags: waveRows });
writeJson("incident_journal.json", { applied, ignored });
writeJson("summary.json", {
  flags_total: Object.keys(flags).length,
  segments_total: Object.keys(segments).length,
  applied_incidents: applied.length,
  ignored_incidents: ignored.length,
  killed_flags: killed.size,
  cycle_blocked_flags: cycleNodes.size,
  quarantined_segments: compromised.size,
  over_budget_flags: budgetRows.filter((r) => r.status === "over_budget").length,
  quarantine_exposure_flags: budgetRows.filter((r) => r.status === "quarantine_exposure").length,
});

TSEOF
cd "$APP_DIR/rollout"
npm run audit -- --input "${FRLA_FLAGS_DIR:-/app/flags}" --output "${FRLA_AUDIT_DIR:-/app/audit}"
