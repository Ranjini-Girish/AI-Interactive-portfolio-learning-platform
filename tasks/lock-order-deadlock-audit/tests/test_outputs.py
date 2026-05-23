"""Verifier suite for  (typescript)."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
BUILD_DIR = Path("/app/build")
BINARY_PATH = BUILD_DIR / "lockaudit"

LOCKS_PATH = DATA_DIR / "locks.json"
EVENTS_PATH = DATA_DIR / "events.json"
POLICY_PATH = DATA_DIR / "policy.json"

LOCK_STATE_PATH = OUT_DIR / "lock_state.json"
WF_PATH = OUT_DIR / "wait_for_graph.json"
LO_PATH = OUT_DIR / "lock_order_graph.json"
DIAG_PATH = OUT_DIR / "thread_diagnostics.json"
CONT_PATH = OUT_DIR / "contention_summary.json"
SAFE_PATH = OUT_DIR / "safe_order_plan.json"

ALL_OUT_PATHS = (
    LOCK_STATE_PATH,
    WF_PATH,
    LO_PATH,
    DIAG_PATH,
    CONT_PATH,
    SAFE_PATH,
)

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    LOCKS_PATH: "fdb1e56009d789026110772037bc5fb34047627f851fdbe93229a8bc580a3f33",
    EVENTS_PATH: "4d863b7c36f73132f031e1e044f10f1d25290e1e6111024b7325a35636005731",
    POLICY_PATH: "73aa7700c5762d8eb3d6eee41d26fbad0aaf8230ffe90acd8b5ab5af96cff6f1",
}

VALID_DIAG_CODES = frozenset({
    "E_UNMATCHED_RELEASE",
    "E_NON_REENTRANT_REACQUIRE",
    "E_UNSUPPORTED_MODE",
    "E_WAIT_WHILE_HOLDING",
    "E_DEADLOCKED_AT_END",
    "W_HELD_AT_EXIT",
    "W_LOCK_ORDER_INVERSION",
    "N_BLOCKED_ON_ACQUIRE",
})

DIAG_SEVERITY = {
    "E_UNMATCHED_RELEASE": "error",
    "E_NON_REENTRANT_REACQUIRE": "error",
    "E_UNSUPPORTED_MODE": "error",
    "E_WAIT_WHILE_HOLDING": "error",
    "E_DEADLOCKED_AT_END": "error",
    "W_HELD_AT_EXIT": "warning",
    "W_LOCK_ORDER_INVERSION": "warning",
    "N_BLOCKED_ON_ACQUIRE": "note",
}
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
# Reference implementation (mirrors instruction.md, used to compute expected
# outputs from inputs at test time)
# ---------------------------------------------------------------------------


class LockState:
    __slots__ = ("id", "priority", "mode_supported", "recursive",
                 "exclusive_holders", "shared_holders", "recursive_holds",
                 "wait_queue", "acquire_count", "blocked_count",
                 "peak_holders", "intervals")

    def __init__(self, lock: dict[str, Any], default_recursive: bool):
        self.id: str = lock["id"]
        self.priority: int = lock["priority"]
        self.mode_supported: str = lock["mode_supported"]
        rec = lock["recursive"]
        self.recursive: bool = default_recursive if rec is None else bool(rec)
        self.exclusive_holders: list[str] = []
        self.shared_holders: list[str] = []
        self.recursive_holds: dict[str, int] = {}
        self.wait_queue: list[dict[str, Any]] = []
        self.acquire_count: int = 0
        self.blocked_count: int = 0
        self.peak_holders: int = 0
        self.intervals: list[dict[str, Any]] = []

    def distinct_holders(self) -> set[str]:
        return set(self.exclusive_holders) | set(self.shared_holders)

    def update_peak(self) -> None:
        n = len(self.distinct_holders())
        if n > self.peak_holders:
            self.peak_holders = n


def _is_compatible(lock: LockState, requested_mode: str,
                   policy: dict[str, Any]) -> bool:
    if requested_mode == "exclusive":
        return not lock.exclusive_holders and not lock.shared_holders
    if lock.exclusive_holders:
        return False
    if lock.shared_holders and policy["share_acquire_blocks_on"] == "any":
        return False
    return True


def _add_holder(lock: LockState, thread: str, mode: str) -> None:
    if mode == "exclusive":
        if thread not in lock.exclusive_holders:
            lock.exclusive_holders.append(thread)
    else:
        if thread not in lock.shared_holders:
            lock.shared_holders.append(thread)
    lock.update_peak()


def _thread_holds_in_mode(lock: LockState, thread: str) -> str | None:
    if thread in lock.exclusive_holders:
        return "exclusive"
    if thread in lock.shared_holders:
        return "shared"
    return None


def _thread_holds(lock: LockState, thread: str) -> bool:
    return _thread_holds_in_mode(lock, thread) is not None


def _order_wait_queue(lock: LockState, policy: dict[str, Any]) -> list[dict[str, Any]]:
    wr = policy["wait_resolution"]
    queue = list(lock.wait_queue)
    if wr == "first_holder_then_id":
        return queue
    if wr == "priority_then_id":
        return sorted(queue, key=lambda w: (-w["requested_priority"], w["thread"]))
    if wr == "id_only":
        return sorted(queue, key=lambda w: w["thread"])
    raise ValueError(wr)


def _drain(lock: LockState, policy: dict[str, Any]) -> None:
    while True:
        scan = _order_wait_queue(lock, policy)
        granted: list[str] = []
        virt_excl = list(lock.exclusive_holders)
        virt_shar = list(lock.shared_holders)
        for w in scan:
            mode = w["mode"]
            ok = True
            if mode == "exclusive":
                if virt_excl or virt_shar:
                    ok = False
            else:
                if virt_excl:
                    ok = False
                elif virt_shar and policy["share_acquire_blocks_on"] == "any":
                    ok = False
            if not ok:
                break
            granted.append(w["thread"])
            if mode == "exclusive":
                virt_excl.append(w["thread"])
            else:
                virt_shar.append(w["thread"])
        if not granted:
            return
        for tid in granted:
            idx = next(i for i, w in enumerate(lock.wait_queue) if w["thread"] == tid)
            w = lock.wait_queue.pop(idx)
            _add_holder(lock, tid, w["mode"])


def _open_interval(lock: LockState, thread: str, mode: str,
                   acquire_seq: int, acquire_tick: int,
                   open_intervals: dict[tuple[str, str], dict[str, Any]]) -> None:
    open_intervals[(lock.id, thread)] = {
        "lock": lock.id,
        "thread": thread,
        "mode": mode,
        "acquire_seq": acquire_seq,
        "acquire_tick": acquire_tick,
    }


def _close_interval(lock: LockState, thread: str, release_seq: int,
                    release_tick: int,
                    open_intervals: dict[tuple[str, str], dict[str, Any]]) -> None:
    key = (lock.id, thread)
    if key not in open_intervals:
        return
    iv = open_intervals.pop(key)
    lock.intervals.append({
        "acquire_seq": iv["acquire_seq"],
        "duration": release_tick - iv["acquire_tick"],
        "lock": lock.id,
        "release_seq": release_seq,
        "thread": thread,
    })


def _compute_sccs(nodes: list[str], edges: set[tuple[str, str]]) -> list[list[str]]:
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

    def strongconnect(v: str) -> None:
        call_stack: list[tuple[str, int]] = [(v, 0)]
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
    cycles = sorted([sorted(s) for s in sccs if len(s) > 1], key=lambda c: c[0])
    return cycles


def _compute_kahn_layers(nodes: list[str],
                         edges: set[tuple[str, str]]) -> list[list[str]]:
    out_n: dict[str, set[str]] = {n: set() for n in nodes}
    for a, b in edges:
        if a in out_n:
            out_n[a].add(b)
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    idx_counter = [0]
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        call_stack: list[tuple[str, int]] = [(v, 0)]
        while call_stack:
            cur, child_pos = call_stack[-1]
            if child_pos == 0:
                indices[cur] = idx_counter[0]
                lowlink[cur] = idx_counter[0]
                idx_counter[0] += 1
                stack.append(cur)
                on_stack[cur] = True
            children = sorted(out_n.get(cur, set()))
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
    scc_of: dict[str, int] = {}
    for i, scc in enumerate(sccs):
        for x in scc:
            scc_of[x] = i
    cond_out: dict[int, set[int]] = {i: set() for i in range(len(sccs))}
    cond_in_count: dict[int, int] = {i: 0 for i in range(len(sccs))}
    for a, b in edges:
        si, ti = scc_of[a], scc_of[b]
        if si == ti:
            continue
        if ti not in cond_out[si]:
            cond_out[si].add(ti)
            cond_in_count[ti] += 1
    layers: list[list[str]] = []
    placed: set[int] = set()
    indeg = dict(cond_in_count)
    while len(placed) < len(sccs):
        current = sorted(
            [i for i in range(len(sccs)) if i not in placed and indeg[i] == 0],
            key=lambda i: sorted(sccs[i])[0],
        )
        if not current:
            break
        ids: list[str] = []
        for i in current:
            ids.extend(sccs[i])
            placed.add(i)
        layers.append(sorted(ids))
        for i in current:
            for j in cond_out[i]:
                indeg[j] -= 1
    return layers


def _run_simulation(locks_in: list[dict[str, Any]],
                    events_in: list[dict[str, Any]],
                    policy: dict[str, Any]) -> dict[str, Any]:
    locks: dict[str, LockState] = {
        lk["id"]: LockState(lk, policy["recursive_default"]) for lk in locks_in
    }
    threads_seen: set[str] = set()
    diagnostics: dict[str, list[dict[str, Any]]] = {}
    lo_edges: dict[tuple[str, str], int] = {}
    open_intervals: dict[tuple[str, str], dict[str, Any]] = {}

    total_acquires = 0
    total_blocked_acquires = 0
    total_releases = 0
    total_unmatched_releases = 0
    acquire_issue_log: list[dict[str, Any]] = []

    def _diag(thread: str, code: str, lock_id: str | None, seq: int) -> None:
        diagnostics.setdefault(thread, []).append({
            "code": code,
            "lock": lock_id,
            "seq": seq,
            "severity": DIAG_SEVERITY[code],
        })

    for ev in events_in:
        seq = ev["seq"]
        thr = ev["thread"]
        op = ev["op"]
        lock_id = ev["lock"]
        mode = ev["mode"]
        target = ev["target_thread"]
        threads_seen.add(thr)
        if target:
            threads_seen.add(target)

        if op == "spawn":
            continue
        if op == "exit":
            held = [lid for lid, lk in locks.items() if _thread_holds(lk, thr)]
            for lid in sorted(held):
                _diag(thr, "W_HELD_AT_EXIT", lid, seq)
            continue
        if op == "wake":
            if target is None:
                continue
            candidate_locks = sorted(
                lid for lid, lk in locks.items()
                if any(w["thread"] == target for w in lk.wait_queue)
            )
            if not candidate_locks:
                continue
            chosen = candidate_locks[0]
            lk = locks[chosen]
            lk.wait_queue = [w for w in lk.wait_queue if w["thread"] != target]
            _drain(lk, policy)
            continue
        if lock_id is None:
            continue
        lk = locks.get(lock_id)
        if lk is None:
            continue

        if op == "acquire":
            total_acquires += 1
            if mode == "shared" and lk.mode_supported == "exclusive":
                _diag(thr, "E_UNSUPPORTED_MODE", lock_id, seq)
                continue
            if mode == "exclusive" and lk.mode_supported == "shared":
                _diag(thr, "E_UNSUPPORTED_MODE", lock_id, seq)
                continue
            holder_mode = _thread_holds_in_mode(lk, thr)
            if holder_mode is not None:
                if not lk.recursive:
                    _diag(thr, "E_NON_REENTRANT_REACQUIRE", lock_id, seq)
                    continue
                cur = lk.recursive_holds.get(thr, 1)
                lk.recursive_holds[thr] = cur + 1
                continue
            already_waiting = any(w["thread"] == thr for w in lk.wait_queue)
            if already_waiting:
                continue
            held_locks_now = sorted(
                lid for lid, oth in locks.items() if _thread_holds(oth, thr)
            )
            for held_lid in held_locks_now:
                key = (held_lid, lock_id)
                if key not in lo_edges:
                    lo_edges[key] = seq
            acquire_issue_log.append({
                "seq": seq,
                "thread": thr,
                "lock": lock_id,
                "held_at_issue": held_locks_now,
            })
            if _is_compatible(lk, mode, policy):
                _add_holder(lk, thr, mode)
                _open_interval(lk, thr, mode, seq, ev["tick"], open_intervals)
            else:
                total_blocked_acquires += 1
                lk.blocked_count += 1
                lk.wait_queue.append({
                    "mode": mode,
                    "requested_priority": lk.priority,
                    "seq": seq,
                    "thread": thr,
                })
                _diag(thr, "N_BLOCKED_ON_ACQUIRE", lock_id, seq)
            lk.acquire_count += 1
            continue

        if op == "release":
            holder_mode = _thread_holds_in_mode(lk, thr)
            if holder_mode is None:
                total_unmatched_releases += 1
                if policy["unmatched_release_action"] == "error":
                    _diag(thr, "E_UNMATCHED_RELEASE", lock_id, seq)
                continue
            total_releases += 1
            if lk.recursive and lk.recursive_holds.get(thr, 1) > 1:
                lk.recursive_holds[thr] -= 1
                if lk.recursive_holds[thr] == 1:
                    del lk.recursive_holds[thr]
                continue
            if thr in lk.exclusive_holders:
                lk.exclusive_holders.remove(thr)
            if thr in lk.shared_holders:
                lk.shared_holders.remove(thr)
            _close_interval(lk, thr, seq, ev["tick"], open_intervals)
            _drain(lk, policy)
            continue

        if op == "wait":
            if _thread_holds(lk, thr):
                _diag(thr, "E_WAIT_WHILE_HOLDING", lock_id, seq)
                continue
            already_waiting = any(w["thread"] == thr for w in lk.wait_queue)
            if already_waiting:
                continue
            lk.wait_queue.append({
                "mode": mode if mode in ("exclusive", "shared") else "exclusive",
                "requested_priority": lk.priority,
                "seq": seq,
                "thread": thr,
            })
            continue

    # wait_for graph (final state)
    wf_edges_raw: dict[tuple[str, str], dict[str, Any]] = {}
    for lid in sorted(locks):
        lk = locks[lid]
        if not lk.wait_queue:
            continue
        if lk.exclusive_holders:
            holder_mode = "exclusive"
        elif lk.shared_holders:
            holder_mode = "shared"
        else:
            continue
        all_holders = sorted(set(lk.exclusive_holders) | set(lk.shared_holders))
        for w in lk.wait_queue:
            T = w["thread"]
            req_mode = w["mode"]
            for H in all_holders:
                if H == T:
                    continue
                conflicts = False
                if holder_mode == "exclusive":
                    conflicts = True
                elif holder_mode == "shared":
                    if req_mode == "exclusive":
                        conflicts = True
                    elif req_mode == "shared" and policy["share_acquire_blocks_on"] == "any":
                        conflicts = True
                if not conflicts:
                    continue
                key = (T, H)
                if key in wf_edges_raw:
                    if lid < wf_edges_raw[key]["lock"]:
                        wf_edges_raw[key] = {
                            "lock": lid,
                            "holder_mode": holder_mode,
                            "requested_mode": req_mode,
                        }
                else:
                    wf_edges_raw[key] = {
                        "lock": lid,
                        "holder_mode": holder_mode,
                        "requested_mode": req_mode,
                    }

    wf_nodes = sorted(threads_seen)
    wf_edges_list = []
    for (T, H) in sorted(wf_edges_raw):
        meta = wf_edges_raw[(T, H)]
        wf_edges_list.append({
            "from": T,
            "holder_mode": meta["holder_mode"],
            "lock": meta["lock"],
            "requested_mode": meta["requested_mode"],
            "to": H,
        })
    wf_in_count = {n: 0 for n in wf_nodes}
    wf_out_count = {n: 0 for n in wf_nodes}
    for e in wf_edges_list:
        wf_in_count[e["to"]] = wf_in_count.get(e["to"], 0) + 1
        wf_out_count[e["from"]] = wf_out_count.get(e["from"], 0) + 1
    wf_node_list = [
        {"id": n, "in_degree": wf_in_count.get(n, 0), "out_degree": wf_out_count.get(n, 0)}
        for n in wf_nodes
    ]
    wf_cycles = _compute_sccs(
        list(wf_nodes), {(e["from"], e["to"]) for e in wf_edges_list}
    )
    wf_doc = {"cycles": wf_cycles, "edges": wf_edges_list, "nodes": wf_node_list}

    deadlocked_threads_set: set[str] = set()
    for c in wf_cycles:
        deadlocked_threads_set.update(c)
    for t in sorted(deadlocked_threads_set):
        _diag(t, "E_DEADLOCKED_AT_END", None, max(
            (w["seq"] for lk in locks.values() for w in lk.wait_queue if w["thread"] == t),
            default=0,
        ))

    lo_node_ids = sorted(locks)
    lo_edge_keys = sorted(lo_edges)
    lo_in = {lid: 0 for lid in lo_node_ids}
    lo_out = {lid: 0 for lid in lo_node_ids}
    for (a, b) in lo_edge_keys:
        lo_out[a] = lo_out.get(a, 0) + 1
        lo_in[b] = lo_in.get(b, 0) + 1
    lo_nodes = [
        {"id": lid, "in_degree": lo_in[lid], "out_degree": lo_out[lid]}
        for lid in lo_node_ids
    ]
    lo_edges_list = [
        {"first_witness_seq": lo_edges[(a, b)], "from": a, "to": b}
        for (a, b) in lo_edge_keys
    ]
    lo_cycles = _compute_sccs(lo_node_ids, set(lo_edge_keys))
    lo_layers = _compute_kahn_layers(lo_node_ids, set(lo_edge_keys))
    lo_doc = {
        "cycles": lo_cycles,
        "edges": lo_edges_list,
        "nodes": lo_nodes,
        "topological_layers": lo_layers,
    }

    cycles_set = [set(c) for c in lo_cycles]
    if policy["enforce_strict_order"]:
        seen_inv: set[tuple[str, str]] = set()
        for entry in acquire_issue_log:
            for held in entry["held_at_issue"]:
                shared_cycle = any(
                    held in c and entry["lock"] in c and held != entry["lock"]
                    for c in cycles_set
                )
                if shared_cycle:
                    key = (entry["thread"], entry["lock"])
                    if key not in seen_inv:
                        _diag(entry["thread"], "W_LOCK_ORDER_INVERSION",
                              entry["lock"], entry["seq"])
                        seen_inv.add(key)

    lock_state_entries = []
    for lid in sorted(locks):
        lk = locks[lid]
        recursive_holds_list = sorted(
            ({"count": cnt, "thread": tid}
             for tid, cnt in lk.recursive_holds.items() if cnt >= 2),
            key=lambda x: x["thread"],
        )
        lock_state_entries.append({
            "exclusive_holders": sorted(lk.exclusive_holders),
            "holders_count": len(set(lk.exclusive_holders) | set(lk.shared_holders)),
            "id": lid,
            "recursive_holds": recursive_holds_list,
            "shared_holders": sorted(lk.shared_holders),
            "wait_queue": list(lk.wait_queue),
        })
    lock_state_doc = {"locks": lock_state_entries}

    thread_ids = sorted(threads_seen)
    thread_diag_entries = []
    for tid in thread_ids:
        diags = list(diagnostics.get(tid, []))
        diags.sort(key=lambda d: (SEVERITY_RANK[d["severity"]], d["code"], d["seq"]))
        thread_diag_entries.append({"diagnostics": diags, "id": tid})
    thread_diag_doc = {"threads": thread_diag_entries}

    hot_locks = []
    for lid in sorted(locks):
        lk = locks[lid]
        if lk.acquire_count == 0:
            continue
        hot_locks.append({
            "acquire_count": lk.acquire_count,
            "blocked_count": lk.blocked_count,
            "id": lid,
            "peak_holders": lk.peak_holders,
        })
    hot_locks.sort(key=lambda x: (-x["acquire_count"], x["id"]))

    all_intervals: list[dict[str, Any]] = []
    for lk in locks.values():
        all_intervals.extend(lk.intervals)
    all_intervals.sort(
        key=lambda iv: (-iv["duration"], iv["lock"], iv["thread"], iv["acquire_seq"])
    )
    n_top = min(5, len(all_intervals))
    longest_holds = []
    for iv in all_intervals[:n_top]:
        longest_holds.append({
            "acquire_seq": iv["acquire_seq"],
            "duration": iv["duration"],
            "lock": iv["lock"],
            "release_seq": iv["release_seq"],
            "thread": iv["thread"],
        })

    contention_doc = {
        "hot_locks": hot_locks,
        "longest_holds": longest_holds,
        "summary": {
            "deadlocked_threads": len(deadlocked_threads_set),
            "locks_total": len(locks_in),
            "threads_total": len(threads_seen),
            "total_acquires": total_acquires,
            "total_blocked_acquires": total_blocked_acquires,
            "total_releases": total_releases,
            "total_unmatched_releases": total_unmatched_releases,
        },
    }

    plan = []
    for layer in lo_layers:
        plan.extend(sorted(layer))
    safe_order_doc = {
        "cycles": lo_cycles,
        "layers": lo_layers,
        "plan": plan,
    }

    return {
        "lock_state": lock_state_doc,
        "wait_for_graph": wf_doc,
        "lock_order_graph": lo_doc,
        "thread_diagnostics": thread_diag_doc,
        "contention_summary": contention_doc,
        "safe_order_plan": safe_order_doc,
        "_locks": locks_in,
        "_events": events_in,
        "_policy": policy,
        "_threads_seen": sorted(threads_seen),
    }


def reference_outputs() -> dict[str, Any]:
    locks_doc = load_json(LOCKS_PATH)
    events_doc = load_json(EVENTS_PATH)
    policy = load_json(POLICY_PATH)
    return _run_simulation(locks_doc["locks"], events_doc["events"], policy)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def expected_outputs() -> dict[str, Any]:
    return reference_outputs()


@pytest.fixture(scope="session")
def binary_run_outputs() -> dict[str, Any]:
    """Wipe /app/output, then run the agent's binary with the canonical CLI
    contract and capture exit code, stdout, stderr, and start time.

    All ``test_*_match_reference`` tests depend on this fixture, ensuring the
    binary is the *only* thing that produces the canonical-input outputs that
    those tests then assert against. This neutralises the "ship precomputed
    /app/output JSON" bypass.
    """
    assert BINARY_PATH.exists(), (
        f"binary not found at {BINARY_PATH}; agent must build TypeScript sources to "
        f"this path before tests run"
    )
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
        "start": start,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inputs_unchanged() -> None:
    """Pinned input data files at /app/data/* must be byte-identical to the
    snapshot the task ships with (sha256 hashes embedded in this file).

    This both prevents the agent from rewriting inputs to ease its task AND
    is what makes our live-recomputed reference deterministic.
    """
    for path, expected in EXPECTED_INPUT_HASHES.items():
        assert path.exists(), f"input missing: {path}"
        actual = sha256_of(path)
        assert actual == expected, (
            f"input file {path} has unexpected hash {actual}; expected {expected}"
        )


def test_binary_built_and_executable() -> None:
    """Agent must install a runnable TypeScript launcher at BINARY_PATH."""
    assert BINARY_PATH.exists(), f"expected launcher at {BINARY_PATH}"
    assert BINARY_PATH.stat().st_mode & stat.S_IXUSR, (
        f"{BINARY_PATH} is not executable"
    )
    src_ts = list(Path("/app/src").rglob("*.ts"))
    assert src_ts, "expected agent-authored TypeScript under /app/src"





def test_binary_runs_cleanly_and_outputs_are_fresh(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The agent's binary must run with the canonical two-arg CLI on the pinned
    /app/data, exit 0, and produce all six outputs that are mtime-newer than
    the moment the verifier started the run.

    This forecloses the "ship precomputed /app/output JSON" bypass: the
    verifier wipes /app/output before running, so the outputs we check against
    must come from this run of the binary.
    """
    rc = binary_run_outputs["returncode"]
    assert rc == 0, (
        f"/app/build/lockaudit exited with rc={rc} when run with canonical "
        f"args /app/data /app/output;\nstdout={binary_run_outputs['stdout']!r}\n"
        f"stderr={binary_run_outputs['stderr']!r}"
    )
    start = binary_run_outputs["start"]
    for path in ALL_OUT_PATHS:
        assert path.exists(), f"output missing after binary run: {path}"
        assert path.stat().st_size > 0, f"output empty after binary run: {path}"
        m = path.stat().st_mtime
        assert m + 1.0 >= start, (
            f"output {path} has mtime {m} older than test start {start}; this "
            "looks like a stale/precomputed file rather than fresh binary output"
        )
        load_json(path)


def test_binary_rejects_wrong_arg_counts(tmp_path: Path) -> None:
    """The binary must enforce exactly two positional args.

    Calls with 0/1/3 args must exit non-zero. With the correct two args
    pointing at fresh empty dirs, it must exit zero. This locks in the CLI
    contract from the spec.
    """
    fake_data = tmp_path / "data"
    fake_data.mkdir()
    fake_out = tmp_path / "out"
    fake_out.mkdir()
    for n_args in (0, 1, 3):
        argv = [str(BINARY_PATH)]
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


def test_binary_uses_argv_paths_not_hardcoded(tmp_path: Path) -> None:
    """The binary must read inputs from argv[1] and write outputs to argv[2],
    not hardcoded /app/data and /app/output paths.

    We materialise the canonical pinned inputs into a tmp dir, point the
    binary at that tmp dir + a tmp output dir, and assert outputs land in the
    tmp output dir (not /app/output). We then assert structural equality with
    the reference, proving the binary actually consumed the tmp inputs.
    """
    in_dir = tmp_path / "data"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    for src in (LOCKS_PATH, EVENTS_PATH, POLICY_PATH):
        shutil.copy2(src, in_dir / src.name)
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"binary failed with tmp argv paths: rc={proc.returncode} "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    expected_names = {p.name for p in ALL_OUT_PATHS}
    produced = {p.name for p in out_dir.iterdir() if p.is_file()}
    missing = expected_names - produced
    assert not missing, (
        f"binary did not write expected outputs to argv[2] ({out_dir}); "
        f"missing {sorted(missing)}, found {sorted(produced)}"
    )
    ref = reference_outputs()
    name_to_key = {
        "lock_state.json": "lock_state",
        "wait_for_graph.json": "wait_for_graph",
        "lock_order_graph.json": "lock_order_graph",
        "thread_diagnostics.json": "thread_diagnostics",
        "contention_summary.json": "contention_summary",
        "safe_order_plan.json": "safe_order_plan",
    }
    for fname, key in name_to_key.items():
        produced_doc = json.loads((out_dir / fname).read_text(encoding="utf-8"))
        assert produced_doc == ref[key], (
            f"binary output {fname} from argv-path run differs from reference; "
            "this indicates the binary either ignored argv or produces "
            "inconsistent results across runs"
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
    """Every string at every depth in every output JSON must be pure ASCII.

    The spec mandates ASCII-only output; ``json.dumps(..., ensure_ascii=True)``
    will escape non-ASCII at serialization, so this test additionally asserts
    that no semantic string in the document contains non-ASCII codepoints
    (this would only happen if the agent intentionally smuggled them in).
    """
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


def test_lock_state_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """lock_state.json must equal the live-computed reference exactly.

    Stresses:
      - final per-lock holder lists for both exclusive and shared modes
      - recursive_holds emitted ONLY for counters >= 2 (single holds implicit)
      - holders_count counts distinct threads (not summed counters)
      - wait_queue persisted in arrival order regardless of wait_resolution
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(LOCK_STATE_PATH)
    assert actual == expected_outputs["lock_state"]


def test_wait_for_graph_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """wait_for_graph.json must equal the live-computed reference exactly.

    Stresses:
      - canonical (from, to) edge dedup with lex-smallest witnessing lock
      - aggregated holder_mode (exclusive wins over shared on the same lock)
      - SCC decomposition surfacing runtime deadlocks
      - in_degree / out_degree from the deduplicated edge set
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(WF_PATH)
    assert actual == expected_outputs["wait_for_graph"]


def test_lock_order_graph_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """lock_order_graph.json must equal the live-computed reference exactly.

    Stresses:
      - edges recorded both for granted AND blocked acquires (an acquire that
        ends up queued still establishes A->B if A was held at issue time)
      - first_witness_seq is the smallest seq that established the edge
      - SCC cycles + Kahn-style condensation layers
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(LO_PATH)
    assert actual == expected_outputs["lock_order_graph"]


def test_thread_diagnostics_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """thread_diagnostics.json must equal the live-computed reference exactly.

    Stresses:
      - all 8 diagnostic codes appear with correct severity
      - diagnostics sorted by (severity_rank, code, seq) within each thread
      - W_LOCK_ORDER_INVERSION emitted exactly once per (thread, lock)
      - E_DEADLOCKED_AT_END emitted for every thread in any wait_for cycle
      - threads with no diagnostics still appear with empty list
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(DIAG_PATH)
    assert actual == expected_outputs["thread_diagnostics"]


def test_contention_summary_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """contention_summary.json must equal the live-computed reference exactly.

    Stresses:
      - hot_locks acquire_count counts ONLY acquire events that reached the
        holder/wait-queue update step: (a) granted acquires (added to holder
        set) and (b) blocked-and-queued acquires (appended to wait_queue).
        The FOUR early-exit branches do NOT count: E_UNSUPPORTED_MODE
        rejections, E_NON_REENTRANT_REACQUIRE rejections, recursive re-entries
        (which only bump the per-thread hold counter), and silently-ignored
        duplicates of an acquire already sitting in the wait queue.
      - summary.total_acquires counts EVERY acquire event in the trace
        (incremented at the top, before any early-exit check) — including
        recursive re-entries and the three diagnostic-emitting / silent-skip
        early exits. Therefore total_acquires >= sum(hot_locks.acquire_count).
      - hot_locks sorted by (-acquire_count, id ASCII)
      - peak_holders captures the maximum distinct concurrent holders
      - longest_holds top-min(5, N) by (-duration, lock, thread, acquire_seq)
      - completed-only intervals (open-at-end excluded)
      - summary counts match the trace exactly
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(CONT_PATH)
    assert actual == expected_outputs["contention_summary"]


def test_safe_order_plan_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """safe_order_plan.json must equal the live-computed reference exactly.

    Stresses:
      - plan = Kahn-ordered SCC condensation flattened ASCII per layer
      - layers match lock_order_graph.topological_layers
      - cycles repeat lock_order_graph.cycles
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(SAFE_PATH)
    assert actual == expected_outputs["safe_order_plan"]


def test_diagnostic_codes_are_legal(
    binary_run_outputs: dict[str, Any],
) -> None:
    """All diagnostic codes are drawn from the fixed set with correct severity,
    and each thread's diagnostics list is sorted by (severity_rank, code, seq).
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(DIAG_PATH)
    for t in actual["threads"]:
        prev = (-1, "", -1)
        for d in t["diagnostics"]:
            assert d["code"] in VALID_DIAG_CODES, (
                f"thread {t['id']!r}: unknown diag code {d['code']!r}"
            )
            assert d["severity"] in SEVERITY_RANK, (
                f"thread {t['id']!r}: bad severity {d['severity']!r}"
            )
            assert DIAG_SEVERITY[d["code"]] == d["severity"], (
                f"thread {t['id']!r}: code {d['code']!r} has wrong severity "
                f"{d['severity']!r}, expected {DIAG_SEVERITY[d['code']]!r}"
            )
            key = (SEVERITY_RANK[d["severity"]], d["code"], d["seq"])
            assert key >= prev, (
                f"thread {t['id']!r}: diagnostics not sorted by "
                f"(severity_rank, code, seq); got {key} after {prev}"
            )
            prev = key


def test_safe_order_plan_topological_invariant(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """For every non-cycle edge A->B in the lock_order graph, plan must place
    A strictly before B (the dependency lock is acquired-before, so A precedes
    B in the safe order). Cycle edges keep both endpoints in the same Kahn
    layer.
    """
    assert binary_run_outputs["returncode"] == 0
    plan_doc = load_json(SAFE_PATH)
    lo_doc = load_json(LO_PATH)
    plan = plan_doc["plan"]
    plan_index = {u: i for i, u in enumerate(plan)}
    cycles = lo_doc["cycles"]
    cycle_pairs: set[tuple[str, str]] = set()
    for c in cycles:
        for a in c:
            for b in c:
                if a != b:
                    cycle_pairs.add((a, b))
    layers = plan_doc["layers"]
    layer_index = {}
    for i, layer in enumerate(layers):
        for x in layer:
            layer_index[x] = i
    for e in lo_doc["edges"]:
        a = e["from"]
        b = e["to"]
        if (a, b) in cycle_pairs:
            assert layer_index[a] == layer_index[b], (
                f"cycle edge {a}->{b} but ended in layers "
                f"{layer_index[a]} != {layer_index[b]}"
            )
        else:
            assert plan_index[a] < plan_index[b], (
                f"non-cycle edge {a}->{b} but plan has index "
                f"{plan_index[a]} >= {plan_index[b]}"
            )


def test_wait_for_edges_consistent_with_lock_state(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every wait_for edge T->H must be witnessed in lock_state by:
      - thread T currently waiting on edge.lock
      - thread H currently in the holders set of edge.lock
      - the holder_mode aggregate matches what lock_state shows on that lock
    """
    assert binary_run_outputs["returncode"] == 0
    wf = load_json(WF_PATH)
    state = load_json(LOCK_STATE_PATH)
    by_id = {lk["id"]: lk for lk in state["locks"]}
    for e in wf["edges"]:
        lock = e["lock"]
        assert lock in by_id, f"wait_for edge references unknown lock {lock!r}"
        lk = by_id[lock]
        T = e["from"]
        H = e["to"]
        wq_threads = {w["thread"] for w in lk["wait_queue"]}
        assert T in wq_threads, (
            f"wait_for edge {T}->{H} on {lock!r}: but {T!r} not in wait_queue {wq_threads}"
        )
        holders = set(lk["exclusive_holders"]) | set(lk["shared_holders"])
        assert H in holders, (
            f"wait_for edge {T}->{H} on {lock!r}: but {H!r} not a holder {holders}"
        )
        if e["holder_mode"] == "exclusive":
            assert lk["exclusive_holders"], (
                f"edge holder_mode=exclusive on {lock!r} but no exclusive holders"
            )
        elif e["holder_mode"] == "shared":
            assert not lk["exclusive_holders"], (
                f"edge holder_mode=shared on {lock!r} but lock has exclusive holders"
            )


def test_lock_order_graph_consistency(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """In/out degrees must equal counts of edges, no self-loops, edges sorted
    by (from, to), and topological_layers must partition the full node set.
    """
    assert binary_run_outputs["returncode"] == 0
    lo = load_json(LO_PATH)
    in_count: dict[str, int] = {}
    out_count: dict[str, int] = {}
    pairs = [(e["from"], e["to"]) for e in lo["edges"]]
    assert pairs == sorted(pairs), "lock_order edges must be sorted by (from, to)"
    for s, t in pairs:
        assert s != t, f"lock_order self-loop {s}->{t} forbidden"
    assert len(pairs) == len(set(pairs)), f"duplicate lock_order edges in {pairs}"
    for s, t in pairs:
        out_count[s] = out_count.get(s, 0) + 1
        in_count[t] = in_count.get(t, 0) + 1
    for n in lo["nodes"]:
        rid = n["id"]
        assert n["in_degree"] == in_count.get(rid, 0), (
            f"lock_order node {rid!r}: in_degree {n['in_degree']} != edge count "
            f"{in_count.get(rid, 0)}"
        )
        assert n["out_degree"] == out_count.get(rid, 0), (
            f"lock_order node {rid!r}: out_degree {n['out_degree']} != edge count "
            f"{out_count.get(rid, 0)}"
        )
    expected_locks = sorted(
        lk["id"] for lk in expected_outputs["_locks"]
    )
    seen = set()
    for layer in lo["topological_layers"]:
        assert layer == sorted(layer), f"layer not ASCII-sorted: {layer}"
        for x in layer:
            assert x not in seen, f"lock {x!r} repeats in topological_layers"
            seen.add(x)
    assert seen == set(expected_locks), (
        f"topological_layers must cover every lock id; missing "
        f"{set(expected_locks) - seen}, extra {seen - set(expected_locks)}"
    )


def test_unsupported_mode_diagnostic_is_emitted_and_event_skipped(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """For every input event whose acquire mode is not supported by the lock
    (e.g. exclusive on a shared-only lock), the agent must (a) emit an
    E_UNSUPPORTED_MODE diagnostic against the issuing thread, AND (b) NOT
    add the thread to that lock's exclusive_holders, shared_holders, OR
    wait_queue as a result of this event (event is ignored after the
    diagnostic).
    """
    assert binary_run_outputs["returncode"] == 0
    locks_doc = load_json(LOCKS_PATH)
    events_doc = load_json(EVENTS_PATH)
    locks_by_id = {lk["id"]: lk for lk in locks_doc["locks"]}
    diag = load_json(DIAG_PATH)
    diag_by_thread: dict[str, list[dict[str, Any]]] = {
        t["id"]: t["diagnostics"] for t in diag["threads"]
    }
    state = load_json(LOCK_STATE_PATH)
    state_by_id = {lk["id"]: lk for lk in state["locks"]}
    saw_at_least_one = False
    for ev in events_doc["events"]:
        if ev["op"] != "acquire":
            continue
        lock = locks_by_id.get(ev["lock"])
        if lock is None:
            continue
        unsupported = (
            (ev["mode"] == "shared" and lock["mode_supported"] == "exclusive")
            or (ev["mode"] == "exclusive" and lock["mode_supported"] == "shared")
        )
        if not unsupported:
            continue
        saw_at_least_one = True
        thread_diags = diag_by_thread.get(ev["thread"], [])
        matching = [d for d in thread_diags
                    if d["code"] == "E_UNSUPPORTED_MODE"
                    and d["lock"] == ev["lock"]
                    and d["seq"] == ev["seq"]]
        assert matching, (
            f"event seq={ev['seq']} thread={ev['thread']!r} requested "
            f"unsupported mode {ev['mode']!r} on lock {ev['lock']!r}; expected "
            f"E_UNSUPPORTED_MODE diagnostic but found none in {thread_diags}"
        )
        # And the thread must NOT have ended up holding (in either mode) or
        # queued on that lock as a result of this event. We also check that
        # the wait_queue does not contain a wait_entry whose seq matches this
        # event's seq, which would be the canonical witness of "we queued the
        # rejected request".
        ls = state_by_id[ev["lock"]]
        assert ev["thread"] not in ls["exclusive_holders"], (
            f"event seq={ev['seq']}: thread {ev['thread']!r} ended up in "
            f"exclusive_holders of {ev['lock']!r} despite unsupported-mode skip"
        )
        assert ev["thread"] not in ls["shared_holders"], (
            f"event seq={ev['seq']}: thread {ev['thread']!r} ended up in "
            f"shared_holders of {ev['lock']!r} despite unsupported-mode skip"
        )
        seqs_for_this_thread_in_q = [
            w["seq"] for w in ls["wait_queue"] if w["thread"] == ev["thread"]
        ]
        assert ev["seq"] not in seqs_for_this_thread_in_q, (
            f"event seq={ev['seq']}: thread {ev['thread']!r} ended up in "
            f"wait_queue of {ev['lock']!r} via this rejected acquire (queue "
            f"seqs={seqs_for_this_thread_in_q})"
        )
    assert saw_at_least_one, (
        "dataset invariant: expected at least one E_UNSUPPORTED_MODE event so "
        "this behavior is exercised end-to-end"
    )


def test_non_reentrant_reacquire_is_skipped(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """Every acquire event by a thread that already holds a non-recursive
    lock must produce E_NON_REENTRANT_REACQUIRE without changing state.
    """
    assert binary_run_outputs["returncode"] == 0
    diag = load_json(DIAG_PATH)
    seen = False
    for t in diag["threads"]:
        for d in t["diagnostics"]:
            if d["code"] == "E_NON_REENTRANT_REACQUIRE":
                seen = True
                break
    assert seen, (
        "dataset invariant: expected at least one E_NON_REENTRANT_REACQUIRE "
        "diagnostic, signalling the spec's non-recursive-reacquire branch is "
        "exercised"
    )


def test_wait_queue_persisted_in_arrival_order(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """lock_state.wait_queue must persist arrival (seq-ascending) order
    regardless of policy.wait_resolution; the drain order is a
    SCAN-time view, not a stored shape.
    """
    assert binary_run_outputs["returncode"] == 0
    state = load_json(LOCK_STATE_PATH)
    for lk in state["locks"]:
        seqs = [w["seq"] for w in lk["wait_queue"]]
        assert seqs == sorted(seqs), (
            f"lock {lk['id']!r}: wait_queue persisted in non-arrival order: {seqs}"
        )


def test_wake_with_null_lock_dequeues_named_target(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """Wake events with ``lock=null`` and ``target_thread`` set must dequeue
    that target from whatever lock it is currently waiting on (lex-smallest
    if ambiguous), then trigger a drain. The dataset includes at least one
    such event; we verify that the target ends up either out of every
    wait_queue OR has been re-queued by a later event with a strictly later
    seq, by comparing the binary's lock_state to the live reference.
    """
    assert binary_run_outputs["returncode"] == 0
    events_doc = load_json(EVENTS_PATH)
    seen_null_lock_wake = any(
        ev["op"] == "wake" and ev["lock"] is None and ev["target_thread"] is not None
        for ev in events_doc["events"]
    )
    assert seen_null_lock_wake, (
        "dataset invariant: expected at least one wake event with lock=null "
        "and target_thread!=null so the unbound-wake branch is exercised"
    )
    state = load_json(LOCK_STATE_PATH)
    assert state == expected_outputs["lock_state"], (
        "lock_state diverges from the reference; if a wake-with-null-lock was "
        "incorrectly handled (e.g. treated as a no-op or applied to the wrong "
        "lock) this is the test that surfaces it"
    )


def _run_binary_on(tmp_path: Path, locks: dict, events: dict, policy: dict) -> dict[str, Any]:
    """Materialise a tmp dataset, run the binary, return parsed outputs."""
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    (in_dir / "locks.json").write_text(json.dumps(locks), encoding="utf-8")
    (in_dir / "events.json").write_text(json.dumps(events), encoding="utf-8")
    (in_dir / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"binary failed on hidden dataset: rc={proc.returncode} "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    docs: dict[str, Any] = {}
    for fname in ("lock_state.json", "wait_for_graph.json", "lock_order_graph.json",
                  "thread_diagnostics.json", "contention_summary.json", "safe_order_plan.json"):
        docs[fname] = json.loads((out_dir / fname).read_text(encoding="utf-8"))
    return docs


def _ref_for(locks: dict, events: dict, policy: dict) -> dict[str, Any]:
    return _run_simulation(locks["locks"], events["events"], policy)


def test_hidden_dataset_wake_with_lock_id_drains_queue(tmp_path: Path) -> None:
    """Hidden dataset: wake event with a non-null lock id triggers a drain on
    that lock, granting any compatible queued waiters. Asserts the binary
    matches the reference for this branch (which the pinned dataset never
    exercises directly).
    """
    locks = {"locks": [
        {"id": "L1", "priority": 1, "mode_supported": "both",
         "recursive": False, "description": "test lock"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "acquire",
         "lock": "L1", "mode": "exclusive", "target_thread": None},
        {"seq": 1, "tick": 1, "thread": "T2", "op": "acquire",
         "lock": "L1", "mode": "exclusive", "target_thread": None},
        {"seq": 2, "tick": 2, "thread": "Tk", "op": "wake",
         "lock": "L1", "mode": "none", "target_thread": None},
        {"seq": 3, "tick": 3, "thread": "T1", "op": "release",
         "lock": "L1", "mode": "exclusive", "target_thread": None},
    ]}
    policy = {"recursive_default": True, "share_acquire_blocks_on": "exclusive_only",
              "wait_resolution": "first_holder_then_id", "enforce_strict_order": True,
              "unmatched_release_action": "error"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    assert actual["lock_state.json"] == expected["lock_state"]
    assert actual["wait_for_graph.json"] == expected["wait_for_graph"]
    assert actual["thread_diagnostics.json"] == expected["thread_diagnostics"]


def test_hidden_dataset_wait_mode_none_coerced_to_exclusive(tmp_path: Path) -> None:
    """Hidden dataset: a `wait` event with mode="none" is coerced to
    "exclusive" for queue-recording purposes per the spec. This ensures the
    binary doesn't reject mode="none" or store it literally.
    """
    locks = {"locks": [
        {"id": "L1", "priority": 1, "mode_supported": "both",
         "recursive": False, "description": "test"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "acquire",
         "lock": "L1", "mode": "exclusive", "target_thread": None},
        {"seq": 1, "tick": 1, "thread": "T2", "op": "wait",
         "lock": "L1", "mode": "none", "target_thread": None},
    ]}
    policy = {"recursive_default": True, "share_acquire_blocks_on": "exclusive_only",
              "wait_resolution": "first_holder_then_id", "enforce_strict_order": True,
              "unmatched_release_action": "error"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    assert actual["lock_state.json"] == expected["lock_state"]
    state = actual["lock_state.json"]
    L1 = next(lk for lk in state["locks"] if lk["id"] == "L1")
    queued = [w for w in L1["wait_queue"] if w["thread"] == "T2"]
    assert queued, "T2 must end up in L1.wait_queue after wait(mode=none)"
    assert queued[0]["mode"] == "exclusive", (
        f"wait(mode=none) must coerce to exclusive for queue purposes; got "
        f"{queued[0]['mode']!r}"
    )


def test_hidden_dataset_share_acquire_blocks_on_any(tmp_path: Path) -> None:
    """Hidden dataset: under policy.share_acquire_blocks_on='any', a second
    shared acquire blocks even if no exclusive holder exists. Ensures the
    binary honors all three values of share_acquire_blocks_on rather than
    hardcoding 'exclusive_only'.
    """
    locks = {"locks": [
        {"id": "S1", "priority": 1, "mode_supported": "both",
         "recursive": False, "description": "shared lock"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "acquire",
         "lock": "S1", "mode": "shared", "target_thread": None},
        {"seq": 1, "tick": 1, "thread": "T2", "op": "acquire",
         "lock": "S1", "mode": "shared", "target_thread": None},
    ]}
    policy = {"recursive_default": True, "share_acquire_blocks_on": "any",
              "wait_resolution": "first_holder_then_id", "enforce_strict_order": True,
              "unmatched_release_action": "error"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    assert actual["lock_state.json"] == expected["lock_state"]
    S1 = next(lk for lk in actual["lock_state.json"]["locks"] if lk["id"] == "S1")
    assert S1["shared_holders"] == ["T1"], (
        f"under share_acquire_blocks_on='any', only T1 should hold S1; got "
        f"{S1['shared_holders']}"
    )
    assert any(w["thread"] == "T2" for w in S1["wait_queue"]), (
        "T2's shared acquire must block under share_acquire_blocks_on='any'"
    )


def test_hidden_dataset_unmatched_release_ignore(tmp_path: Path) -> None:
    """Hidden dataset: under policy.unmatched_release_action='ignore', a
    release of a lock the thread does not hold is a silent no-op (no
    diagnostic). Ensures the binary honors the policy knob.
    """
    locks = {"locks": [
        {"id": "L1", "priority": 1, "mode_supported": "both",
         "recursive": False, "description": "test"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "release",
         "lock": "L1", "mode": "exclusive", "target_thread": None},
    ]}
    policy = {"recursive_default": True, "share_acquire_blocks_on": "exclusive_only",
              "wait_resolution": "first_holder_then_id", "enforce_strict_order": True,
              "unmatched_release_action": "ignore"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    assert actual["thread_diagnostics.json"] == expected["thread_diagnostics"]
    diag = actual["thread_diagnostics.json"]
    for t in diag["threads"]:
        for d in t["diagnostics"]:
            assert d["code"] != "E_UNMATCHED_RELEASE", (
                "no E_UNMATCHED_RELEASE expected when unmatched_release_action=='ignore'"
            )


def test_hidden_dataset_enforce_strict_order_false_suppresses_inversion(
    tmp_path: Path,
) -> None:
    """Hidden dataset: when enforce_strict_order=False, W_LOCK_ORDER_INVERSION
    diagnostics must be suppressed entirely even if the lock_order graph has
    cycles.
    """
    locks = {"locks": [
        {"id": "A", "priority": 1, "mode_supported": "exclusive",
         "recursive": False, "description": "A"},
        {"id": "B", "priority": 1, "mode_supported": "exclusive",
         "recursive": False, "description": "B"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "acquire",
         "lock": "A", "mode": "exclusive", "target_thread": None},
        {"seq": 1, "tick": 1, "thread": "T1", "op": "acquire",
         "lock": "B", "mode": "exclusive", "target_thread": None},
        {"seq": 2, "tick": 2, "thread": "T2", "op": "acquire",
         "lock": "B", "mode": "exclusive", "target_thread": None},
        {"seq": 3, "tick": 3, "thread": "T2", "op": "acquire",
         "lock": "A", "mode": "exclusive", "target_thread": None},
    ]}
    policy = {"recursive_default": True, "share_acquire_blocks_on": "exclusive_only",
              "wait_resolution": "first_holder_then_id", "enforce_strict_order": False,
              "unmatched_release_action": "error"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    assert actual["thread_diagnostics.json"] == expected["thread_diagnostics"]
    for t in actual["thread_diagnostics.json"]["threads"]:
        for d in t["diagnostics"]:
            assert d["code"] != "W_LOCK_ORDER_INVERSION", (
                "W_LOCK_ORDER_INVERSION must be suppressed when "
                "enforce_strict_order=False"
            )


def test_hidden_dataset_recursive_lock_counter(tmp_path: Path) -> None:
    """Hidden dataset: recursive lock acquired multiple times by the same
    thread tracks a per-thread counter (>=2 only) and is fully released only
    after matching releases.
    """
    locks = {"locks": [
        {"id": "R1", "priority": 1, "mode_supported": "exclusive",
         "recursive": True, "description": "recursive"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "acquire",
         "lock": "R1", "mode": "exclusive", "target_thread": None},
        {"seq": 1, "tick": 1, "thread": "T1", "op": "acquire",
         "lock": "R1", "mode": "exclusive", "target_thread": None},
        {"seq": 2, "tick": 2, "thread": "T1", "op": "acquire",
         "lock": "R1", "mode": "exclusive", "target_thread": None},
        {"seq": 3, "tick": 3, "thread": "T1", "op": "release",
         "lock": "R1", "mode": "exclusive", "target_thread": None},
    ]}
    policy = {"recursive_default": False, "share_acquire_blocks_on": "exclusive_only",
              "wait_resolution": "first_holder_then_id", "enforce_strict_order": True,
              "unmatched_release_action": "error"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    assert actual["lock_state.json"] == expected["lock_state"]
    R1 = next(lk for lk in actual["lock_state.json"]["locks"] if lk["id"] == "R1")
    assert R1["exclusive_holders"] == ["T1"]
    assert R1["recursive_holds"] == [{"count": 2, "thread": "T1"}], (
        f"after acquire-acquire-acquire-release on a recursive lock, counter "
        f"must drop to 2; got {R1['recursive_holds']}"
    )


def test_hidden_dataset_priority_then_id_wait_resolution(tmp_path: Path) -> None:
    """Hidden dataset: under wait_resolution='priority_then_id', drain prefers
    the higher-priority requester (priorities are per-lock here). With a
    single lock, priority_then_id falls back to thread-id order, but the
    persisted wait_queue is still arrival-order.
    """
    locks = {"locks": [
        {"id": "L1", "priority": 5, "mode_supported": "exclusive",
         "recursive": False, "description": "test"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "acquire",
         "lock": "L1", "mode": "exclusive", "target_thread": None},
        {"seq": 1, "tick": 1, "thread": "T_z", "op": "acquire",
         "lock": "L1", "mode": "exclusive", "target_thread": None},
        {"seq": 2, "tick": 2, "thread": "T_a", "op": "acquire",
         "lock": "L1", "mode": "exclusive", "target_thread": None},
        {"seq": 3, "tick": 3, "thread": "T1", "op": "release",
         "lock": "L1", "mode": "exclusive", "target_thread": None},
    ]}
    policy = {"recursive_default": True, "share_acquire_blocks_on": "exclusive_only",
              "wait_resolution": "priority_then_id", "enforce_strict_order": True,
              "unmatched_release_action": "error"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    assert actual["lock_state.json"] == expected["lock_state"]
    L1 = next(lk for lk in actual["lock_state.json"]["locks"] if lk["id"] == "L1")
    assert L1["exclusive_holders"] == ["T_a"], (
        f"under priority_then_id with equal priorities, T_a (lex-smallest) "
        f"should be drained first; got {L1['exclusive_holders']}"
    )
    assert [w["thread"] for w in L1["wait_queue"]] == ["T_z"], (
        f"after granting T_a, T_z should remain in wait_queue; got {L1['wait_queue']}"
    )


def test_hidden_dataset_wake_with_null_target_and_null_lock_is_noop(
    tmp_path: Path,
) -> None:
    """Hidden dataset: a `wake` event whose target_thread is null AND whose
    lock is null must be a silent no-op — the simulator must not crash, must
    not modify any wait queue, and must not emit any diagnostic.

    Stresses the defensive-null-guard branch the spec calls out for `wake`
    events. Agents that dereference a null target_thread or lock unguarded
    here will segfault; agents that mishandle the branch (e.g. treat it as
    a drain on every lock) will diverge from the reference.
    """
    locks = {"locks": [
        {"id": "L1", "priority": 1, "mode_supported": "exclusive",
         "recursive": False, "description": "test"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "acquire",
         "lock": "L1", "mode": "exclusive", "target_thread": None},
        {"seq": 1, "tick": 1, "thread": "T2", "op": "acquire",
         "lock": "L1", "mode": "exclusive", "target_thread": None},
        {"seq": 2, "tick": 2, "thread": "Tk", "op": "wake",
         "lock": None, "mode": "none", "target_thread": None},
        {"seq": 3, "tick": 3, "thread": "Tk", "op": "wake",
         "lock": None, "mode": "none", "target_thread": None},
    ]}
    policy = {"recursive_default": True, "share_acquire_blocks_on": "exclusive_only",
              "wait_resolution": "first_holder_then_id", "enforce_strict_order": True,
              "unmatched_release_action": "error"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    assert actual["lock_state.json"] == expected["lock_state"], (
        "wake(lock=null,target_thread=null) must be a silent no-op; lock_state "
        "must equal the reference computed without that event having any effect"
    )
    L1 = next(lk for lk in actual["lock_state.json"]["locks"] if lk["id"] == "L1")
    assert L1["exclusive_holders"] == ["T1"], (
        f"silent-noop wake must not affect holders; expected ['T1'], got "
        f"{L1['exclusive_holders']}"
    )
    assert [w["thread"] for w in L1["wait_queue"]] == ["T2"], (
        f"silent-noop wake must not affect wait_queue; expected ['T2'], got "
        f"{[w['thread'] for w in L1['wait_queue']]}"
    )
    diag = actual["thread_diagnostics.json"]
    for t in diag["threads"]:
        for d in t["diagnostics"]:
            assert d["code"] != "E_UNMATCHED_RELEASE", (
                "silent-noop wake must not emit any diagnostic"
            )


def test_hidden_dataset_wake_with_null_target_is_silent_noop(
    tmp_path: Path,
) -> None:
    """Hidden dataset: a `wake` event with target_thread=null is a silent
    no-op regardless of the `lock` field — the simulator must not drain the
    named lock, must not crash on null target/lock dereferences, and must
    not emit any diagnostic.

    This catches agents that mishandle the null-target wake branch by
    unconditionally draining a named lock or by segfaulting on null access.
    """
    locks = {"locks": [
        {"id": "M1", "priority": 1, "mode_supported": "exclusive",
         "recursive": False, "description": "test"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "acquire",
         "lock": "M1", "mode": "exclusive", "target_thread": None},
        {"seq": 1, "tick": 1, "thread": "T2", "op": "acquire",
         "lock": "M1", "mode": "exclusive", "target_thread": None},
        {"seq": 2, "tick": 2, "thread": "Tk", "op": "wake",
         "lock": "M1", "mode": "none", "target_thread": None},
    ]}
    policy = {"recursive_default": True, "share_acquire_blocks_on": "exclusive_only",
              "wait_resolution": "first_holder_then_id", "enforce_strict_order": True,
              "unmatched_release_action": "error"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    assert actual["lock_state.json"] == expected["lock_state"]
    M1 = next(lk for lk in actual["lock_state.json"]["locks"] if lk["id"] == "M1")
    assert M1["exclusive_holders"] == ["T1"], (
        f"wake(target=null) must be a silent no-op; T1 must remain holder; got "
        f"{M1['exclusive_holders']}"
    )
    assert [w["thread"] for w in M1["wait_queue"]] == ["T2"], (
        f"wake(target=null) must NOT drain the named lock's wait queue; T2 "
        f"must remain queued; got {[w['thread'] for w in M1['wait_queue']]}"
    )


def test_hidden_dataset_e_deadlocked_at_end_lock_is_null_and_seq_is_max_wq_seq(
    tmp_path: Path,
) -> None:
    """Hidden dataset: every E_DEADLOCKED_AT_END diagnostic must carry
    lock=null (the spec's sole thread-only code) and seq equal to the maximum
    wait-queue seq for that thread at trace end. Catches agents that:
      - attach a non-null lock id to E_DEADLOCKED_AT_END
      - use the last-event seq, INT64_MAX, or the cycle-witness seq
    """
    locks = {"locks": [
        {"id": "A", "priority": 1, "mode_supported": "exclusive",
         "recursive": False, "description": "A"},
        {"id": "B", "priority": 1, "mode_supported": "exclusive",
         "recursive": False, "description": "B"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "acquire",
         "lock": "A", "mode": "exclusive", "target_thread": None},
        {"seq": 1, "tick": 1, "thread": "T2", "op": "acquire",
         "lock": "B", "mode": "exclusive", "target_thread": None},
        {"seq": 2, "tick": 2, "thread": "T1", "op": "acquire",
         "lock": "B", "mode": "exclusive", "target_thread": None},
        {"seq": 3, "tick": 3, "thread": "T2", "op": "acquire",
         "lock": "A", "mode": "exclusive", "target_thread": None},
        {"seq": 4, "tick": 4, "thread": "Tx", "op": "spawn",
         "lock": None, "mode": "none", "target_thread": None},
    ]}
    policy = {"recursive_default": True, "share_acquire_blocks_on": "exclusive_only",
              "wait_resolution": "first_holder_then_id", "enforce_strict_order": True,
              "unmatched_release_action": "error"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    assert actual["thread_diagnostics.json"] == expected["thread_diagnostics"]
    found_for = {}
    for t in actual["thread_diagnostics.json"]["threads"]:
        for d in t["diagnostics"]:
            if d["code"] == "E_DEADLOCKED_AT_END":
                assert d["lock"] is None, (
                    f"E_DEADLOCKED_AT_END for thread {t['id']!r} must have "
                    f"lock=null; got {d['lock']!r}"
                )
                found_for[t["id"]] = d["seq"]
    assert "T1" in found_for and "T2" in found_for, (
        f"both T1 and T2 must have E_DEADLOCKED_AT_END; got {sorted(found_for)}"
    )
    # T1 is queued on B (seq=2), T2 is queued on A (seq=3). Max-wait-queue-seq
    # rule: T1 -> 2, T2 -> 3.
    assert found_for["T1"] == 2, (
        f"T1's E_DEADLOCKED_AT_END seq must equal max wait-queue seq (2); "
        f"got {found_for['T1']}"
    )
    assert found_for["T2"] == 3, (
        f"T2's E_DEADLOCKED_AT_END seq must equal max wait-queue seq (3); "
        f"got {found_for['T2']}"
    )


def test_hidden_dataset_safe_order_plan_is_flat_list_of_strings(
    tmp_path: Path,
) -> None:
    """Hidden dataset: safe_order_plan.plan must be a flat list[str], not a
    list[list[str]]. layers must be the list[list[str]] shape, and plan must
    equal the concatenation of layers.
    """
    locks = {"locks": [
        {"id": "X", "priority": 1, "mode_supported": "exclusive",
         "recursive": False, "description": "X"},
        {"id": "Y", "priority": 1, "mode_supported": "exclusive",
         "recursive": False, "description": "Y"},
        {"id": "Z", "priority": 1, "mode_supported": "exclusive",
         "recursive": False, "description": "Z"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "acquire",
         "lock": "X", "mode": "exclusive", "target_thread": None},
        {"seq": 1, "tick": 1, "thread": "T1", "op": "acquire",
         "lock": "Y", "mode": "exclusive", "target_thread": None},
        {"seq": 2, "tick": 2, "thread": "T1", "op": "acquire",
         "lock": "Z", "mode": "exclusive", "target_thread": None},
    ]}
    policy = {"recursive_default": True, "share_acquire_blocks_on": "exclusive_only",
              "wait_resolution": "first_holder_then_id", "enforce_strict_order": True,
              "unmatched_release_action": "error"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    plan_doc = actual["safe_order_plan.json"]
    assert plan_doc == expected["safe_order_plan"]
    plan = plan_doc["plan"]
    layers = plan_doc["layers"]
    assert isinstance(plan, list), f"plan must be a list; got {type(plan).__name__}"
    for x in plan:
        assert isinstance(x, str), (
            f"plan must be a flat list of strings, not list-of-lists; "
            f"found element {x!r} of type {type(x).__name__}"
        )
    flat_layers = [lock for layer in layers for lock in layer]
    assert plan == flat_layers, (
        f"plan must equal flat concatenation of layers; got plan={plan} "
        f"vs flat_layers={flat_layers}"
    )


def test_hidden_dataset_acquire_count_excludes_unsupported_and_non_reentrant(
    tmp_path: Path,
) -> None:
    """Hidden dataset: contention_summary.hot_locks.acquire_count must NOT
    include acquire events that were short-circuited by E_UNSUPPORTED_MODE,
    E_NON_REENTRANT_REACQUIRE, recursive re-entry counter increments, or
    silent duplicate-queued skips (all four are pre-counter early exits per
    spec). Only acquires that reached the holder-add or wait-queue-append
    step contribute to acquire_count.
    """
    locks = {"locks": [
        {"id": "EXC", "priority": 1, "mode_supported": "exclusive",
         "recursive": False, "description": "exclusive only"},
        {"id": "SHR", "priority": 1, "mode_supported": "shared",
         "recursive": False, "description": "shared only"},
    ]}
    events = {"events": [
        {"seq": 0, "tick": 0, "thread": "T1", "op": "acquire",
         "lock": "EXC", "mode": "exclusive", "target_thread": None},
        {"seq": 1, "tick": 1, "thread": "T1", "op": "acquire",
         "lock": "EXC", "mode": "exclusive", "target_thread": None},
        {"seq": 2, "tick": 2, "thread": "T2", "op": "acquire",
         "lock": "EXC", "mode": "shared", "target_thread": None},
        {"seq": 3, "tick": 3, "thread": "T2", "op": "acquire",
         "lock": "SHR", "mode": "exclusive", "target_thread": None},
        {"seq": 4, "tick": 4, "thread": "T2", "op": "acquire",
         "lock": "SHR", "mode": "shared", "target_thread": None},
    ]}
    policy = {"recursive_default": False, "share_acquire_blocks_on": "exclusive_only",
              "wait_resolution": "first_holder_then_id", "enforce_strict_order": True,
              "unmatched_release_action": "error"}
    actual = _run_binary_on(tmp_path, locks, events, policy)
    expected = _ref_for(locks, events, policy)
    assert actual["contention_summary.json"] == expected["contention_summary"]
    by_id = {h["id"]: h for h in actual["contention_summary.json"]["hot_locks"]}
    # EXC: seq=0 granted (counts), seq=1 non-reentrant retry (NOT counted),
    #      seq=2 unsupported-mode shared (NOT counted) -> acquire_count = 1.
    assert by_id["EXC"]["acquire_count"] == 1, (
        f"EXC acquire_count must be 1 (only seq=0 counts; non-reentrant and "
        f"unsupported-mode are excluded); got {by_id['EXC']['acquire_count']}"
    )
    # SHR: seq=3 unsupported-mode exclusive (NOT counted),
    #      seq=4 granted (counts) -> acquire_count = 1.
    assert by_id["SHR"]["acquire_count"] == 1, (
        f"SHR acquire_count must be 1 (only seq=4 counts; unsupported-mode "
        f"is excluded); got {by_id['SHR']['acquire_count']}"
    )


def test_hidden_dataset_determinism_two_runs_byte_identical(tmp_path: Path) -> None:
    """Hidden invariant: running the binary twice on the same input produces
    byte-identical outputs. Catches latent nondeterminism (hash-map iteration
    order, address-dependent ordering, etc.).
    """
    in_dir = tmp_path / "data"
    in_dir.mkdir()
    for src in (LOCKS_PATH, EVENTS_PATH, POLICY_PATH):
        shutil.copy2(src, in_dir / src.name)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    out_a.mkdir()
    out_b.mkdir()
    for out in (out_a, out_b):
        proc = subprocess.run(
            [str(BINARY_PATH), str(in_dir), str(out)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, (
            f"determinism run failed: rc={proc.returncode} stderr={proc.stderr!r}"
        )
    for fname in ("lock_state.json", "wait_for_graph.json", "lock_order_graph.json",
                  "thread_diagnostics.json", "contention_summary.json", "safe_order_plan.json"):
        a = (out_a / fname).read_bytes()
        b = (out_b / fname).read_bytes()
        assert a == b, (
            f"{fname} differs between two runs on identical input; "
            f"binary is non-deterministic"
        )


def test_dataset_invariants_have_cycles_and_diagnostics(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """Dataset-level sanity: at least one runtime deadlock cycle, at least one
    lock-order cycle, at least one E_UNMATCHED_RELEASE, at least one
    E_NON_REENTRANT_REACQUIRE, and at least one W_HELD_AT_EXIT must be
    produced by the input. A trivially clean input would mean the simulator
    is never stressed and the verifier reduces to formatting.
    """
    expected = expected_outputs
    assert len(expected["wait_for_graph"]["cycles"]) >= 1, (
        "dataset invariant: at least one runtime deadlock cycle must exist"
    )
    assert len(expected["lock_order_graph"]["cycles"]) >= 1, (
        "dataset invariant: at least one lock-order cycle must exist"
    )
    diag_doc = expected["thread_diagnostics"]
    seen_codes: set[str] = set()
    for t in diag_doc["threads"]:
        for d in t["diagnostics"]:
            seen_codes.add(d["code"])
    required = {
        "E_UNMATCHED_RELEASE",
        "E_NON_REENTRANT_REACQUIRE",
        "E_UNSUPPORTED_MODE",
        "E_WAIT_WHILE_HOLDING",
        "E_DEADLOCKED_AT_END",
        "W_HELD_AT_EXIT",
        "W_LOCK_ORDER_INVERSION",
        "N_BLOCKED_ON_ACQUIRE",
    }
    missing = required - seen_codes
    assert not missing, (
        f"dataset invariant: expected every diagnostic code at least once; "
        f"missing {sorted(missing)}"
    )
