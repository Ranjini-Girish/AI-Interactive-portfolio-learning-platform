"""Behavioral test suite for the simulation-checkpoint rollback planner.

Tests are organised into named classes that each cover one slice of the
contract published in `/app/runs/SPEC.md`. Every test asserts a property
the agent's outputs must satisfy. Hash-locked checks compare canonical
JSON serialisations so byte-equivalent agents and reference implementations
agree regardless of indentation choices the agent makes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import statistics
from collections import deque
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SCR_DATA_DIR", "/app/runs"))
PLAN_DIR = Path(os.environ.get("SCR_PLAN_DIR", "/app/plan"))

OUTPUT_FILES = (
    "rollback_plan.json",
    "trend_report.json",
    "dependency_order.json",
    "chronic_runs.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "d96a71b93dfcd28af355622c2ae8d3f5cd4843c83da159756a577e6704c74ec5",
    "dependencies.json": "e5264ca9e31592fec25b5a6fb040e518c9840b134cf749fc9aaae5a5b8f7a578",
    "governance/policy.json": "31d57a90d5fd13bc5076d57830ddf8287d0f6abaf53ca3d279eb3923b9f1ee6b",
    "history/run_history.csv": "a743d66ed381c3c68ef7795859b274d8aa24a2ff11913c51dc7a022ad894e9db",
    "incident_log.json": "4d31775a7cf4befca31f6a0ca8701c6b29dfebb7bab1fdb6d7485a05ecbcc788",
    "manifests/sim_alpha.json": "be819a4c7e05ec68b48990b6d64fa7983e108406d2044839b02a1e7d143107a2",
    "manifests/sim_beta.json": "38cd45259aeb7d28e7a9ae83177b60ba5828e44f1754d430aa4850f2a44e491d",
    "manifests/sim_delta.json": "0c2aabfeb9103a35f9b6f578195f9788c58831003567accb146525240efb7cdb",
    "manifests/sim_epsilon.json": "b7817aed11b6cebabf82dc5a9173544339f5ab0c33b524b457eea23fba276fe9",
    "manifests/sim_eta.json": "1de3a7ca47960d47536b070633acd4200d4a2ab43e73af76c09b82f3871e705b",
    "manifests/sim_gamma.json": "97fa85dd1100a670001f35cadf6b80c9c4ba42be98035860dcb00336d32fe49d",
    "manifests/sim_iota.json": "86dbcd66a45d4533a03d813d1e4aa044caf2a7c5ded49043bc9345e73403d37b",
    "manifests/sim_kappa.json": "1ca59a1727b2767f8ec66ccc3ea0db6288a36584a065ac2479585edfb5005a9b",
    "manifests/sim_lambda.json": "fcf35cf0d2b9aedc6df0fa59858bf49f7ee48f37be889e8d467778774bb07099",
    "manifests/sim_mu.json": "af12a71f254b37ec15a104fede63d8626622618908b88776417d0afad212a816",
    "manifests/sim_nu.json": "bc86ec937d29881fba949857fc389a1e53d069411d84e0f9c74d8a86735c26ef",
    "manifests/sim_theta.json": "d0ab24d0774ac9dbc51465dd2bcc50159825d9e26b4fbb04ca89f9e01777869c",
    "manifests/sim_xi.json": "57fe33d4fdb3eb514b14af7c9ddf4b71cc40ecc32ac4628f521ffd3e0d3a7550",
    "manifests/sim_zeta.json": "3651efdfbeda464c464e433a23ead3d074b07110128c6259988f6185190c4855",
    "metrics/current_telemetry.json": "2e214f4a3e5222049791e2790d86c98cb902c2741acdc20e388f03febe7b8cd4",
    "metrics/window_history.json": "eea17fedad4870f987dc58b7f810ba9d0a83afe8b56f630c662676d5d3bd121e",
    "pool_state.json": "1a2099b479a5ce1541003b9ef6c27e68beb3a3c81af90cc3d7651898ead766a4",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "chronic_runs.json": "563212d603104bd084ccaf45484e73bd8d1afb9a70003c9f174a2f1f661bfecd",
    "dependency_order.json": "a0a747d07e18ef3dccbb01f885344f8c065adb619b7bdb5c8d8afb0b6acaa643",
    "rollback_plan.json": "bdaf380530178c89f6857623749158e3fe01d3f9e695e6edeb2763977fbd1074",
    "summary.json": "c3c16ef8a225bb002e5fb1f2d3ae3effa32dcdc00abe578d092f12160dde04b5",
    "trend_report.json": "1376469bfa06e910b4e75f9f4a7a40b80c4cf3975bb4ab69c3871a3b6eadb3be",
}

EXPECTED_FIELD_HASHES = {
    "chronic_runs.chronic": "64e9693d73c31269444c280dacdc88e9d6cc60fab27dfaa6125b2eef5ce87ed1",
    "dependency_order.consumers_to_pause": "a5ed9b7353426a7f7cc6d21f8f89a5919c17ed4c9f87498f508f098fb72e495e",
    "dependency_order.order": "0f8a44221f7be625d9841357e7b7ca923682fe91fb88ab54687a5e255e9dc304",
    "rollback_plan.plans": "024ef08d575f0c9f164f27c739f6b1ba2587c3d3ae69373de7085422847a1dc2",
    "summary.current_day": "6af1f692e9496c6d0b668316eccb93276ae6b6774fa728aac31ff40a38318760",
    "summary.dependency_chain_max_depth": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.force_pinned_count": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.ignored_incident_events": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.invalid_simulations": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    "summary.manual_approvals_required": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.peak_quiesce_active": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
    "summary.severity_breakdown": "4836bbd7946799e89eefbc035c7542eabc8d034ef2b5e6f05acbc2e3e0576e50",
    "summary.simulations_healthy": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.simulations_requiring_rollback": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "summary.simulations_skipped_capacity": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.simulations_skipped_grace": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.simulations_skipped_quiesce": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.total_estimated_cost_node_hours": "a692c0a2eecbfba2a196d3229225af3d081730f1e591771f0b22e70a5b7f0ec0",
    "summary.total_simulations_checked": "8527a891e224136950ff32ca212b45bc93f69fbb801c3b1ebedac52775f99e61",
    "trend_report.trends": "b1f61e66d5e922f196ec705bc7dbc7ef4f8cb3aadabbbd13377d73625f62e26c",
}


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _json_number_str(n: float | int) -> str:
    """ECMAScript JSON.stringify for a finite number (SPEC reason tokens)."""
    if isinstance(n, bool):
        return json.dumps(n)
    if isinstance(n, int):
        return str(n)
    if isinstance(n, float) and math.isfinite(n) and n == int(n):
        return str(int(n))
    return json.dumps(n)


def _normalize_json_numbers(value):
    """Coerce whole-valued floats to int so canonical JSON matches JSON.stringify."""
    if isinstance(value, float):
        if math.isfinite(value) and value == int(value):
            return int(value)
        return value
    if isinstance(value, dict):
        return {k: _normalize_json_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_json_numbers(v) for v in value]
    return value


def _canonical(value) -> str:
    """Compact canonical JSON for input anti-cheat (raw float forms preserved)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _canonical_output(value) -> str:
    """Compact canonical JSON for output hash locks (JSON.stringify number rules)."""
    return json.dumps(
        _normalize_json_numbers(value),
        sort_keys=True,
        separators=(",", ":"),
    )


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs():
    """Load every emitted artifact once per test session."""
    payload = {}
    for name in OUTPUT_FILES:
        path = PLAN_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


@pytest.fixture(scope="session")
def reference():
    """Compute the reference plan independently from the inputs."""
    return _build_reference()


# ---------------------------------------------------------------------------
# Independent reference implementation derived directly from SPEC.md.
# Implemented in test code so failures isolate to the agent's behavior, not
# any shared module.
# ---------------------------------------------------------------------------

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
                reason_parts.append(
                    f"residual_norm={_json_number_str(m['residual_norm'])}>"
                    f"{_json_number_str(residual_max)}"
                )
            elif metric_name == "energy_drift_pct":
                reason_parts.append(
                    f"energy_drift_pct={_json_number_str(m['energy_drift_pct'])}>"
                    f"{_json_number_str(energy_max)}"
                )
            elif metric_name == "samples_per_second":
                reason_parts.append(
                    f"samples_per_second={_json_number_str(m['samples_per_second'])}<"
                    f"{_json_number_str(sps_min)}"
                )
            elif metric_name == "nan_count":
                reason_parts.append(f"nan_count={_json_number_str(m['nan_count'])}>0")
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

    healthy = 0
    for sim_id in manifests:
        if classifications.get(sim_id) != "healthy":
            continue
        if sim_id in direct_compromised:
            continue
        if sim_id in corruption_events:
            continue
        if telemetry[sim_id].get("nan_count", 0) > 0:
            continue
        healthy += 1
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


class TestInputIntegrity:
    """The dataset under /app/runs must remain byte-identical."""

    @pytest.mark.parametrize("rel_path", sorted(EXPECTED_INPUT_HASHES.keys()))
    def test_input_file_hash(self, rel_path):
        """Each fixture file must hash to its locked SHA-256."""
        path = DATA_DIR / rel_path
        assert path.is_file(), f"missing fixture: {rel_path}"
        if rel_path.endswith(".json"):
            payload = _load_json(path)
            digest = _sha(_canonical(payload))
        else:
            digest = _sha(path.read_text(encoding="utf-8"))
        assert digest == EXPECTED_INPUT_HASHES[rel_path], rel_path


class TestReportStructure:
    """Every emitted artifact must exist and parse as JSON with the right top-level shape."""

    @pytest.mark.parametrize("name", OUTPUT_FILES)
    def test_artifact_present(self, outputs, name):
        """The required artifact lives at the published path."""
        assert name in outputs

    def test_rollback_plan_top_level(self, outputs):
        """rollback_plan.json has exactly one top-level key 'plans' which is a list."""
        payload = outputs["rollback_plan.json"]
        assert set(payload.keys()) == {"plans"}
        assert isinstance(payload["plans"], list)

    def test_trend_report_top_level(self, outputs):
        """trend_report.json has exactly one top-level key 'trends' which is a list."""
        payload = outputs["trend_report.json"]
        assert set(payload.keys()) == {"trends"}
        assert isinstance(payload["trends"], list)

    def test_dependency_order_top_level(self, outputs):
        """dependency_order.json has exactly the keys 'order' and 'consumers_to_pause'."""
        payload = outputs["dependency_order.json"]
        assert set(payload.keys()) == {"consumers_to_pause", "order"}
        assert isinstance(payload["order"], list)
        assert isinstance(payload["consumers_to_pause"], list)

    def test_chronic_runs_top_level(self, outputs):
        """chronic_runs.json has exactly one top-level key 'chronic' which is a list."""
        payload = outputs["chronic_runs.json"]
        assert set(payload.keys()) == {"chronic"}
        assert isinstance(payload["chronic"], list)

    def test_summary_keys(self, outputs):
        """summary.json carries every documented top-level counter key."""
        expected = {
            "current_day", "dependency_chain_max_depth", "force_pinned_count",
            "ignored_incident_events", "invalid_simulations", "manual_approvals_required",
            "peak_quiesce_active", "severity_breakdown", "simulations_healthy",
            "simulations_requiring_rollback", "simulations_skipped_capacity",
            "simulations_skipped_grace", "simulations_skipped_quiesce",
            "total_estimated_cost_node_hours", "total_simulations_checked",
        }
        assert set(outputs["summary.json"].keys()) == expected

    @pytest.mark.parametrize("name", OUTPUT_FILES)
    def test_artifact_hash(self, outputs, name):
        """Canonical-form JSON of each artifact must hash to its locked digest."""
        digest = _sha(_canonical_output(outputs[name]))
        assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES[name], name


class TestRollbackPlan:
    """rollback_plan.json: per-entry decisions, severity, strategy, cost, dependency_warnings."""

    def test_plans_field_hash(self, outputs):
        """The list of plans matches the locked canonical hash."""
        digest = _sha(_canonical_output(outputs["rollback_plan.json"]["plans"]))
        assert digest == EXPECTED_FIELD_HASHES["rollback_plan.plans"]

    def test_plans_match_reference(self, outputs, reference):
        """Every plan entry agrees field-for-field with the reference re-derivation."""
        assert outputs["rollback_plan.json"]["plans"] == reference["rollback_plan"]["plans"]

    def test_plans_sorted_by_sim_id(self, outputs):
        """plans is sorted ascending by sim_id."""
        ids = [p["sim_id"] for p in outputs["rollback_plan.json"]["plans"]]
        assert ids == sorted(ids)

    def test_severity_enum_values(self, outputs):
        """Every severity is one of the four documented buckets."""
        allowed = {"minor", "moderate", "severe", "critical"}
        for plan in outputs["rollback_plan.json"]["plans"]:
            assert plan["severity"] in allowed

    def test_strategy_enum_values(self, outputs):
        """Every strategy is one of the three documented strategies."""
        allowed = {"resume_in_place", "fork_replicate", "full_restart"}
        for plan in outputs["rollback_plan.json"]["plans"]:
            assert plan["strategy"] in allowed

    def test_severity_strategy_mapping(self, outputs):
        """severity uniquely determines strategy and traffic_share_percent."""
        mapping = {
            "minor": ("resume_in_place", 10),
            "moderate": ("fork_replicate", 25),
            "severe": ("full_restart", 75),
            "critical": ("full_restart", 100),
        }
        for plan in outputs["rollback_plan.json"]["plans"]:
            assert (plan["strategy"], plan["traffic_share_percent"]) == mapping[plan["severity"]]

    def test_minor_severity_present(self, outputs):
        """At least one plan entry classifies as minor."""
        sevs = [p["severity"] for p in outputs["rollback_plan.json"]["plans"]]
        assert "minor" in sevs

    def test_moderate_severity_present(self, outputs):
        """At least one plan entry classifies as moderate."""
        sevs = [p["severity"] for p in outputs["rollback_plan.json"]["plans"]]
        assert "moderate" in sevs

    def test_severe_severity_present(self, outputs):
        """At least one plan entry classifies as severe."""
        sevs = [p["severity"] for p in outputs["rollback_plan.json"]["plans"]]
        assert "severe" in sevs

    def test_critical_severity_present(self, outputs):
        """At least one plan entry classifies as critical."""
        sevs = [p["severity"] for p in outputs["rollback_plan.json"]["plans"]]
        assert "critical" in sevs

    def test_dataset_compromise_substring(self, outputs):
        """A directly-compromised entry's reason carries dataset_compromise:<dataset>."""
        compromised_entries = [
            p for p in outputs["rollback_plan.json"]["plans"]
            if "dataset_compromise:" in p["reason"]
        ]
        assert compromised_entries, "no dataset_compromise:<id> reason found"
        for p in compromised_entries:
            assert p["severity"] == "critical"
            assert p["strategy"] == "full_restart"
            assert p["rollback_to_step"] == 0

    def test_nan_force_rolled_critical(self, outputs):
        """An entry whose violated_metrics contains nan_count must be critical."""
        nan_entries = [
            p for p in outputs["rollback_plan.json"]["plans"]
            if "nan_count" in p["violated_metrics"]
        ]
        assert nan_entries
        for p in nan_entries:
            assert p["severity"] == "critical"
            assert p["strategy"] == "full_restart"

    def test_corruption_confirmed_safe_step_honored(self, outputs):
        """A corruption_confirmed-only entry rolls back to the event's safe_step."""
        corr_entries = [
            p for p in outputs["rollback_plan.json"]["plans"]
            if "corruption_confirmed" in p["reason"] and "dataset_compromise:" not in p["reason"]
        ]
        assert corr_entries
        for p in corr_entries:
            assert p["severity"] == "critical"
            assert p["rollback_to_step"] == 2500

    def test_violated_metrics_sorted(self, outputs):
        """violated_metrics is sorted ASCII-ascending."""
        for plan in outputs["rollback_plan.json"]["plans"]:
            assert plan["violated_metrics"] == sorted(plan["violated_metrics"])

    def test_dependency_warnings_match_input(self, outputs):
        """dependency_warnings of each plan equals the sorted direct consumers from the dependencies file."""
        deps = _load_json(DATA_DIR / "dependencies.json")
        for plan in outputs["rollback_plan.json"]["plans"]:
            expected = sorted(deps.get(plan["sim_id"], []))
            assert plan["dependency_warnings"] == expected, plan["sim_id"]

    def test_manual_approval_above_threshold(self, outputs):
        """manual_approval_required is exactly cost > cost_approval_node_hours."""
        policy = _load_json(DATA_DIR / "governance" / "policy.json")
        cap = policy["cost_approval_node_hours"]
        for plan in outputs["rollback_plan.json"]["plans"]:
            assert plan["manual_approval_required"] == (plan["estimated_cost_node_hours"] > cap)

    def test_peak_surcharge_applied_when_active(self, outputs):
        """When peak quiesce is active, cost is CSV times surcharge rounded, then exploratory discount if applicable."""
        summary = outputs["summary.json"]
        if not summary["peak_quiesce_active"]:
            pytest.skip("peak quiesce not active")
        policy = _load_json(DATA_DIR / "governance" / "policy.json")
        factor = 1.0 + policy["peak_quiesce_surcharge_pct"] / 100.0
        disc = policy["exploratory_cost_discount_pct"] / 100.0
        manifests = {}
        for path in (DATA_DIR / "manifests").glob("*.json"):
            m = _load_json(path)
            manifests[m["sim_id"]] = m
        csv_cost = {}
        with open(DATA_DIR / "history" / "run_history.csv", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    csv_cost[row["simulation"].strip()] = float(row["avg_rollback_cost_node_hours"])
                except (ValueError, TypeError):
                    csv_cost[row["simulation"].strip()] = 50.0
        for plan in outputs["rollback_plan.json"]["plans"]:
            raw = csv_cost.get(plan["sim_id"], 50.0)
            base = round(raw * factor, 2)
            if manifests.get(plan["sim_id"], {}).get("kind") == "exploratory":
                base = round(base * (1 - disc), 2)
            assert plan["estimated_cost_node_hours"] == base, plan["sim_id"]


class TestTrendReport:
    """trend_report.json: 4-state classifier on the most-violated metric."""

    def test_trends_field_hash(self, outputs):
        """The list of trends matches the locked canonical hash."""
        digest = _sha(_canonical_output(outputs["trend_report.json"]["trends"]))
        assert digest == EXPECTED_FIELD_HASHES["trend_report.trends"]

    def test_trends_match_reference(self, outputs, reference):
        """Every trend entry agrees field-for-field with the reference re-derivation."""
        assert outputs["trend_report.json"]["trends"] == reference["trend_report"]["trends"]

    def test_trends_sim_ids_match_plan(self, outputs):
        """trend_report covers exactly the same sim_ids as rollback_plan."""
        trend_ids = {t["sim_id"] for t in outputs["trend_report.json"]["trends"]}
        plan_ids = {p["sim_id"] for p in outputs["rollback_plan.json"]["plans"]}
        assert trend_ids == plan_ids

    def test_trend_enum_values(self, outputs):
        """Every trend label is one of the four documented states."""
        allowed = {"improving", "stable", "degrading", "volatile"}
        for entry in outputs["trend_report.json"]["trends"]:
            assert entry["trend"] in allowed

    def test_improving_present(self, outputs):
        """At least one trend classifies as improving."""
        labels = [t["trend"] for t in outputs["trend_report.json"]["trends"]]
        assert "improving" in labels

    def test_degrading_present(self, outputs):
        """At least one trend classifies as degrading."""
        labels = [t["trend"] for t in outputs["trend_report.json"]["trends"]]
        assert "degrading" in labels

    def test_stable_present(self, outputs):
        """At least one trend classifies as stable."""
        labels = [t["trend"] for t in outputs["trend_report.json"]["trends"]]
        assert "stable" in labels

    def test_volatile_present(self, outputs):
        """At least one trend classifies as volatile."""
        labels = [t["trend"] for t in outputs["trend_report.json"]["trends"]]
        assert "volatile" in labels

    def test_volatile_takes_precedence(self, outputs):
        """A volatile classification is justified by volatility_ratio above the policy threshold."""
        policy = _load_json(DATA_DIR / "governance" / "policy.json")
        vt = policy["volatility_ratio_threshold"]
        for entry in outputs["trend_report.json"]["trends"]:
            if entry["trend"] == "volatile":
                assert entry["volatility_ratio"] > vt

    def test_samples_per_second_sign_inversion(self, outputs):
        """For samples_per_second-primary entries, change_pct sign is inverted relative to raw delta."""
        history = _load_json(DATA_DIR / "metrics" / "window_history.json")["history"]
        telemetry = _load_json(DATA_DIR / "metrics" / "current_telemetry.json")["telemetry"]
        for entry in outputs["trend_report.json"]["trends"]:
            if entry["primary_metric"] != "samples_per_second":
                continue
            sid = entry["sim_id"]
            oldest = history[sid][0]["samples_per_second"]
            newest = telemetry[sid]["samples_per_second"]
            raw = (newest - oldest) / oldest * 100
            assert round(-raw, 4) == entry["change_pct"], sid


class TestDependencyOrder:
    """dependency_order.json: ranks and consumers_to_pause derived from the graph."""

    def test_order_field_hash(self, outputs):
        """The order list matches the locked canonical hash."""
        digest = _sha(_canonical_output(outputs["dependency_order.json"]["order"]))
        assert digest == EXPECTED_FIELD_HASHES["dependency_order.order"]

    def test_consumers_field_hash(self, outputs):
        """consumers_to_pause matches the locked canonical hash."""
        digest = _sha(_canonical_output(outputs["dependency_order.json"]["consumers_to_pause"]))
        assert digest == EXPECTED_FIELD_HASHES["dependency_order.consumers_to_pause"]

    def test_order_matches_reference(self, outputs, reference):
        """The full order list matches the reference re-derivation."""
        assert outputs["dependency_order.json"]["order"] == reference["dependency_order"]["order"]

    def test_consumers_match_reference(self, outputs, reference):
        """consumers_to_pause matches the reference closure."""
        assert outputs["dependency_order.json"]["consumers_to_pause"] == reference["dependency_order"]["consumers_to_pause"]

    def test_ranks_consecutive_from_one(self, outputs):
        """Ranks form a consecutive sequence 1..len(order)."""
        ranks = [e["rank"] for e in outputs["dependency_order.json"]["order"]]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_consumers_excludes_directly_compromised(self, outputs):
        """Sims that are themselves directly compromised do not appear in consumers_to_pause."""
        compromised = {
            p["sim_id"] for p in outputs["rollback_plan.json"]["plans"]
            if "dataset_compromise:" in p["reason"]
        }
        for sid in outputs["dependency_order.json"]["consumers_to_pause"]:
            assert sid not in compromised

    def test_consumers_sorted_ascending(self, outputs):
        """consumers_to_pause is sorted ASCII ascending."""
        listing = outputs["dependency_order.json"]["consumers_to_pause"]
        assert listing == sorted(listing)

    def test_upstream_lists_sorted(self, outputs):
        """Each depends_on_upstream array is sorted ascending."""
        for entry in outputs["dependency_order.json"]["order"]:
            assert entry["depends_on_upstream"] == sorted(entry["depends_on_upstream"])

    def test_severity_bumped_for_consumer_with_own_entry(self, outputs):
        """A sim listed in consumers_to_pause that also has its own rollback entry must not stay minor."""
        pause = set(outputs["dependency_order.json"]["consumers_to_pause"])
        for plan in outputs["rollback_plan.json"]["plans"]:
            if plan["sim_id"] in pause:
                assert plan["severity"] != "minor", plan["sim_id"]


class TestChronicRuns:
    """chronic_runs.json: simulations with high recent rollback frequency."""

    def test_chronic_field_hash(self, outputs):
        """The chronic list matches the locked canonical hash."""
        digest = _sha(_canonical_output(outputs["chronic_runs.json"]["chronic"]))
        assert digest == EXPECTED_FIELD_HASHES["chronic_runs.chronic"]

    def test_chronic_matches_reference(self, outputs, reference):
        """The chronic list agrees with the reference re-derivation."""
        assert outputs["chronic_runs.json"]["chronic"] == reference["chronic_runs"]["chronic"]

    def test_chronic_threshold_respected(self, outputs):
        """Each chronic entry has total_rollbacks above the threshold AND a recent last_rollback_day."""
        policy = _load_json(DATA_DIR / "governance" / "policy.json")
        pool = _load_json(DATA_DIR / "pool_state.json")
        for entry in outputs["chronic_runs.json"]["chronic"]:
            assert entry["total_rollbacks"] >= policy["chronic_runs_threshold"]
            assert pool["current_day"] - entry["last_rollback_day"] <= policy["chronic_runs_recent_days"]
            assert entry["days_since_last_rollback"] == pool["current_day"] - entry["last_rollback_day"]

    def test_chronic_sorted_by_sim_id(self, outputs):
        """chronic is sorted ascending by sim_id."""
        ids = [e["sim_id"] for e in outputs["chronic_runs.json"]["chronic"]]
        assert ids == sorted(ids)


class TestSummary:
    """summary.json: per-counter assertions plus composition checks."""

    @pytest.mark.parametrize(
        "field",
        sorted(k.split(".", 1)[1] for k in EXPECTED_FIELD_HASHES if k.startswith("summary.")),
    )
    def test_summary_field_hash(self, outputs, field):
        """Each summary field hashes to its locked canonical digest."""
        value = outputs["summary.json"][field]
        digest = _sha(_canonical_output(value))
        assert digest == EXPECTED_FIELD_HASHES[f"summary.{field}"]

    def test_summary_matches_reference(self, outputs, reference):
        """Every summary field agrees with the reference re-derivation."""
        assert outputs["summary.json"] == reference["summary"]

    def test_total_simulations_equals_manifest_count(self, outputs):
        """total_simulations_checked equals the number of manifest files."""
        manifests = list((DATA_DIR / "manifests").glob("*.json"))
        assert outputs["summary.json"]["total_simulations_checked"] == len(manifests)

    def test_severity_breakdown_sums_match(self, outputs):
        """severity_breakdown counters sum to simulations_requiring_rollback."""
        s = outputs["summary.json"]
        assert sum(s["severity_breakdown"].values()) == s["simulations_requiring_rollback"]

    def test_skip_counters_partition_residual(self, outputs):
        """healthy + skipped_capacity + skipped_grace + skipped_quiesce + force_pinned + rollback equals total."""
        s = outputs["summary.json"]
        compromised_only = sum(
            1 for p in outputs["rollback_plan.json"]["plans"]
            if "dataset_compromise:" in p["reason"]
        )
        plain_rollback = s["simulations_requiring_rollback"] - compromised_only
        partitioned = (
            s["simulations_healthy"]
            + s["simulations_skipped_capacity"]
            + s["simulations_skipped_grace"]
            + s["simulations_skipped_quiesce"]
            + s["force_pinned_count"]
            + plain_rollback
            + compromised_only
        )
        assert partitioned == s["total_simulations_checked"]

    def test_total_cost_matches_plan_sum(self, outputs):
        """total_estimated_cost_node_hours equals the sum across plan entries (rounded to 2 decimals)."""
        plan_sum = round(
            sum(p["estimated_cost_node_hours"] for p in outputs["rollback_plan.json"]["plans"]),
            2,
        )
        assert outputs["summary.json"]["total_estimated_cost_node_hours"] == plan_sum

    def test_manual_approvals_count_matches(self, outputs):
        """manual_approvals_required equals the count of manual_approval_required True flags."""
        manual = sum(
            1 for p in outputs["rollback_plan.json"]["plans"] if p["manual_approval_required"]
        )
        assert outputs["summary.json"]["manual_approvals_required"] == manual

    def test_dep_max_depth_matches_order(self, outputs):
        """dependency_chain_max_depth equals the max len(depends_on_upstream) across order entries."""
        order = outputs["dependency_order.json"]["order"]
        expected = max((len(e["depends_on_upstream"]) for e in order), default=0)
        assert outputs["summary.json"]["dependency_chain_max_depth"] == expected

    def test_peak_quiesce_active_matches_window(self, outputs):
        """peak_quiesce_active is True iff current_day lies within the policy window."""
        policy = _load_json(DATA_DIR / "governance" / "policy.json")
        pool = _load_json(DATA_DIR / "pool_state.json")
        w = policy["peak_quiesce_window"]
        expected = w["start_day"] <= pool["current_day"] <= w["end_day"]
        assert outputs["summary.json"]["peak_quiesce_active"] == expected

    def test_simulations_healthy_excludes_force_rolled_and_compromise(self, outputs, reference):
        """simulations_healthy excludes force-rolled, corruption-forced, and compromised sims."""
        assert outputs["summary.json"]["simulations_healthy"] == reference["summary"]["simulations_healthy"]
        plan_ids = {p["sim_id"] for p in outputs["rollback_plan.json"]["plans"]}
        incidents = _load_json(DATA_DIR / "incident_log.json")
        pool = _load_json(DATA_DIR / "pool_state.json")
        current_day = pool["current_day"]
        corruption_sims = {
            e["sim_id"]
            for e in incidents.get("events", [])
            if e.get("kind") == "corruption_confirmed"
            and e.get("day", 10**9) <= current_day
            and e.get("sim_id")
        }
        telemetry = _load_json(DATA_DIR / "metrics" / "current_telemetry.json")["telemetry"]
        for sim_id, row in telemetry.items():
            if row.get("nan_count", 0) > 0:
                assert sim_id in plan_ids, f"nan force-roll {sim_id} must have a plan entry"
            if sim_id in corruption_sims:
                assert sim_id in plan_ids, f"corruption force-roll {sim_id} must have a plan entry"
