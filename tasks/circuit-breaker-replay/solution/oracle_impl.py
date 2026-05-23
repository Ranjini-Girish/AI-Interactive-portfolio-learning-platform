from __future__ import annotations

import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def write_canonical(path: Path, obj: Any) -> None:
    path.write_text(canonical(obj), encoding="utf-8")


def _load_diag_codes_from_docs_path(docs_path: Path) -> tuple[frozenset[str], dict[str, str]]:
    """Parse /app/docs/diagnostics.md for the canonical list of diagnostic
    codes and their severities. Code lines look like:
        | `E_ENDPOINT_NOT_FOUND`     | error    | ...
    The single source of truth for codes is the docs, not this test file.
    """
    text = docs_path.read_text(encoding="utf-8")
    codes: set[str] = set()
    severity: dict[str, str] = {}
    pat = re.compile(
        r"^\s*\|\s*`?(?P<code>[A-Z][A-Z0-9_]+)`?\s*\|\s*"
        r"(?P<severity>error|warning|note)\s*\|"
    )
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            codes.add(m.group("code"))
            severity[m.group("code")] = m.group("severity")
    if not codes:
        raise RuntimeError(
            f"could not parse any diagnostic codes from {docs_path}; "
            "check the docs format"
        )
    return frozenset(codes), severity



SEVERITY_RANK = {"error": 0, "warning": 1, "note": 2}


# ---------------------------------------------------------------------------
# Reference simulator (mirrors /app/docs/) -- live verifier ground truth
# ---------------------------------------------------------------------------


def _effective(ep: dict[str, Any], policy: dict[str, Any], key: str) -> int:
    val = ep.get(key)
    if val is None:
        return policy["default_" + key]
    return val


def _add_diag(diags: dict[int, list[dict[str, Any]]], seq: int,
              code: str, endpoint_id: str) -> None:
    diags.setdefault(seq, []).append({
        "code": code,
        "endpoint_id": endpoint_id,
        "severity": DIAG_SEVERITY[code],
    })


def run_simulation(initial_endpoints: list[dict[str, Any]],
                   events: list[dict[str, Any]],
                   policy: dict[str, Any]) -> dict[str, Any]:
    """Pure-python reference simulator. Produces the five expected output
    documents from a fresh input set. The C++ binary's job is to produce
    byte-identical canonical JSON for the same five documents.
    """
    endpoints: dict[str, dict[str, Any]] = {}
    for e in initial_endpoints:
        endpoints[e["id"]] = {
            "id": e["id"],
            "failure_threshold_pct": e.get("failure_threshold_pct"),
            "window_size": e.get("window_size"),
            "half_open_max_probes": e.get("half_open_max_probes"),
            "recovery_ticks": e.get("recovery_ticks"),
            "state": "CLOSED",
            "window": deque(),
            "probes_used": 0,
            "probe_successes": 0,
            "probe_failures": 0,
            "tick_entered_open": None,
            "last_state_change_seq": None,
            "state_transition_count": 0,
            "total_admitted": 0,
            "total_short_circuited": 0,
            "total_successes": 0,
            "total_failures": 0,
            "total_timeouts": 0,
        }

    transitions: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    diagnostics: dict[int, list[dict[str, Any]]] = {}
    global_tick = 0
    peak_open_endpoints = 0

    def emit_transition(ep, seq, tick, from_state, to_state, reason):
        ep["state"] = to_state
        ep["last_state_change_seq"] = seq
        ep["state_transition_count"] += 1
        if policy["track_state_transitions"]:
            transitions.append({
                "endpoint_id": ep["id"],
                "from_state": from_state,
                "reason": reason,
                "seq": seq,
                "tick": tick,
                "to_state": to_state,
            })
        code = {
            "OPEN": "N_TRANSITION_TO_OPEN",
            "HALF_OPEN": "N_TRANSITION_TO_HALF_OPEN",
            "CLOSED": "N_TRANSITION_TO_CLOSED",
        }[to_state]
        _add_diag(diagnostics, seq, code, ep["id"])

    def time_based_prune(ep):
        if policy["sliding_strategy"] != "time_based":
            return
        ws = _effective(ep, policy, "window_size")
        cutoff = global_tick - ws + 1
        while ep["window"] and ep["window"][0][1] < cutoff:
            ep["window"].popleft()

    def threshold_check(ep, seq, tick):
        if ep["state"] != "CLOSED":
            return
        ws = _effective(ep, policy, "window_size")
        if policy["sliding_strategy"] == "count_based":
            while len(ep["window"]) > ws:
                ep["window"].popleft()
        n = len(ep["window"])
        if n < policy["min_window_observations"]:
            return
        fails = sum(1 for (oc, _t) in ep["window"]
                    if oc in ("failure", "timeout"))
        if (fails * 100) // n >= _effective(ep, policy, "failure_threshold_pct"):
            ep["tick_entered_open"] = tick
            emit_transition(ep, seq, tick, "CLOSED", "OPEN", "threshold_breach")

    def update_peak():
        nonlocal peak_open_endpoints
        c = sum(1 for ep in endpoints.values() if ep["state"] == "OPEN")
        if c > peak_open_endpoints:
            peak_open_endpoints = c


    for ev in events:
        seq = ev["seq"]
        op = ev["op"]
        if op == "request":
            eid = ev["endpoint_id"]
            outcome = ev["outcome"]
            ep = endpoints.get(eid)
            if ep is None:
                _add_diag(diagnostics, seq, "E_ENDPOINT_NOT_FOUND", eid)
                update_peak()
                continue
            if ep["state"] == "OPEN":
                ep["total_short_circuited"] += 1
                requests.append({
                    "admission": "short_circuited",
                    "endpoint_id": eid,
                    "outcome": outcome,
                    "seq": seq,
                    "state_at_admission": "OPEN",
                })
                _add_diag(diagnostics, seq, "N_REQUEST_SHORT_CIRCUITED", eid)
            elif ep["state"] == "CLOSED":
                time_based_prune(ep)
                ep["window"].append((outcome, global_tick))
                ep["total_admitted"] += 1
                if outcome == "success":
                    ep["total_successes"] += 1
                elif outcome == "failure":
                    ep["total_failures"] += 1
                else:
                    ep["total_timeouts"] += 1
                requests.append({
                    "admission": "admitted",
                    "endpoint_id": eid,
                    "outcome": outcome,
                    "seq": seq,
                    "state_at_admission": "CLOSED",
                })
                threshold_check(ep, seq, global_tick)
            else:
                ep["total_admitted"] += 1
                if outcome == "success":
                    ep["total_successes"] += 1
                elif outcome == "failure":
                    ep["total_failures"] += 1
                else:
                    ep["total_timeouts"] += 1
                requests.append({
                    "admission": "probe_admitted",
                    "endpoint_id": eid,
                    "outcome": outcome,
                    "seq": seq,
                    "state_at_admission": "HALF_OPEN",
                })
                _add_diag(diagnostics, seq, "N_PROBE_ADMITTED", eid)
                ep["probes_used"] += 1
                if outcome == "success":
                    ep["probe_successes"] += 1
                else:
                    ep["probe_failures"] += 1
                if ep["probe_failures"] >= 1:
                    ep["probes_used"] = 0
                    ep["probe_successes"] = 0
                    ep["probe_failures"] = 0
                    ep["tick_entered_open"] = global_tick
                    emit_transition(ep, seq, global_tick, "HALF_OPEN",
                                    "OPEN", "probe_failure")
                elif ep["probe_successes"] >= _effective(
                        ep, policy, "half_open_max_probes"):
                    ep["probes_used"] = 0
                    ep["probe_successes"] = 0
                    ep["probe_failures"] = 0
                    ep["window"].clear()
                    emit_transition(ep, seq, global_tick, "HALF_OPEN",
                                    "CLOSED", "probe_success_quota")
            update_peak()
            continue
        if op == "tick":
            global_tick += 1
            for eid in sorted(endpoints):
                ep = endpoints[eid]
                if ep["state"] == "OPEN":
                    rt = _effective(ep, policy, "recovery_ticks")
                    if (ep["tick_entered_open"] is not None
                            and global_tick - ep["tick_entered_open"] >= rt):
                        ep["tick_entered_open"] = None
                        ep["probes_used"] = 0
                        ep["probe_successes"] = 0
                        ep["probe_failures"] = 0
                        emit_transition(ep, seq, global_tick, "OPEN",
                                        "HALF_OPEN", "recovery_timeout")
            for ep in endpoints.values():
                time_based_prune(ep)
            update_peak()
            continue
        if op == "add_endpoint":
            eid = ev["endpoint_id"]
            if eid in endpoints:
                _add_diag(diagnostics, seq, "E_DUPLICATE_ENDPOINT", eid)
                update_peak()
                continue
            endpoints[eid] = {
                "id": eid,
                "failure_threshold_pct": ev.get("failure_threshold_pct"),
                "window_size": ev.get("window_size"),
                "half_open_max_probes": ev.get("half_open_max_probes"),
                "recovery_ticks": ev.get("recovery_ticks"),
                "state": "CLOSED",
                "window": deque(),
                "probes_used": 0,
                "probe_successes": 0,
                "probe_failures": 0,
                "tick_entered_open": None,
                "last_state_change_seq": None,
                "state_transition_count": 0,
                "total_admitted": 0,
                "total_short_circuited": 0,
                "total_successes": 0,
                "total_failures": 0,
                "total_timeouts": 0,
            }
            update_peak()
            continue
        if op == "remove_endpoint":
            eid = ev["endpoint_id"]
            if eid not in endpoints:
                _add_diag(diagnostics, seq, "E_ENDPOINT_NOT_FOUND", eid)
                update_peak()
                continue
            del endpoints[eid]
            update_peak()
            continue
        if op == "config_update":
            eid = ev["endpoint_id"]
            if eid not in endpoints:
                _add_diag(diagnostics, seq, "E_ENDPOINT_NOT_FOUND", eid)
                update_peak()
                continue
            ep = endpoints[eid]
            for key in ("failure_threshold_pct", "window_size",
                        "half_open_max_probes", "recovery_ticks"):
                ep[key] = ev.get(key)
            continue
        if op == "force_open":
            eid = ev["endpoint_id"]
            ep = endpoints.get(eid)
            if ep is None:
                _add_diag(diagnostics, seq, "E_ENDPOINT_NOT_FOUND", eid)
                update_peak()
                continue
            if ep["state"] == "OPEN":
                _add_diag(diagnostics, seq, "W_FORCED_OPEN_NOOP", eid)
                ep["probes_used"] = 0
                ep["probe_successes"] = 0
                ep["probe_failures"] = 0
                ep["tick_entered_open"] = global_tick
                update_peak()
                continue
            from_state = ep["state"]
            _add_diag(diagnostics, seq, "W_FORCED_OPEN", eid)
            ep["probes_used"] = 0
            ep["probe_successes"] = 0
            ep["probe_failures"] = 0
            ep["tick_entered_open"] = global_tick
            emit_transition(ep, seq, global_tick, from_state, "OPEN",
                            "manual_open")
            update_peak()
            continue
        if op == "force_close":
            eid = ev["endpoint_id"]
            ep = endpoints.get(eid)
            if ep is None:
                _add_diag(diagnostics, seq, "E_ENDPOINT_NOT_FOUND", eid)
                update_peak()
                continue
            if ep["state"] == "CLOSED":
                _add_diag(diagnostics, seq, "W_FORCED_CLOSE_NOOP", eid)
                ep["probes_used"] = 0
                ep["probe_successes"] = 0
                ep["probe_failures"] = 0
                ep["window"].clear()
                update_peak()
                continue
            from_state = ep["state"]
            _add_diag(diagnostics, seq, "W_FORCED_CLOSE", eid)
            ep["probes_used"] = 0
            ep["probe_successes"] = 0
            ep["probe_failures"] = 0
            ep["tick_entered_open"] = None
            ep["window"].clear()
            emit_transition(ep, seq, global_tick, from_state, "CLOSED",
                            "manual_close")
            update_peak()
            continue
        raise ValueError(f"unknown op: {op}")

    final_endpoints = []
    for eid in sorted(endpoints):
        ep = endpoints[eid]
        final_endpoints.append({
            "current_failure_threshold_pct": _effective(
                ep, policy, "failure_threshold_pct"),
            "current_half_open_max_probes": _effective(
                ep, policy, "half_open_max_probes"),
            "current_recovery_ticks": _effective(
                ep, policy, "recovery_ticks"),
            "current_window_size": _effective(ep, policy, "window_size"),
            "id": ep["id"],
            "last_state_change_seq": ep["last_state_change_seq"],
            "probe_failures": ep["probe_failures"],
            "probe_successes": ep["probe_successes"],
            "probes_used": ep["probes_used"],
            "state": ep["state"],
            "state_transition_count": ep["state_transition_count"],
            "tick_entered_open": ep["tick_entered_open"],
            "total_admitted": ep["total_admitted"],
            "total_failures": ep["total_failures"],
            "total_short_circuited": ep["total_short_circuited"],
            "total_successes": ep["total_successes"],
            "total_timeouts": ep["total_timeouts"],
        })

    transitions_sorted = sorted(transitions,
                                key=lambda t: (t["seq"], t["endpoint_id"]))

    diag_events = []
    for seq in sorted(diagnostics):
        diags = diagnostics[seq]
        diags_sorted = sorted(diags, key=lambda d: (
            SEVERITY_RANK[d["severity"]], d["code"], d["endpoint_id"],
        ))
        diag_events.append({"diagnostics": diags_sorted, "seq": seq})

    total_admitted = sum(r["admission"] in ("admitted", "probe_admitted")
                         for r in requests)
    total_short_circuited = sum(r["admission"] == "short_circuited"
                                for r in requests)
    total_successes = sum(1 for r in requests
                          if r["admission"] in ("admitted", "probe_admitted")
                          and r["outcome"] == "success")
    total_failures = sum(1 for r in requests
                         if r["admission"] in ("admitted", "probe_admitted")
                         and r["outcome"] == "failure")
    total_timeouts = sum(1 for r in requests
                         if r["admission"] in ("admitted", "probe_admitted")
                         and r["outcome"] == "timeout")
    total_to_open = sum(1 for t in transitions_sorted
                        if t["to_state"] == "OPEN")
    total_to_half = sum(1 for t in transitions_sorted
                        if t["to_state"] == "HALF_OPEN")
    total_to_closed = sum(1 for t in transitions_sorted
                          if t["to_state"] == "CLOSED")

    summary = {
        "endpoints_at_end": len(endpoints),
        "events_with_diagnostics": len(diag_events),
        "global_tick_at_end": global_tick,
        "peak_open_endpoints": peak_open_endpoints,
        "total_admitted": total_admitted,
        "total_events": len(events),
        "total_failures": total_failures,
        "total_requests": total_admitted + total_short_circuited,
        "total_short_circuited": total_short_circuited,
        "total_state_transitions": len(transitions_sorted),
        "total_successes": total_successes,
        "total_timeouts": total_timeouts,
        "total_transitions_to_closed": total_to_closed,
        "total_transitions_to_half_open": total_to_half,
        "total_transitions_to_open": total_to_open,
    }

    return {
        "final_endpoints": {"endpoints": final_endpoints},
        "state_transitions": {"transitions": transitions_sorted},
        "request_log": {"requests": requests},
        "diagnostics": {"events": diag_events},
        "summary": summary,
    }
def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = in_dir.parent / "docs" / "diagnostics.md"
    if not docs.is_file():
        docs = Path("/app/docs/diagnostics.md")
    global DIAG_SEVERITY, VALID_DIAG_CODES
    VALID_DIAG_CODES, DIAG_SEVERITY = _load_diag_codes_from_docs_path(docs)
    eps_doc = load_json(in_dir / "endpoints.json")
    evs_doc = load_json(in_dir / "events.json")
    pol_doc = load_json(in_dir / "policy.json")
    outputs = run_simulation(eps_doc["endpoints"], evs_doc["events"], pol_doc)
    write_canonical(out_dir / "final_endpoints.json", outputs["final_endpoints"])
    write_canonical(out_dir / "state_transitions.json", outputs["state_transitions"])
    write_canonical(out_dir / "request_log.json", outputs["request_log"])
    write_canonical(out_dir / "diagnostics.json", outputs["diagnostics"])
    write_canonical(out_dir / "summary.json", outputs["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
