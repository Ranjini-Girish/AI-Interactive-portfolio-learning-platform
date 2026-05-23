"""Verifier suite for Replay (java)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from collections import deque
import os
from pathlib import Path
from typing import Any

import pytest



def _java_cmd(data_dir: Path, out_dir: Path) -> list[str]:
    """Build argv for the Java entry class."""
    return [
        "java",
        "-cp",
        f"{BUILD_DIR}:{GSON_CP}",
        JAVA_CLASS,
        str(data_dir),
        str(out_dir),
    ]




SOURCE_SUFFIXES = (".java",)
BUILD_SCRIPT_SUFFIXES = (".mk", ".cmake", ".sh", ".bash")
BUILD_SCRIPT_NAMES = {"Makefile", "GNUmakefile", "makefile",
                      "CMakeLists.txt", "build.ninja"}


def _src_files() -> list[Path]:
    out: list[Path] = []
    for root in (Path("/app/src"),):
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in SOURCE_SUFFIXES:
                    out.append(p)
    return out


def _all_app_source_files() -> list[Path]:
    out: list[Path] = []
    skip_roots = (Path("/app/build"), Path("/app/output"))
    for p in Path("/app").rglob("*"):
        if not p.is_file() or p.suffix not in SOURCE_SUFFIXES:
            continue
        if any(str(p).startswith(str(r) + os.sep) for r in skip_roots):
            continue
        out.append(p)
    return out


def _all_app_build_inputs() -> list[Path]:
    out: list[Path] = []
    skip_roots = (Path("/app/build"), Path("/app/output"))
    for p in Path("/app").rglob("*"):
        if not p.is_file():
            continue
        if any(str(p).startswith(str(r) + os.sep) for r in skip_roots):
            continue
        if p.suffix in SOURCE_SUFFIXES + BUILD_SCRIPT_SUFFIXES:
            out.append(p)
        elif p.name in BUILD_SCRIPT_NAMES:
            out.append(p)
    return out

def _java_class_ready() -> bool:
    """Return True when the compiled entry class exists."""
    return (BUILD_DIR / f"{JAVA_CLASS}.class").is_file()


DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
BUILD_DIR = Path("/app/build")
JAVA_CLASS = "Replay"
GSON_CP = "/opt/gson.jar"

ENDPOINTS_PATH = DATA_DIR / "endpoints.json"
EVENTS_PATH    = DATA_DIR / "events.json"
POLICY_PATH    = DATA_DIR / "policy.json"

FINAL_EP_PATH    = OUT_DIR / "final_endpoints.json"
TRANSITIONS_PATH = OUT_DIR / "state_transitions.json"
REQUEST_LOG_PATH = OUT_DIR / "request_log.json"
DIAG_PATH        = OUT_DIR / "diagnostics.json"
SUMMARY_PATH     = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    FINAL_EP_PATH,
    TRANSITIONS_PATH,
    REQUEST_LOG_PATH,
    DIAG_PATH,
    SUMMARY_PATH,
)

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    ENDPOINTS_PATH: "366ad9929e3ee1ca0e90950fff950e183e58c53352722dfb246a44703ba019c2",
    EVENTS_PATH:    "98aeb4b8379efe5f6175091cabe15861c589af7e250cbc91219b6819841fe150",
    POLICY_PATH:    "8959bd3e558b94be825e1f95590859a31d73710272b521603e2ddbf742abe6e3",
}

DOCS_DIAG_PATH = Path("/app/docs/diagnostics.md")


def _load_diag_codes_from_docs() -> tuple[frozenset[str], dict[str, str]]:
    """Parse /app/docs/diagnostics.md for the canonical list of diagnostic
    codes and their severities. Code lines look like:
        | `E_ENDPOINT_NOT_FOUND`     | error    | ...
    The single source of truth for codes is the docs, not this test file.
    """
    import re
    text = DOCS_DIAG_PATH.read_text(encoding="utf-8")
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
            f"could not parse any diagnostic codes from {DOCS_DIAG_PATH}; "
            "check the docs format"
        )
    return frozenset(codes), severity


VALID_DIAG_CODES, DIAG_SEVERITY = _load_diag_codes_from_docs()
SEVERITY_RANK = {"error": 0, "warning": 1, "note": 2}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def reference_outputs() -> dict[str, Any]:
    eps_doc = load_json(ENDPOINTS_PATH)
    evs_doc = load_json(EVENTS_PATH)
    pol_doc = load_json(POLICY_PATH)
    return run_simulation(eps_doc["endpoints"], evs_doc["events"], pol_doc)



# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def expected_outputs() -> dict[str, Any]:
    return reference_outputs()


@pytest.fixture(scope="session")
def binary_run_outputs() -> dict[str, Any]:
    """Wipe /app/output, run the agent's binary with the canonical CLI, capture
    rc/stdout/stderr/start_time. Tests asserting against /app/output/*.json
    depend on this fixture so the agent's binary is the only thing that
    produces those files."""
    assert _java_class_ready(), (
        f"binary not found at {(BUILD_DIR / f"{JAVA_CLASS}.class")}; agent must build Java sources to "
        f"this path before tests run"
    )
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()
    proc = subprocess.run(
        [*_java_cmd(DATA_DIR, OUT_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    return {"start": start, "returncode": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inputs_unchanged() -> None:
    """Pinned input files must match the snapshot SHA-256 the task ships with.
    Both prevents agents rewriting inputs to ease the task AND keeps the
    live-recomputed reference deterministic."""
    for path, expected in EXPECTED_INPUT_HASHES.items():
        assert path.exists(), f"input missing: {path}"
        actual = sha256_of(path)
        assert actual == expected, (
            f"input file {path} has unexpected hash {actual}; expected {expected}"
        )


def test_java_entry_class_exists() -> None:
    """Compiled Java entry class exists under /app/build after the agent build."""
    assert _java_class_ready()


def test_sources_present_and_class_newer() -> None:
    """Java sources under /app/src are no older than the compiled entry class."""
    required_sources = _src_files()
    assert required_sources, "no .java under /app/src"
    inputs = _all_app_build_inputs()
    class_path = BUILD_DIR / f"{JAVA_CLASS}.class"
    bin_mtime = int(class_path.stat().st_mtime)
    for s in inputs:
        src_mtime = int(s.stat().st_mtime)
        assert bin_mtime >= src_mtime, (
            f"class mtime {bin_mtime} older than build input {s} mtime {src_mtime}"
        )



def test_binary_runs_cleanly_and_outputs_are_fresh(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The agent's binary must run with the canonical two-arg CLI on
    /app/data, exit 0, and produce all five outputs that are mtime-newer than
    the moment the verifier started the run.
    """
    rc = binary_run_outputs["returncode"]
    assert rc == 0, (
        f"/app/build/cbreplay exited with rc={rc} when run with canonical "
        f"args /app/data /app/output;\nstdout={binary_run_outputs['stdout']!r}\n"
        f"stderr={binary_run_outputs['stderr']!r}"
    )
    start = binary_run_outputs["start"]
    for path in ALL_OUT_PATHS:
        assert path.exists(), f"output missing after binary run: {path}"
        assert path.stat().st_size > 0, f"output empty after binary run: {path}"
        m = path.stat().st_mtime
        assert m + 1.0 >= start, (
            f"output {path} has mtime {m} older than test start {start}; "
            "looks like a stale/precomputed file rather than fresh output"
        )
        load_json(path)
    expected_names = {p.name for p in ALL_OUT_PATHS}
    actual_names = {p.name for p in OUT_DIR.iterdir() if p.is_file()}
    extras = actual_names - expected_names
    assert not extras, (
        f"binary wrote extra files into /app/output: {sorted(extras)}; "
        "the spec says exactly five JSON outputs and no others"
    )


def test_binary_rejects_wrong_arg_counts(tmp_path: Path) -> None:
    """The binary must enforce exactly two positional args.

    Calls with 0/1/3 args must exit non-zero. With the correct two args
    pointing at fresh empty dirs, it would be expected to fail because the
    inputs are missing -- but absence-of-zero-arg is what we check here, not
    the success path.
    """
    fake_data = tmp_path / "data"
    fake_data.mkdir()
    fake_out = tmp_path / "out"
    fake_out.mkdir()
    for n_args in (0, 1, 3):
        argv = [*_java_cmd(DATA_DIR, OUT_DIR)]
        if n_args >= 1:
            argv.append(str(fake_data))
        if n_args >= 2:
            argv.append(str(fake_out))
        if n_args >= 3:
            argv.append("extra")
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        assert proc.returncode != 0, (
            f"binary should exit non-zero on {n_args} arg(s); got rc=0 "
            f"with stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )


def test_outputs_strict_json_formatting(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every output is 2-space, sort-keys, ASCII-only, trailing-newline JSON."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(path)
        assert ok, msg


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def test_outputs_are_ascii_at_every_depth(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every string at every depth in every output JSON must be pure ASCII."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        raw = path.read_bytes()
        for i, b in enumerate(raw):
            assert b < 0x80, (
                f"{path} byte {i} = 0x{b:02x} is non-ASCII; outputs must be "
                "pure ASCII at the byte level"
            )
        doc = json.loads(raw.decode("utf-8"))
        for s in _walk_strings(doc):
            for ch in s:
                assert ord(ch) < 0x80, (
                    f"{path} contains non-ASCII string codepoint U+{ord(ch):04X} "
                    f"in {s!r}"
                )



def test_final_endpoints_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """final_endpoints.json must equal the live-computed reference exactly.

    Stresses:
      - per-endpoint final state, probe counters, last_state_change_seq
      - effective threshold computation (override fallthrough to policy default)
      - endpoints sorted by id ASCII
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(FINAL_EP_PATH)
    assert actual == expected_outputs["final_endpoints"]


def test_state_transitions_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """state_transitions.json must equal the live-computed reference exactly.

    Stresses:
      - chronological seq order (with intra-seq endpoint_id ordering on
        multi-endpoint tick events)
      - reasons drawn only from the closed set
      - both manual and automatic transitions logged
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(TRANSITIONS_PATH)
    assert actual == expected_outputs["state_transitions"]


def test_request_log_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """request_log.json must equal the live-computed reference exactly.

    Stresses:
      - chronological seq order
      - admission decisions per state at admission time
      - E_ENDPOINT_NOT_FOUND requests do NOT enter request_log
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(REQUEST_LOG_PATH)
    assert actual == expected_outputs["request_log"]


def test_diagnostics_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """diagnostics.json must equal the live-computed reference exactly.

    Stresses:
      - per-event seq sort
      - within-event sort by (severity_rank, code, endpoint_id)
      - co-emission rules (W_FORCED_OPEN co-emits N_TRANSITION_TO_OPEN, etc.)
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(DIAG_PATH)
    assert actual == expected_outputs["diagnostics"]


def test_summary_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """summary.json must equal the live-computed reference exactly.

    Stresses:
      - per-bucket transition counters (to_open, to_half_open, to_closed)
      - peak_open_endpoints across the trace
      - total_requests = total_admitted + total_short_circuited
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(SUMMARY_PATH)
    assert actual == expected_outputs["summary"]


def test_diagnostic_codes_are_legal(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every diagnostic code is drawn from the closed set with correct severity,
    and within each event the list is sorted by (severity_rank, code, endpoint_id).
    """
    assert binary_run_outputs["returncode"] == 0
    diag = load_json(DIAG_PATH)
    seqs = [e["seq"] for e in diag["events"]]
    assert seqs == sorted(seqs), f"events not sorted by seq: {seqs}"
    for e in diag["events"]:
        prev = (-1, "", "")
        for d in e["diagnostics"]:
            assert d["code"] in VALID_DIAG_CODES, (
                f"event seq={e['seq']!r}: unknown code {d['code']!r}"
            )
            assert DIAG_SEVERITY[d["code"]] == d["severity"], (
                f"event seq={e['seq']!r}: code {d['code']!r} has wrong "
                f"severity {d['severity']!r}, expected {DIAG_SEVERITY[d['code']]!r}"
            )
            key = (SEVERITY_RANK[d["severity"]], d["code"], d["endpoint_id"])
            assert key >= prev, (
                f"event seq={e['seq']!r}: diagnostics not sorted by "
                f"(severity_rank, code, endpoint_id); got {key} after {prev}"
            )
            prev = key


def test_state_transitions_seq_order(
    binary_run_outputs: dict[str, Any],
) -> None:
    """state_transitions.transitions must be sorted by seq ascending; within a
    single seq, by endpoint_id ASCII."""
    assert binary_run_outputs["returncode"] == 0
    doc = load_json(TRANSITIONS_PATH)
    keys = [(t["seq"], t["endpoint_id"]) for t in doc["transitions"]]
    assert keys == sorted(keys), (
        f"state_transitions.transitions not sorted by (seq, endpoint_id): {keys}"
    )


def test_request_log_seq_order(
    binary_run_outputs: dict[str, Any],
) -> None:
    """request_log.requests must be sorted by seq ascending."""
    assert binary_run_outputs["returncode"] == 0
    doc = load_json(REQUEST_LOG_PATH)
    seqs = [r["seq"] for r in doc["requests"]]
    assert seqs == sorted(seqs), f"request_log not sorted by seq: {seqs}"


def test_final_endpoints_id_order(
    binary_run_outputs: dict[str, Any],
) -> None:
    """final_endpoints.endpoints must be sorted by id ASCII ascending."""
    assert binary_run_outputs["returncode"] == 0
    doc = load_json(FINAL_EP_PATH)
    ids = [e["id"] for e in doc["endpoints"]]
    assert ids == sorted(ids), f"final_endpoints not sorted by id: {ids}"


def test_dataset_invariants_exercise_all_branches(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """Dataset-level sanity: at least eight distinct diagnostic codes and at
    least four distinct transition reasons must be exercised. A trivially
    clean trace would mean the simulator is never stressed.
    """
    diag_doc = expected_outputs["diagnostics"]
    seen_codes: set[str] = set()
    for e in diag_doc["events"]:
        for d in e["diagnostics"]:
            seen_codes.add(d["code"])
    assert len(seen_codes) >= 8, (
        f"dataset invariant: expected at least 8 distinct diagnostic codes "
        f"exercised; got {sorted(seen_codes)}"
    )
    seen_reasons: set[str] = set()
    for t in expected_outputs["state_transitions"]["transitions"]:
        seen_reasons.add(t["reason"])
    assert len(seen_reasons) >= 4, (
        f"dataset invariant: expected at least 4 distinct transition reasons; "
        f"got {sorted(seen_reasons)}"
    )
    assert expected_outputs["summary"]["peak_open_endpoints"] >= 1, (
        "dataset invariant: at least one endpoint should be OPEN at some point"
    )
    assert expected_outputs["summary"]["total_short_circuited"] >= 1, (
        "dataset invariant: at least one short-circuited request should occur"
    )


def test_summary_total_requests_sum_invariant(
    binary_run_outputs: dict[str, Any],
) -> None:
    """summary.total_requests must equal total_admitted + total_short_circuited."""
    assert binary_run_outputs["returncode"] == 0
    s = load_json(SUMMARY_PATH)
    assert s["total_requests"] == s["total_admitted"] + s["total_short_circuited"], (
        f"total_requests {s['total_requests']} != "
        f"total_admitted {s['total_admitted']} + "
        f"total_short_circuited {s['total_short_circuited']}"
    )


def test_summary_transitions_partition_invariant(
    binary_run_outputs: dict[str, Any],
) -> None:
    """summary.total_state_transitions must equal the sum of the three to_*
    bucket counters."""
    assert binary_run_outputs["returncode"] == 0
    s = load_json(SUMMARY_PATH)
    bucket_sum = (s["total_transitions_to_closed"]
                  + s["total_transitions_to_half_open"]
                  + s["total_transitions_to_open"])
    assert s["total_state_transitions"] == bucket_sum, (
        f"total_state_transitions {s['total_state_transitions']} != "
        f"closed+half_open+open buckets {bucket_sum}"
    )


def test_per_endpoint_admitted_sum_invariant(
    binary_run_outputs: dict[str, Any],
) -> None:
    """For every endpoint at trace end, total_admitted ==
    total_successes + total_failures + total_timeouts. Removed endpoints are
    out of scope here -- they are no longer in final_endpoints."""
    assert binary_run_outputs["returncode"] == 0
    doc = load_json(FINAL_EP_PATH)
    for ep in doc["endpoints"]:
        s = ep["total_successes"] + ep["total_failures"] + ep["total_timeouts"]
        assert ep["total_admitted"] == s, (
            f"endpoint {ep['id']}: total_admitted {ep['total_admitted']} != "
            f"successes+failures+timeouts {s}"
        )



# ---------------------------------------------------------------------------
# Hidden-dataset behavioural tests (exercise branches the pinned dataset
# may not stress directly).
# ---------------------------------------------------------------------------


def _make_event(seq: int, op: str, **kwargs) -> dict[str, Any]:
    base = {
        "seq": seq, "op": op,
        "endpoint_id": kwargs.get("endpoint_id"),
        "outcome": kwargs.get("outcome"),
        "failure_threshold_pct": kwargs.get("failure_threshold_pct"),
        "window_size": kwargs.get("window_size"),
        "half_open_max_probes": kwargs.get("half_open_max_probes"),
        "recovery_ticks": kwargs.get("recovery_ticks"),
    }
    return base


def _make_endpoint(eid: str, **overrides) -> dict[str, Any]:
    return {
        "id": eid,
        "failure_threshold_pct": overrides.get("failure_threshold_pct"),
        "window_size": overrides.get("window_size"),
        "half_open_max_probes": overrides.get("half_open_max_probes"),
        "recovery_ticks": overrides.get("recovery_ticks"),
    }


def _default_policy(**overrides) -> dict[str, Any]:
    p = {
        "default_failure_threshold_pct": 50,
        "default_window_size": 5,
        "default_half_open_max_probes": 2,
        "default_recovery_ticks": 3,
        "sliding_strategy": "count_based",
        "min_window_observations": 4,
        "track_state_transitions": True,
    }
    p.update(overrides)
    return p


def _run_binary_on(tmp_path: Path,
                   endpoints_doc: dict, events_doc: dict, policy_doc: dict
                   ) -> dict[str, Any]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    (in_dir / "endpoints.json").write_text(json.dumps(endpoints_doc),
                                           encoding="utf-8")
    (in_dir / "events.json").write_text(json.dumps(events_doc),
                                        encoding="utf-8")
    (in_dir / "policy.json").write_text(json.dumps(policy_doc),
                                        encoding="utf-8")
    proc = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"binary failed on hidden dataset: rc={proc.returncode} "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    docs: dict[str, Any] = {}
    for fname in ("final_endpoints.json", "state_transitions.json",
                  "request_log.json", "diagnostics.json", "summary.json"):
        docs[fname] = json.loads((out_dir / fname).read_text(encoding="utf-8"))
    return docs


def _ref_for(endpoints_doc, events_doc, policy_doc):
    return run_simulation(endpoints_doc["endpoints"],
                          events_doc["events"], policy_doc)


def test_hidden_threshold_breach_exact_boundary(tmp_path: Path) -> None:
    """At exactly threshold% failures with >= min_window_observations samples,
    the breaker must trip CLOSED -> OPEN. Off-by-one regressions show up here."""
    eps = {"endpoints": [_make_endpoint("svc",
                                        failure_threshold_pct=50,
                                        window_size=4,
                                        half_open_max_probes=1,
                                        recovery_ticks=2)]}
    evs = {"events": [
        _make_event(0, "request", endpoint_id="svc", outcome="failure"),
        _make_event(1, "request", endpoint_id="svc", outcome="success"),
        _make_event(2, "request", endpoint_id="svc", outcome="failure"),
        _make_event(3, "request", endpoint_id="svc", outcome="success"),
    ]}
    pol = _default_policy(min_window_observations=4)
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    expected = _ref_for(eps, evs, pol)
    assert actual["final_endpoints.json"] == expected["final_endpoints"]
    assert actual["state_transitions.json"] == expected["state_transitions"]
    final = actual["final_endpoints.json"]["endpoints"][0]
    assert final["state"] == "OPEN", (
        f"4 obs at exactly 50% failures should trip OPEN; got {final['state']}"
    )


def test_hidden_min_window_observations_blocks_trip(tmp_path: Path) -> None:
    """A window with fewer than min_window_observations samples must NOT trip
    even at 100% failure rate."""
    eps = {"endpoints": [_make_endpoint("svc",
                                        failure_threshold_pct=50,
                                        window_size=10,
                                        half_open_max_probes=1,
                                        recovery_ticks=2)]}
    evs = {"events": [
        _make_event(0, "request", endpoint_id="svc", outcome="failure"),
        _make_event(1, "request", endpoint_id="svc", outcome="failure"),
        _make_event(2, "request", endpoint_id="svc", outcome="failure"),
    ]}
    pol = _default_policy(min_window_observations=4)
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    final = actual["final_endpoints.json"]["endpoints"][0]
    assert final["state"] == "CLOSED", (
        f"3 < min_window_observations=4 must keep state CLOSED even at 100% "
        f"failure rate; got {final['state']}"
    )
    assert actual["state_transitions.json"]["transitions"] == [], (
        "no transitions should fire when min_window_observations is unmet"
    )


def test_hidden_request_in_open_does_not_recover(tmp_path: Path) -> None:
    """An OPEN endpoint must NOT transition to HALF_OPEN on a request event,
    only on a tick event whose elapsed >= recovery_ticks."""
    eps = {"endpoints": [_make_endpoint("svc",
                                        failure_threshold_pct=50,
                                        window_size=4,
                                        half_open_max_probes=1,
                                        recovery_ticks=2)]}
    evs = {"events": [
        _make_event(0, "request", endpoint_id="svc", outcome="failure"),
        _make_event(1, "request", endpoint_id="svc", outcome="failure"),
        _make_event(2, "request", endpoint_id="svc", outcome="failure"),
        _make_event(3, "request", endpoint_id="svc", outcome="failure"),
        _make_event(4, "request", endpoint_id="svc", outcome="success"),
        _make_event(5, "request", endpoint_id="svc", outcome="success"),
        _make_event(6, "request", endpoint_id="svc", outcome="success"),
    ]}
    pol = _default_policy(min_window_observations=4)
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    final = actual["final_endpoints.json"]["endpoints"][0]
    assert final["state"] == "OPEN", (
        f"requests cannot move OPEN -> HALF_OPEN; got {final['state']}"
    )
    sc = sum(1 for r in actual["request_log.json"]["requests"]
             if r["admission"] == "short_circuited")
    assert sc == 3, (
        f"expected 3 short-circuited requests after the trip; got {sc}"
    )


def test_hidden_tick_recovers_open_to_half_open(tmp_path: Path) -> None:
    """A tick event whose new global_tick - tick_entered_open >= recovery_ticks
    moves the endpoint OPEN -> HALF_OPEN."""
    eps = {"endpoints": [_make_endpoint("svc",
                                        failure_threshold_pct=50,
                                        window_size=4,
                                        half_open_max_probes=1,
                                        recovery_ticks=2)]}
    evs = {"events": [
        _make_event(0, "request", endpoint_id="svc", outcome="failure"),
        _make_event(1, "request", endpoint_id="svc", outcome="failure"),
        _make_event(2, "request", endpoint_id="svc", outcome="failure"),
        _make_event(3, "request", endpoint_id="svc", outcome="failure"),
        _make_event(4, "tick"),
        _make_event(5, "tick"),
    ]}
    pol = _default_policy(min_window_observations=4)
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    expected = _ref_for(eps, evs, pol)
    assert actual["final_endpoints.json"] == expected["final_endpoints"]
    final = actual["final_endpoints.json"]["endpoints"][0]
    assert final["state"] == "HALF_OPEN", (
        f"tick=2 with recovery_ticks=2 should produce HALF_OPEN; "
        f"got {final['state']}"
    )
    transitions = actual["state_transitions.json"]["transitions"]
    reasons = [t["reason"] for t in transitions]
    assert "recovery_timeout" in reasons, (
        f"expected a recovery_timeout transition; got reasons {reasons}"
    )


def test_hidden_half_open_first_failure_reopens(tmp_path: Path) -> None:
    """In HALF_OPEN, the very first failing probe must drop the endpoint back
    to OPEN; subsequent successes do not save it."""
    eps = {"endpoints": [_make_endpoint("svc",
                                        failure_threshold_pct=50,
                                        window_size=4,
                                        half_open_max_probes=3,
                                        recovery_ticks=1)]}
    evs = {"events": [
        _make_event(0, "force_open", endpoint_id="svc"),
        _make_event(1, "tick"),
        _make_event(2, "request", endpoint_id="svc", outcome="failure"),
    ]}
    pol = _default_policy(min_window_observations=4)
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    final = actual["final_endpoints.json"]["endpoints"][0]
    assert final["state"] == "OPEN", (
        f"a single probe failure in HALF_OPEN should re-open; got {final['state']}"
    )
    assert final["probe_failures"] == 0 and final["probe_successes"] == 0, (
        "probe counters must reset on the HALF_OPEN -> OPEN transition; "
        f"got probe_failures={final['probe_failures']!r}, "
        f"probe_successes={final['probe_successes']!r}"
    )
    reasons = [t["reason"]
               for t in actual["state_transitions.json"]["transitions"]]
    assert "probe_failure" in reasons, (
        f"expected a probe_failure transition; got reasons {reasons}"
    )


def test_hidden_half_open_quota_closes(tmp_path: Path) -> None:
    """In HALF_OPEN, after exactly `half_open_max_probes` successful probes
    the endpoint must transition to CLOSED."""
    eps = {"endpoints": [_make_endpoint("svc",
                                        failure_threshold_pct=50,
                                        window_size=4,
                                        half_open_max_probes=2,
                                        recovery_ticks=1)]}
    evs = {"events": [
        _make_event(0, "force_open", endpoint_id="svc"),
        _make_event(1, "tick"),
        _make_event(2, "request", endpoint_id="svc", outcome="success"),
        _make_event(3, "request", endpoint_id="svc", outcome="success"),
    ]}
    pol = _default_policy(min_window_observations=4)
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    final = actual["final_endpoints.json"]["endpoints"][0]
    assert final["state"] == "CLOSED", (
        f"2 successful probes with quota=2 should close; got {final['state']}"
    )
    reasons = [t["reason"]
               for t in actual["state_transitions.json"]["transitions"]]
    assert "probe_success_quota" in reasons, (
        f"expected a probe_success_quota transition; got reasons {reasons}"
    )


def test_hidden_force_open_already_open_is_noop(tmp_path: Path) -> None:
    """force_open on an already-OPEN endpoint emits W_FORCED_OPEN_NOOP and adds
    no new entry to state_transitions (but does refresh tick_entered_open)."""
    eps = {"endpoints": [_make_endpoint("svc",
                                        failure_threshold_pct=50,
                                        window_size=4,
                                        half_open_max_probes=1,
                                        recovery_ticks=10)]}
    evs = {"events": [
        _make_event(0, "force_open", endpoint_id="svc"),
        _make_event(1, "tick"),
        _make_event(2, "force_open", endpoint_id="svc"),
    ]}
    pol = _default_policy(min_window_observations=4)
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    transitions = actual["state_transitions.json"]["transitions"]
    open_transitions = [t for t in transitions
                        if t["endpoint_id"] == "svc" and t["to_state"] == "OPEN"]
    assert len(open_transitions) == 1, (
        f"force_open on already-OPEN must not duplicate a transition; "
        f"got {open_transitions}"
    )
    diag_codes = [d["code"]
                  for e in actual["diagnostics.json"]["events"]
                  for d in e["diagnostics"]]
    assert diag_codes.count("W_FORCED_OPEN_NOOP") >= 1, (
        f"expected W_FORCED_OPEN_NOOP diagnostic; got codes {diag_codes}"
    )


def test_hidden_force_close_already_closed_is_noop(tmp_path: Path) -> None:
    """force_close on an already-CLOSED endpoint emits W_FORCED_CLOSE_NOOP
    and adds no new entry to state_transitions."""
    eps = {"endpoints": [_make_endpoint("svc",
                                        failure_threshold_pct=50,
                                        window_size=4,
                                        half_open_max_probes=1,
                                        recovery_ticks=2)]}
    evs = {"events": [
        _make_event(0, "force_close", endpoint_id="svc"),
    ]}
    pol = _default_policy(min_window_observations=4)
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    assert actual["state_transitions.json"]["transitions"] == [], (
        f"force_close NOOP must not produce a state transition; "
        f"got {actual['state_transitions.json']['transitions']}"
    )
    diag_codes = [d["code"]
                  for e in actual["diagnostics.json"]["events"]
                  for d in e["diagnostics"]]
    assert "W_FORCED_CLOSE_NOOP" in diag_codes, (
        f"expected W_FORCED_CLOSE_NOOP diagnostic; got codes {diag_codes}"
    )


def test_hidden_track_state_transitions_false_empties_list(tmp_path: Path) -> None:
    """When policy.track_state_transitions is false, state_transitions is empty
    even when the endpoint actually transitioned."""
    eps = {"endpoints": [_make_endpoint("svc",
                                        failure_threshold_pct=50,
                                        window_size=4,
                                        half_open_max_probes=1,
                                        recovery_ticks=2)]}
    evs = {"events": [
        _make_event(0, "request", endpoint_id="svc", outcome="failure"),
        _make_event(1, "request", endpoint_id="svc", outcome="failure"),
        _make_event(2, "request", endpoint_id="svc", outcome="failure"),
        _make_event(3, "request", endpoint_id="svc", outcome="failure"),
    ]}
    pol = _default_policy(min_window_observations=4, track_state_transitions=False)
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    final = actual["final_endpoints.json"]["endpoints"][0]
    assert final["state"] == "OPEN", (
        f"the endpoint should still trip OPEN; got {final['state']}"
    )
    assert actual["state_transitions.json"]["transitions"] == [], (
        f"state_transitions must be empty when track_state_transitions=false; "
        f"got {actual['state_transitions.json']['transitions']}"
    )
    assert actual["summary.json"]["total_state_transitions"] == 0, (
        f"summary.total_state_transitions must be 0 when "
        f"track_state_transitions=false; "
        f"got {actual['summary.json']['total_state_transitions']}"
    )



def test_hidden_time_based_sliding_strategy(tmp_path: Path) -> None:
    """Under sliding_strategy=time_based, entries older than
    `current_global_tick - window_size + 1` are pruned. Old failures must
    NOT keep an endpoint trip-able forever -- after enough ticks pass, a
    single later failure stays under the min_window_observations gate."""
    eps = {"endpoints": [_make_endpoint("svc",
                                        failure_threshold_pct=50,
                                        window_size=4,
                                        half_open_max_probes=1,
                                        recovery_ticks=10)]}
    evs = {"events": [
        _make_event(0, "request", endpoint_id="svc", outcome="failure"),
        _make_event(1, "request", endpoint_id="svc", outcome="failure"),
        _make_event(2, "request", endpoint_id="svc", outcome="failure"),
        _make_event(3, "tick"),
        _make_event(4, "tick"),
        _make_event(5, "tick"),
        _make_event(6, "tick"),
        _make_event(7, "request", endpoint_id="svc", outcome="failure"),
    ]}
    pol = _default_policy(min_window_observations=4,
                          sliding_strategy="time_based")
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    expected = _ref_for(eps, evs, pol)
    assert actual["final_endpoints.json"] == expected["final_endpoints"]
    assert actual["state_transitions.json"] == expected["state_transitions"]
    final = actual["final_endpoints.json"]["endpoints"][0]
    assert final["state"] == "CLOSED", (
        f"by tick=4 the three tick=0 failures must be pruned (cutoff = "
        f"4 - window_size 4 + 1 = 1); the seq=7 failure alone is below "
        f"min_window_observations=4 and must not trip. got {final['state']}"
    )
    assert actual["state_transitions.json"]["transitions"] == [], (
        "no transitions should fire when time-based pruning has emptied "
        "the window before the only post-tick failure arrives"
    )


def test_hidden_e_endpoint_not_found_no_request_log_entry(tmp_path: Path) -> None:
    """A request to a missing endpoint must produce E_ENDPOINT_NOT_FOUND in
    diagnostics but NO row in request_log."""
    eps = {"endpoints": [_make_endpoint("svc")]}
    evs = {"events": [
        _make_event(0, "request", endpoint_id="ghost", outcome="success"),
    ]}
    pol = _default_policy()
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    assert actual["request_log.json"]["requests"] == [], (
        f"request_log must not contain entries for missing endpoints; "
        f"got {actual['request_log.json']['requests']}"
    )
    diag_codes = [d["code"]
                  for e in actual["diagnostics.json"]["events"]
                  for d in e["diagnostics"]]
    assert "E_ENDPOINT_NOT_FOUND" in diag_codes, (
        f"expected E_ENDPOINT_NOT_FOUND; got codes {diag_codes}"
    )


def test_hidden_remove_then_add_endpoint(tmp_path: Path) -> None:
    """Unlike region ids, an endpoint id can be re-added after being removed.
    The new endpoint starts with fresh counters in CLOSED."""
    eps = {"endpoints": [_make_endpoint("svc",
                                        failure_threshold_pct=50,
                                        window_size=4,
                                        half_open_max_probes=1,
                                        recovery_ticks=2)]}
    evs = {"events": [
        _make_event(0, "force_open", endpoint_id="svc"),
        _make_event(1, "remove_endpoint", endpoint_id="svc"),
        _make_event(2, "add_endpoint", endpoint_id="svc",
                    failure_threshold_pct=80,
                    window_size=10,
                    half_open_max_probes=1,
                    recovery_ticks=1),
    ]}
    pol = _default_policy()
    actual = _run_binary_on(tmp_path, eps, evs, pol)
    final = actual["final_endpoints.json"]["endpoints"]
    assert len(final) == 1
    e = final[0]
    assert e["state"] == "CLOSED", (
        f"re-added endpoint must start CLOSED; got {e['state']}"
    )
    assert e["state_transition_count"] == 0, (
        f"re-added endpoint must have fresh counters; "
        f"got state_transition_count={e['state_transition_count']}"
    )
    assert e["current_failure_threshold_pct"] == 80, (
        f"re-added endpoint should use its own override; "
        f"got {e['current_failure_threshold_pct']}"
    )


def test_hidden_determinism_two_runs_byte_identical(tmp_path: Path) -> None:
    """Two runs of the binary on the same /app/data inputs into different
    output directories must produce byte-identical files. Catches latent
    nondeterminism (hash-map iteration, address-dependent ordering, etc.).
    """
    in_dir = tmp_path / "data"
    in_dir.mkdir()
    for src in (ENDPOINTS_PATH, EVENTS_PATH, POLICY_PATH):
        shutil.copy2(src, in_dir / src.name)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    out_a.mkdir()
    out_b.mkdir()
    for out in (out_a, out_b):
        proc = subprocess.run(
            [*_java_cmd(in_dir, out)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, (
            f"determinism run failed: rc={proc.returncode} stderr={proc.stderr!r}"
        )
    for fname in ("final_endpoints.json", "state_transitions.json",
                  "request_log.json", "diagnostics.json", "summary.json"):
        a = (out_a / fname).read_bytes()
        b = (out_b / fname).read_bytes()
        assert a == b, (
            f"{fname} differs between two runs on identical input; "
            f"binary is non-deterministic"
        )


# ---------------------------------------------------------------------------
# Anti-tampering: /app/data must be untouched by the binary
# ---------------------------------------------------------------------------


def _snapshot_data_tree() -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for p in sorted(DATA_DIR.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(DATA_DIR))
            snapshot[rel] = sha256_of(p)
    return snapshot


def test_data_dir_tree_unchanged_after_run(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The full file tree under /app/data must be byte-identical before and
    after the binary runs. The binary may not add, remove, rename, or modify
    any file under /app/data -- only read from it.
    """
    assert binary_run_outputs["returncode"] == 0
    after = _snapshot_data_tree()
    expected_files = set(EXPECTED_INPUT_HASHES.keys())
    expected_rel = {str(p.relative_to(DATA_DIR)) for p in expected_files}
    extra = set(after.keys()) - expected_rel
    assert not extra, (
        f"binary created extra files under /app/data: {sorted(extra)}; "
        "the binary must treat /app/data as read-only"
    )
    missing = expected_rel - set(after.keys())
    assert not missing, (
        f"binary removed files from /app/data: {sorted(missing)}"
    )
    for path, expected in EXPECTED_INPUT_HASHES.items():
        rel = str(path.relative_to(DATA_DIR))
        assert after[rel] == expected, (
            f"input file {path} was modified by the binary; "
            f"hash before={expected}, after={after[rel]}"
        )


def test_input_hashes_unchanged_after_run(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Re-hash the three pinned inputs after the binary has finished running.
    Catches a binary that transiently mutates inputs (e.g., to write its own
    intermediate state) and tries to restore them later.
    """
    assert binary_run_outputs["returncode"] == 0
    for path, expected in EXPECTED_INPUT_HASHES.items():
        actual = sha256_of(path)
        assert actual == expected, (
            f"after-run sha256 of {path} is {actual}; expected {expected}. "
            "Binary must not write to inputs even transiently."
        )


# ---------------------------------------------------------------------------
# Malformed-input tests (instruction.md mandates non-zero exit on these)
# ---------------------------------------------------------------------------


def _malformed_run(tmp_path: Path,
                   endpoints_text: str | None,
                   events_text: str | None,
                   policy_text: str | None) -> subprocess.CompletedProcess[str]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    if endpoints_text is not None:
        (in_dir / "endpoints.json").write_text(endpoints_text, encoding="utf-8")
    if events_text is not None:
        (in_dir / "events.json").write_text(events_text, encoding="utf-8")
    if policy_text is not None:
        (in_dir / "policy.json").write_text(policy_text, encoding="utf-8")
    return subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )


_VALID_POLICY_TEXT = json.dumps(_default_policy())
_VALID_ENDPOINTS_TEXT = json.dumps({
    "endpoints": [
        _make_endpoint("svc"),
    ],
})
_VALID_EVENTS_TEXT = json.dumps({"events": []})


def _assert_no_valid_outputs(tmp_path: Path) -> None:
    """When the binary correctly rejects malformed input, the output directory
    must not contain a complete, valid set of canonical outputs. (It is OK if
    some files were partially written before the binary errored.)"""
    out_dir = tmp_path / "out"
    if not out_dir.exists():
        return
    expected_names = {"final_endpoints.json", "state_transitions.json",
                      "request_log.json", "diagnostics.json", "summary.json"}
    present = {p.name for p in out_dir.iterdir() if p.is_file()}
    if expected_names.issubset(present):
        for name in expected_names:
            try:
                json.loads((out_dir / name).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return
        raise AssertionError(
            "binary produced a complete, JSON-parsable output set despite "
            f"malformed input; outputs={sorted(present)}"
        )


def test_binary_rejects_malformed_json_syntax(tmp_path: Path) -> None:
    """An events.json that is not valid JSON must produce a non-zero exit
    AND must not leave a complete, valid output set behind."""
    proc = _malformed_run(
        tmp_path,
        endpoints_text=_VALID_ENDPOINTS_TEXT,
        events_text="{not valid json,",
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted malformed-syntax events.json (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_missing_required_fields(tmp_path: Path) -> None:
    """An endpoints.json whose entries omit required keys must non-zero exit."""
    bad_eps = json.dumps({"endpoints": [{"id": "svc"}]})
    proc = _malformed_run(
        tmp_path,
        endpoints_text=bad_eps,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted endpoint missing override fields (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_wrong_value_types(tmp_path: Path) -> None:
    """An endpoint with a non-integer 'window_size' must produce a non-zero exit."""
    bad_eps = json.dumps({"endpoints": [{
        "id": "svc",
        "failure_threshold_pct": None,
        "window_size": "not-an-integer",
        "half_open_max_probes": None,
        "recovery_ticks": None,
    }]})
    proc = _malformed_run(
        tmp_path,
        endpoints_text=bad_eps,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted endpoint with non-integer window_size "
        f"(rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_non_dense_seq(tmp_path: Path) -> None:
    """events.json must have seq values 0,1,2,... dense and increasing."""
    bad_events = json.dumps({"events": [
        _make_event(0, "tick"),
        _make_event(5, "tick"),
    ]})
    proc = _malformed_run(
        tmp_path,
        endpoints_text=_VALID_ENDPOINTS_TEXT,
        events_text=bad_events,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted non-dense seq values (0,5) (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_duplicate_initial_endpoint_ids(tmp_path: Path) -> None:
    """endpoints.json must contain unique ids."""
    bad_eps = json.dumps({"endpoints": [
        _make_endpoint("svc"),
        _make_endpoint("svc"),
    ]})
    proc = _malformed_run(
        tmp_path,
        endpoints_text=bad_eps,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted duplicate initial endpoint ids "
        f"(rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_missing_input_files(tmp_path: Path) -> None:
    """If any of the three required input files is missing from argv[1], the
    binary must exit non-zero (and not silently produce empty outputs)."""
    proc = _malformed_run(
        tmp_path,
        endpoints_text=_VALID_ENDPOINTS_TEXT,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=None,
    )
    assert proc.returncode != 0, (
        f"binary accepted missing policy.json (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_unknown_sliding_strategy(tmp_path: Path) -> None:
    """policy.sliding_strategy must be one of count_based / time_based."""
    bad_pol = json.dumps(_default_policy(sliding_strategy="exponential"))
    proc = _malformed_run(
        tmp_path,
        endpoints_text=_VALID_ENDPOINTS_TEXT,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=bad_pol,
    )
    assert proc.returncode != 0, (
        f"binary accepted policy.sliding_strategy='exponential' "
        f"(rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_unknown_op(tmp_path: Path) -> None:
    """events.json op must be one of the closed set."""
    bad_events = json.dumps({"events": [{
        "seq": 0, "op": "explode", "endpoint_id": "svc",
        "outcome": None, "failure_threshold_pct": None,
        "window_size": None, "half_open_max_probes": None,
        "recovery_ticks": None,
    }]})
    proc = _malformed_run(
        tmp_path,
        endpoints_text=_VALID_ENDPOINTS_TEXT,
        events_text=bad_events,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted op='explode' (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)



# ---------------------------------------------------------------------------
# Property-based / randomized hidden datasets
# ---------------------------------------------------------------------------


def _gen_random_dataset(seed: int, *,
                        n_initial: int = 4,
                        n_events: int = 50,
                        sliding_strategy: str = "count_based",
                        ) -> tuple[dict, dict, dict]:
    """Deterministic pseudo-random dataset generator. Pure Python `random`
    seeded for reproducibility. Returns (endpoints_doc, events_doc, policy_doc)
    that the reference is guaranteed to accept (no malformed inputs)."""
    import random
    rng = random.Random(seed)
    ep_ids = [f"svc_{i}" for i in range(n_initial)]
    initial: list[dict] = []
    used_ids: set[str] = set()
    for eid in ep_ids:
        used_ids.add(eid)
        initial.append({
            "id": eid,
            "failure_threshold_pct": rng.choice([None, 25, 40, 50, 60, 75]),
            "window_size": rng.choice([None, 4, 6, 8]),
            "half_open_max_probes": rng.choice([None, 1, 2, 3]),
            "recovery_ticks": rng.choice([None, 0, 1, 2, 4]),
        })

    next_n = n_initial
    events: list[dict] = []
    op_choices = (["request"] * 6
                  + ["tick"] * 3
                  + ["force_open", "force_close",
                     "config_update",
                     "add_endpoint", "remove_endpoint"])
    for seq in range(n_events):
        op = rng.choice(op_choices)
        if op == "request":
            target = rng.choice(sorted(used_ids) + ["ghost_x"])
            outcome = rng.choices(
                ["success", "failure", "timeout"],
                weights=[5, 3, 2], k=1,
            )[0]
            events.append(_make_event(seq, "request",
                                      endpoint_id=target, outcome=outcome))
        elif op == "tick":
            events.append(_make_event(seq, "tick"))
        elif op == "force_open":
            target = rng.choice(sorted(used_ids) + ["ghost_x"])
            events.append(_make_event(seq, "force_open", endpoint_id=target))
        elif op == "force_close":
            target = rng.choice(sorted(used_ids) + ["ghost_x"])
            events.append(_make_event(seq, "force_close", endpoint_id=target))
        elif op == "config_update":
            target = rng.choice(sorted(used_ids) + ["ghost_x"])
            events.append(_make_event(seq, "config_update",
                                      endpoint_id=target,
                                      failure_threshold_pct=rng.choice(
                                          [None, 30, 50, 70]),
                                      window_size=rng.choice(
                                          [None, 4, 6]),
                                      half_open_max_probes=rng.choice(
                                          [None, 1, 2]),
                                      recovery_ticks=rng.choice(
                                          [None, 1, 2, 3])))
        elif op == "add_endpoint":
            new_id = f"svc_{next_n}"
            next_n += 1
            events.append(_make_event(seq, "add_endpoint",
                                      endpoint_id=new_id,
                                      failure_threshold_pct=rng.choice(
                                          [None, 50, 75]),
                                      window_size=rng.choice([None, 4]),
                                      half_open_max_probes=rng.choice(
                                          [None, 1, 2]),
                                      recovery_ticks=rng.choice(
                                          [None, 1, 2])))
            used_ids.add(new_id)
        elif op == "remove_endpoint":
            ids = sorted(used_ids)
            target = rng.choice(ids + ["ghost_x"]) if ids else "ghost_x"
            events.append(_make_event(seq, "remove_endpoint",
                                      endpoint_id=target))
            used_ids.discard(target)

    endpoints_doc = {"endpoints": initial}
    events_doc = {"events": events}
    policy_doc = _default_policy(sliding_strategy=sliding_strategy,
                                 default_recovery_ticks=rng.choice([1, 2, 3]),
                                 min_window_observations=rng.choice([2, 3, 4]))
    return endpoints_doc, events_doc, policy_doc


@pytest.mark.parametrize("seed", [101, 202, 303, 404, 505])
def test_randomized_property_dataset_against_reference(
    tmp_path: Path, seed: int,
) -> None:
    """Generate a fresh pseudo-random dataset at test time and assert the
    binary's outputs match the live reference. With diverse inputs and
    a different seed in each parametrize, an agent cannot precompute
    expected outputs offline and embed them as JSON literals.
    """
    endpoints, events, policy = _gen_random_dataset(seed)
    actual = _run_binary_on(tmp_path, endpoints, events, policy)
    expected = _ref_for(endpoints, events, policy)
    for name, key in (("final_endpoints.json", "final_endpoints"),
                      ("state_transitions.json", "state_transitions"),
                      ("request_log.json", "request_log"),
                      ("diagnostics.json", "diagnostics"),
                      ("summary.json", "summary")):
        assert actual[name] == expected[key], (
            f"seed={seed}: binary {name} differs from reference"
        )


@pytest.mark.parametrize("seed", [11, 22, 33])
def test_randomized_property_dataset_with_time_based_strategy(
    tmp_path: Path, seed: int,
) -> None:
    """Same as above but pinned to sliding_strategy='time_based' to
    specifically exercise the tick-driven pruning path."""
    endpoints, events, policy = _gen_random_dataset(
        seed, sliding_strategy="time_based")
    actual = _run_binary_on(tmp_path, endpoints, events, policy)
    expected = _ref_for(endpoints, events, policy)
    for name, key in (("final_endpoints.json", "final_endpoints"),
                      ("state_transitions.json", "state_transitions"),
                      ("summary.json", "summary")):
        assert actual[name] == expected[key], (
            f"seed={seed} time_based: binary {name} differs from reference"
        )


def test_randomized_property_dataset_no_initial_endpoints(
    tmp_path: Path,
) -> None:
    """An empty initial endpoint set with mostly add/request events.
    Ensures the binary does not assume the initial table is non-empty."""
    endpoints, events, policy = _gen_random_dataset(
        seed=777, n_initial=0, n_events=30,
    )
    actual = _run_binary_on(tmp_path, endpoints, events, policy)
    expected = _ref_for(endpoints, events, policy)
    assert actual["final_endpoints.json"] == expected["final_endpoints"]
    assert actual["state_transitions.json"] == expected["state_transitions"]
    assert actual["summary.json"] == expected["summary"]


# ---------------------------------------------------------------------------
# Documentation cross-checks
# ---------------------------------------------------------------------------


DOCS_OUTPUT_FORMAT_PATH = Path("/app/docs/output_format.md")


def _expected_summary_keys_from_docs() -> set[str]:
    """Parse /app/docs/output_format.md for the documented summary key set
    rather than hardcoding it in the test file. The summary block looks like:
        "endpoints_at_end":               <int>,
    """
    import re
    text = DOCS_OUTPUT_FORMAT_PATH.read_text(encoding="utf-8")
    summary_match = re.search(r"##\s+`summary\.json`(.*?)(?:^##\s+|\Z)",
                              text, flags=re.DOTALL | re.MULTILINE)
    if summary_match is None:
        raise RuntimeError(
            "could not locate summary.json section in output_format.md"
        )
    summary_block = summary_match.group(1)
    keys = set(re.findall(r'"([a-z_]+)"\s*:', summary_block))
    if not keys:
        raise RuntimeError(
            "could not extract any summary keys from output_format.md"
        )
    return keys


def test_summary_keys_match_documented_set(
    binary_run_outputs: dict[str, Any],
) -> None:
    """summary.json's top-level keys must exactly match the set documented in
    /app/docs/output_format.md. The docs are the source of truth, not a
    hardcoded list in this test file."""
    assert binary_run_outputs["returncode"] == 0
    expected = _expected_summary_keys_from_docs()
    actual = set(load_json(SUMMARY_PATH).keys())
    extra = actual - expected
    missing = expected - actual
    assert not extra, (
        f"summary.json has undocumented keys: {sorted(extra)}; "
        f"docs expect exactly {sorted(expected)}"
    )
    assert not missing, (
        f"summary.json missing documented keys: {sorted(missing)}"
    )
