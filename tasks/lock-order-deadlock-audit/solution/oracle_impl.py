from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"

def write_canonical(path: Path, obj: Any) -> None:
    path.write_text(canonical(obj), encoding='utf-8')
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


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    locks_doc = load_json(in_dir / "locks.json")
    events_doc = load_json(in_dir / "events.json")
    policy_doc = load_json(in_dir / "policy.json")
    outputs = _run_simulation(locks_doc["locks"], events_doc["events"], policy_doc)
    write_canonical(out_dir / "lock_state.json", outputs["lock_state"])
    write_canonical(out_dir / "wait_for_graph.json", outputs["wait_for_graph"])
    write_canonical(out_dir / "lock_order_graph.json", outputs["lock_order_graph"])
    write_canonical(out_dir / "thread_diagnostics.json", outputs["thread_diagnostics"])
    write_canonical(out_dir / "contention_summary.json", outputs["contention_summary"])
    write_canonical(out_dir / "safe_order_plan.json", outputs["safe_order_plan"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
