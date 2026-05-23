
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def write_canonical(path: Path, obj: Any) -> None:
    path.write_text(canonical(obj), encoding="utf-8")


SEVERITY_RANK = {"error": 0, "warning": 1, "note": 2}

def _docs_diag_path() -> Path:
    candidates = (
        Path("/app/docs/diagnostics.md"),
        Path(__file__).resolve().parent.parent
        / "environment"
        / "docs"
        / "diagnostics.md",
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


DOCS_DIAG_PATH = _docs_diag_path()


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
        raise RuntimeError(f"could not parse diagnostic codes from {DOCS_DIAG_PATH}")
    return frozenset(codes), severity


VALID_DIAG_CODES, DIAG_SEVERITY = _load_diag_codes_from_docs()


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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



def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    nodes_doc = load_json(in_dir / "nodes.json")
    shards_doc = load_json(in_dir / "shards.json")
    events_doc = load_json(in_dir / "events.json")
    policy_doc = load_json(in_dir / "policy.json")
    outputs = run_simulation(nodes_doc, shards_doc, events_doc, policy_doc)
    write_canonical(out_dir / "cluster_state.json", outputs["cluster_state"])
    write_canonical(out_dir / "move_log.json", outputs["move_log"])
    write_canonical(out_dir / "cluster_diagnostics.json", outputs["cluster_diagnostics"])
    write_canonical(out_dir / "move_graph.json", outputs["move_graph"])
    write_canonical(out_dir / "summary.json", outputs["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
