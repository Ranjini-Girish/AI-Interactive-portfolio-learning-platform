import * as fs from "node:fs";
import * as path from "node:path";

const DATA = process.env.SCR_DATA_DIR ?? "/app/runs";
const OUT = process.env.SCR_PLAN_DIR ?? "/app/plan";

type Json = null | boolean | number | string | Json[] | { [k: string]: Json };

function sortKeysDeep(v: unknown): unknown {
  if (v === null || typeof v !== "object") {
    return v;
  }
  if (Array.isArray(v)) {
    return v.map(sortKeysDeep);
  }
  const o = v as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  for (const k of Object.keys(o).sort()) {
    out[k] = sortKeysDeep(o[k]);
  }
  return out;
}

function writeJson(name: string, payload: unknown): void {
  const sorted = sortKeysDeep(payload);
  const text = JSON.stringify(sorted, null, 2) + "\n";
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, name), text, "utf-8");
}

function readJson<T>(rel: string): T {
  const p = path.join(DATA, rel);
  return JSON.parse(fs.readFileSync(p, "utf-8")) as T;
}

/** ECMAScript JSON.stringify for a finite number (SPEC reason tokens). */
function jsonNumberStr(n: number): string {
  return JSON.stringify(n);
}

function mean(xs: number[]): number {
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

function pstdev(xs: number[]): number {
  const m = mean(xs);
  const v = xs.reduce((s, x) => s + (x - m) ** 2, 0) / xs.length;
  return Math.sqrt(v);
}

interface Manifest {
  sim_id: string;
  inputs_dataset: string;
  kind?: string;
  current_checkpoint_step: number;
  stabilization_steps: number;
  last_known_good_step: number;
  scheduled_quiesce_window?: { start_day: number; end_day: number };
}

interface TelemetryRow {
  residual_norm: number;
  energy_drift_pct: number;
  samples_per_second: number;
  gpu_util_percent: number;
  nan_count?: number;
}

interface RunRow {
  avg_rollback_walltime_hours: number;
  avg_rollback_cost_node_hours: number;
  total_rollbacks: number;
  last_rollback_day: number | null;
}

interface IncidentEvent {
  kind: string;
  day?: number;
  sim_id?: string;
  dataset_id?: string;
  safe_step?: number;
  event_id?: string;
}

const pool = readJson<{ current_day: number }>("pool_state.json");
const policy = readJson<{
  residual_max: number;
  energy_drift_pct_max: number;
  samples_per_second_min: number;
  gpu_saturation_max: number;
  cost_approval_node_hours: number;
  peak_quiesce_window: { start_day: number; end_day: number };
  peak_quiesce_surcharge_pct: number;
  chronic_runs_threshold: number;
  chronic_runs_recent_days: number;
  volatility_ratio_threshold: number;
  trend_change_pct_threshold: number;
  consumer_pause_max_hops: number;
  exploratory_cost_discount_pct: number;
  severity_buckets: Record<
    string,
    { max_violation_pct: number | null }
  >;
}>("governance/policy.json");
const deps = readJson<Record<string, string[]>>("dependencies.json");
const incidents = readJson<{ events?: IncidentEvent[] }>("incident_log.json");
const telemetry = readJson<{ telemetry: Record<string, TelemetryRow> }>(
  "metrics/current_telemetry.json",
).telemetry;
const history = readJson<{ history: Record<string, Record<string, number>[]> }>(
  "metrics/window_history.json",
).history;

const manifests: Record<string, Manifest> = {};
const manifestsDir = path.join(DATA, "manifests");
for (const f of fs.readdirSync(manifestsDir).filter((x) => x.endsWith(".json")).sort()) {
  const manifest = readJson<Manifest>(path.join("manifests", f));
  manifests[manifest.sim_id] = manifest;
}

const currentDay = pool.current_day;
const residualMax = policy.residual_max;
const energyMax = policy.energy_drift_pct_max;
const spsMin = policy.samples_per_second_min;
const gpuCap = policy.gpu_saturation_max;
const costCap = policy.cost_approval_node_hours;
const peakWindow = policy.peak_quiesce_window;
const peakActive =
  peakWindow.start_day <= currentDay && currentDay <= peakWindow.end_day;
const surchargeFactor = 1.0 + policy.peak_quiesce_surcharge_pct / 100.0;
const chronicN = policy.chronic_runs_threshold;
const chronicWindow = policy.chronic_runs_recent_days;
const volatilityThreshold = policy.volatility_ratio_threshold;
const trendThreshold = policy.trend_change_pct_threshold;
const maxPauseHops = policy.consumer_pause_max_hops;
const exploratoryPct = policy.exploratory_cost_discount_pct;
const severityBuckets = policy.severity_buckets;

const events = incidents.events ?? [];
const acceptedEvents: IncidentEvent[] = [];
let ignoredCount = 0;
const allowedKinds = new Set(["corruption_confirmed", "dataset_compromise", "force_pin"]);
for (const event of events) {
  if (!allowedKinds.has(event.kind ?? "")) {
    ignoredCount += 1;
    continue;
  }
  if ((event.day ?? 1e9) > currentDay) {
    ignoredCount += 1;
    continue;
  }
  if (event.kind === "dataset_compromise") {
    if (!event.dataset_id) {
      ignoredCount += 1;
      continue;
    }
  } else if (!event.sim_id || !(event.sim_id in manifests)) {
    ignoredCount += 1;
    continue;
  }
  acceptedEvents.push(event);
}

const compromisedDatasets = [
  ...new Set(
    acceptedEvents
      .filter((e) => e.kind === "dataset_compromise")
      .map((e) => e.dataset_id as string),
  ),
].sort();
const corruptionCandidates: Record<string, IncidentEvent[]> = {};
for (const e of acceptedEvents) {
  if (e.kind === "corruption_confirmed" && e.sim_id) {
    if (!corruptionCandidates[e.sim_id]) {
      corruptionCandidates[e.sim_id] = [];
    }
    corruptionCandidates[e.sim_id].push(e);
  }
}
const corruptionEvents: Record<string, IncidentEvent> = {};
for (const simId of Object.keys(corruptionCandidates).sort()) {
  const arr = corruptionCandidates[simId];
  arr.sort((a, b) => {
    const dayA = a.day ?? -1;
    const dayB = b.day ?? -1;
    if (dayB !== dayA) {
      return dayB - dayA;
    }
    const ida = a.event_id ?? "";
    const idb = b.event_id ?? "";
    return ida.localeCompare(idb);
  });
  corruptionEvents[simId] = arr[0] as IncidentEvent;
}
const forcePinned = [
  ...new Set(
    acceptedEvents.filter((e) => e.kind === "force_pin").map((e) => e.sim_id as string),
  ),
].sort();

function pickSeverity(violationPct: number): string {
  const order = ["minor", "moderate", "severe", "critical"];
  for (const name of order) {
    const ceiling = severityBuckets[name].max_violation_pct;
    if (ceiling === null || violationPct <= ceiling) {
      return name;
    }
  }
  return "critical";
}

function bumpSeverity(name: string): string {
  const order = ["minor", "moderate", "severe", "critical"];
  const idx = order.indexOf(name);
  return order[Math.min(idx + 1, order.length - 1)];
}

const SEVERITY_TO_STRATEGY: Record<string, [string, number]> = {
  minor: ["resume_in_place", 10],
  moderate: ["fork_replicate", 25],
  severe: ["full_restart", 75],
  critical: ["full_restart", 100],
};

function computeViolations(simId: string): Record<string, number> {
  const m = telemetry[simId];
  const violations: Record<string, number> = {};
  if (m.residual_norm > residualMax) {
    violations.residual_norm = (m.residual_norm - residualMax) / residualMax;
  }
  if (m.energy_drift_pct > energyMax) {
    violations.energy_drift_pct = (m.energy_drift_pct - energyMax) / energyMax;
  }
  if (m.samples_per_second < spsMin) {
    violations.samples_per_second = (spsMin - m.samples_per_second) / spsMin;
  }
  return violations;
}

function selectPrimaryMetric(violations: Record<string, number>): string {
  const candidates = Object.keys(violations).filter((m) => m !== "nan_count");
  if (candidates.length === 0) {
    return "residual_norm";
  }
  return [...candidates].sort((a, b) => {
    const da = violations[b] - violations[a];
    if (da !== 0) {
      return da;
    }
    return a.localeCompare(b);
  })[0];
}

function evaluateGate(
  simId: string,
  manifest: Manifest,
  forceRolled: boolean,
): ["healthy" | "skipped_capacity" | "skipped_grace" | "skipped_quiesce" | "eligible" | "invalid", Record<string, number>] {
  const metrics = telemetry[simId];
  const violations = computeViolations(simId);
  const hasViolation =
    Object.keys(violations).length > 0 || (metrics.nan_count ?? 0) > 0;
  if (!(hasViolation || forceRolled)) {
    return ["healthy", violations];
  }
  if (metrics.gpu_util_percent > gpuCap) {
    return ["skipped_capacity", violations];
  }
  if (!forceRolled) {
    if (manifest.current_checkpoint_step < manifest.stabilization_steps) {
      return ["skipped_grace", violations];
    }
    const window = manifest.scheduled_quiesce_window;
    if (window && window.start_day <= currentDay && currentDay <= window.end_day) {
      return ["skipped_quiesce", violations];
    }
  }
  return ["eligible", violations];
}

const classifications: Record<
  string,
  "healthy" | "skipped_capacity" | "skipped_grace" | "skipped_quiesce" | "eligible" | "invalid"
> = {};
const violationsMap: Record<string, Record<string, number>> = {};
for (const simId of Object.keys(manifests).sort()) {
  if (!(simId in telemetry) || !(simId in history)) {
    classifications[simId] = "invalid";
    continue;
  }
  const forceRolled =
    (telemetry[simId].nan_count ?? 0) > 0 || simId in corruptionEvents;
  const [label, violations] = evaluateGate(simId, manifests[simId], forceRolled);
  classifications[simId] = label;
  violationsMap[simId] = violations;
}

const directCompromised = Object.keys(manifests)
  .filter((simId) => compromisedDatasets.includes(manifests[simId].inputs_dataset))
  .sort();

function transitiveConsumers(seeds: string[]): Set<string> {
  const visited = new Set<string>();
  const queue = [...seeds];
  while (queue.length > 0) {
    const node = queue.shift() as string;
    for (const child of deps[node] ?? []) {
      if (!visited.has(child)) {
        visited.add(child);
        queue.push(child);
      }
    }
  }
  return visited;
}

function shortestConsumerHops(seeds: string[]): Map<string, number> {
  const seedSet = new Set(seeds);
  const dist = new Map<string, number>();
  const q: string[] = [];
  for (const s of seeds) {
    for (const c of deps[s] ?? []) {
      if (seedSet.has(c)) {
        continue;
      }
      const prev = dist.get(c);
      if (prev === undefined || 1 < prev) {
        dist.set(c, 1);
        q.push(c);
      }
    }
  }
  let qi = 0;
  while (qi < q.length) {
    const u = q[qi] as string;
    qi += 1;
    const du = dist.get(u) as number;
    for (const v of deps[u] ?? []) {
      if (seedSet.has(v)) {
        continue;
      }
      const nd = du + 1;
      const prev = dist.get(v);
      if (prev === undefined || nd < prev) {
        dist.set(v, nd);
        q.push(v);
      }
    }
  }
  return dist;
}

const hopDistances = shortestConsumerHops(directCompromised);
const consumersToPause = [...hopDistances.entries()]
  .filter(([, d]) => d >= 1 && d <= maxPauseHops)
  .map(([sid]) => sid)
  .sort();
const pauseSet = new Set(consumersToPause);

function loadRunCsv(): Map<string, RunRow> {
  const m = new Map<string, RunRow>();
  const csvPath = path.join(DATA, "history", "run_history.csv");
  const lines = fs.readFileSync(csvPath, "utf-8").split(/\r?\n/).filter((l) => l.length > 0);
  if (lines.length < 2) {
    return m;
  }
  const header = lines[0].split(",");
  for (let i = 1; i < lines.length; i += 1) {
    const cols = lines[i].split(",");
    const row: Record<string, string> = {};
    for (let j = 0; j < header.length; j += 1) {
      row[header[j]] = cols[j] ?? "";
    }
    const simId = row.simulation?.trim() ?? "";
    let walltime = 4.0;
    let cost = 50.0;
    let totalRollbacks = 0;
    let lastRollbackDay: number | null = null;
    try {
      walltime = Number.parseFloat(row.avg_rollback_walltime_hours);
    } catch {
      walltime = 4.0;
    }
    try {
      cost = Number.parseFloat(row.avg_rollback_cost_node_hours);
    } catch {
      cost = 50.0;
    }
    try {
      totalRollbacks = Number.parseInt(row.total_rollbacks, 10);
    } catch {
      totalRollbacks = 0;
    }
    try {
      const raw = row.last_rollback_day?.trim() ?? "";
      lastRollbackDay = raw ? Number.parseInt(raw, 10) : null;
    } catch {
      lastRollbackDay = null;
    }
    m.set(simId, {
      avg_rollback_walltime_hours: walltime,
      avg_rollback_cost_node_hours: cost,
      total_rollbacks: totalRollbacks,
      last_rollback_day: lastRollbackDay,
    });
  }
  return m;
}

const runCsv = loadRunCsv();

function buildPlanEntry(simId: string): [Json, Json] {
  const manifest = manifests[simId];
  const metrics = telemetry[simId];
  const violations = violationsMap[simId] ?? {};
  const directCompromise = directCompromised.includes(simId);
  const forceCorruption = simId in corruptionEvents;
  const hasNan = (metrics.nan_count ?? 0) > 0;
  const forceRolled = hasNan || forceCorruption;

  let violatedMetrics = Object.keys(violations).sort();
  if (hasNan) {
    violatedMetrics = [...new Set([...violatedMetrics, "nan_count"])].sort();
  }

  let maxPct = 0.0;
  if (Object.keys(violations).length > 0) {
    maxPct = Math.max(...Object.values(violations)) * 100;
  }

  let severity: string;
  let strategyName: string;
  let traffic: number;
  let rollbackToStep: number;

  if (directCompromise) {
    severity = "critical";
    [strategyName, traffic] = SEVERITY_TO_STRATEGY.critical;
    rollbackToStep = 0;
  } else if (forceRolled) {
    severity = "critical";
    [strategyName, traffic] = SEVERITY_TO_STRATEGY.critical;
    const ev = corruptionEvents[simId];
    if (forceCorruption && ev && "safe_step" in ev && ev.safe_step !== undefined) {
      rollbackToStep = ev.safe_step as number;
    } else {
      rollbackToStep = manifest.last_known_good_step;
    }
  } else {
    severity = pickSeverity(maxPct);
    [strategyName, traffic] = SEVERITY_TO_STRATEGY[severity];
    rollbackToStep = manifest.last_known_good_step;
  }

  if (pauseSet.has(simId) && !directCompromise && severity !== "critical") {
    severity = bumpSeverity(severity);
    [strategyName, traffic] = SEVERITY_TO_STRATEGY[severity];
  }

  const costDefault = 50.0;
  const walltimeDefault = 4.0;
  const row = runCsv.get(simId);
  let cost = row?.avg_rollback_cost_node_hours ?? costDefault;
  let walltime = row?.avg_rollback_walltime_hours ?? walltimeDefault;
  if (peakActive) {
    cost *= surchargeFactor;
  }
  cost = Math.round(cost * 100) / 100;
  if ((manifest.kind ?? "production") === "exploratory") {
    cost *= 1 - exploratoryPct / 100;
    cost = Math.round(cost * 100) / 100;
  }
  walltime = Math.round(walltime * 100) / 100;

  const reasonParts: string[] = [];
  for (const metricName of violatedMetrics) {
    if (metricName === "residual_norm") {
      reasonParts.push(
        `residual_norm=${jsonNumberStr(metrics.residual_norm)}>${jsonNumberStr(residualMax)}`,
      );
    } else if (metricName === "energy_drift_pct") {
      reasonParts.push(
        `energy_drift_pct=${jsonNumberStr(metrics.energy_drift_pct)}>${jsonNumberStr(energyMax)}`,
      );
    } else if (metricName === "samples_per_second") {
      reasonParts.push(
        `samples_per_second=${jsonNumberStr(metrics.samples_per_second)}<${jsonNumberStr(spsMin)}`,
      );
    } else if (metricName === "nan_count") {
      reasonParts.push(`nan_count=${jsonNumberStr(metrics.nan_count ?? 0)}>0`);
    }
  }
  if (directCompromise) {
    reasonParts.push(`dataset_compromise:${manifest.inputs_dataset}`);
  }
  if (forceCorruption) {
    reasonParts.push("corruption_confirmed");
  }
  if (reasonParts.length === 0) {
    reasonParts.push("forced_entry");
  }
  const reason = reasonParts.join("; ");

  const primaryMetric = selectPrimaryMetric(violations);
  const hist = history[simId];
  const oldest = hist[0][primaryMetric];
  const newest = metrics[primaryMetric as keyof TelemetryRow] as number;
  let changePct = 0.0;
  if (oldest === 0) {
    changePct = 0.0;
  } else {
    changePct = ((newest - oldest) / oldest) * 100;
  }
  if (primaryMetric === "samples_per_second") {
    changePct = -changePct;
  }
  const series = hist.map((sample) => sample[primaryMetric] as number);
  const meanVal = mean(series);
  let volatilityRatio = 0.0;
  if (meanVal === 0) {
    volatilityRatio = 0.0;
  } else {
    volatilityRatio = pstdev(series) / Math.abs(meanVal);
  }
  let trend: string;
  if (volatilityRatio > volatilityThreshold) {
    trend = "volatile";
  } else if (changePct >= trendThreshold) {
    trend = "degrading";
  } else if (changePct <= -trendThreshold) {
    trend = "improving";
  } else {
    trend = "stable";
  }

  const planEntry: Json = {
    current_checkpoint_step: manifest.current_checkpoint_step,
    dependency_warnings: [...(deps[simId] ?? [])].sort(),
    estimated_cost_node_hours: cost,
    estimated_walltime_hours: walltime,
    manual_approval_required: cost > costCap,
    reason,
    rollback_to_step: rollbackToStep,
    severity,
    sim_id: simId,
    strategy: strategyName,
    traffic_share_percent: traffic,
    trend,
    violated_metrics: violatedMetrics,
  };
  const trendEntry: Json = {
    change_pct: Math.round(changePct * 1e4) / 1e4,
    current_value: Math.round(newest * 1e4) / 1e4,
    oldest_value: Math.round(oldest * 1e4) / 1e4,
    primary_metric: primaryMetric,
    sim_id: simId,
    trend,
    volatility_ratio: Math.round(volatilityRatio * 1e4) / 1e4,
  };
  return [planEntry, trendEntry];
}

const rollbackSet = new Set<string>();
for (const simId of Object.keys(classifications)) {
  if (classifications[simId] === "eligible") {
    rollbackSet.add(simId);
  }
}
for (const simId of directCompromised) {
  rollbackSet.add(simId);
}
for (const fp of forcePinned) {
  rollbackSet.delete(fp);
}

const plans: Json[] = [];
const trends: Json[] = [];
for (const simId of [...rollbackSet].sort()) {
  const [pe, te] = buildPlanEntry(simId);
  plans.push(pe);
  trends.push(te);
}

writeJson("rollback_plan.json", { plans });
writeJson("trend_report.json", { trends });

const order: { depends_on_upstream: string[]; sim_id: string; rank?: number }[] = [];
for (const simId of [...rollbackSet].sort()) {
  const upstreams = [...rollbackSet]
    .filter((u) => u !== simId && transitiveConsumers([u]).has(simId))
    .sort();
  order.push({ depends_on_upstream: upstreams, sim_id: simId });
}
order.sort((a, b) => {
  const la = a.depends_on_upstream.length;
  const lb = b.depends_on_upstream.length;
  if (la !== lb) {
    return la - lb;
  }
  return a.sim_id.localeCompare(b.sim_id);
});
for (let i = 0; i < order.length; i += 1) {
  order[i].rank = i + 1;
}
writeJson("dependency_order.json", {
  consumers_to_pause: consumersToPause,
  order,
});

const chronic: Json[] = [];
for (const simId of Object.keys(manifests).sort()) {
  const row = runCsv.get(simId);
  const last = row?.last_rollback_day ?? null;
  const totalRb = row?.total_rollbacks ?? 0;
  if (totalRb >= chronicN && last !== null && currentDay - last <= chronicWindow) {
    chronic.push({
      days_since_last_rollback: currentDay - last,
      last_rollback_day: last,
      sim_id: simId,
      total_rollbacks: totalRb,
    });
  }
}
writeJson("chronic_runs.json", { chronic });

let healthyCount = 0;
let skipCapacity = 0;
let skipGrace = 0;
let skipQuiesce = 0;
const invalidSims: string[] = [];
for (const simId of Object.keys(classifications)) {
  if (directCompromised.includes(simId)) {
    continue;
  }
  const label = classifications[simId];
  if (label === "healthy") {
    healthyCount += 1;
  } else if (label === "skipped_capacity") {
    skipCapacity += 1;
  } else if (label === "skipped_grace") {
    skipGrace += 1;
  } else if (label === "skipped_quiesce") {
    skipQuiesce += 1;
  } else if (label === "invalid") {
    invalidSims.push(simId);
  }
}

const severityBreakdown: Record<string, number> = {
  critical: 0,
  minor: 0,
  moderate: 0,
  severe: 0,
};
for (const planEntry of plans) {
  const sev = (planEntry as { severity: string }).severity;
  severityBreakdown[sev] += 1;
}

const totalCost =
  Math.round(plans.reduce((s, p) => s + (p as { estimated_cost_node_hours: number }).estimated_cost_node_hours, 0) * 100) /
  100;
const manualCount = plans.filter((p) => (p as { manual_approval_required: boolean }).manual_approval_required).length;
const depMaxDepth = order.length === 0 ? 0 : Math.max(...order.map((e) => e.depends_on_upstream.length));

writeJson("summary.json", {
  current_day: currentDay,
  dependency_chain_max_depth: depMaxDepth,
  force_pinned_count: forcePinned.length,
  ignored_incident_events: ignoredCount,
  invalid_simulations: invalidSims.sort(),
  manual_approvals_required: manualCount,
  peak_quiesce_active: peakActive,
  severity_breakdown: severityBreakdown,
  simulations_healthy: healthyCount,
  simulations_requiring_rollback: plans.length,
  simulations_skipped_capacity: skipCapacity,
  simulations_skipped_grace: skipGrace,
  simulations_skipped_quiesce: skipQuiesce,
  total_estimated_cost_node_hours: totalCost,
  total_simulations_checked: Object.keys(manifests).length,
});
