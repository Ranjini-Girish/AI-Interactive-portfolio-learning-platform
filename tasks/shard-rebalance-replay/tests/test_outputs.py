"""Verifier suite for Replay (java)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
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


def _java_class_ready() -> bool:
    """Return True when the compiled entry class exists."""
    return (BUILD_DIR / f"{JAVA_CLASS}.class").is_file()


DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
JAVA_CLASS = "Replay"
BUILD_DIR = Path("/app/build")
GSON_CP = "/opt/gson.jar"

NODES_PATH  = DATA_DIR / "nodes.json"
SHARDS_PATH = DATA_DIR / "shards.json"
EVENTS_PATH = DATA_DIR / "events.json"
POLICY_PATH = DATA_DIR / "policy.json"

CLUSTER_STATE_PATH = OUT_DIR / "cluster_state.json"
MOVE_LOG_PATH      = OUT_DIR / "move_log.json"
DIAG_PATH          = OUT_DIR / "cluster_diagnostics.json"
GRAPH_PATH         = OUT_DIR / "move_graph.json"
SUMMARY_PATH       = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    CLUSTER_STATE_PATH,
    MOVE_LOG_PATH,
    DIAG_PATH,
    GRAPH_PATH,
    SUMMARY_PATH,
)

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    NODES_PATH:  "3ce4ca6953930f7b78e0ca13786185019a0ceb5304a36ee3a5f8f2d00442c688",
    SHARDS_PATH: "956506caedeb8832b5956c7a8ad2800a4b4dd8e9c48f8ef26eb80f6c40425cfc",
    EVENTS_PATH: "7d326be3852e10d79e39f2b5a904ac05b99cff3b1335f574e4f806d887c518d6",
    POLICY_PATH: "3efd9cdf0c05f4da6d54679172cca2cbbe05df181c14c69a7be0325bffb43543",
}

DOCS_DIAG_PATH = Path("/app/docs/diagnostics.md")


def _load_diag_codes_from_docs() -> tuple[frozenset[str], dict[str, str]]:
    """Parse /app/docs/diagnostics.md for the canonical list of diagnostic
    codes and their severities. Code lines look like:
        | `E_NODE_NOT_FOUND`      | error    | ...
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


def _is_strictly_more_loaded(a_load: int, a_weight: int,
                             b_load: int, b_weight: int) -> bool:
    return a_load * b_weight > b_load * a_weight


def _node_load(state, node_id: str) -> int:
    total = 0
    for s in state["shards"].values():
        if s["primary"] == node_id or node_id in s["replicas"]:
            total += s["size_bytes"]
    return total


def _holders(shard) -> list[str]:
    return [shard["primary"]] + list(shard["replicas"])


def _diag(diags, seq: int, code: str, ref_id):
    diags.setdefault(seq, []).append({
        "code": code,
        "ref_id": ref_id,
        "severity": DIAG_SEVERITY[code],
    })


def _pick_lowest_load(state, candidates: list[str]):
    best = None
    for nid in sorted(candidates):
        node = state["nodes"][nid]
        load = _node_load(state, nid)
        if best is None:
            best = (nid, load, node["weight"])
            continue
        if _is_strictly_more_loaded(best[1], best[2], load, node["weight"]):
            best = (nid, load, node["weight"])
    return None if best is None else best[0]


def _record_move(state, seq: int, shard_id: str, frm: str, to: str,
                 role: str, trigger: str):
    state["move_log"].append({
        "from_node": frm,
        "role":      role,
        "seq":       seq,
        "shard_id":  shard_id,
        "to_node":   to,
        "trigger":   trigger,
    })
    if state["policy"]["track_history"]:
        state["lineage_edges"].add((frm, to))


def _apply_move(shard, frm: str, to: str, role: str):
    if role == "primary":
        shard["primary"] = to
    else:
        shard["replicas"] = sorted(set(shard["replicas"]) - {frm} | {to})


def _rack_conflict_after_move(state, shard, frm: str, to: str) -> bool:
    if not state["policy"]["rack_awareness"]:
        return False
    others = [h for h in _holders(shard) if h != frm]
    other_racks = {state["nodes"][h]["rack"] for h in others
                   if h in state["nodes"]}
    to_rack = state["nodes"][to]["rack"]
    return to_rack in other_racks


def _rebalance_round(state, seq: int, trigger: str, diagnostics):
    moves_done = 0
    max_moves = state["policy"]["max_moves_per_round"]
    while moves_done < max_moves:
        active = sorted([nid for nid, n in state["nodes"].items()
                         if n["status"] == "active"])
        if len(active) < 2:
            return
        loads = {nid: _node_load(state, nid) for nid in active}
        weights = {nid: state["nodes"][nid]["weight"] for nid in active}
        m_id = active[0]
        for nid in active[1:]:
            if _is_strictly_more_loaded(loads[nid], weights[nid],
                                        loads[m_id], weights[m_id]):
                m_id = nid
        l_id = active[0]
        for nid in active[1:]:
            if _is_strictly_more_loaded(loads[l_id], weights[l_id],
                                        loads[nid], weights[nid]):
                l_id = nid
        if m_id == l_id:
            return
        if not _is_strictly_more_loaded(loads[m_id], weights[m_id],
                                        loads[l_id], weights[l_id]):
            return
        cands = []
        for sid in sorted(state["shards"].keys()):
            s = state["shards"][sid]
            if (s["primary"] == m_id or m_id in s["replicas"]) and \
                    s["primary"] != l_id and l_id not in s["replicas"]:
                cands.append(sid)
        cands.sort(key=lambda sid: (-state["shards"][sid]["size_bytes"], sid))
        if not cands:
            return
        chosen = None
        if state["policy"]["rack_awareness"]:
            for sid in cands:
                s = state["shards"][sid]
                if not _rack_conflict_after_move(state, s, m_id, l_id):
                    chosen = sid
                    break
            if chosen is None:
                chosen = cands[0]
                _diag(diagnostics, seq, "W_RACK_FALLBACK", chosen)
        else:
            chosen = cands[0]
        s = state["shards"][chosen]
        role = "primary" if s["primary"] == m_id else "replica"
        _apply_move(s, m_id, l_id, role)
        _record_move(state, seq, chosen, m_id, l_id, role, trigger)
        _diag(diagnostics, seq, "N_SHARD_MOVED", chosen)
        if trigger == "rebalance":
            state["counters"]["rebalance_moves"] += 1
        elif trigger == "auto_join":
            state["counters"]["auto_join_moves"] += 1
        elif trigger == "auto_leave":
            state["counters"]["auto_leave_moves"] += 1
        moves_done += 1


def _handle_node_join(state, ev, diagnostics):
    nid = ev["node_id"]
    if nid in state["seen_nodes"]:
        _diag(diagnostics, ev["seq"], "E_DUPLICATE_NODE", nid)
        return
    state["nodes"][nid] = {
        "id":     nid,
        "weight": ev["weight"],
        "rack":   ev["rack"],
        "status": "active",
    }
    state["seen_nodes"].add(nid)
    state["counters"]["nodes_joined"] += 1
    if state["policy"]["auto_rebalance_after_join"] and state["shards"]:
        _rebalance_round(state, ev["seq"], "auto_join", diagnostics)


def _handle_node_leave(state, ev, diagnostics):
    nid = ev["node_id"]
    if nid not in state["nodes"]:
        _diag(diagnostics, ev["seq"], "E_NODE_NOT_FOUND", nid)
        return
    held = []
    for sid in sorted(state["shards"].keys()):
        s = state["shards"][sid]
        if s["primary"] == nid or nid in s["replicas"]:
            held.append(sid)
    plan = []
    for sid in held:
        s = state["shards"][sid]
        elig = []
        for other_id, other in state["nodes"].items():
            if other_id == nid:
                continue
            if other["status"] != "active":
                continue
            if other_id in _holders(s):
                continue
            elig.append(other_id)
        sub = _pick_lowest_load(state, elig)
        if sub is None:
            _diag(diagnostics, ev["seq"], "E_REBALANCE_INFEASIBLE", sid)
            return
        plan.append((sid, sub))
    for sid, sub in plan:
        s = state["shards"][sid]
        role = "primary" if s["primary"] == nid else "replica"
        if _rack_conflict_after_move(state, s, nid, sub):
            _diag(diagnostics, ev["seq"], "W_RACK_FALLBACK", sid)
        _apply_move(s, nid, sub, role)
        _record_move(state, ev["seq"], sid, nid, sub, role, "leave")
        _diag(diagnostics, ev["seq"], "N_SHARD_MOVED", sid)
        state["counters"]["auto_leave_moves"] += 1
    del state["nodes"][nid]
    state["counters"]["nodes_left"] += 1
    if state["policy"]["auto_rebalance_after_leave"]:
        _rebalance_round(state, ev["seq"], "auto_leave", diagnostics)


def _handle_node_drain(state, ev, diagnostics):
    nid = ev["node_id"]
    if nid not in state["nodes"]:
        _diag(diagnostics, ev["seq"], "E_NODE_NOT_FOUND", nid)
        return
    if state["nodes"][nid]["status"] == "draining":
        _diag(diagnostics, ev["seq"], "E_NODE_BUSY", nid)
        return
    state["nodes"][nid]["status"] = "draining"
    state["counters"]["nodes_drained"] += 1
    for sid in sorted(state["shards"].keys()):
        s = state["shards"][sid]
        if s["primary"] != nid:
            continue
        active_replicas = [r for r in s["replicas"]
                           if r in state["nodes"]
                           and state["nodes"][r]["status"] == "active"]
        if not active_replicas:
            continue
        promoted = _pick_lowest_load(state, active_replicas)
        s["primary"] = promoted
        s["replicas"] = sorted(set(s["replicas"]) - {promoted} | {nid})
        _record_move(state, ev["seq"], sid, nid, promoted, "primary",
                     "drain")
        _diag(diagnostics, ev["seq"], "W_REPLICA_DEMOTED", nid)
        _diag(diagnostics, ev["seq"], "N_SHARD_MOVED", sid)
        state["counters"]["drain_swaps"] += 1


def _handle_node_resume(state, ev, diagnostics):
    nid = ev["node_id"]
    if nid not in state["nodes"]:
        _diag(diagnostics, ev["seq"], "E_NODE_NOT_FOUND", nid)
        return
    if state["nodes"][nid]["status"] != "draining":
        _diag(diagnostics, ev["seq"], "E_NODE_BUSY", nid)
        return
    state["nodes"][nid]["status"] = "active"


def _handle_manual_move(state, ev, diagnostics):
    sid = ev["shard_id"]
    frm = ev["from_node"]
    to  = ev["to_node"]
    role = ev["role"]
    if sid not in state["shards"]:
        _diag(diagnostics, ev["seq"], "E_SHARD_NOT_FOUND", sid)
        return
    if frm not in state["nodes"]:
        _diag(diagnostics, ev["seq"], "E_NODE_NOT_FOUND", frm)
        return
    if to not in state["nodes"]:
        _diag(diagnostics, ev["seq"], "E_NODE_NOT_FOUND", to)
        return
    s = state["shards"][sid]
    busy = False
    if frm == to:
        busy = True
    elif role == "primary" and s["primary"] != frm:
        busy = True
    elif role == "replica" and frm not in s["replicas"]:
        busy = True
    elif to in _holders(s):
        busy = True
    elif state["nodes"][to]["status"] == "draining":
        busy = True
    if busy:
        _diag(diagnostics, ev["seq"], "E_NODE_BUSY", sid)
        return
    if _rack_conflict_after_move(state, s, frm, to):
        _diag(diagnostics, ev["seq"], "W_RACK_FALLBACK", sid)
    _apply_move(s, frm, to, role)
    _record_move(state, ev["seq"], sid, frm, to, role, "manual")
    _diag(diagnostics, ev["seq"], "N_SHARD_MOVED", sid)
    state["counters"]["manual_moves"] += 1


def _handle_rebalance_round(state, ev, diagnostics):
    state["counters"]["rebalances"] += 1
    _rebalance_round(state, ev["seq"], "rebalance", diagnostics)


def _handle_shard_resize(state, ev, diagnostics):
    sid = ev["shard_id"]
    if sid not in state["shards"]:
        _diag(diagnostics, ev["seq"], "E_SHARD_NOT_FOUND", sid)
        return
    state["shards"][sid]["size_bytes"] = ev["size_bytes"]
    state["counters"]["shard_resizes"] += 1


HANDLERS = {
    "node_join":       _handle_node_join,
    "node_leave":      _handle_node_leave,
    "node_drain":      _handle_node_drain,
    "node_resume":     _handle_node_resume,
    "manual_move":     _handle_manual_move,
    "rebalance_round": _handle_rebalance_round,
    "shard_resize":    _handle_shard_resize,
}


def _initial_state(nodes_doc, shards_doc, policy_doc):
    state: dict[str, Any] = {
        "nodes":          {},
        "shards":         {},
        "seen_nodes":     set(),
        "policy":         dict(policy_doc),
        "move_log":       [],
        "lineage_edges":  set(),
        "counters": {
            "auto_join_moves":  0,
            "auto_leave_moves": 0,
            "drain_swaps":      0,
            "manual_moves":     0,
            "nodes_drained":    0,
            "nodes_joined":     0,
            "nodes_left":       0,
            "rebalance_moves":  0,
            "rebalances":       0,
            "shard_resizes":    0,
        },
    }
    for n in nodes_doc["nodes"]:
        state["nodes"][n["id"]] = {
            "id":     n["id"],
            "weight": n["weight"],
            "rack":   n["rack"],
            "status": "active",
        }
        state["seen_nodes"].add(n["id"])
    for s in shards_doc["shards"]:
        state["shards"][s["id"]] = {
            "id":         s["id"],
            "primary":    s["primary"],
            "replicas":   sorted(s["replicas"]),
            "size_bytes": s["size_bytes"],
        }
    return state


def _compute_sccs(nodes, edges):
    out_n: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        if a in out_n:
            out_n[a].append(b)
    for n in out_n:
        out_n[n].sort()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    idx_counter = [0]
    sccs: list[list[str]] = []

    def strongconnect(start: str) -> None:
        call_stack: list[tuple[str, int]] = [(start, 0)]
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
                    scc: list[str] = []
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
    multi = [s for s in sccs if len(s) > 1]
    return sorted(multi, key=lambda c: c[0])


def _emit_outputs(state, diagnostics, total_events):
    nodes_arr = []
    for nid in sorted(state["nodes"].keys()):
        n = state["nodes"][nid]
        nodes_arr.append({
            "id":          nid,
            "owned_bytes": _node_load(state, nid),
            "rack":        n["rack"],
            "shard_count": sum(
                1 for s in state["shards"].values()
                if s["primary"] == nid or nid in s["replicas"]
            ),
            "status":      n["status"],
            "weight":      n["weight"],
        })
    shards_arr = []
    for sid in sorted(state["shards"].keys()):
        s = state["shards"][sid]
        shards_arr.append({
            "id":         sid,
            "primary":    s["primary"],
            "replicas":   sorted(s["replicas"]),
            "size_bytes": s["size_bytes"],
        })
    cluster_state = {"nodes": nodes_arr, "shards": shards_arr}
    move_log = {"moves": list(state["move_log"])}
    diag_events = []
    for seq in sorted(diagnostics):
        diags = diagnostics[seq]
        diags_sorted = sorted(diags, key=lambda d: (
            SEVERITY_RANK[d["severity"]], d["code"],
            "" if d["ref_id"] is None else d["ref_id"],
        ))
        diag_events.append({"diagnostics": diags_sorted, "seq": seq})
    diag_doc = {"events": diag_events}
    if state["policy"]["track_history"]:
        nodes_set: set[str] = set(state["seen_nodes"])
        for a, b in state["lineage_edges"]:
            nodes_set.add(a)
            nodes_set.add(b)
        nodes_sorted = sorted(nodes_set)
        edges_sorted = sorted(state["lineage_edges"])
        in_count: dict[str, int] = {n: 0 for n in nodes_sorted}
        out_count: dict[str, int] = {n: 0 for n in nodes_sorted}
        for a, b in edges_sorted:
            out_count[a] = out_count.get(a, 0) + 1
            in_count[b] = in_count.get(b, 0) + 1
        node_arr = [{"id": n, "in_degree": in_count[n],
                     "out_degree": out_count[n]} for n in nodes_sorted]
        edge_arr = [{"from": a, "to": b} for (a, b) in edges_sorted]
        cycles = _compute_sccs(nodes_sorted, set(edges_sorted))
        graph_doc = {"cycles": cycles, "edges": edge_arr, "nodes": node_arr}
    else:
        graph_doc = {"cycles": [], "edges": [], "nodes": []}
    racks_at_end = sorted({n["rack"] for n in state["nodes"].values()})
    summary = {
        "auto_join_moves":         state["counters"]["auto_join_moves"],
        "auto_leave_moves":        state["counters"]["auto_leave_moves"],
        "drain_swaps":             state["counters"]["drain_swaps"],
        "events_with_diagnostics": len(diag_events),
        "final_node_count":        len(state["nodes"]),
        "final_shard_count":       len(state["shards"]),
        "manual_moves":            state["counters"]["manual_moves"],
        "nodes_drained":           state["counters"]["nodes_drained"],
        "nodes_joined":            state["counters"]["nodes_joined"],
        "nodes_left":              state["counters"]["nodes_left"],
        "racks":                   racks_at_end,
        "rebalance_moves":         state["counters"]["rebalance_moves"],
        "rebalances":              state["counters"]["rebalances"],
        "shard_resizes":           state["counters"]["shard_resizes"],
        "total_events":            total_events,
    }
    return {
        "cluster_state":       cluster_state,
        "move_log":            move_log,
        "cluster_diagnostics": diag_doc,
        "move_graph":          graph_doc,
        "summary":             summary,
    }


def run_simulation(nodes_doc, shards_doc, events_doc, policy_doc):
    state = _initial_state(nodes_doc, shards_doc, policy_doc)
    diagnostics: dict[int, list[dict[str, Any]]] = {}
    events = sorted(events_doc["events"], key=lambda e: e["seq"])
    for ev in events:
        op = ev["op"]
        if op not in HANDLERS:
            raise ValueError(f"unknown op: {op}")
        HANDLERS[op](state, ev, diagnostics)
    return _emit_outputs(state, diagnostics, total_events=len(events))


def reference_outputs() -> dict[str, Any]:
    nodes_doc  = load_json(NODES_PATH)
    shards_doc = load_json(SHARDS_PATH)
    events_doc = load_json(EVENTS_PATH)
    policy_doc = load_json(POLICY_PATH)
    return run_simulation(nodes_doc, shards_doc, events_doc, policy_doc)


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
        f"binary not found at {(BUILD_DIR / f"{JAVA_CLASS}.class")}; agent must build C++ sources to "
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
# Build provenance + CLI contract
# ---------------------------------------------------------------------------


def test_inputs_unchanged() -> None:
    """Pinned input files must match the snapshot SHA-256 the task ships
    with. Both prevents agents rewriting inputs to ease the task AND keeps
    the live-recomputed reference deterministic."""
    for path, expected in EXPECTED_INPUT_HASHES.items():
        assert path.exists(), f"input missing: {path}"
        actual = sha256_of(path)
        assert actual == expected, (
            f"input file {path} has unexpected hash {actual}; expected {expected}"
        )


def test_java_entry_class_exists() -> None:
    """Compiled Java entry class exists under /app/build after the agent build."""
    assert _java_class_ready()


def test_java_sources_present() -> None:
    """Agent-authored Java sources exist under /app/src."""
    src_dir = Path("/app/src")
    src_files = list(src_dir.rglob("*.java"))
    assert src_files, "expected .java under /app/src"


def test_binary_runs_cleanly_and_outputs_are_fresh(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The agent's binary must run with the canonical two-arg CLI on
    /app/data, exit 0, and produce all five outputs that are mtime-newer
    than the moment the verifier started the run."""
    rc = binary_run_outputs["returncode"]
    assert rc == 0, (
        f"/app/build/shardsim exited with rc={rc} when run with canonical "
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
    """The binary must enforce exactly two positional args."""
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


# ---------------------------------------------------------------------------
# Reference-equality on the pinned dataset
# ---------------------------------------------------------------------------


def test_cluster_state_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """cluster_state.json must equal the live-computed reference exactly."""
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(CLUSTER_STATE_PATH)
    assert actual == expected_outputs["cluster_state"]


def test_move_log_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """move_log.json must equal the live-computed reference exactly,
    preserving chronological order."""
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(MOVE_LOG_PATH)
    assert actual == expected_outputs["move_log"]


def test_cluster_diagnostics_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """cluster_diagnostics.json must equal the live-computed reference
    exactly, including the (severity_rank, code, ref_id) ordering."""
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(DIAG_PATH)
    assert actual == expected_outputs["cluster_diagnostics"]


def test_move_graph_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """move_graph.json must equal the live-computed reference exactly,
    including SCC cycles, sorted edges, and per-node degree counts."""
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(GRAPH_PATH)
    assert actual == expected_outputs["move_graph"]


def test_summary_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """summary.json must equal the live-computed reference exactly,
    including the racks list and every documented counter."""
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(SUMMARY_PATH)
    assert actual == expected_outputs["summary"]


# ---------------------------------------------------------------------------
# Structural / ordering invariants
# ---------------------------------------------------------------------------


def test_diagnostic_codes_are_legal(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every diagnostic code is drawn from the closed set with correct
    severity, and within each event the list is sorted by
    (severity_rank, code, ref_id)."""
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
            rid = "" if d["ref_id"] is None else d["ref_id"]
            key = (SEVERITY_RANK[d["severity"]], d["code"], rid)
            assert key >= prev, (
                f"event seq={e['seq']!r}: diagnostics not sorted by "
                f"(severity_rank, code, ref_id); got {key} after {prev}"
            )
            prev = key


def test_cluster_state_sorted(binary_run_outputs: dict[str, Any]) -> None:
    """cluster_state.nodes and cluster_state.shards must each be sorted by id."""
    assert binary_run_outputs["returncode"] == 0
    state = load_json(CLUSTER_STATE_PATH)
    node_ids = [n["id"] for n in state["nodes"]]
    assert node_ids == sorted(node_ids), (
        f"cluster_state.nodes must be sorted by id; got {node_ids}"
    )
    shard_ids = [s["id"] for s in state["shards"]]
    assert shard_ids == sorted(shard_ids), (
        f"cluster_state.shards must be sorted by id; got {shard_ids}"
    )
    for s in state["shards"]:
        assert s["primary"] not in s["replicas"], (
            f"shard {s['id']!r}: primary {s['primary']!r} appears in replicas"
        )
        assert s["replicas"] == sorted(s["replicas"]), (
            f"shard {s['id']!r}: replicas not ASCII-sorted"
        )
        assert len(s["replicas"]) == len(set(s["replicas"])), (
            f"shard {s['id']!r}: replicas contain duplicates"
        )


def test_move_log_chronological_ordering(
    binary_run_outputs: dict[str, Any],
) -> None:
    """move_log.moves must be in non-decreasing seq order."""
    assert binary_run_outputs["returncode"] == 0
    mlog = load_json(MOVE_LOG_PATH)
    seqs = [m["seq"] for m in mlog["moves"]]
    assert seqs == sorted(seqs), (
        f"move_log entries must be in non-decreasing seq order; got {seqs}"
    )
    for m in mlog["moves"]:
        assert m["trigger"] in {"manual", "drain", "leave",
                                "auto_join", "auto_leave", "rebalance"}, (
            f"unknown trigger {m['trigger']!r} in move_log"
        )
        assert m["role"] in {"primary", "replica"}, (
            f"unknown role {m['role']!r} in move_log"
        )
        assert m["from_node"] != m["to_node"], (
            f"move with from_node == to_node: {m}"
        )


def test_move_graph_explicit_ordering_invariants(
    binary_run_outputs: dict[str, Any],
) -> None:
    """move_graph nodes sorted by id, edges sorted by (from, to), cycles
    sorted by lex-smallest member."""
    assert binary_run_outputs["returncode"] == 0
    graph = load_json(GRAPH_PATH)
    if "nodes" in graph and graph["nodes"]:
        node_ids = [n["id"] for n in graph["nodes"]]
        assert node_ids == sorted(node_ids), (
            f"move_graph.nodes must be sorted by id; got {node_ids}"
        )
    if "edges" in graph and graph["edges"]:
        edge_pairs = [(e["from"], e["to"]) for e in graph["edges"]]
        assert edge_pairs == sorted(edge_pairs), (
            f"move_graph.edges must be sorted by (from, to); got {edge_pairs}"
        )
    if "cycles" in graph:
        for cyc in graph["cycles"]:
            assert cyc == sorted(cyc), (
                f"each cycle's members must be sorted; got {cyc}"
            )
        cycle_keys = [c[0] if c else "" for c in graph["cycles"]]
        assert cycle_keys == sorted(cycle_keys), (
            f"move_graph.cycles must be sorted by lex-smallest member; "
            f"got {cycle_keys}"
        )


DOCS_OUTPUT_FORMAT_PATH = Path("/app/docs/output_format.md")


def _expected_summary_keys_from_docs() -> set[str]:
    """Parse /app/docs/output_format.md for the documented summary key set."""
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
    """summary.json's top-level keys must exactly match the set documented
    in /app/docs/output_format.md."""
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


def test_summary_racks_field_is_sorted_ascii_list(
    binary_run_outputs: dict[str, Any],
) -> None:
    """summary.racks must be a list of strings, sorted ASCII, distinct."""
    assert binary_run_outputs["returncode"] == 0
    summary = load_json(SUMMARY_PATH)
    racks = summary["racks"]
    assert isinstance(racks, list)
    assert all(isinstance(r, str) for r in racks), (
        f"summary.racks must be all-strings; got {racks}"
    )
    assert racks == sorted(racks), (
        f"summary.racks must be sorted ASCII; got {racks}"
    )
    assert len(racks) == len(set(racks)), (
        f"summary.racks must be distinct; got {racks}"
    )


def test_dataset_invariants_have_cycle_and_diagnostics(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """Dataset-level sanity: at least one lineage cycle (a 2-cycle from
    a manual move that undoes a prior rebalance) and at least seven of the
    eight diagnostic codes must be exercised."""
    expected = expected_outputs
    diag_doc = expected["cluster_diagnostics"]
    seen_codes: set[str] = set()
    for e in diag_doc["events"]:
        for d in e["diagnostics"]:
            seen_codes.add(d["code"])
    assert len(seen_codes) >= 7, (
        f"dataset invariant: expected at least 7 distinct diagnostic codes "
        f"exercised; got {sorted(seen_codes)}"
    )
    assert len(expected["move_graph"]["cycles"]) >= 1, (
        "dataset invariant: expected at least one lineage cycle"
    )
    assert expected["summary"]["manual_moves"] >= 1
    assert expected["summary"]["rebalances"] >= 2


# ---------------------------------------------------------------------------
# Hidden-dataset behavioural tests
# ---------------------------------------------------------------------------


def _run_binary_on(tmp_path: Path,
                   nodes_doc: dict, shards_doc: dict,
                   events_doc: dict, policy_doc: dict
                   ) -> dict[str, Any]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    (in_dir / "nodes.json").write_text(json.dumps(nodes_doc), encoding="utf-8")
    (in_dir / "shards.json").write_text(json.dumps(shards_doc), encoding="utf-8")
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
    expected_files = {"cluster_state.json", "move_log.json",
                      "cluster_diagnostics.json", "move_graph.json",
                      "summary.json"}
    actual_files = {p.name for p in out_dir.iterdir() if p.is_file()}
    extras = actual_files - expected_files
    assert not extras, (
        f"binary wrote extra files into output dir for hidden dataset: "
        f"{sorted(extras)}; expected exactly {sorted(expected_files)}"
    )
    in_snapshot = sorted(p.name for p in in_dir.iterdir() if p.is_file())
    assert in_snapshot == sorted(
        ["events.json", "nodes.json", "policy.json", "shards.json"]
    ), (
        f"binary modified or added files in input dir for hidden dataset: "
        f"{in_snapshot}"
    )
    for fname in expected_files:
        docs[fname] = json.loads((out_dir / fname).read_text(encoding="utf-8"))
    return docs


def _ref_for(nodes_doc, shards_doc, events_doc, policy_doc):
    return run_simulation(nodes_doc, shards_doc, events_doc, policy_doc)


def _ev(seq, op, **kw):
    base = {"seq": seq, "op": op, "node_id": None, "weight": None,
            "rack": None, "shard_id": None, "from_node": None,
            "to_node": None, "role": None, "size_bytes": None}
    base.update(kw)
    return base


_DEFAULT_POLICY = {
    "auto_rebalance_after_join": False,
    "auto_rebalance_after_leave": False,
    "max_moves_per_round": 1,
    "rack_awareness": True,
    "rebalance_strategy": "greedy_weight",
    "replication_factor": 2,
    "track_history": True,
}


def test_hidden_dataset_drain_promotes_lowest_load_replica(tmp_path: Path) -> None:
    """node_drain promotes the lowest-load active replica to primary; the
    draining node becomes a replica and W_REPLICA_DEMOTED fires."""
    nodes = {"nodes": [
        {"id": "a", "weight": 100, "rack": "r1"},
        {"id": "b", "weight": 100, "rack": "r2"},
        {"id": "c", "weight": 100, "rack": "r3"},
    ]}
    shards = {"shards": [
        {"id": "s00", "primary": "a", "replicas": ["b", "c"], "size_bytes": 1024},
        {"id": "s01", "primary": "b", "replicas": ["c"], "size_bytes": 4096},
    ]}
    events = {"events": [_ev(0, "node_drain", node_id="a")]}
    actual = _run_binary_on(tmp_path, nodes, shards, events, _DEFAULT_POLICY)
    expected = _ref_for(nodes, shards, events, _DEFAULT_POLICY)
    assert actual["cluster_state.json"] == expected["cluster_state"]
    assert actual["cluster_diagnostics.json"] == expected["cluster_diagnostics"]
    s00 = next(s for s in actual["cluster_state.json"]["shards"]
               if s["id"] == "s00")
    assert s00["primary"] == "b", (
        f"drain should promote 'b' (lowest load replica); got {s00['primary']!r}"
    )
    assert "a" in s00["replicas"], (
        f"drained node 'a' should become a replica of s00; got {s00['replicas']}"
    )
    diag_codes = [d["code"]
                  for e in actual["cluster_diagnostics.json"]["events"]
                  for d in e["diagnostics"]]
    assert diag_codes.count("W_REPLICA_DEMOTED") == 1


def test_hidden_dataset_node_leave_infeasible_aborts_state(tmp_path: Path) -> None:
    """A node_leave that cannot find a substitute for at least one shard
    must emit E_REBALANCE_INFEASIBLE and leave the node in place."""
    nodes = {"nodes": [
        {"id": "a", "weight": 100, "rack": "r1"},
        {"id": "b", "weight": 100, "rack": "r2"},
        {"id": "c", "weight": 100, "rack": "r3"},
    ]}
    shards = {"shards": [
        {"id": "s00", "primary": "a", "replicas": ["b", "c"], "size_bytes": 1024},
    ]}
    events = {"events": [_ev(0, "node_leave", node_id="a")]}
    actual = _run_binary_on(tmp_path, nodes, shards, events, _DEFAULT_POLICY)
    expected = _ref_for(nodes, shards, events, _DEFAULT_POLICY)
    assert actual["cluster_state.json"] == expected["cluster_state"]
    state_ids = sorted(n["id"] for n in actual["cluster_state.json"]["nodes"])
    assert state_ids == ["a", "b", "c"], (
        f"infeasible leave must preserve all nodes; got {state_ids}"
    )
    diag_codes = [d["code"]
                  for e in actual["cluster_diagnostics.json"]["events"]
                  for d in e["diagnostics"]]
    assert "E_REBALANCE_INFEASIBLE" in diag_codes, (
        f"expected E_REBALANCE_INFEASIBLE; got {diag_codes}"
    )
    assert actual["summary.json"]["nodes_left"] == 0


def test_hidden_dataset_track_history_false_empties_graph(tmp_path: Path) -> None:
    """When policy.track_history is false, move_graph carries empty
    cycles, edges, and nodes."""
    nodes = {"nodes": [
        {"id": "a", "weight": 100, "rack": "r1"},
        {"id": "b", "weight": 100, "rack": "r2"},
    ]}
    shards = {"shards": [
        {"id": "s00", "primary": "a", "replicas": ["b"], "size_bytes": 1024},
    ]}
    events = {"events": [
        _ev(0, "manual_move", shard_id="s00", from_node="a", to_node="b",
            role="primary"),
    ]}
    policy = dict(_DEFAULT_POLICY)
    policy["track_history"] = False
    policy["rack_awareness"] = False
    actual = _run_binary_on(tmp_path, nodes, shards, events, policy)
    expected = _ref_for(nodes, shards, events, policy)
    assert actual["move_graph.json"] == expected["move_graph"]
    assert actual["move_graph.json"] == {"cycles": [], "edges": [], "nodes": []}


def test_hidden_dataset_id_not_reused_after_leave(tmp_path: Path) -> None:
    """A node id that has been seen cannot be re-introduced via node_join."""
    nodes = {"nodes": [
        {"id": "a", "weight": 100, "rack": "r1"},
        {"id": "b", "weight": 100, "rack": "r2"},
        {"id": "c", "weight": 100, "rack": "r3"},
    ]}
    shards = {"shards": [
        {"id": "s00", "primary": "a", "replicas": ["b"], "size_bytes": 1024},
    ]}
    events = {"events": [
        _ev(0, "manual_move", shard_id="s00", from_node="a", to_node="c",
            role="primary"),
        _ev(1, "node_leave", node_id="a"),
        _ev(2, "node_join", node_id="a", weight=200, rack="r1"),
    ]}
    actual = _run_binary_on(tmp_path, nodes, shards, events, _DEFAULT_POLICY)
    expected = _ref_for(nodes, shards, events, _DEFAULT_POLICY)
    assert actual["cluster_diagnostics.json"] == expected["cluster_diagnostics"]
    diag = actual["cluster_diagnostics.json"]
    seq2 = next((e for e in diag["events"] if e["seq"] == 2), None)
    assert seq2 is not None and any(
        d["code"] == "E_DUPLICATE_NODE" and d["ref_id"] == "a"
        for d in seq2["diagnostics"]), (
        f"re-using 'a' via node_join after leave must emit E_DUPLICATE_NODE; "
        f"got {seq2}"
    )


def test_hidden_dataset_manual_move_to_draining_is_busy(tmp_path: Path) -> None:
    """manual_move to a draining node must be rejected as E_NODE_BUSY."""
    nodes = {"nodes": [
        {"id": "a", "weight": 100, "rack": "r1"},
        {"id": "b", "weight": 100, "rack": "r2"},
        {"id": "c", "weight": 100, "rack": "r3"},
    ]}
    shards = {"shards": [
        {"id": "s00", "primary": "a", "replicas": ["b"], "size_bytes": 1024},
    ]}
    events = {"events": [
        _ev(0, "node_drain", node_id="c"),
        _ev(1, "manual_move", shard_id="s00", from_node="a", to_node="c",
            role="primary"),
    ]}
    actual = _run_binary_on(tmp_path, nodes, shards, events, _DEFAULT_POLICY)
    expected = _ref_for(nodes, shards, events, _DEFAULT_POLICY)
    assert actual["cluster_diagnostics.json"] == expected["cluster_diagnostics"]
    assert actual["summary.json"]["manual_moves"] == 0


def test_hidden_dataset_rebalance_no_progress_stops(tmp_path: Path) -> None:
    """A rebalance_round on an already-balanced cluster makes zero moves
    but still increments the `rebalances` counter."""
    nodes = {"nodes": [
        {"id": "a", "weight": 100, "rack": "r1"},
        {"id": "b", "weight": 100, "rack": "r2"},
    ]}
    shards = {"shards": [
        {"id": "s00", "primary": "a", "replicas": ["b"], "size_bytes": 1024},
        {"id": "s01", "primary": "b", "replicas": ["a"], "size_bytes": 1024},
    ]}
    events = {"events": [_ev(0, "rebalance_round")]}
    actual = _run_binary_on(tmp_path, nodes, shards, events, _DEFAULT_POLICY)
    expected = _ref_for(nodes, shards, events, _DEFAULT_POLICY)
    assert actual["move_log.json"] == expected["move_log"]
    assert actual["summary.json"]["rebalances"] == 1
    assert actual["summary.json"]["rebalance_moves"] == 0


def test_hidden_dataset_determinism_two_runs_byte_identical(
    tmp_path: Path,
) -> None:
    """Two runs of the binary on the same /app/data inputs into different
    output directories must produce byte-identical files."""
    in_dir = tmp_path / "data"
    in_dir.mkdir()
    for src in (NODES_PATH, SHARDS_PATH, EVENTS_PATH, POLICY_PATH):
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
    for fname in ("cluster_state.json", "move_log.json",
                  "cluster_diagnostics.json", "move_graph.json",
                  "summary.json"):
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
    """The full file tree under /app/data must be byte-identical before
    and after the binary runs."""
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
    """Re-hash the four pinned inputs after the binary has finished."""
    assert binary_run_outputs["returncode"] == 0
    for path, expected in EXPECTED_INPUT_HASHES.items():
        actual = sha256_of(path)
        assert actual == expected


# ---------------------------------------------------------------------------
# Malformed-input tests (instruction.md mandates non-zero exit on these)
# ---------------------------------------------------------------------------


_VALID_NODES_TEXT = json.dumps({
    "nodes": [{"id": "a", "weight": 100, "rack": "r1"}],
})
_VALID_SHARDS_TEXT = json.dumps({"shards": []})
_VALID_EVENTS_TEXT = json.dumps({"events": []})
_VALID_POLICY_TEXT = json.dumps(_DEFAULT_POLICY)


def _malformed_run(tmp_path: Path, *,
                   nodes_text: str = _VALID_NODES_TEXT,
                   shards_text: str = _VALID_SHARDS_TEXT,
                   events_text: str = _VALID_EVENTS_TEXT,
                   policy_text: str | None = _VALID_POLICY_TEXT,
                   ) -> subprocess.CompletedProcess[str]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    (in_dir / "nodes.json").write_text(nodes_text, encoding="utf-8")
    (in_dir / "shards.json").write_text(shards_text, encoding="utf-8")
    (in_dir / "events.json").write_text(events_text, encoding="utf-8")
    if policy_text is not None:
        (in_dir / "policy.json").write_text(policy_text, encoding="utf-8")
    return subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )


def _assert_no_valid_outputs(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    if not out_dir.exists():
        return
    expected_names = {"cluster_state.json", "move_log.json",
                      "cluster_diagnostics.json", "move_graph.json",
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
    """A nodes.json that is not valid JSON must produce a non-zero exit."""
    proc = _malformed_run(tmp_path, nodes_text="{not valid json,")
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_missing_required_fields(tmp_path: Path) -> None:
    """A nodes.json whose entries omit required keys must non-zero exit."""
    bad = json.dumps({"nodes": [{"id": "a", "weight": 100}]})  # no rack
    proc = _malformed_run(tmp_path, nodes_text=bad)
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_wrong_value_types(tmp_path: Path) -> None:
    """A node with a non-integer weight must produce a non-zero exit."""
    bad = json.dumps({"nodes": [{"id": "a", "weight": "lots", "rack": "r1"}]})
    proc = _malformed_run(tmp_path, nodes_text=bad)
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_non_dense_seq(tmp_path: Path) -> None:
    """events.json must have seq values 0,1,2,... dense."""
    bad = json.dumps({"events": [
        {"seq": 0, "op": "rebalance_round", "node_id": None, "weight": None,
         "rack": None, "shard_id": None, "from_node": None, "to_node": None,
         "role": None, "size_bytes": None},
        {"seq": 5, "op": "rebalance_round", "node_id": None, "weight": None,
         "rack": None, "shard_id": None, "from_node": None, "to_node": None,
         "role": None, "size_bytes": None},
    ]})
    proc = _malformed_run(tmp_path, events_text=bad)
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_unknown_node_in_shard(tmp_path: Path) -> None:
    """shards.json referencing a node not declared in nodes.json must
    non-zero exit."""
    bad = json.dumps({
        "shards": [{"id": "s00", "primary": "ghost",
                    "replicas": [], "size_bytes": 1024}],
    })
    proc = _malformed_run(tmp_path, shards_text=bad)
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_missing_input_files(tmp_path: Path) -> None:
    """If any of the four required input files is missing, the binary
    must exit non-zero."""
    proc = _malformed_run(tmp_path, policy_text=None)
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


# ---------------------------------------------------------------------------
# Property-based / randomized hidden datasets
# ---------------------------------------------------------------------------


def _gen_random_dataset(seed: int, *,
                        n_initial_nodes: int = 4,
                        n_initial_shards: int = 5,
                        n_events: int = 25,
                        ) -> tuple[dict, dict, dict, dict]:
    """Deterministic pseudo-random dataset generator. Pure Python `random`
    seeded for reproducibility. Returns four input docs that the reference
    is guaranteed to accept (no malformed inputs)."""
    import random
    rng = random.Random(seed)
    racks = ["r1", "r2", "r3"]
    initial_nodes = []
    used_node_ids: set[str] = set()
    for i in range(n_initial_nodes):
        nid = f"n{i:02d}"
        used_node_ids.add(nid)
        initial_nodes.append({
            "id": nid,
            "weight": 100 * rng.randint(1, 3),
            "rack": rng.choice(racks),
        })
    next_node_n = n_initial_nodes
    initial_shards = []
    for i in range(n_initial_shards):
        sid = f"s{i:02d}"
        node_pool = sorted(used_node_ids)
        primary = rng.choice(node_pool)
        rep_count = rng.randint(0, min(2, len(node_pool) - 1))
        rep_pool = [n for n in node_pool if n != primary]
        rng.shuffle(rep_pool)
        replicas = sorted(rep_pool[:rep_count])
        initial_shards.append({
            "id": sid,
            "primary": primary,
            "replicas": replicas,
            "size_bytes": 256 * rng.randint(1, 8),
        })
    events = []
    for seq in range(n_events):
        op = rng.choice(["node_join", "node_drain", "node_resume",
                         "manual_move", "rebalance_round", "shard_resize"])
        ev = {"seq": seq, "op": op, "node_id": None, "weight": None,
              "rack": None, "shard_id": None, "from_node": None,
              "to_node": None, "role": None, "size_bytes": None}
        if op == "node_join":
            new_id = f"n{next_node_n:02d}"
            next_node_n += 1
            ev["node_id"] = new_id
            ev["weight"] = 100 * rng.randint(1, 3)
            ev["rack"] = rng.choice(racks)
            used_node_ids.add(new_id)
        elif op in ("node_drain", "node_resume"):
            pool = sorted(used_node_ids) + ["nNN"]
            ev["node_id"] = rng.choice(pool)
        elif op == "manual_move":
            sid = f"s{rng.randint(0, max(0, n_initial_shards + 1)):02d}"
            ev["shard_id"] = sid
            pool = sorted(used_node_ids) + ["nNN"]
            ev["from_node"] = rng.choice(pool)
            ev["to_node"] = rng.choice(pool)
            ev["role"] = rng.choice(["primary", "replica"])
        elif op == "rebalance_round":
            pass
        elif op == "shard_resize":
            sid = f"s{rng.randint(0, max(0, n_initial_shards + 1)):02d}"
            ev["shard_id"] = sid
            ev["size_bytes"] = 256 * rng.randint(1, 8)
        events.append(ev)
    nodes_doc = {"nodes": initial_nodes}
    shards_doc = {"shards": initial_shards}
    events_doc = {"events": events}
    policy_doc = {
        "auto_rebalance_after_join":  rng.choice([True, False]),
        "auto_rebalance_after_leave": rng.choice([True, False]),
        "max_moves_per_round":        rng.randint(1, 2),
        "rack_awareness":             rng.choice([True, False]),
        "rebalance_strategy":         "greedy_weight",
        "replication_factor":         rng.randint(2, 3),
        "track_history":              rng.choice([True, False]),
    }
    return nodes_doc, shards_doc, events_doc, policy_doc


@pytest.mark.parametrize("seed", [101, 202, 303, 404, 505])
def test_randomized_property_dataset_against_reference(
    tmp_path: Path, seed: int,
) -> None:
    """Generate a fresh pseudo-random dataset at test time and assert the
    binary's outputs match the live reference."""
    nodes, shards, events, policy = _gen_random_dataset(seed)
    actual = _run_binary_on(tmp_path, nodes, shards, events, policy)
    expected = _ref_for(nodes, shards, events, policy)
    for name, key in (("cluster_state.json", "cluster_state"),
                      ("move_log.json", "move_log"),
                      ("cluster_diagnostics.json", "cluster_diagnostics"),
                      ("move_graph.json", "move_graph"),
                      ("summary.json", "summary")):
        assert actual[name] == expected[key], (
            f"seed={seed}: binary {name} differs from reference"
        )


@pytest.mark.parametrize("seed", [11, 22, 33])
def test_randomized_property_dataset_no_rack_awareness(
    tmp_path: Path, seed: int,
) -> None:
    """Same as above but pinned to rack_awareness=False to exercise the
    no-fallback rebalance path."""
    nodes, shards, events, policy = _gen_random_dataset(seed)
    policy["rack_awareness"] = False
    actual = _run_binary_on(tmp_path, nodes, shards, events, policy)
    expected = _ref_for(nodes, shards, events, policy)
    for name, key in (("cluster_state.json", "cluster_state"),
                      ("move_log.json", "move_log"),
                      ("cluster_diagnostics.json", "cluster_diagnostics"),
                      ("move_graph.json", "move_graph"),
                      ("summary.json", "summary")):
        assert actual[name] == expected[key]


def test_binary_rejects_zero_size_shard(tmp_path: Path) -> None:
    """A shard with size_bytes=0 must be rejected (positive integer per spec)."""
    bad = json.dumps({
        "shards": [{"id": "s00", "primary": "a",
                    "replicas": [], "size_bytes": 0}],
    })
    proc = _malformed_run(tmp_path, shards_text=bad)
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_replica_equal_to_primary(tmp_path: Path) -> None:
    """A shard whose replicas list includes the primary must be rejected."""
    bad = json.dumps({
        "shards": [{"id": "s00", "primary": "a",
                    "replicas": ["a"], "size_bytes": 1024}],
    })
    proc = _malformed_run(tmp_path, shards_text=bad)
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_duplicate_replicas(tmp_path: Path) -> None:
    """A shard whose replicas list has duplicate node ids must be rejected."""
    nodes = json.dumps({"nodes": [
        {"id": "a", "weight": 100, "rack": "r1"},
        {"id": "b", "weight": 100, "rack": "r2"},
    ]})
    bad = json.dumps({
        "shards": [{"id": "s00", "primary": "a",
                    "replicas": ["b", "b"], "size_bytes": 1024}],
    })
    proc = _malformed_run(tmp_path, nodes_text=nodes, shards_text=bad)
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_unknown_event_op(tmp_path: Path) -> None:
    """An events.json with an unknown `op` value must be rejected."""
    bad = json.dumps({"events": [
        {"seq": 0, "op": "transmute_node", "node_id": None, "weight": None,
         "rack": None, "shard_id": None, "from_node": None, "to_node": None,
         "role": None, "size_bytes": None},
    ]})
    proc = _malformed_run(tmp_path, events_text=bad)
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)
    

def test_binary_rejects_invalid_strategy(tmp_path: Path) -> None:
    """A policy.rebalance_strategy outside the allowed set must be rejected."""
    bad = dict(_DEFAULT_POLICY)
    bad["rebalance_strategy"] = "least_recently_used"
    proc = _malformed_run(tmp_path, policy_text=json.dumps(bad))
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_zero_max_moves_per_round(tmp_path: Path) -> None:
    """A non-positive max_moves_per_round must be rejected."""
    bad = dict(_DEFAULT_POLICY)
    bad["max_moves_per_round"] = 0
    proc = _malformed_run(tmp_path, policy_text=json.dumps(bad))
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_duplicate_node_ids_in_initial_layout(tmp_path: Path) -> None:
    """Two nodes with the same id in nodes.json must be rejected."""
    bad = json.dumps({"nodes": [
        {"id": "a", "weight": 100, "rack": "r1"},
        {"id": "a", "weight": 200, "rack": "r2"},
    ]})
    proc = _malformed_run(tmp_path, nodes_text=bad)
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


# ---------------------------------------------------------------------------
# Schema validation: outputs must conform to /app/schemas/ on the pinned run
# ---------------------------------------------------------------------------


SCHEMA_DIR = Path("/app/schemas")


def _validate_schema_minimal(payload, schema, path: str = "$"):
    """A tiny dependency-free JSON Schema validator covering the constructs
    the project's schemas use: type, required, properties, additionalProperties,
    items, enum, minimum, minItems, uniqueItems."""
    types = schema.get("type")
    if types is not None:
        if isinstance(types, str):
            types = [types]
        ok = False
        for t in types:
            if t == "object" and isinstance(payload, dict):
                ok = True
            elif t == "array" and isinstance(payload, list):
                ok = True
            elif t == "string" and isinstance(payload, str):
                ok = True
            elif t == "integer" and isinstance(payload, int) and not isinstance(payload, bool):
                ok = True
            elif t == "boolean" and isinstance(payload, bool):
                ok = True
            elif t == "null" and payload is None:
                ok = True
        assert ok, f"{path}: type mismatch (got {type(payload).__name__}, expected {types})"
    if "enum" in schema:
        assert payload in schema["enum"], (
            f"{path}: value {payload!r} not in enum {schema['enum']}"
        )
    if "minimum" in schema and isinstance(payload, (int, float)) and not isinstance(payload, bool):
        assert payload >= schema["minimum"], (
            f"{path}: value {payload} < minimum {schema['minimum']}"
        )
    if isinstance(payload, dict):
        for required in schema.get("required", []):
            assert required in payload, f"{path}: missing required key {required!r}"
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}).keys())
            extras = set(payload.keys()) - allowed
            assert not extras, f"{path}: extra keys not allowed: {sorted(extras)}"
        for k, v in payload.items():
            sub = schema.get("properties", {}).get(k)
            if sub is not None:
                _validate_schema_minimal(v, sub, f"{path}.{k}")
    if isinstance(payload, list):
        if schema.get("uniqueItems") is True:
            seen = set()
            for it in payload:
                key = json.dumps(it, sort_keys=True)
                assert key not in seen, f"{path}: duplicate item {it!r}"
                seen.add(key)
        if "minItems" in schema:
            assert len(payload) >= schema["minItems"], (
                f"{path}: only {len(payload)} items, need >= {schema['minItems']}"
            )
        items_schema = schema.get("items")
        if items_schema is not None:
            for i, it in enumerate(payload):
                _validate_schema_minimal(it, items_schema, f"{path}[{i}]")


@pytest.mark.parametrize("output,schema_name", [
    ("cluster_state.json",       "cluster_state.schema.json"),
    ("move_log.json",            "move_log.schema.json"),
    ("cluster_diagnostics.json", "cluster_diagnostics.schema.json"),
    ("move_graph.json",          "move_graph.schema.json"),
    ("summary.json",             "summary.schema.json"),
])
def test_outputs_conform_to_documented_schemas(
    binary_run_outputs: dict[str, Any],
    output: str,
    schema_name: str,
) -> None:
    """Every output JSON conforms to the JSON Schema shipped under
    /app/schemas/. Defends against accidental drift between the agent's
    output shape and the documented schema."""
    assert binary_run_outputs["returncode"] == 0
    schema_path = SCHEMA_DIR / schema_name
    assert schema_path.exists(), f"schema missing: {schema_path}"
    schema = load_json(schema_path)
    payload = load_json(OUT_DIR / output)
    _validate_schema_minimal(payload, schema, path=f"<{output}>")
