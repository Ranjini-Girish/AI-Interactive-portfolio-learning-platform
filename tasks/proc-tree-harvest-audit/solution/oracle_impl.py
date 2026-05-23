from __future__ import annotations

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


def _load_diag_codes_from_docs_path(docs_path: Path) -> tuple[frozenset[str], dict[str, str]]:
    """Parse /app/docs/diagnostics.md for the canonical list of diagnostic
    codes and their severities. Code lines look like:
        | E_INVALID_PARENT       | error    | ...
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
    procs_doc = load_json(in_dir / "processes.json")
    events_doc = load_json(in_dir / "events.json")
    policy_doc = load_json(in_dir / "policy.json")
    outputs = run_simulation(procs_doc["processes"], events_doc["events"], policy_doc)
    write_canonical(out_dir / "process_state.json", outputs["process_state"])
    write_canonical(out_dir / "harvest_log.json", outputs["harvest_log"])
    write_canonical(out_dir / "process_diagnostics.json", outputs["process_diagnostics"])
    write_canonical(out_dir / "lineage_graph.json", outputs["lineage_graph"])
    write_canonical(out_dir / "summary.json", outputs["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
