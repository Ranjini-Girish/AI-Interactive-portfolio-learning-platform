from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_canonical(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def is_strictly_formatted(path: Path) -> tuple[bool, str]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        return False, f"{path} missing trailing newline"
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"{path} not utf-8: {exc}"
    payload = json.loads(decoded)
    canonical = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if decoded != canonical:
        return False, f"{path} not in canonical 2-space sorted-keys form"
    return True, ""


VALID_CODES = (
    "D_CYCLE_DETECTED",
    "D_FUTURE_TIMESTAMP",
    "D_INCOMPLETE_TRACE",
    "D_MULTI_ROOT",
    "D_ORPHAN_SPAN",
)

# ---------------------------------------------------------------------------
# Reference simulator (mirrors /app/docs/) -- live verifier ground truth
# ---------------------------------------------------------------------------


def _sha256_bucket(hash_seed: str, trace_id: str) -> int:
    h = hashlib.sha256((hash_seed + ":" + trace_id).encode("utf-8")).digest()
    val = int.from_bytes(h[:8], byteorder="big", signed=False)
    return val % 1000


def _evaluate_policies(policies: list[dict], trace_spans: list[dict], trace_id: str):
    statuses_in_trace = {s["status"] for s in trace_spans}
    services_in_trace = {s["service"] for s in trace_spans}
    for p in policies:
        t = p["type"]
        if t == "status_match":
            ok_status = any(s in statuses_in_trace for s in p["statuses"])
            ok_svc = True
            if "services" in p:
                ok_svc = any(s in services_in_trace for s in p["services"])
            if ok_status and ok_svc:
                return p, p["action"]
        elif t == "latency":
            mode = p["mode"]
            thr = p["threshold_ms"]
            matched = False
            if mode == "any_span":
                matched = any(s["duration_ms"] >= thr for s in trace_spans)
            elif mode == "root_span":
                roots = [s for s in trace_spans if s["parent_span_id"] is None]
                if len(roots) == 1:
                    matched = roots[0]["duration_ms"] >= thr
                else:
                    matched = False
            elif mode == "trace_total":
                if trace_spans:
                    total = max(s["start_unix_ms"] + s["duration_ms"] for s in trace_spans) \
                          - min(s["start_unix_ms"] for s in trace_spans)
                    matched = total >= thr
            if matched:
                return p, p["action"]
        elif t == "attribute":
            key = p["key"]
            values = set(p["values"])
            if any(
                key in s["attributes"] and s["attributes"][key] in values
                for s in trace_spans
            ):
                return p, p["action"]
        elif t == "service":
            if any(s in services_in_trace for s in p["services"]):
                return p, p["action"]
        elif t == "probabilistic":
            bucket = _sha256_bucket(p["hash_seed"], trace_id)
            action = "keep" if bucket < p["sampling_rate_per_mille"] else "drop"
            return p, action
    return None, "drop"


def simulate(spans_in: dict, policies_in: dict, config: dict) -> dict[str, Any]:
    severity_ranks = config["severity_ranks"]
    now_unix_ms = config["now_unix_ms"]
    future_thresh = config["future_timestamp_threshold_ms"]

    by_trace: dict[str, list[dict]] = {}
    for sp in spans_in["spans"]:
        by_trace.setdefault(sp["trace_id"], []).append(sp)

    decisions: list[dict] = []
    diagnostics: list[dict] = []

    pol_match = {p["name"]: 0 for p in policies_in["policies"]}
    pol_keep = {p["name"]: 0 for p in policies_in["policies"]}
    pol_drop = {p["name"]: 0 for p in policies_in["policies"]}

    def add_diag(code: str, severity: str, trace_id: str, span_id, evidence: dict):
        diagnostics.append({
            "code": code,
            "evidence": evidence,
            "severity": severity,
            "severity_rank": severity_ranks[severity],
            "span_id": span_id,
            "trace_id": trace_id,
        })

    for trace_id in sorted(by_trace.keys()):
        trace_spans = sorted(by_trace[trace_id], key=lambda s: (s["start_unix_ms"], s["span_id"]))
        span_ids = {s["span_id"] for s in trace_spans}
        roots = [s for s in trace_spans if s["parent_span_id"] is None]
        parent_of: dict[str, str | None] = {s["span_id"]: s["parent_span_id"] for s in trace_spans}

        cycle_members: set[str] = set()
        for sid in span_ids:
            seen: set[str] = set()
            visited: list[str] = []
            cur = sid
            while cur is not None and cur in parent_of:
                if cur in seen:
                    idx = visited.index(cur)
                    cycle_members.update(visited[idx:])
                    break
                seen.add(cur)
                visited.append(cur)
                cur = parent_of.get(cur)
        has_cycle = bool(cycle_members)

        orphan_pairs: list[tuple[str, str]] = []
        for s in trace_spans:
            p = s["parent_span_id"]
            if p is not None and p not in span_ids:
                orphan_pairs.append((s["span_id"], p))

        has_multi_root = len(roots) >= 2
        is_incomplete = len(trace_spans) < config["min_spans_per_trace"]

        reason: str
        decision: str
        matched_policy: str | None = None

        if has_cycle:
            reason = "cycle_detected"
            decision = config["cycle_action"]
            add_diag(
                "D_CYCLE_DETECTED", "error", trace_id, None,
                {"cycle_span_ids": sorted(cycle_members)},
            )
        elif has_multi_root:
            reason = "multi_root"
            decision = config["multi_root_action"]
        elif is_incomplete:
            reason = "incomplete_trace"
            decision = config["incomplete_action"]
        elif orphan_pairs:
            reason = "orphan_span"
            decision = config["orphan_action"]
        else:
            matched, dec_action = _evaluate_policies(policies_in["policies"], trace_spans, trace_id)
            if matched is not None:
                reason = "policy_match"
                matched_policy = matched["name"]
                decision = dec_action
                pol_match[matched["name"]] += 1
                if decision == "keep":
                    pol_keep[matched["name"]] += 1
                else:
                    pol_drop[matched["name"]] += 1
            else:
                reason = "no_policy_matched"
                decision = "drop"

        if has_multi_root:
            add_diag(
                "D_MULTI_ROOT", "warn", trace_id, None,
                {"root_span_ids": sorted(r["span_id"] for r in roots)},
            )
        if is_incomplete:
            add_diag(
                "D_INCOMPLETE_TRACE", "info", trace_id, None,
                {"actual_spans": len(trace_spans), "min_required": config["min_spans_per_trace"]},
            )
        for orphan_sid, missing in orphan_pairs:
            add_diag(
                "D_ORPHAN_SPAN", "warn", trace_id, orphan_sid,
                {"missing_parent_span_id": missing},
            )

        for s in trace_spans:
            skew = s["start_unix_ms"] - now_unix_ms
            if skew > future_thresh:
                add_diag(
                    "D_FUTURE_TIMESTAMP", "warn", trace_id, s["span_id"],
                    {
                        "now_unix_ms": now_unix_ms,
                        "skew_ms": skew,
                        "start_unix_ms": s["start_unix_ms"],
                    },
                )

        decisions.append({
            "decision": decision,
            "matched_policy": matched_policy,
            "reason": reason,
            "trace_id": trace_id,
        })

    decisions.sort(key=lambda d: d["trace_id"])

    diagnostics.sort(key=lambda d: (
        d["severity_rank"],
        d["trace_id"],
        d["code"],
        (0, "") if d["span_id"] is None else (1, d["span_id"]),
    ))

    pol_stats: list[dict] = []
    for p in policies_in["policies"]:
        pol_stats.append({
            "dropped_count": pol_drop[p["name"]],
            "kept_count":    pol_keep[p["name"]],
            "matched_count": pol_match[p["name"]],
            "name":          p["name"],
            "type":          p["type"],
        })
    pol_stats.sort(key=lambda x: x["name"])

    decisions_by_trace = {d["trace_id"]: d["decision"] for d in decisions}
    trace_total_dur: dict[str, int] = {}
    for trace_id, ts in by_trace.items():
        if not ts:
            trace_total_dur[trace_id] = 0
            continue
        trace_total_dur[trace_id] = (
            max(s["start_unix_ms"] + s["duration_ms"] for s in ts)
            - min(s["start_unix_ms"] for s in ts)
        )

    services_seen: dict[str, dict] = {}
    service_traces: dict[str, set[str]] = {}
    for sp in spans_in["spans"]:
        svc = sp["service"]
        entry = services_seen.setdefault(svc, {
            "dropped_traces": 0,
            "error_spans": 0,
            "kept_traces": 0,
            "max_trace_duration_ms": 0,
            "service": svc,
            "span_count": 0,
            "timeout_spans": 0,
            "trace_count": 0,
        })
        entry["span_count"] += 1
        if sp["status"] == "error":
            entry["error_spans"] += 1
        if sp["status"] == "timeout":
            entry["timeout_spans"] += 1
        service_traces.setdefault(svc, set()).add(sp["trace_id"])

    for svc, traces in service_traces.items():
        entry = services_seen[svc]
        entry["trace_count"] = len(traces)
        kept = sum(1 for t in traces if decisions_by_trace.get(t) == "keep")
        dropped = sum(1 for t in traces if decisions_by_trace.get(t) == "drop")
        entry["kept_traces"] = kept
        entry["dropped_traces"] = dropped
        entry["max_trace_duration_ms"] = max(
            (trace_total_dur[t] for t in traces), default=0
        )

    service_stats = sorted(services_seen.values(), key=lambda x: x["service"])

    spans_total = len(spans_in["spans"])
    traces_total = len(by_trace)
    kept_traces = sum(1 for d in decisions if d["decision"] == "keep")
    traces_dropped = traces_total - kept_traces

    code_counts = {c: 0 for c in VALID_CODES}
    for d in diagnostics:
        code_counts[d["code"]] += 1

    if spans_total == 0:
        hottest = None
    else:
        best = None
        best_span = -1
        for x in service_stats:
            if x["span_count"] > best_span or (
                x["span_count"] == best_span and (best is None or x["service"] < best)
            ):
                best = x["service"]
                best_span = x["span_count"]
        hottest = best

    summary = {
        "anomaly_counts": code_counts,
        "hottest_service": hottest,
        "kept_traces": kept_traces,
        "spans_total": spans_total,
        "traces_dropped": traces_dropped,
        "traces_total": traces_total,
    }

    return {
        "sampling_decisions": {"decisions": decisions},
        "policy_stats": {"policies": pol_stats},
        "service_stats": {"services": service_stats},
        "trace_diagnostics": {"diagnostics": diagnostics},
        "summary": summary,
    }




def main() -> int:
    if len(sys.argv) != 3:
        print('usage: oracle <input_dir> <output_dir>', file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    spans = load_json(in_dir / 'spans.json')
    policies = load_json(in_dir / 'policies.json')
    config = load_json(in_dir / 'config.json')
    outputs = simulate(spans, policies, config)
    write_canonical(out_dir / 'sampling_decisions.json', outputs['sampling_decisions'])
    write_canonical(out_dir / 'service_stats.json', outputs['service_stats'])
    write_canonical(out_dir / 'policy_stats.json', outputs['policy_stats'])
    write_canonical(out_dir / 'trace_diagnostics.json', outputs['trace_diagnostics'])
    write_canonical(out_dir / 'summary.json', outputs['summary'])
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
