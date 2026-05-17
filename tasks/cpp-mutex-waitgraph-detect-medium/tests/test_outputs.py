"""Verifier for cpp-mutex-waitgraph-detect-medium."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
BINARY_PATH = Path("/usr/local/bin/mtxgraph")
ENV_MAKEFILE = Path("/app/environment/Makefile")

MUTEXES_PATH = DATA_DIR / "mutexes.json"
EVENTS_PATH = DATA_DIR / "events.json"
POLICY_PATH = DATA_DIR / "policy.json"

MUTEX_STATE_PATH = OUT_DIR / "mutex_state.json"
WAIT_EDGES_PATH = OUT_DIR / "wait_edges.json"
ACTION_LOG_PATH = OUT_DIR / "action_log.json"
DIAG_PATH = OUT_DIR / "diagnostics.json"
SUMMARY_PATH = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    MUTEX_STATE_PATH,
    WAIT_EDGES_PATH,
    ACTION_LOG_PATH,
    DIAG_PATH,
    SUMMARY_PATH,
)

DOCS_DIAG_PATH = Path("/app/docs/diagnostics.md")

EXPECTED_DATA_FILES: dict[str, str] = {
    "events.json": "38790ddaf8afb9fbc1ab9b1ab06458a84efe8dcf8afec768ad1b2cf8c19ce3f9",
    "mutexes.json": "93b70bec950397276d44adb738f9be6da73ebe86692075dd16f44384793f7ea4",
    "policy.json": "a825728c527cad2d81ddd681bec2851c849303ed2fd5149bd3a1ecfe5f07c981",
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def keys_sorted_recursive(obj: Any) -> bool:
    if isinstance(obj, dict):
        keys = list(obj.keys())
        if keys != sorted(keys):
            return False
        return all(keys_sorted_recursive(v) for v in obj.values())
    if isinstance(obj, list):
        return all(keys_sorted_recursive(item) for item in obj)
    return True


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


def _load_diag_codes_from_docs() -> tuple[frozenset[str], dict[str, str]]:
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
        raise RuntimeError(f"no diagnostic codes parsed from {DOCS_DIAG_PATH}")
    return frozenset(codes), severity


VALID_DIAG_CODES, DIAG_SEVERITY = _load_diag_codes_from_docs()
SEVERITY_RANK = {"error": 0, "warning": 1, "note": 2}


def detects_cycle(
    mutexes: dict[str, dict[str, Any]], blocker: str, mutex_name: str
) -> bool:
    owner = mutexes[mutex_name]["owner"]
    if owner is None:
        return False
    adj: dict[str, set[str]] = {}
    for m in mutexes.values():
        o = m["owner"]
        if o is None:
            continue
        for w in m["waiters"]:
            adj.setdefault(w, set()).add(o)
    adj.setdefault(blocker, set()).add(owner)
    stack = [owner]
    visited = {owner}
    while stack:
        cur = stack.pop()
        if cur == blocker:
            return True
        for nxt in adj.get(cur, []):
            if nxt not in visited:
                visited.add(nxt)
                stack.append(nxt)
    return False


def compute_reference(
    mutexes_root: dict[str, Any],
    events_root: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    fifo = bool(policy["fifo_waiters"])
    detect = bool(policy["detect_cycles"])
    note_on_tick = bool(policy["note_on_tick"])

    mutexes: dict[str, dict[str, Any]] = {}
    for row in mutexes_root["mutexes"]:
        name = row["name"]
        mutexes[name] = {
            "name": name,
            "owner": row["owner"],
            "waiters": [],
        }

    actions: list[dict[str, Any]] = []
    diag_events: dict[int, list[dict[str, Any]]] = {}
    acquires_ok = 0
    acquires_blocked = 0
    try_rejected = 0
    releases = 0
    wakes = 0
    cycles_detected = 0
    ticks = 0

    def emit(seq: int, code: str, mutex: str | None) -> None:
        diag_events.setdefault(seq, []).append(
            {
                "code": code,
                "mutex": mutex,
                "severity": DIAG_SEVERITY[code],
            }
        )

    def wait_edges() -> list[dict[str, str]]:
        edges: list[dict[str, str]] = []
        for mname, m in mutexes.items():
            owner = m["owner"]
            if owner is None:
                continue
            for w in m["waiters"]:
                edges.append({"mutex": mname, "owner": owner, "waiter": w})
        return sorted(edges, key=lambda e: (e["waiter"], e["mutex"]))

    events = events_root["events"]
    for i, ev in enumerate(events):
        if ev["seq"] != i:
            raise ValueError("seq not dense")
        seq = ev["seq"]
        op = ev["op"]
        mname = ev["mutex"]
        task = ev["task"]

        if op == "tick":
            ticks += 1
            if note_on_tick:
                emit(seq, "N_TICK", None)
        elif op == "acquire":
            if mname not in mutexes:
                emit(seq, "E_UNKNOWN_MUTEX", mname)
                continue
            m = mutexes[mname]
            if m["owner"] is None:
                m["owner"] = task
                acquires_ok += 1
                emit(seq, "N_ACQUIRE", mname)
                actions.append(
                    {
                        "mutex": mname,
                        "op": "acquire",
                        "seq": seq,
                        "task": task,
                        "tick": ev["tick"],
                    }
                )
            else:
                m["waiters"].append(task)
                acquires_blocked += 1
                emit(seq, "E_BLOCKED", mname)
                if detect and detects_cycle(mutexes, task, mname):
                    cycles_detected += 1
                    emit(seq, "W_CYCLE", mname)
        elif op == "try_acquire":
            if mname not in mutexes:
                emit(seq, "E_UNKNOWN_MUTEX", mname)
                continue
            m = mutexes[mname]
            if m["owner"] is None:
                m["owner"] = task
                acquires_ok += 1
                emit(seq, "N_ACQUIRE", mname)
                actions.append(
                    {
                        "mutex": mname,
                        "op": "try_acquire",
                        "seq": seq,
                        "task": task,
                        "tick": ev["tick"],
                    }
                )
            else:
                try_rejected += 1
                emit(seq, "E_BUSY_TRY", mname)
        elif op == "release":
            if mname not in mutexes:
                emit(seq, "E_UNKNOWN_MUTEX", mname)
                continue
            m = mutexes[mname]
            if m["owner"] is None:
                emit(seq, "E_IDLE", mname)
                continue
            if task != m["owner"]:
                emit(seq, "E_WRONG_OWNER", mname)
                continue
            m["owner"] = None
            releases += 1
            actions.append(
                {
                    "mutex": mname,
                    "op": "release",
                    "seq": seq,
                    "task": task,
                    "tick": ev["tick"],
                }
            )
            if m["waiters"]:
                if fifo:
                    next_task = m["waiters"].pop(0)
                else:
                    next_task = m["waiters"].pop()
                m["owner"] = next_task
                wakes += 1
                emit(seq, "N_WAKE", mname)
                actions.append(
                    {
                        "mutex": mname,
                        "op": "wake",
                        "seq": seq,
                        "task": next_task,
                        "tick": ev["tick"],
                    }
                )
        else:
            raise ValueError(f"unknown op {op}")

    final_edges = wait_edges()
    mutex_list = [
        {"name": m["name"], "owner": m["owner"]}
        for m in sorted(mutexes.values(), key=lambda x: x["name"])
    ]

    diag_out: list[dict[str, Any]] = []
    for seq in sorted(diag_events):

        def sort_key(d: dict[str, Any]) -> tuple[int, str, tuple[int, str]]:
            b = d["mutex"]
            key = (-1, "") if b is None else (0, b)
            return (SEVERITY_RANK[d["severity"]], d["code"], key)

        diags_sorted = sorted(diag_events[seq], key=sort_key)
        diag_out.append({"diagnostics": diags_sorted, "seq": seq})

    return {
        "mutex_state": {"mutexes": mutex_list},
        "wait_edges": {"edges": final_edges},
        "action_log": {"actions": actions},
        "diagnostics": {"events": diag_out},
        "summary": {
            "acquires_blocked": acquires_blocked,
            "acquires_succeeded": acquires_ok,
            "cycles_detected": cycles_detected,
            "releases": releases,
            "ticks": ticks,
            "total_events": len(events),
            "try_acquire_rejected": try_rejected,
            "wakes_from_queue": wakes,
        },
    }


@pytest.fixture(scope="session")
def expected_outputs() -> dict[str, Any]:
    return compute_reference(
        load_json(MUTEXES_PATH),
        load_json(EVENTS_PATH),
        load_json(POLICY_PATH),
    )


@pytest.fixture
def binary_run_outputs() -> dict[str, Any]:
    assert ENV_MAKEFILE.is_file(), f"Makefile missing at {ENV_MAKEFILE}"
    build = subprocess.run(
        ["make", "-C", "/app/environment", "build"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert build.returncode == 0, (
        f"make build failed:\nstdout={build.stdout}\nstderr={build.stderr}"
    )
    assert BINARY_PATH.is_file(), f"binary missing at {BINARY_PATH}"
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()
    proc = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "start": start,
    }


_BASE_POLICY = {
    "detect_cycles": False,
    "fifo_waiters": True,
    "note_on_tick": False,
}
_VALID_MUTEXES = {"mutexes": [{"name": "edge", "owner": None}]}
_VALID_EVENTS = {"events": []}


def _ensure_built() -> None:
    subprocess.run(["make", "-C", "/app/environment", "build"], check=True, timeout=120)


def _malformed_run(
    tmp_path: Path,
    mutexes_text: str | None,
    events_text: str | None,
    policy_text: str | None,
) -> subprocess.CompletedProcess[str]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    if mutexes_text is not None:
        (in_dir / "mutexes.json").write_text(mutexes_text, encoding="utf-8")
    if events_text is not None:
        (in_dir / "events.json").write_text(events_text, encoding="utf-8")
    if policy_text is not None:
        (in_dir / "policy.json").write_text(policy_text, encoding="utf-8")
    return subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _assert_no_complete_outputs(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    if not out_dir.exists():
        return
    expected_names = {p.name for p in ALL_OUT_PATHS}
    present = {p.name for p in out_dir.iterdir() if p.is_file()}
    if not expected_names.issubset(present):
        return
    for name in expected_names:
        try:
            json.loads((out_dir / name).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
    raise AssertionError(
        "binary produced a complete parsable output set despite malformed input"
    )


def test_input_hashes_locked() -> None:
    """Pinned fixture hashes for every file under /app/data."""
    present = {
        p.relative_to(DATA_DIR).as_posix()
        for p in DATA_DIR.rglob("*")
        if p.is_file()
    }
    assert present == set(EXPECTED_DATA_FILES.keys())
    for rel, expected in EXPECTED_DATA_FILES.items():
        assert sha256_of(DATA_DIR / rel) == expected


def test_binary_runs_cleanly(binary_run_outputs: dict[str, Any]) -> None:
    """Binary exits 0 and writes all five outputs with fresh mtimes."""
    rc = binary_run_outputs["returncode"]
    assert rc == 0, (
        f"mtxgraph rc={rc}\nstdout={binary_run_outputs['stdout']!r}\n"
        f"stderr={binary_run_outputs['stderr']!r}"
    )
    start = binary_run_outputs["start"]
    for path in ALL_OUT_PATHS:
        assert path.exists(), f"missing {path}"
        assert path.stat().st_mtime + 1.0 >= start
        load_json(path)


def test_output_directory_has_only_expected_files(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Output directory must contain exactly the five contract JSON files."""
    assert binary_run_outputs["returncode"] == 0
    expected = {p.name for p in ALL_OUT_PATHS}
    actual = {p.name for p in OUT_DIR.iterdir() if p.is_file()}
    assert actual == expected, f"unexpected files in /app/output: {sorted(actual)}"


def test_outputs_canonical(binary_run_outputs: dict[str, Any]) -> None:
    """Every output matches canonical json.dumps indent=2 sort_keys ASCII."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(path)
        assert ok, msg


def test_outputs_are_ascii_only(binary_run_outputs: dict[str, Any]) -> None:
    """Output bytes must be ASCII-only per instruction.md."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        raw = path.read_bytes()
        try:
            raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise AssertionError(f"{path} contains non-ASCII bytes: {exc}") from exc


def test_outputs_nested_keys_sorted(binary_run_outputs: dict[str, Any]) -> None:
    """Every object at every depth must have lexicographically sorted keys."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        payload = load_json(path)
        assert keys_sorted_recursive(payload), f"{path} has unsorted nested keys"


def test_mutex_state_sorted_by_name(binary_run_outputs: dict[str, Any]) -> None:
    """mutex_state.json mutexes array must be sorted by name."""
    assert binary_run_outputs["returncode"] == 0
    names = [row["name"] for row in load_json(MUTEX_STATE_PATH)["mutexes"]]
    assert names == sorted(names)


def test_wait_edges_sorted(binary_run_outputs: dict[str, Any]) -> None:
    """wait_edges.json edges must be sorted by waiter then mutex."""
    assert binary_run_outputs["returncode"] == 0
    edges = load_json(WAIT_EDGES_PATH)["edges"]
    keys = [(e["waiter"], e["mutex"]) for e in edges]
    assert keys == sorted(keys)


def test_action_log_chronological_by_seq(binary_run_outputs: dict[str, Any]) -> None:
    """action_log.json actions must follow ascending seq order."""
    assert binary_run_outputs["returncode"] == 0
    seqs = [row["seq"] for row in load_json(ACTION_LOG_PATH)["actions"]]
    assert seqs == sorted(seqs)


def test_diagnostics_events_sorted_by_seq(binary_run_outputs: dict[str, Any]) -> None:
    """diagnostics.json events array must be sorted by seq."""
    assert binary_run_outputs["returncode"] == 0
    seqs = [row["seq"] for row in load_json(DIAG_PATH)["events"]]
    assert seqs == sorted(seqs)


def test_mutex_state_match(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """mutex_state.json equals the live reference replay."""
    assert binary_run_outputs["returncode"] == 0
    assert load_json(MUTEX_STATE_PATH) == expected_outputs["mutex_state"]


def test_wait_edges_match(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """wait_edges.json equals the live reference replay."""
    assert binary_run_outputs["returncode"] == 0
    assert load_json(WAIT_EDGES_PATH) == expected_outputs["wait_edges"]


def test_action_log_match(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """action_log.json equals the live reference replay."""
    assert binary_run_outputs["returncode"] == 0
    assert load_json(ACTION_LOG_PATH) == expected_outputs["action_log"]


def test_diagnostics_match(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """diagnostics.json equals the live reference replay."""
    assert binary_run_outputs["returncode"] == 0
    assert load_json(DIAG_PATH) == expected_outputs["diagnostics"]


def test_summary_match(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """summary.json counters equal the live reference replay."""
    assert binary_run_outputs["returncode"] == 0
    assert load_json(SUMMARY_PATH) == expected_outputs["summary"]


def test_diagnostic_codes_legal(binary_run_outputs: dict[str, Any]) -> None:
    """Diagnostic codes and severities match /app/docs/diagnostics.md."""
    assert binary_run_outputs["returncode"] == 0
    doc = load_json(DIAG_PATH)
    for ev in doc["events"]:
        for d in ev["diagnostics"]:
            assert d["code"] in VALID_DIAG_CODES
            assert DIAG_SEVERITY[d["code"]] == d["severity"]


def test_diagnostics_sorted_within_events(binary_run_outputs: dict[str, Any]) -> None:
    """Within each event, diagnostics are sorted by severity, code, then mutex."""
    assert binary_run_outputs["returncode"] == 0
    doc = load_json(DIAG_PATH)
    for ev in doc["events"]:
        prev: tuple[int, str, tuple[int, str]] | None = None
        for d in ev["diagnostics"]:
            b = d["mutex"]
            key = (-1, "") if b is None else (0, b)
            sort_k = (SEVERITY_RANK[d["severity"]], d["code"], key)
            if prev is not None:
                assert sort_k >= prev, f"seq {ev['seq']}: diagnostics out of order"
            prev = sort_k


def test_data_unmodified_after_run(binary_run_outputs: dict[str, Any]) -> None:
    """Running the binary must not alter any file under /app/data."""
    assert binary_run_outputs["returncode"] == 0
    for rel, expected in EXPECTED_DATA_FILES.items():
        assert sha256_of(DATA_DIR / rel) == expected


def test_zero_args_exits_nonzero() -> None:
    """Arity 0 must exit non-zero per instruction.md."""
    _ensure_built()
    proc = subprocess.run([str(BINARY_PATH)], capture_output=True, text=True)
    assert proc.returncode != 0


def test_one_arg_exits_nonzero() -> None:
    """Arity 1 must exit non-zero."""
    _ensure_built()
    proc = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0


def test_three_args_exits_nonzero() -> None:
    """Arity 3 must exit non-zero."""
    _ensure_built()
    proc = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR), "extra"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0


def test_swapped_directories_exits_nonzero(tmp_path: Path) -> None:
    """Output directory must be the second positional argument, not the first."""
    _ensure_built()
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    shutil.copytree(DATA_DIR, in_dir, dirs_exist_ok=True)
    proc = subprocess.run(
        [str(BINARY_PATH), str(out_dir), str(in_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0


def test_binary_rejects_negative_tick(tmp_path: Path) -> None:
    """Event tick values less than zero must exit non-zero."""
    _ensure_built()
    bad_events = json.dumps(
        {
            "events": [
                {
                    "mutex": None,
                    "op": "tick",
                    "seq": 0,
                    "task": None,
                    "tick": -1,
                }
            ]
        }
    )
    proc = _malformed_run(
        tmp_path,
        mutexes_text=json.dumps(_VALID_MUTEXES),
        events_text=bad_events,
        policy_text=json.dumps(_BASE_POLICY),
    )
    assert proc.returncode != 0
    _assert_no_complete_outputs(tmp_path)


def test_binary_rejects_missing_events_file(tmp_path: Path) -> None:
    """Missing events.json must exit non-zero."""
    _ensure_built()
    proc = _malformed_run(
        tmp_path,
        mutexes_text=json.dumps(_VALID_MUTEXES),
        events_text=None,
        policy_text=json.dumps(_BASE_POLICY),
    )
    assert proc.returncode != 0
    _assert_no_complete_outputs(tmp_path)


def test_binary_rejects_missing_policy_file(tmp_path: Path) -> None:
    """Missing policy.json must exit non-zero."""
    _ensure_built()
    proc = _malformed_run(
        tmp_path,
        mutexes_text=json.dumps(_VALID_MUTEXES),
        events_text=json.dumps(_VALID_EVENTS),
        policy_text=None,
    )
    assert proc.returncode != 0
    _assert_no_complete_outputs(tmp_path)


def test_lifo_waiter_order_on_release(tmp_path: Path) -> None:
    """fifo_waiters false must wake the most recently blocked waiter."""
    _ensure_built()
    in_dir = tmp_path / "lifo_data"
    out_dir = tmp_path / "lifo_out"
    in_dir.mkdir()
    out_dir.mkdir()
    mutexes = {"mutexes": [{"name": "m", "owner": "hold"}]}
    events = {
        "events": [
            {
                "mutex": "m",
                "op": "acquire",
                "seq": 0,
                "task": "w1",
                "tick": 0,
            },
            {
                "mutex": "m",
                "op": "acquire",
                "seq": 1,
                "task": "w2",
                "tick": 0,
            },
            {
                "mutex": "m",
                "op": "release",
                "seq": 2,
                "task": "hold",
                "tick": 1,
            },
        ]
    }
    policy = {
        "detect_cycles": False,
        "fifo_waiters": False,
        "note_on_tick": False,
    }
    (in_dir / "mutexes.json").write_text(json.dumps(mutexes), encoding="utf-8")
    (in_dir / "events.json").write_text(json.dumps(events), encoding="utf-8")
    (in_dir / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
    expected = compute_reference(mutexes, events, policy)
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert load_json(out_dir / "mutex_state.json") == expected["mutex_state"]
    wake_ops = [
        a for a in load_json(out_dir / "action_log.json")["actions"] if a["op"] == "wake"
    ]
    assert len(wake_ops) == 1
    assert wake_ops[0]["task"] == "w2"


def test_replay_on_alternate_valid_fixture(tmp_path: Path) -> None:
    """Binary must replay arbitrary valid inputs, not only the shipped fixture."""
    _ensure_built()
    in_dir = tmp_path / "alt_data"
    out_dir = tmp_path / "alt_out"
    in_dir.mkdir()
    out_dir.mkdir()
    mutexes = {"mutexes": [{"name": "edge", "owner": None}]}
    events = {
        "events": [
            {
                "mutex": "edge",
                "op": "acquire",
                "seq": 0,
                "task": "solo",
                "tick": 0,
            },
            {
                "mutex": "edge",
                "op": "release",
                "seq": 1,
                "task": "solo",
                "tick": 1,
            },
        ]
    }
    policy = {
        "detect_cycles": False,
        "fifo_waiters": True,
        "note_on_tick": False,
    }
    (in_dir / "mutexes.json").write_text(json.dumps(mutexes), encoding="utf-8")
    (in_dir / "events.json").write_text(json.dumps(events), encoding="utf-8")
    (in_dir / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
    expected = compute_reference(mutexes, events, policy)
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert load_json(out_dir / "mutex_state.json") == expected["mutex_state"]
    assert load_json(out_dir / "wait_edges.json") == expected["wait_edges"]
    assert load_json(out_dir / "action_log.json") == expected["action_log"]
    assert load_json(out_dir / "diagnostics.json") == expected["diagnostics"]
    assert load_json(out_dir / "summary.json") == expected["summary"]


def test_cycle_detection_emits_w_cycle(tmp_path: Path) -> None:
    """detect_cycles true must emit W_CYCLE when a wait edge closes a cycle."""
    _ensure_built()
    in_dir = tmp_path / "cyc_data"
    out_dir = tmp_path / "cyc_out"
    in_dir.mkdir()
    out_dir.mkdir()
    mutexes = {
        "mutexes": [
            {"name": "a", "owner": None},
            {"name": "b", "owner": None},
        ]
    }
    events = {
        "events": [
            {
                "mutex": "a",
                "op": "acquire",
                "seq": 0,
                "task": "t1",
                "tick": 0,
            },
            {
                "mutex": "b",
                "op": "acquire",
                "seq": 1,
                "task": "t2",
                "tick": 0,
            },
            {
                "mutex": "b",
                "op": "acquire",
                "seq": 2,
                "task": "t1",
                "tick": 1,
            },
            {
                "mutex": "a",
                "op": "acquire",
                "seq": 3,
                "task": "t2",
                "tick": 1,
            },
        ]
    }
    policy = {
        "detect_cycles": True,
        "fifo_waiters": True,
        "note_on_tick": False,
    }
    (in_dir / "mutexes.json").write_text(json.dumps(mutexes), encoding="utf-8")
    (in_dir / "events.json").write_text(json.dumps(events), encoding="utf-8")
    (in_dir / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
    expected = compute_reference(mutexes, events, policy)
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert load_json(out_dir / "summary.json")["cycles_detected"] == 1
    assert load_json(out_dir / "diagnostics.json") == expected["diagnostics"]


def test_binary_rejects_missing_mutexes_file(tmp_path: Path) -> None:
    """Missing mutexes.json must exit non-zero."""
    _ensure_built()
    proc = _malformed_run(
        tmp_path,
        mutexes_text=None,
        events_text=json.dumps(_VALID_EVENTS),
        policy_text=json.dumps(_BASE_POLICY),
    )
    assert proc.returncode != 0
    _assert_no_complete_outputs(tmp_path)


def test_binary_rejects_malformed_json_syntax(tmp_path: Path) -> None:
    """Invalid JSON syntax must exit non-zero."""
    _ensure_built()
    proc = _malformed_run(
        tmp_path,
        mutexes_text="{bad",
        events_text=json.dumps(_VALID_EVENTS),
        policy_text=json.dumps(_BASE_POLICY),
    )
    assert proc.returncode != 0
    _assert_no_complete_outputs(tmp_path)


def test_binary_rejects_non_dense_seq(tmp_path: Path) -> None:
    """Events whose seq values are not dense 0..N-1 must exit non-zero."""
    _ensure_built()
    bad_events = json.dumps(
        {
            "events": [
                {
                    "mutex": None,
                    "op": "tick",
                    "seq": 0,
                    "task": None,
                    "tick": 0,
                },
                {
                    "mutex": None,
                    "op": "tick",
                    "seq": 2,
                    "task": None,
                    "tick": 1,
                },
            ]
        }
    )
    proc = _malformed_run(
        tmp_path,
        mutexes_text=json.dumps(_VALID_MUTEXES),
        events_text=bad_events,
        policy_text=json.dumps(_BASE_POLICY),
    )
    assert proc.returncode != 0
    _assert_no_complete_outputs(tmp_path)


def test_action_log_ops_are_allowed(binary_run_outputs: dict[str, Any]) -> None:
    """action_log rows must use only acquire, try_acquire, release, or wake ops."""
    assert binary_run_outputs["returncode"] == 0
    allowed = frozenset({"acquire", "try_acquire", "release", "wake"})
    for row in load_json(ACTION_LOG_PATH)["actions"]:
        assert row["op"] in allowed


def test_diagnostic_codes_only_from_closed_set(binary_run_outputs: dict[str, Any]) -> None:
    """Every emitted diagnostic code must belong to the closed set in diagnostics.md."""
    assert binary_run_outputs["returncode"] == 0
    for ev in load_json(DIAG_PATH)["events"]:
        for d in ev["diagnostics"]:
            assert d["code"] in VALID_DIAG_CODES, f"unexpected code {d['code']}"


def test_binary_rejects_missing_required_mutex_field(tmp_path: Path) -> None:
    """Mutex rows missing required fields must exit non-zero."""
    _ensure_built()
    bad_mutexes = json.dumps({"mutexes": [{"name": "x"}]})
    proc = _malformed_run(
        tmp_path,
        mutexes_text=bad_mutexes,
        events_text=json.dumps(_VALID_EVENTS),
        policy_text=json.dumps(_BASE_POLICY),
    )
    assert proc.returncode != 0
    _assert_no_complete_outputs(tmp_path)


def test_binary_rejects_acquire_without_task(tmp_path: Path) -> None:
    """Acquire events with null task must exit non-zero."""
    _ensure_built()
    bad_events = json.dumps(
        {
            "events": [
                {
                    "mutex": "edge",
                    "op": "acquire",
                    "seq": 0,
                    "task": None,
                    "tick": 0,
                }
            ]
        }
    )
    proc = _malformed_run(
        tmp_path,
        mutexes_text=json.dumps(_VALID_MUTEXES),
        events_text=bad_events,
        policy_text=json.dumps(_BASE_POLICY),
    )
    assert proc.returncode != 0
    _assert_no_complete_outputs(tmp_path)


def test_binary_rejects_unknown_op(tmp_path: Path) -> None:
    """Unknown event op values must exit non-zero."""
    _ensure_built()
    bad_events = json.dumps(
        {
            "events": [
                {
                    "mutex": "edge",
                    "op": "explode",
                    "seq": 0,
                    "task": "t",
                    "tick": 0,
                }
            ]
        }
    )
    proc = _malformed_run(
        tmp_path,
        mutexes_text=json.dumps(_VALID_MUTEXES),
        events_text=bad_events,
        policy_text=json.dumps(_BASE_POLICY),
    )
    assert proc.returncode != 0
    _assert_no_complete_outputs(tmp_path)
