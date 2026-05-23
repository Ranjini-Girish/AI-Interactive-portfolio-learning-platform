"""Verifier suite for Replay (java)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
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

PROCESSES_PATH = DATA_DIR / "processes.json"
EVENTS_PATH    = DATA_DIR / "events.json"
POLICY_PATH    = DATA_DIR / "policy.json"

PROCESS_STATE_PATH = OUT_DIR / "process_state.json"
HARVEST_LOG_PATH      = OUT_DIR / "harvest_log.json"
DIAG_PATH          = OUT_DIR / "process_diagnostics.json"
LINEAGE_PATH       = OUT_DIR / "lineage_graph.json"
SUMMARY_PATH       = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    PROCESS_STATE_PATH,
    HARVEST_LOG_PATH,
    DIAG_PATH,
    LINEAGE_PATH,
    SUMMARY_PATH,
)

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    PROCESSES_PATH: "fc9b55283a7dd8bb375182bd00c80728e7a8568ffce6c0a1232830d14c47b856",
    EVENTS_PATH:    "80d8e8a43bd6bab17d499a60c236745a8ac5c41c67f6810020b0f759e1a788ce",
    POLICY_PATH:    "272b15318212f669662fdc7a932ef286f97067e7b98e20c30f69eab80f3c7ea5",
}

DOCS_DIAG_PATH = Path("/app/docs/diagnostics.md")

VALID_SIGNALS = frozenset({"SIGTERM", "SIGKILL", "SIGINT", "SIGCHLD"})
VALID_OPS = frozenset({"fork", "exit", "wait", "kill", "exec"})


def _load_diag_codes_from_docs() -> tuple[frozenset[str], dict[str, str]]:
    """Parse /app/docs/diagnostics.md for the canonical list of diagnostic
    codes and their severities. Code lines look like:
        | E_INVALID_PARENT       | error    | ...
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


def _diag(diags: dict[int, list[dict[str, Any]]],
          seq: int, code: str, pid: int | None) -> None:
    diags.setdefault(seq, []).append({
        "code": code,
        "pid": pid,
        "severity": DIAG_SEVERITY[code],
    })


def _run_orphan_harvest_pipeline(processes: dict[int, dict[str, Any]],
                              just_died_pid: int,
                              seq: int, tick: int,
                              policy: dict[str, Any],
                              diagnostics: dict[int, list[dict[str, Any]]],
                              harvest_log: list[dict[str, Any]],
                              lineage_edges: set[tuple[int, int, str]],
                              counters: dict[str, int]) -> None:
    children = [pid for pid, p in processes.items()
                if pid != just_died_pid
                and p["ppid"] == just_died_pid
                and p["state"] in ("RUNNING", "ZOMBIE")]
    children.sort()
    for child in children:
        _diag(diagnostics, seq, "W_ORPHANED", child)
        counters["orphans_reparented"] += 1
        if policy["orphan_handling"] == "reparent_to_init":
            processes[child]["ppid"] = policy["init_pid"]
            if policy["track_lineage"]:
                lineage_edges.add((policy["init_pid"], child, "reparent_init"))

    if (policy["implicit_init_harvest"]
            and policy["orphan_handling"] == "reparent_to_init"):
        for child in children:
            p = processes.get(child)
            if p is None:
                continue
            if p["state"] == "ZOMBIE" and p["ppid"] == policy["init_pid"]:
                p["state"] = "EXITED"
                harvest_log.append({
                    "parent_pid": policy["init_pid"],
                    "pid": child,
                    "seq": seq,
                    "tick": tick,
                    "trigger": "init_harvest",
                })
                _diag(diagnostics, seq, "N_AUTO_HARVESTED", child)

    if policy["implicit_init_harvest"]:
        p = processes.get(just_died_pid)
        if p is not None and p["state"] == "ZOMBIE" and p["ppid"] == policy["init_pid"]:
            p["state"] = "EXITED"
            harvest_log.append({
                "parent_pid": policy["init_pid"],
                "pid": just_died_pid,
                "seq": seq,
                "tick": tick,
                "trigger": "init_harvest",
            })
            _diag(diagnostics, seq, "N_AUTO_HARVESTED", just_died_pid)


def _compute_sccs(nodes: list[int],
                  edges: set[tuple[int, int]]) -> list[list[int]]:
    out_n: dict[int, list[int]] = {n: [] for n in nodes}
    for a, b in edges:
        if a in out_n:
            out_n[a].append(b)
    for n in out_n:
        out_n[n].sort()
    indices: dict[int, int] = {}
    lowlink: dict[int, int] = {}
    on_stack: dict[int, bool] = {}
    stack: list[int] = []
    idx_counter = [0]
    sccs: list[list[int]] = []

    def strongconnect(v: int) -> None:
        call_stack: list[tuple[int, int]] = [(v, 0)]
        while call_stack:
            cur, child_pos = call_stack[-1]
            if child_pos == 0:
                indices[cur] = idx_counter[0]
                lowlink[cur] = idx_counter[0]
                idx_counter[0] += 1
                stack.append(cur)
                on_stack[cur] = True
            children = out_n.get(cur, [])
            if child_pos < len(children):
                w = children[child_pos]
                call_stack[-1] = (cur, child_pos + 1)
                if w not in indices:
                    call_stack.append((w, 0))
                elif on_stack.get(w, False):
                    lowlink[cur] = min(lowlink[cur], indices[w])
            else:
                if lowlink[cur] == indices[cur]:
                    scc: list[int] = []
                    while True:
                        x = stack.pop()
                        on_stack[x] = False
                        scc.append(x)
                        if x == cur:
                            break
                    sccs.append(sorted(scc))
                call_stack.pop()
                if call_stack:
                    pv = call_stack[-1][0]
                    lowlink[pv] = min(lowlink[pv], lowlink[cur])

    for n in nodes:
        if n not in indices:
            strongconnect(n)
    return sorted([sorted(s) for s in sccs if len(s) > 1], key=lambda c: c[0])


def run_simulation(initial_procs: list[dict[str, Any]],
                   events: list[dict[str, Any]],
                   policy: dict[str, Any]) -> dict[str, Any]:
    processes: dict[int, dict[str, Any]] = {}
    for p in initial_procs:
        processes[p["pid"]] = {
            "cmdline": p["cmdline"],
            "exit_code": None,
            "exit_signal": None,
            "exit_tick": None,
            "exit_seq": None,
            "pid": p["pid"],
            "ppid": p["ppid"],
            "start_tick": p["start_tick"],
            "state": "RUNNING",
            "uid": p["uid"],
        }
    seen_pids: set[int] = set(processes)
    diagnostics: dict[int, list[dict[str, Any]]] = {}
    harvest_log: list[dict[str, Any]] = []
    lineage_edges: set[tuple[int, int, str]] = set()
    counters = {
        "forks_succeeded": 0,
        "forks_rejected": 0,
        "killed_by_signal": 0,
        "orphans_reparented": 0,
        "max_concurrent_processes": 0,
    }

    def update_max_concurrent() -> None:
        c = sum(1 for p in processes.values() if p["state"] in ("RUNNING", "ZOMBIE"))
        if c > counters["max_concurrent_processes"]:
            counters["max_concurrent_processes"] = c

    update_max_concurrent()

    def is_running(pid: int) -> bool:
        return pid in processes and processes[pid]["state"] == "RUNNING"

    for ev in events:
        seq = ev["seq"]
        tick = ev["tick"]
        op = ev["op"]
        if op == "fork":
            parent_pid = ev["parent_pid"]
            new_pid = ev["pid"]
            if parent_pid is None or not is_running(parent_pid):
                _diag(diagnostics, seq, "E_INVALID_PARENT", parent_pid)
                counters["forks_rejected"] += 1
                continue
            if new_pid in seen_pids:
                _diag(diagnostics, seq, "E_PID_REUSED", new_pid)
                counters["forks_rejected"] += 1
                continue
            cmdline = ev["cmdline"] if ev["cmdline"] is not None else processes[parent_pid]["cmdline"]
            processes[new_pid] = {
                "cmdline": cmdline,
                "exit_code": None,
                "exit_signal": None,
                "exit_tick": None,
                "exit_seq": None,
                "pid": new_pid,
                "ppid": parent_pid,
                "start_tick": tick,
                "state": "RUNNING",
                "uid": processes[parent_pid]["uid"],
            }
            seen_pids.add(new_pid)
            counters["forks_succeeded"] += 1
            if policy["track_lineage"]:
                lineage_edges.add((parent_pid, new_pid, "fork"))
            update_max_concurrent()
        elif op == "exit":
            pid = ev["pid"]
            if pid not in processes:
                _diag(diagnostics, seq, "E_INVALID_TARGET", pid)
                continue
            if processes[pid]["state"] != "RUNNING":
                _diag(diagnostics, seq, "E_DOUBLE_EXIT", pid)
                continue
            p = processes[pid]
            p["state"] = "ZOMBIE"
            p["exit_tick"] = tick
            p["exit_code"] = ev["exit_code"]
            p["exit_signal"] = None
            p["exit_seq"] = seq
            _run_orphan_harvest_pipeline(processes, pid, seq, tick, policy,
                                      diagnostics, harvest_log, lineage_edges,
                                      counters)
            update_max_concurrent()
        elif op == "kill":
            issuer = ev["pid"]
            target = ev["target_pid"]
            if not is_running(issuer):
                _diag(diagnostics, seq, "E_INVALID_TARGET", issuer)
                continue
            if target is None or not is_running(target):
                _diag(diagnostics, seq, "E_INVALID_TARGET", target)
                continue
            sig = ev["signal"]
            if sig == "SIGCHLD":
                continue
            p = processes[target]
            p["state"] = "ZOMBIE"
            p["exit_tick"] = tick
            p["exit_code"] = None
            p["exit_signal"] = sig
            p["exit_seq"] = seq
            _diag(diagnostics, seq, "W_KILLED_BY_SIGNAL", target)
            counters["killed_by_signal"] += 1
            _run_orphan_harvest_pipeline(processes, target, seq, tick, policy,
                                      diagnostics, harvest_log, lineage_edges,
                                      counters)
            update_max_concurrent()
        elif op == "wait":
            issuer = ev["pid"]
            target = ev["target_pid"]
            if not is_running(issuer):
                _diag(diagnostics, seq, "E_INVALID_TARGET", issuer)
                continue
            if target is not None:
                if target not in processes:
                    _diag(diagnostics, seq, "E_INVALID_TARGET", target)
                    continue
                if processes[target]["ppid"] != issuer:
                    _diag(diagnostics, seq, "E_NOT_CHILD", target)
                    continue
                if processes[target]["state"] == "RUNNING":
                    if policy["wait_on_living_child"] == "diagnostic":
                        _diag(diagnostics, seq, "E_NOT_ZOMBIE", target)
                    continue
                if processes[target]["state"] == "EXITED":
                    _diag(diagnostics, seq, "E_INVALID_TARGET", target)
                    continue
                resolved = target
            else:
                zombies = sorted(pid for pid, p in processes.items()
                                 if p["ppid"] == issuer and p["state"] == "ZOMBIE")
                if not zombies:
                    _diag(diagnostics, seq, "E_NOT_ZOMBIE", None)
                    continue
                resolved = zombies[0]
            processes[resolved]["state"] = "EXITED"
            _diag(diagnostics, seq, "N_HARVESTED", resolved)
            harvest_log.append({
                "parent_pid": issuer,
                "pid": resolved,
                "seq": seq,
                "tick": tick,
                "trigger": "wait",
            })
            update_max_concurrent()
        elif op == "exec":
            issuer = ev["pid"]
            if not is_running(issuer):
                _diag(diagnostics, seq, "E_INVALID_TARGET", issuer)
                continue
            if ev["cmdline"] is None:
                continue
            processes[issuer]["cmdline"] = ev["cmdline"]

    # End-of-trace W_ZOMBIE_LEAK on every still-zombie process.
    for pid, p in processes.items():
        if p["state"] == "ZOMBIE":
            s = p["exit_seq"] if p["exit_seq"] is not None else 0
            _diag(diagnostics, s, "W_ZOMBIE_LEAK", pid)

    process_state = {
        "processes": [
            {
                "cmdline": p["cmdline"],
                "exit_code": p["exit_code"],
                "exit_signal": p["exit_signal"],
                "exit_tick": p["exit_tick"],
                "pid": p["pid"],
                "ppid": p["ppid"],
                "start_tick": p["start_tick"],
                "state": p["state"],
                "uid": p["uid"],
            }
            for p in sorted(processes.values(), key=lambda x: x["pid"])
        ]
    }
    harvest_doc = {"harvests": list(harvest_log)}
    diag_events = []
    for seq in sorted(diagnostics):
        diags = diagnostics[seq]
        diags_sorted = sorted(diags, key=lambda d: (
            SEVERITY_RANK[d["severity"]],
            d["code"],
            (-1, 0) if d["pid"] is None else (0, d["pid"]),
        ))
        diag_events.append({"diagnostics": diags_sorted, "seq": seq})
    diag_doc = {"events": diag_events}

    if policy["track_lineage"]:
        nodes_set = set(seen_pids)
        for (a, b, _t) in lineage_edges:
            nodes_set.add(a)
            nodes_set.add(b)
        nodes_sorted = sorted(nodes_set)
        edges_sorted = sorted(lineage_edges)
        deduped_pair = {(a, b) for (a, b, _t) in edges_sorted}
        in_count = {n: 0 for n in nodes_sorted}
        out_count = {n: 0 for n in nodes_sorted}
        for (a, b) in deduped_pair:
            out_count[a] += 1
            in_count[b] += 1
        node_arr = [{"id": n, "in_degree": in_count[n], "out_degree": out_count[n]}
                    for n in nodes_sorted]
        edge_arr = [{"from": a, "to": b, "type": t}
                    for (a, b, t) in edges_sorted]
        cycles = _compute_sccs(nodes_sorted, deduped_pair)
        lineage_doc = {"cycles": cycles, "edges": edge_arr, "nodes": node_arr}
    else:
        lineage_doc = {"cycles": [], "edges": [], "nodes": []}

    auto_harvested = sum(1 for r in harvest_log if r["trigger"] == "init_harvest")
    explicit_harvested = sum(1 for r in harvest_log if r["trigger"] == "wait")
    final_alive = sum(1 for p in processes.values() if p["state"] == "RUNNING")
    zombies = sum(1 for p in processes.values() if p["state"] == "ZOMBIE")
    users_at_end = sorted({p["uid"] for p in processes.values()
                           if p["state"] == "RUNNING"})
    summary = {
        "auto_harvested":              auto_harvested,
        "events_with_diagnostics":  len(diag_events),
        "explicit_harvested":          explicit_harvested,
        "final_alive_count":        final_alive,
        "forks_rejected":           counters["forks_rejected"],
        "forks_succeeded":          counters["forks_succeeded"],
        "killed_by_signal":         counters["killed_by_signal"],
        "max_concurrent_processes": counters["max_concurrent_processes"],
        "orphans_reparented":       counters["orphans_reparented"],
        "total_events":             len(events),
        "users_at_end":             users_at_end,
        "zombies_at_end":           zombies,
    }
    return {
        "process_state":       process_state,
        "harvest_log":            harvest_doc,
        "process_diagnostics": diag_doc,
        "lineage_graph":       lineage_doc,
        "summary":             summary,
    }


def reference_outputs() -> dict[str, Any]:
    procs_doc  = load_json(PROCESSES_PATH)
    events_doc = load_json(EVENTS_PATH)
    policy_doc = load_json(POLICY_PATH)
    return run_simulation(procs_doc["processes"], events_doc["events"], policy_doc)


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



def test_java_entry_class_exists():
    """Compiled Java entry class exists under /app/build after the agent build."""
    assert _java_class_ready()




def test_sources_present_and_class_newer():
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
        f"/app/build/proctreehv exited with rc={rc} when run with canonical "
        f"args /app/data /app/output;\nstdout={binary_run_outputs['stdout']!r}\n"
        f"stderr={binary_run_outputs['stderr']!r}"
    )
    start = binary_run_outputs["start"]
    for path in ALL_OUT_PATHS:
        assert path.exists(), f"output missing after binary run: {path}"
        assert path.stat().st_size > 0, f"output empty after binary run: {path}"
        m = path.stat().st_mtime
        assert m + 1.0 >= start, (
            f"output {path} has mtime {m} older than test start {start}"
        )
        load_json(path)
    expected_names = {p.name for p in ALL_OUT_PATHS}
    actual_names = {p.name for p in OUT_DIR.iterdir() if p.is_file()}
    extras = actual_names - expected_names
    assert not extras, (
        f"binary wrote extra files into /app/output: {sorted(extras)}"
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


def _walk_strings(value: Any):
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
                f"{path} byte {i} = 0x{b:02x} is non-ASCII"
            )
        doc = json.loads(raw.decode("utf-8"))
        for s in _walk_strings(doc):
            for ch in s:
                assert ord(ch) < 0x80, (
                    f"{path} contains non-ASCII string codepoint U+{ord(ch):04X} "
                    f"in {s!r}"
                )


def test_process_state_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """process_state.json must equal the live-computed reference exactly."""
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(PROCESS_STATE_PATH)
    assert actual == expected_outputs["process_state"]


def test_harvest_log_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """harvest_log.json must equal the live-computed reference exactly."""
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(HARVEST_LOG_PATH)
    assert actual == expected_outputs["harvest_log"]


def test_process_diagnostics_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """process_diagnostics.json must equal the live-computed reference."""
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(DIAG_PATH)
    assert actual == expected_outputs["process_diagnostics"]


def test_lineage_graph_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """lineage_graph.json must equal the live-computed reference exactly."""
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(LINEAGE_PATH)
    assert actual == expected_outputs["lineage_graph"]


def test_summary_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """summary.json must equal the live-computed reference exactly."""
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(SUMMARY_PATH)
    assert actual == expected_outputs["summary"]


def test_diagnostic_codes_are_legal(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every diagnostic code is drawn from the closed set with correct severity,
    and within each event the list is sorted by (severity_rank, code, pid)."""
    assert binary_run_outputs["returncode"] == 0
    diag = load_json(DIAG_PATH)
    seqs = [e["seq"] for e in diag["events"]]
    assert seqs == sorted(seqs), f"events not sorted by seq: {seqs}"
    for e in diag["events"]:
        prev: tuple[int, str, tuple[int, int]] | None = None
        for d in e["diagnostics"]:
            assert d["code"] in VALID_DIAG_CODES, (
                f"event seq={e['seq']!r}: unknown code {d['code']!r}"
            )
            assert DIAG_SEVERITY[d["code"]] == d["severity"], (
                f"event seq={e['seq']!r}: code {d['code']!r} has wrong "
                f"severity {d['severity']!r}, expected {DIAG_SEVERITY[d['code']]!r}"
            )
            pid_key = (-1, 0) if d["pid"] is None else (0, d["pid"])
            key = (SEVERITY_RANK[d["severity"]], d["code"], pid_key)
            if prev is not None:
                assert key >= prev, (
                    f"event seq={e['seq']!r}: diagnostics not sorted by "
                    f"(severity_rank, code, pid); got {key} after {prev}"
                )
            prev = key


def test_dataset_invariants(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """Dataset-level sanity: at least one zombie leaks at end, at least nine
    of the eleven diagnostic codes are exercised, at least two reparent
    events occur. A trivially clean trace would mean the simulator is never
    stressed.
    """
    expected = expected_outputs
    diag_doc = expected["process_diagnostics"]
    seen_codes: set[str] = set()
    for e in diag_doc["events"]:
        for d in e["diagnostics"]:
            seen_codes.add(d["code"])
    assert len(seen_codes) >= 9, (
        f"dataset invariant: expected at least 9 distinct diagnostic codes "
        f"exercised; got {sorted(seen_codes)}"
    )
    assert "W_ZOMBIE_LEAK" in seen_codes, (
        "dataset invariant: expected at least one zombie to leak at trace end"
    )
    assert expected["summary"]["orphans_reparented"] >= 2, (
        "dataset invariant: expected at least two orphan reparents"
    )
    assert expected["summary"]["forks_succeeded"] >= 3, (
        "dataset invariant: expected at least three successful forks"
    )
    assert expected["summary"]["killed_by_signal"] >= 1, (
        "dataset invariant: expected at least one kill by signal"
    )


# ---------------------------------------------------------------------------
# Hidden-dataset behavioural tests (exercise branches the pinned dataset
# may not stress directly).
# ---------------------------------------------------------------------------


def _run_binary_on(tmp_path: Path,
                   procs_doc: dict, events_doc: dict, policy_doc: dict
                   ) -> dict[str, Any]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    (in_dir / "processes.json").write_text(json.dumps(procs_doc), encoding="utf-8")
    (in_dir / "events.json").write_text(json.dumps(events_doc), encoding="utf-8")
    (in_dir / "policy.json").write_text(json.dumps(policy_doc), encoding="utf-8")
    proc = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"binary failed on hidden dataset: rc={proc.returncode} "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    docs: dict[str, Any] = {}
    for fname in ("process_state.json", "harvest_log.json",
                  "process_diagnostics.json", "lineage_graph.json",
                  "summary.json"):
        docs[fname] = json.loads((out_dir / fname).read_text(encoding="utf-8"))
    return docs


def _ref_for(procs_doc, events_doc, policy_doc):
    return run_simulation(procs_doc["processes"], events_doc["events"], policy_doc)


_BASE_POLICY = {
    "implicit_init_harvest": True,
    "init_pid": 1,
    "orphan_handling": "reparent_to_init",
    "track_lineage": True,
    "wait_on_living_child": "diagnostic",
}


def _ev(seq: int, op: str, pid: int, *, tick: int = 0,
        parent_pid=None, target_pid=None, exit_code=None,
        signal=None, cmdline=None) -> dict:
    return {
        "seq": seq, "tick": tick, "op": op, "pid": pid,
        "parent_pid": parent_pid, "target_pid": target_pid,
        "exit_code": exit_code, "signal": signal, "cmdline": cmdline,
    }


def test_hidden_orphan_reparent_to_init_flag_off(tmp_path: Path) -> None:
    """Under orphan_handling='leave_orphaned', W_ORPHANED still fires but
    the child's ppid is NOT rewritten to init_pid and no 'reparent_init'
    lineage edge is added."""
    procs = {"processes": [
        {"cmdline": "/sbin/init", "pid": 1, "ppid": 0,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
        {"cmdline": "/bin/p", "pid": 100, "ppid": 1,
         "start_tick": 0, "state": "RUNNING", "uid": 1000},
    ]}
    events = {"events": [
        _ev(0, "fork",  pid=200, parent_pid=100, tick=1, cmdline="/bin/c"),
        _ev(1, "exit",  pid=100, exit_code=0, tick=2),
    ]}
    policy = dict(_BASE_POLICY)
    policy["orphan_handling"] = "leave_orphaned"
    policy["implicit_init_harvest"] = False
    actual = _run_binary_on(tmp_path, procs, events, policy)
    expected = _ref_for(procs, events, policy)
    assert actual["process_state.json"] == expected["process_state"]
    assert actual["lineage_graph.json"] == expected["lineage_graph"]
    state_pids = {p["pid"]: p for p in actual["process_state.json"]["processes"]}
    assert state_pids[200]["ppid"] == 100, (
        f"under leave_orphaned, child 200's ppid stays at 100 (the "
        f"now-zombie parent); got ppid={state_pids[200]['ppid']}"
    )
    edge_types = {e["type"] for e in actual["lineage_graph.json"]["edges"]}
    assert "reparent_init" not in edge_types, (
        "leave_orphaned must NOT produce reparent_init lineage edges"
    )
    diag_codes = {d["code"]
                  for e in actual["process_diagnostics.json"]["events"]
                  for d in e["diagnostics"]}
    assert "W_ORPHANED" in diag_codes, (
        "W_ORPHANED still fires under leave_orphaned"
    )


def test_hidden_implicit_init_harvest_off_leaves_zombies(tmp_path: Path) -> None:
    """Under implicit_init_harvest=false, init's direct zombie children are
    NOT auto-harvested. They sit as zombies until trace end, when W_ZOMBIE_LEAK
    fires."""
    procs = {"processes": [
        {"cmdline": "/sbin/init", "pid": 1, "ppid": 0,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
        {"cmdline": "/bin/c", "pid": 100, "ppid": 1,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
    ]}
    events = {"events": [
        _ev(0, "exit", pid=100, exit_code=0, tick=5),
    ]}
    policy = dict(_BASE_POLICY)
    policy["implicit_init_harvest"] = False
    actual = _run_binary_on(tmp_path, procs, events, policy)
    expected = _ref_for(procs, events, policy)
    assert actual["process_state.json"] == expected["process_state"]
    assert actual["harvest_log.json"] == expected["harvest_log"]
    assert actual["process_diagnostics.json"] == expected["process_diagnostics"]
    state = {p["pid"]: p for p in actual["process_state.json"]["processes"]}
    assert state[100]["state"] == "ZOMBIE", (
        "implicit_init_harvest=false leaves init's zombie child unharvested"
    )
    assert actual["harvest_log.json"]["harvests"] == [], (
        "implicit_init_harvest=false produces no harvest_log entries"
    )
    diag_codes = [d["code"]
                  for e in actual["process_diagnostics.json"]["events"]
                  for d in e["diagnostics"]]
    assert "W_ZOMBIE_LEAK" in diag_codes, (
        "the unharvested zombie should emit W_ZOMBIE_LEAK at trace end"
    )


def test_hidden_track_lineage_false_empties_graph(tmp_path: Path) -> None:
    """When policy.track_lineage is false, lineage_graph carries empty
    cycles, edges, and nodes regardless of how many forks the trace
    contains."""
    procs = {"processes": [
        {"cmdline": "/sbin/init", "pid": 1, "ppid": 0,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
    ]}
    events = {"events": [
        _ev(0, "fork", pid=100, parent_pid=1, tick=1, cmdline="/bin/x"),
        _ev(1, "fork", pid=101, parent_pid=100, tick=2, cmdline="/bin/y"),
    ]}
    policy = dict(_BASE_POLICY)
    policy["track_lineage"] = False
    actual = _run_binary_on(tmp_path, procs, events, policy)
    assert actual["lineage_graph.json"] == {"cycles": [], "edges": [], "nodes": []}, (
        "track_lineage=false must suppress all graph contents; got "
        f"{actual['lineage_graph.json']}"
    )


def test_hidden_wait_on_living_child_noop(tmp_path: Path) -> None:
    """Under wait_on_living_child='noop', a wait on a still-RUNNING child
    is a silent no-op (no diagnostic, no harvest)."""
    procs = {"processes": [
        {"cmdline": "/sbin/init", "pid": 1, "ppid": 0,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
        {"cmdline": "/bin/p", "pid": 100, "ppid": 1,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
    ]}
    events = {"events": [
        _ev(0, "fork", pid=200, parent_pid=100, tick=1, cmdline="/bin/c"),
        _ev(1, "wait", pid=100, target_pid=200, tick=2),
    ]}
    policy = dict(_BASE_POLICY)
    policy["wait_on_living_child"] = "noop"
    actual = _run_binary_on(tmp_path, procs, events, policy)
    expected = _ref_for(procs, events, policy)
    assert actual["process_diagnostics.json"] == expected["process_diagnostics"]
    diag = actual["process_diagnostics.json"]
    seq1 = next((e for e in diag["events"] if e["seq"] == 1), None)
    assert seq1 is None, (
        f"wait on living child under noop must emit nothing; got {seq1}"
    )
    assert actual["harvest_log.json"]["harvests"] == [], (
        "noop wait must not produce any harvest"
    )


def test_hidden_pid_reuse_after_exit_then_harvested(tmp_path: Path) -> None:
    """A pid that was once seen (initial OR via successful fork) cannot be
    re-introduced even after it has been EXITED (harvested)."""
    procs = {"processes": [
        {"cmdline": "/sbin/init", "pid": 1, "ppid": 0,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
    ]}
    events = {"events": [
        _ev(0, "fork", pid=42, parent_pid=1, tick=1, cmdline="/bin/x"),
        _ev(1, "exit", pid=42, exit_code=0, tick=2),
        _ev(2, "fork", pid=42, parent_pid=1, tick=3, cmdline="/bin/y"),
    ]}
    policy = dict(_BASE_POLICY)
    actual = _run_binary_on(tmp_path, procs, events, policy)
    expected = _ref_for(procs, events, policy)
    assert actual["process_diagnostics.json"] == expected["process_diagnostics"]
    diag = actual["process_diagnostics.json"]
    seq2 = next((e for e in diag["events"] if e["seq"] == 2), None)
    assert seq2 is not None, "pid-reuse fork must emit a diagnostic"
    assert any(d["code"] == "E_PID_REUSED" and d["pid"] == 42
               for d in seq2["diagnostics"]), (
        f"re-using pid 42 after harvest must emit E_PID_REUSED; got {seq2}"
    )


def test_hidden_kill_chain_with_grandchild_orphan(tmp_path: Path) -> None:
    """Killing a non-init parent reparents its grandchildren to init, and
    those grandchildren are auto-harvested immediately if they are zombies."""
    procs = {"processes": [
        {"cmdline": "/sbin/init", "pid": 1, "ppid": 0,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
    ]}
    events = {"events": [
        _ev(0, "fork", pid=100, parent_pid=1, tick=1, cmdline="/bin/p"),
        _ev(1, "fork", pid=200, parent_pid=100, tick=2, cmdline="/bin/c"),
        _ev(2, "exit", pid=200, exit_code=7, tick=3),
        _ev(3, "kill", pid=1, target_pid=100, signal="SIGKILL", tick=4),
    ]}
    policy = dict(_BASE_POLICY)
    actual = _run_binary_on(tmp_path, procs, events, policy)
    expected = _ref_for(procs, events, policy)
    assert actual["process_state.json"] == expected["process_state"]
    assert actual["harvest_log.json"] == expected["harvest_log"]
    state = {p["pid"]: p for p in actual["process_state.json"]["processes"]}
    assert state[200]["state"] == "EXITED", (
        f"grandchild zombie 200 must be auto-harvested after parent 100 is "
        f"killed and 200 is reparented to init; got state={state[200]['state']}"
    )
    triggers = [r["trigger"] for r in actual["harvest_log.json"]["harvests"]]
    assert triggers.count("init_harvest") >= 2, (
        f"expected at least 2 init_harvests (200 + 100); got {triggers}"
    )


def test_hidden_kill_on_zombie_target_rejects(tmp_path: Path) -> None:
    """A kill against a target that is already ZOMBIE must emit
    E_INVALID_TARGET (target is no longer in the alive set), not a second
    W_KILLED_BY_SIGNAL."""
    procs = {"processes": [
        {"cmdline": "/sbin/init", "pid": 1, "ppid": 0,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
        {"cmdline": "/bin/x", "pid": 100, "ppid": 1,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
    ]}
    events = {"events": [
        _ev(0, "exit", pid=100, exit_code=0, tick=1),
        _ev(1, "kill", pid=1, target_pid=100, signal="SIGTERM", tick=2),
    ]}
    policy = dict(_BASE_POLICY)
    policy["implicit_init_harvest"] = False
    actual = _run_binary_on(tmp_path, procs, events, policy)
    expected = _ref_for(procs, events, policy)
    assert actual["process_diagnostics.json"] == expected["process_diagnostics"]
    diag = actual["process_diagnostics.json"]
    seq1 = next((e for e in diag["events"] if e["seq"] == 1), None)
    assert seq1 is not None
    codes_at_seq1 = {d["code"] for d in seq1["diagnostics"]}
    assert codes_at_seq1 == {"E_INVALID_TARGET"}, (
        f"kill on zombie target must produce only E_INVALID_TARGET at "
        f"seq=1; got {codes_at_seq1}"
    )


def test_hidden_sigchld_is_silent_no_op(tmp_path: Path) -> None:
    """SIGCHLD against a RUNNING target produces no diagnostic and no state
    change. The closed-set check is what gates SIGCHLD against SIGTERM-class
    behaviour."""
    procs = {"processes": [
        {"cmdline": "/sbin/init", "pid": 1, "ppid": 0,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
        {"cmdline": "/bin/x", "pid": 100, "ppid": 1,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
    ]}
    events = {"events": [
        _ev(0, "kill", pid=1, target_pid=100, signal="SIGCHLD", tick=1),
    ]}
    policy = dict(_BASE_POLICY)
    actual = _run_binary_on(tmp_path, procs, events, policy)
    diag = actual["process_diagnostics.json"]
    assert diag["events"] == [], (
        f"SIGCHLD must produce no diagnostic; got {diag['events']}"
    )
    state = {p["pid"]: p for p in actual["process_state.json"]["processes"]}
    assert state[100]["state"] == "RUNNING", (
        "SIGCHLD must not change target state"
    )


def test_hidden_wait_any_with_no_zombies(tmp_path: Path) -> None:
    """A wait with target_pid=null on an issuer with no zombie children
    must emit E_NOT_ZOMBIE with pid=null."""
    procs = {"processes": [
        {"cmdline": "/sbin/init", "pid": 1, "ppid": 0,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
        {"cmdline": "/bin/p", "pid": 100, "ppid": 1,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
    ]}
    events = {"events": [
        _ev(0, "wait", pid=100, target_pid=None, tick=1),
    ]}
    policy = dict(_BASE_POLICY)
    actual = _run_binary_on(tmp_path, procs, events, policy)
    expected = _ref_for(procs, events, policy)
    assert actual["process_diagnostics.json"] == expected["process_diagnostics"]
    diag = actual["process_diagnostics.json"]
    seq0 = next((e for e in diag["events"] if e["seq"] == 0), None)
    assert seq0 is not None
    assert any(d["code"] == "E_NOT_ZOMBIE" and d["pid"] is None
               for d in seq0["diagnostics"]), (
        f"wait-any with no zombies must emit E_NOT_ZOMBIE pid=null; got {seq0}"
    )


def test_hidden_determinism_two_runs_byte_identical(tmp_path: Path) -> None:
    """Two runs of the binary on the same /app/data inputs into different
    output directories must produce byte-identical files. Catches latent
    nondeterminism (hash-map iteration, address-dependent ordering, etc.).
    """
    in_dir = tmp_path / "data"
    in_dir.mkdir()
    for src in (PROCESSES_PATH, EVENTS_PATH, POLICY_PATH):
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
    for fname in ("process_state.json", "harvest_log.json",
                  "process_diagnostics.json", "lineage_graph.json",
                  "summary.json"):
        a = (out_a / fname).read_bytes()
        b = (out_b / fname).read_bytes()
        assert a == b, (
            f"{fname} differs between two runs on identical input"
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
    after the binary runs."""
    assert binary_run_outputs["returncode"] == 0
    after = _snapshot_data_tree()
    expected_files = set(EXPECTED_INPUT_HASHES.keys())
    expected_rel = {str(p.relative_to(DATA_DIR)) for p in expected_files}
    extra = set(after.keys()) - expected_rel
    assert not extra, (
        f"binary created extra files under /app/data: {sorted(extra)}"
    )
    missing = expected_rel - set(after.keys())
    assert not missing, (
        f"binary removed files from /app/data: {sorted(missing)}"
    )
    for path, expected in EXPECTED_INPUT_HASHES.items():
        rel = str(path.relative_to(DATA_DIR))
        assert after[rel] == expected, (
            f"input file {path} was modified by the binary"
        )


def test_input_hashes_unchanged_after_run(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Re-hash the three pinned inputs after the binary has finished running."""
    assert binary_run_outputs["returncode"] == 0
    for path, expected in EXPECTED_INPUT_HASHES.items():
        actual = sha256_of(path)
        assert actual == expected, (
            f"after-run sha256 of {path} is {actual}; expected {expected}"
        )


# ---------------------------------------------------------------------------
# Malformed-input tests (instruction.md mandates non-zero exit on these)
# ---------------------------------------------------------------------------


def _malformed_run(tmp_path: Path,
                   processes_text: str | None,
                   events_text: str | None,
                   policy_text: str | None) -> subprocess.CompletedProcess[str]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    if processes_text is not None:
        (in_dir / "processes.json").write_text(processes_text, encoding="utf-8")
    if events_text is not None:
        (in_dir / "events.json").write_text(events_text, encoding="utf-8")
    if policy_text is not None:
        (in_dir / "policy.json").write_text(policy_text, encoding="utf-8")
    return subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )


_VALID_POLICY_TEXT = json.dumps(_BASE_POLICY)
_VALID_PROCESSES_TEXT = json.dumps({
    "processes": [
        {"cmdline": "/sbin/init", "pid": 1, "ppid": 0,
         "start_tick": 0, "state": "RUNNING", "uid": 0},
    ],
})
_VALID_EVENTS_TEXT = json.dumps({"events": []})


def _assert_no_valid_outputs(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    if not out_dir.exists():
        return
    expected_names = {"process_state.json", "harvest_log.json",
                      "process_diagnostics.json", "lineage_graph.json",
                      "summary.json"}
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
    proc = _malformed_run(
        tmp_path,
        processes_text="{not valid json,",
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted malformed-syntax processes.json (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_missing_required_fields(tmp_path: Path) -> None:
    bad = json.dumps({
        "processes": [
            {"cmdline": "/sbin/init", "pid": 1,
             "start_tick": 0, "state": "RUNNING", "uid": 0},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=bad,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted process missing 'ppid' (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_wrong_value_types(tmp_path: Path) -> None:
    bad = json.dumps({
        "processes": [
            {"cmdline": "/sbin/init", "pid": "not-an-int", "ppid": 0,
             "start_tick": 0, "state": "RUNNING", "uid": 0},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=bad,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted non-integer pid (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_non_dense_seq(tmp_path: Path) -> None:
    bad_events = json.dumps({
        "events": [
            {"seq": 0, "tick": 0, "op": "fork", "pid": 100, "parent_pid": 1,
             "target_pid": None, "exit_code": None, "signal": None,
             "cmdline": "/bin/x"},
            {"seq": 5, "tick": 1, "op": "fork", "pid": 200, "parent_pid": 1,
             "target_pid": None, "exit_code": None, "signal": None,
             "cmdline": "/bin/y"},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=_VALID_PROCESSES_TEXT,
        events_text=bad_events,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted non-dense seq values (0,5) (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_invalid_signal(tmp_path: Path) -> None:
    bad_events = json.dumps({
        "events": [
            {"seq": 0, "tick": 0, "op": "kill", "pid": 1, "parent_pid": None,
             "target_pid": 1, "exit_code": None, "signal": "SIGEVERYTHING",
             "cmdline": None},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=_VALID_PROCESSES_TEXT,
        events_text=bad_events,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted unknown signal (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_missing_input_files(tmp_path: Path) -> None:
    proc = _malformed_run(
        tmp_path,
        processes_text=_VALID_PROCESSES_TEXT,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=None,
    )
    assert proc.returncode != 0, (
        f"binary accepted missing policy.json (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_unknown_op(tmp_path: Path) -> None:
    """events.json with op outside the closed {fork,exit,wait,kill,exec}
    set must produce non-zero exit."""
    bad_events = json.dumps({
        "events": [
            {"seq": 0, "tick": 0, "op": "yeet", "pid": 1, "parent_pid": None,
             "target_pid": None, "exit_code": None, "signal": None,
             "cmdline": None},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=_VALID_PROCESSES_TEXT,
        events_text=bad_events,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted unknown op 'yeet' (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_kill_missing_signal(tmp_path: Path) -> None:
    """A kill event whose signal is null must be rejected as malformed input.
    The handler dereferences the signal field; an unguarded deref of a null
    optional would be undefined behaviour."""
    bad_events = json.dumps({
        "events": [
            {"seq": 0, "tick": 0, "op": "kill", "pid": 1, "parent_pid": None,
             "target_pid": 1, "exit_code": None, "signal": None,
             "cmdline": None},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=_VALID_PROCESSES_TEXT,
        events_text=bad_events,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted kill with null signal (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_kill_missing_target(tmp_path: Path) -> None:
    """A kill event whose target_pid is null must be rejected as malformed."""
    bad_events = json.dumps({
        "events": [
            {"seq": 0, "tick": 0, "op": "kill", "pid": 1, "parent_pid": None,
             "target_pid": None, "exit_code": None, "signal": "SIGTERM",
             "cmdline": None},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=_VALID_PROCESSES_TEXT,
        events_text=bad_events,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted kill with null target_pid (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_negative_pid(tmp_path: Path) -> None:
    """A process whose pid is negative violates the schema."""
    bad = json.dumps({
        "processes": [
            {"cmdline": "/sbin/init", "pid": -1, "ppid": 0,
             "start_tick": 0, "state": "RUNNING", "uid": 0},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=bad,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted negative pid (rc={proc.returncode})"
    )


def test_binary_rejects_duplicate_initial_pid(tmp_path: Path) -> None:
    """Two initial processes sharing a pid violate the spec invariant of
    pid uniqueness."""
    bad = json.dumps({
        "processes": [
            {"cmdline": "/a", "pid": 1, "ppid": 0, "start_tick": 0,
             "state": "RUNNING", "uid": 0},
            {"cmdline": "/b", "pid": 1, "ppid": 0, "start_tick": 0,
             "state": "RUNNING", "uid": 0},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=bad,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted duplicate initial pid (rc={proc.returncode})"
    )


def test_binary_rejects_invalid_initial_state(tmp_path: Path) -> None:
    """Initial-state processes must be RUNNING; ZOMBIE / EXITED initial
    states are invalid input."""
    bad = json.dumps({
        "processes": [
            {"cmdline": "/sbin/init", "pid": 1, "ppid": 0, "start_tick": 0,
             "state": "ZOMBIE", "uid": 0},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=bad,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted ZOMBIE initial state (rc={proc.returncode})"
    )


def test_binary_rejects_invalid_policy_enum(tmp_path: Path) -> None:
    """policy.orphan_handling outside the closed enum is invalid input."""
    bad_policy = json.dumps({
        "implicit_init_harvest": True,
        "init_pid": 1,
        "orphan_handling": "make_them_zombies",
        "track_lineage": True,
        "wait_on_living_child": "diagnostic",
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=_VALID_PROCESSES_TEXT,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=bad_policy,
    )
    assert proc.returncode != 0, (
        f"binary accepted invalid policy enum (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_initial_ppid_to_unknown(tmp_path: Path) -> None:
    """A non-zero initial ppid must reference another initial pid; pointing
    at a non-existent pid is malformed input."""
    bad = json.dumps({
        "processes": [
            {"cmdline": "/x", "pid": 100, "ppid": 999, "start_tick": 0,
             "state": "RUNNING", "uid": 0},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        processes_text=bad,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted initial ppid pointing at non-existent pid "
        f"(rc={proc.returncode})"
    )


# ---------------------------------------------------------------------------
# Property-based / randomized hidden datasets
# ---------------------------------------------------------------------------


def _gen_random_dataset(seed: int, *,
                        n_initial: int = 4,
                        n_events: int = 30,
                        ) -> tuple[dict, dict, dict]:
    """Deterministic pseudo-random dataset generator. Pure Python `random`
    seeded for reproducibility. Returns (procs_doc, events_doc, policy_doc)
    that the reference is guaranteed to accept."""
    import random
    rng = random.Random(seed)
    initial: list[dict] = []
    used_pids: list[int] = [1]
    initial.append({
        "cmdline": "/sbin/init", "pid": 1, "ppid": 0,
        "start_tick": 0, "state": "RUNNING", "uid": 0,
    })
    for _ in range(n_initial - 1):
        pid = max(used_pids) + rng.randint(1, 9)
        ppid = rng.choice(used_pids)
        used_pids.append(pid)
        initial.append({
            "cmdline": f"/bin/p{pid}", "pid": pid, "ppid": ppid,
            "start_tick": 0, "state": "RUNNING",
            "uid": rng.choice([0, 1000, 33, 2000]),
        })

    next_pid = max(used_pids) + 100
    events: list[dict] = []
    for seq in range(n_events):
        op = rng.choice(["fork", "exit", "wait", "kill", "exec"])
        ev = {"seq": seq, "tick": seq + 1, "op": op, "pid": 1,
              "parent_pid": None, "target_pid": None,
              "exit_code": None, "signal": None, "cmdline": None}
        if op == "fork":
            new_pid = next_pid
            next_pid += 1
            parent = rng.choice(used_pids + [9999])
            ev["pid"] = new_pid
            ev["parent_pid"] = parent
            ev["cmdline"] = f"/bin/c{new_pid}"
            used_pids.append(new_pid)
        elif op == "exit":
            ev["pid"] = rng.choice(used_pids + [9999])
            ev["exit_code"] = rng.randint(0, 127)
        elif op == "wait":
            ev["pid"] = rng.choice(used_pids + [9999])
            ev["target_pid"] = rng.choice(used_pids + [None, 9999])
        elif op == "kill":
            ev["pid"] = rng.choice(used_pids + [9999])
            ev["target_pid"] = rng.choice(used_pids + [9999])
            ev["signal"] = rng.choice(["SIGTERM", "SIGKILL", "SIGINT", "SIGCHLD"])
        elif op == "exec":
            ev["pid"] = rng.choice(used_pids + [9999])
            ev["cmdline"] = f"/bin/e{seq}"
        events.append(ev)

    procs_doc = {"processes": initial}
    events_doc = {"events": events}
    policy_doc = {
        "implicit_init_harvest": rng.choice([True, False]),
        "init_pid": 1,
        "orphan_handling": rng.choice(["reparent_to_init", "leave_orphaned"]),
        "track_lineage": rng.choice([True, False]),
        "wait_on_living_child": rng.choice(["diagnostic", "noop"]),
    }
    return procs_doc, events_doc, policy_doc


@pytest.mark.parametrize("seed", [101, 202, 303, 404, 505])
def test_randomized_property_dataset_against_reference(
    tmp_path: Path, seed: int,
) -> None:
    """Generate a fresh pseudo-random dataset at test time and assert the
    binary's outputs match the live reference. With diverse inputs and
    a different seed in each parametrize, an agent cannot precompute
    expected outputs offline and embed them as JSON literals.
    """
    procs, events, policy = _gen_random_dataset(seed)
    actual = _run_binary_on(tmp_path, procs, events, policy)
    expected = _ref_for(procs, events, policy)
    for name, key in (("process_state.json", "process_state"),
                      ("harvest_log.json", "harvest_log"),
                      ("process_diagnostics.json", "process_diagnostics"),
                      ("lineage_graph.json", "lineage_graph"),
                      ("summary.json", "summary")):
        assert actual[name] == expected[key], (
            f"seed={seed}: binary {name} differs from reference"
        )


@pytest.mark.parametrize("seed", [11, 22, 33])
def test_randomized_property_dataset_with_leave_orphaned(
    tmp_path: Path, seed: int,
) -> None:
    """Same as above but pinned to orphan_handling='leave_orphaned' to
    specifically exercise the no-reparent branch."""
    procs, events, policy = _gen_random_dataset(seed)
    policy["orphan_handling"] = "leave_orphaned"
    actual = _run_binary_on(tmp_path, procs, events, policy)
    expected = _ref_for(procs, events, policy)
    for name, key in (("process_state.json", "process_state"),
                      ("harvest_log.json", "harvest_log"),
                      ("lineage_graph.json", "lineage_graph"),
                      ("summary.json", "summary")):
        assert actual[name] == expected[key], (
            f"seed={seed} leave_orphaned: binary {name} differs from reference"
        )


def test_randomized_property_dataset_no_initial_extra(
    tmp_path: Path,
) -> None:
    """Just init at the start, lots of forks/exits to grow the tree."""
    procs, events, policy = _gen_random_dataset(
        seed=777, n_initial=1, n_events=25,
    )
    actual = _run_binary_on(tmp_path, procs, events, policy)
    expected = _ref_for(procs, events, policy)
    assert actual["process_state.json"] == expected["process_state"]
    assert actual["harvest_log.json"] == expected["harvest_log"]
    assert actual["summary.json"] == expected["summary"]
