#!/usr/bin/env python3
"""Reference planner oracle for sim-checkpoint-plan-audit."""
from __future__ import annotations

import csv
import json
import os
import statistics
from collections import deque
from pathlib import Path

DATA_DIR = Path(os.environ.get("SCR_DATA_DIR", "/app/runs"))
PLAN_DIR = Path(os.environ.get("SCR_PLAN_DIR", "/app/plan"))

OUTPUT_FILES = (
    "rollback_plan.json",
    "trend_report.json",
    "dependency_order.json",
    "chronic_runs.json",
    "summary.json",
)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(name: str, payload) -> None:
    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    path = PLAN_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_reference():
    pool = _load_json(DATA_DIR / "pool_state.json")
    policy = _load_json(DATA_DIR / "governance" / "policy.json")
    deps = _load_json(DATA_DIR / "dependencies.json")
    incidents = _load_json(DATA_DIR / "incident_log.json")
    telemetry = _load_json(DATA_DIR / "metrics" / "current_telemetry.json")["telemetry"]
    history = _load_json(DATA_DIR / "metrics" / "window_history.json")["history"]

    manifests = {}
    for path in sorted((DATA_DIR / "manifests").glob("*.json")):
        manifest = _load_json(path)
        manifests[manifest["sim_id"]] = manifest

    current_day = pool["current_day"]
    residual_max = policy["residual_max"]
    energy_max = policy["energy_drift_pct_max"]
    sps_min = policy["samples_per_second_min"]
    gpu_cap = policy["gpu_saturation_max"]
    cost_cap = policy["cost_approval_node_hours"]
    peak_window = policy["peak_quiesce_window"]
    peak_active = peak_window["start_day"] <= current_day <= peak_window["end_day"]
    surcharge_factor = 1.0 + policy["peak_quiesce_surcharge_pct"] / 100.0
    chronic_n = policy["chronic_runs_threshold"]
    chronic_window = policy["chronic_runs_recent_days"]
    volatility_threshold = policy["volatility_ratio_threshold"]
    trend_threshold = policy["trend_change_pct_threshold"]
    max_pause_hops = policy["consumer_pause_max_hops"]
    exploratory_pct = policy["exploratory_cost_discount_pct"]
    sev_buckets = policy["severity_buckets"]

    accepted_events = []
    ignored_count = 0
    allowed_kinds = {"corruption_confirmed", "dataset_compromise", "force_pin"}
    for event in incidents.get("events", []):
        if event.get("kind") not in allowed_kinds:
            ignored_count += 1
            continue
        if event.get("day", 10**9) > current_day:
            ignored_count += 1
            continue
        if event["kind"] == "dataset_compromise":
            if not event.get("dataset_id"):
                ignored_count += 1
                continue
        else:
            if event.get("sim_id") not in manifests:
                ignored_count += 1
                continue
        accepted_events.append(event)

    compromised_datasets = sorted(
        {e["dataset_id"] for e in accepted_events if e["kind"] == "dataset_compromise"}
    )
    corruption_candidates: dict[str, list] = {}
    for e in accepted_events:
        if e.get("kind") == "corruption_confirmed" and e.get("sim_id"):
            corruption_candidates.setdefault(e["sim_id"], []).append(e)
    corruption_events = {}
    for sid in sorted(corruption_candidates.keys()):
        arr = corruption_candidates[sid]
        arr.sort(
            key=lambda ev: (-(ev.get("day") if ev.get("day") is not None else -1), ev.get("event_id") or ""),
        )
        corruption_events[sid] = arr[0]
    force_pinned = sorted({e["sim_id"] for e in accepted_events if e["kind"] == "force_pin"})

    def violations_for(sim_id):
        m = telemetry[sim_id]
        v = {}
        if m["residual_norm"] > residual_max:
            v["residual_norm"] = (m["residual_norm"] - residual_max) / residual_max
        if m["energy_drift_pct"] > energy_max:
            v["energy_drift_pct"] = (m["energy_drift_pct"] - energy_max) / energy_max
        if m["samples_per_second"] < sps_min:
            v["samples_per_second"] = (sps_min - m["samples_per_second"]) / sps_min
        return v

    def primary_metric(violations):
        cands = [m for m in violations if m != "nan_count"]
        if not cands:
            return "residual_norm"
        return sorted(cands, key=lambda m: (-violations[m], m))[0]

    def transitive_consumers(seeds):
        visited = set()
        queue = deque(seeds)
        while queue:
            node = queue.popleft()
            for child in deps.get(node, []):
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
        return visited

    direct_compromised = sorted(
        sim_id for sim_id, manifest in manifests.items()
        if manifest["inputs_dataset"] in compromised_datasets
    )
    def shortest_consumer_hops(seeds: list[str]) -> dict[str, int]:
        seed_set = set(seeds)
        dist: dict[str, int] = {}
        q: deque[str] = deque()
        for s in seeds:
            for c in deps.get(s, []):
                if c in seed_set:
                    continue
                if c not in dist or dist[c] > 1:
                    dist[c] = 1
                    q.append(c)
        while q:
            u = q.popleft()
            du = dist[u]
            for v in deps.get(u, []):
                if v in seed_set:
                    continue
                nd = du + 1
                if v not in dist or nd < dist[v]:
                    dist[v] = nd
                    q.append(v)
        return dist

    hop_dist = shortest_consumer_hops(direct_compromised)
    consumers_to_pause = sorted(
        sid for sid, d in hop_dist.items() if 1 <= d <= max_pause_hops
    )
    pause_set = set(consumers_to_pause)

    classifications = {}
    violations_map = {}
    for sim_id, manifest in manifests.items():
        if sim_id not in telemetry or sim_id not in history:
            classifications[sim_id] = "invalid"
            continue
        m = telemetry[sim_id]
        forced = m.get("nan_count", 0) > 0 or sim_id in corruption_events
        v = violations_for(sim_id)
        violations_map[sim_id] = v
        has_v = bool(v) or m.get("nan_count", 0) > 0
        if not (has_v or forced):
            classifications[sim_id] = "healthy"
            continue
        if m["gpu_util_percent"] > gpu_cap:
            classifications[sim_id] = "skipped_capacity"
            continue
        if not forced:
            if manifest["current_checkpoint_step"] < manifest["stabilization_steps"]:
                classifications[sim_id] = "skipped_grace"
                continue
            window = manifest.get("scheduled_quiesce_window")
            if window and window["start_day"] <= current_day <= window["end_day"]:
                classifications[sim_id] = "skipped_quiesce"
                continue
        classifications[sim_id] = "eligible"

    rollback_set = {sid for sid, label in classifications.items() if label == "eligible"}
    rollback_set |= set(direct_compromised)
    rollback_set -= set(force_pinned)

    csv_lookup = {}
    with open(DATA_DIR / "history" / "run_history.csv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sim_id = row["simulation"].strip()
            try:
                walltime = float(row["avg_rollback_walltime_hours"])
            except (ValueError, TypeError, KeyError):
                walltime = 4.0
            try:
                cost = float(row["avg_rollback_cost_node_hours"])
            except (ValueError, TypeError, KeyError):
                cost = 50.0
            try:
                total_rb = int(row["total_rollbacks"])
            except (ValueError, TypeError, KeyError):
                total_rb = 0
            try:
                last_day = int(row["last_rollback_day"]) if row["last_rollback_day"].strip() else None
            except (ValueError, TypeError, KeyError):
                last_day = None
            csv_lookup[sim_id] = {
                "walltime": walltime,
                "cost": cost,
                "total_rb": total_rb,
                "last_day": last_day,
            }

    sev_order = ["minor", "moderate", "severe", "critical"]

    def pick_sev(pct):
        for name in sev_order:
            ceiling = sev_buckets[name]["max_violation_pct"]
            if ceiling is None or pct <= ceiling:
                return name
        return "critical"

    def bump(name):
        idx = sev_order.index(name)
        return sev_order[min(idx + 1, len(sev_order) - 1)]

    sev_to_strategy = {
        "minor": ("resume_in_place", 10),
        "moderate": ("fork_replicate", 25),
        "severe": ("full_restart", 75),
        "critical": ("full_restart", 100),
    }

    plans = []
    trends = []
    for sim_id in sorted(rollback_set):
        manifest = manifests[sim_id]
        m = telemetry[sim_id]
        v = violations_map.get(sim_id, {})
        is_direct = sim_id in direct_compromised
        is_corruption = sim_id in corruption_events
        has_nan = m.get("nan_count", 0) > 0
        forced = has_nan or is_corruption

        violated_metrics = sorted(v.keys())
        if has_nan:
            violated_metrics = sorted(set(violated_metrics) | {"nan_count"})

        max_pct = (max(v.values()) * 100) if v else 0.0

        if is_direct:
            severity = "critical"
            rollback_to_step = 0
        elif forced:
            severity = "critical"
            if is_corruption and "safe_step" in corruption_events[sim_id]:
                rollback_to_step = corruption_events[sim_id]["safe_step"]
            else:
                rollback_to_step = manifest["last_known_good_step"]
        else:
            severity = pick_sev(max_pct)
            rollback_to_step = manifest["last_known_good_step"]

        if sim_id in pause_set and not is_direct and severity != "critical":
            severity = bump(severity)

        strategy, traffic = sev_to_strategy[severity]

        cost = csv_lookup.get(sim_id, {}).get("cost", 50.0)
        walltime = csv_lookup.get(sim_id, {}).get("walltime", 4.0)
        if peak_active:
            cost *= surcharge_factor
        cost = round(cost, 2)
        if manifests[sim_id].get("kind") == "exploratory":
            cost = round(cost * (1 - exploratory_pct / 100.0), 2)
        walltime = round(walltime, 2)

        reason_parts = []
        for metric_name in violated_metrics:
            if metric_name == "residual_norm":
                reason_parts.append(f"residual_norm={m['residual_norm']}>{residual_max}")
            elif metric_name == "energy_drift_pct":
                reason_parts.append(f"energy_drift_pct={m['energy_drift_pct']}>{energy_max}")
            elif metric_name == "samples_per_second":
                reason_parts.append(f"samples_per_second={m['samples_per_second']}<{sps_min}")
            elif metric_name == "nan_count":
                reason_parts.append(f"nan_count={m['nan_count']}>0")
        if is_direct:
            reason_parts.append(f"dataset_compromise:{manifest['inputs_dataset']}")
        if is_corruption:
            reason_parts.append("corruption_confirmed")
        if not reason_parts:
            reason_parts.append("forced_entry")
        reason = "; ".join(reason_parts)

        pmetric = primary_metric(v)
        oldest = history[sim_id][0][pmetric]
        newest = telemetry[sim_id][pmetric]
        change_pct = 0.0 if oldest == 0 else (newest - oldest) / oldest * 100
        if pmetric == "samples_per_second":
            change_pct = -change_pct
        series = [s[pmetric] for s in history[sim_id]]
        mean_val = statistics.mean(series)
        vol = 0.0 if mean_val == 0 else statistics.pstdev(series) / abs(mean_val)
        if vol > volatility_threshold:
            trend = "volatile"
        elif change_pct >= trend_threshold:
            trend = "degrading"
        elif change_pct <= -trend_threshold:
            trend = "improving"
        else:
            trend = "stable"

        plans.append({
            "current_checkpoint_step": manifest["current_checkpoint_step"],
            "dependency_warnings": sorted(deps.get(sim_id, [])),
            "estimated_cost_node_hours": cost,
            "estimated_walltime_hours": walltime,
            "manual_approval_required": cost > cost_cap,
            "reason": reason,
            "rollback_to_step": rollback_to_step,
            "severity": severity,
            "sim_id": sim_id,
            "strategy": strategy,
            "traffic_share_percent": traffic,
            "trend": trend,
            "violated_metrics": violated_metrics,
        })
        trends.append({
            "change_pct": round(change_pct, 4),
            "current_value": round(newest, 4),
            "oldest_value": round(oldest, 4),
            "primary_metric": pmetric,
            "sim_id": sim_id,
            "trend": trend,
            "volatility_ratio": round(vol, 4),
        })

    order = []
    for sim_id in sorted(rollback_set):
        upstreams = sorted({u for u in rollback_set if u != sim_id and sim_id in transitive_consumers([u])})
        order.append({"depends_on_upstream": upstreams, "sim_id": sim_id})
    order.sort(key=lambda e: (len(e["depends_on_upstream"]), e["sim_id"]))
    for rank, entry in enumerate(order, start=1):
        entry["rank"] = rank

    chronic = []
    for sim_id in sorted(manifests):
        row = csv_lookup.get(sim_id, {})
        last = row.get("last_day")
        total_rb = row.get("total_rb", 0)
        if total_rb >= chronic_n and last is not None and current_day - last <= chronic_window:
            chronic.append({
                "days_since_last_rollback": current_day - last,
                "last_rollback_day": last,
                "sim_id": sim_id,
                "total_rollbacks": total_rb,
            })

    healthy = sum(1 for sid, lab in classifications.items() if lab == "healthy" and sid not in direct_compromised)
    skip_cap = sum(1 for sid, lab in classifications.items() if lab == "skipped_capacity" and sid not in direct_compromised)
    skip_grace = sum(1 for sid, lab in classifications.items() if lab == "skipped_grace" and sid not in direct_compromised)
    skip_quiesce = sum(1 for sid, lab in classifications.items() if lab == "skipped_quiesce" and sid not in direct_compromised)
    invalids = sorted(sid for sid, lab in classifications.items() if lab == "invalid")
    sev_breakdown = {"critical": 0, "minor": 0, "moderate": 0, "severe": 0}
    for p in plans:
        sev_breakdown[p["severity"]] += 1
    total_cost = round(sum(p["estimated_cost_node_hours"] for p in plans), 2)
    manual_count = sum(1 for p in plans if p["manual_approval_required"])
    dep_max = max((len(e["depends_on_upstream"]) for e in order), default=0)

    summary = {
        "current_day": current_day,
        "dependency_chain_max_depth": dep_max,
        "force_pinned_count": len(force_pinned),
        "ignored_incident_events": ignored_count,
        "invalid_simulations": invalids,
        "manual_approvals_required": manual_count,
        "peak_quiesce_active": peak_active,
        "severity_breakdown": sev_breakdown,
        "simulations_healthy": healthy,
        "simulations_requiring_rollback": len(plans),
        "simulations_skipped_capacity": skip_cap,
        "simulations_skipped_grace": skip_grace,
        "simulations_skipped_quiesce": skip_quiesce,
        "total_estimated_cost_node_hours": total_cost,
        "total_simulations_checked": len(manifests),
    }

    return {
        "rollback_plan": {"plans": plans},
        "trend_report": {"trends": trends},
        "dependency_order": {"consumers_to_pause": consumers_to_pause, "order": order},
        "chronic_runs": {"chronic": chronic},
        "summary": summary,
    }



def main() -> int:
    ref = _build_reference()
    payloads = {
        "rollback_plan.json": ref["rollback_plan"],
        "trend_report.json": ref["trend_report"],
        "dependency_order.json": ref["dependency_order"],
        "chronic_runs.json": ref["chronic_runs"],
        "summary.json": ref["summary"],
    }
    for name in OUTPUT_FILES:
        _write_json(name, payloads[name])
    print(f"wrote {len(OUTPUT_FILES)} artifacts under {PLAN_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
