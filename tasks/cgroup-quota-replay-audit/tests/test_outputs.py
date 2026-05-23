"""Verifier suite for  (typescript)."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
BUILD_DIR = Path("/app/build")
BINARY_PATH = BUILD_DIR / "cgreplay"

CGROUPS_PATH = DATA_DIR / "cgroups.json"
EVENTS_PATH = DATA_DIR / "events.json"
POLICY_PATH = DATA_DIR / "policy.json"

CGROUP_STATE_PATH = OUT_DIR / "cgroup_state.json"
VIOLATION_PATH = OUT_DIR / "quota_violation_log.json"
TASKS_PATH = OUT_DIR / "task_assignments.json"
LINEAGE_PATH = OUT_DIR / "lineage_graph.json"
SUMMARY_PATH = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    CGROUP_STATE_PATH,
    VIOLATION_PATH,
    TASKS_PATH,
    LINEAGE_PATH,
    SUMMARY_PATH,
)

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    # populated below after generation; placeholder is fine - the
    # test_input_hashes_unchanged_after_run test will replace these via
    # the fixture-precomputed dictionary.
}


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


VALID_OPS = frozenset({
    "create", "delete", "attach_task", "detach_task",
    "consume_cpu", "consume_mem", "consume_io",
    "release_cpu", "release_mem",
    "update_quota", "move_subtree",
})


def _is_descendant(cgroups: dict, anc: str, maybe_desc: str) -> bool:
    """True iff `maybe_desc` is a descendant of `anc` (strict)."""
    if anc == maybe_desc:
        return False
    cur = cgroups.get(maybe_desc)
    visited = set()
    while cur is not None and cur["parent_id"] is not None:
        p = cur["parent_id"]
        if p in visited:
            return False
        visited.add(p)
        if p == anc:
            return True
        cur = cgroups.get(p)
    return False


def _children_of(cgroups: dict, parent_id):
    return [cid for cid, c in cgroups.items() if c["parent_id"] == parent_id]


def _ancestors_of(cgroups: dict, cid: str):
    """Returns [cid, parent, grand, ..., root] in walk order."""
    out = [cid]
    cur = cgroups.get(cid)
    while cur is not None and cur["parent_id"] is not None:
        out.append(cur["parent_id"])
        cur = cgroups.get(cur["parent_id"])
    return out


def _check_sum_children_capped_for_parent(cgroups: dict, parent_id, exclude_id=None, replacement=None):
    """Returns True if the sum of mem_quota_kb across `parent_id`'s direct
    children does not exceed `parent_id`'s mem_quota_kb. `replacement` is
    a (id, mem_quota_kb) tuple that is added/overrides in the running sum
    (used to simulate a candidate create / update). `exclude_id` is excluded
    from the running sum (used to simulate a candidate move-out).

    `parent_id` may be None for root-level checks; root-level has no upper
    bound so we always return True.
    """
    if parent_id is None:
        return True  # root has no parent quota to violate
    parent = cgroups.get(parent_id)
    if parent is None:
        return True  # parent missing implies a different error
    total = 0
    for cid, c in cgroups.items():
        if c["parent_id"] != parent_id:
            continue
        if cid == exclude_id:
            continue
        if replacement is not None and replacement[0] == cid:
            total += replacement[1]
        else:
            total += c["mem_quota_kb"]
    if replacement is not None and replacement[0] not in cgroups:
        total += replacement[1]
    return total <= parent["mem_quota_kb"]


def simulate(cgroups_in: dict, events_in: dict, policy: dict) -> dict[str, Any]:
    """Run the reference simulator. Returns a dict with the five output
    documents under keys `cgroup_state`, `quota_violation_log`,
    `task_assignments`, `lineage_graph`, `summary`."""

    quota_inheritance = policy["quota_inheritance"]
    over_quota_action = policy["over_quota_action"]
    delete_action = policy["delete_action"]
    min_quota_kb = policy["min_quota_kb"]
    track_lineage = policy["track_lineage"]

    cgroups: dict[str, dict] = {}
    for c in cgroups_in["cgroups"]:
        cgroups[c["id"]] = {
            "id": c["id"],
            "parent_id": c["parent_id"],
            "cpu_quota_ms": c["cpu_quota_ms"],
            "mem_quota_kb": c["mem_quota_kb"],
            "io_quota_iops": c["io_quota_iops"],
            "cpu_used_ms": 0,
            "mem_used_kb": 0,
            "io_used_iops": 0,
            "peak_cpu_ms": 0,
            "peak_mem_kb": 0,
            "tasks": set(),
        }

    task_to_cgroup: dict[str, str] = {}
    violations: list[dict] = []

    # lineage: collect all observed ids, then add edges
    observed_ids: set[str] = set(cgroups.keys())
    lineage_edges: set[tuple[str, str]] = set()
    ROOT_NODE = "<root>"
    root_node_used = False

    counters = {
        "creates_rejected": 0,
        "creates_succeeded": 0,
        "deletes_succeeded": 0,
        "moves_succeeded": 0,
        "rejected_consumes": 0,
        "throttled_consumes": 0,
        "total_violations": 0,
    }
    violation_count_by_cgroup: dict[str, int] = {}

    def _bump_violation(cid: str):
        violation_count_by_cgroup[cid] = violation_count_by_cgroup.get(cid, 0) + 1

    def _check_chain_headroom(cid: str, resource_field_used: str, resource_field_quota: str, amount: int):
        """Returns (bottleneck_id, headroom). For 'strict', walks ancestors;
        for 'independent' / 'sum_children_capped', only checks the cgroup
        itself. bottleneck_id is the closest ancestor (cgroup itself if
        independent) whose headroom is the minimum, but ONLY when the
        chain headroom is < amount; otherwise (None, headroom)."""
        chain = [cid] if quota_inheritance != "strict" else _ancestors_of(cgroups, cid)
        min_headroom = None
        bottleneck = None
        for ancid in chain:
            anc = cgroups[ancid]
            headroom = anc[resource_field_quota] - anc[resource_field_used]
            if headroom < 0:
                headroom = 0
            if min_headroom is None or headroom < min_headroom:
                min_headroom = headroom
                bottleneck = ancid
        if min_headroom is None:
            return (None, 0)
        if min_headroom < amount:
            return (bottleneck, min_headroom)
        return (None, min_headroom)

    def _do_consume(seq: int, cid: str, resource: str, amount: int):
        """Returns nothing; mutates cgroups + violations + counters."""
        used_field = f"{resource}_used_{'iops' if resource == 'io' else ('ms' if resource == 'cpu' else 'kb')}"
        quota_field = f"{resource}_quota_{'iops' if resource == 'io' else ('ms' if resource == 'cpu' else 'kb')}"
        if amount == 0:
            return  # silent
        if cid not in cgroups:
            return  # E_CGROUP_NOT_FOUND -- not in violation log
        bottleneck, headroom = _check_chain_headroom(cid, used_field, quota_field, amount)
        if bottleneck is None:
            # within quota for the whole chain
            cgroups[cid][used_field] += amount
            if resource == "cpu":
                cgroups[cid]["peak_cpu_ms"] = max(cgroups[cid]["peak_cpu_ms"], cgroups[cid]["cpu_used_ms"])
            elif resource == "mem":
                cgroups[cid]["peak_mem_kb"] = max(cgroups[cid]["peak_mem_kb"], cgroups[cid]["mem_used_kb"])
            return
        # over quota
        if over_quota_action == "reject":
            violations.append({
                "amount": amount,
                "amount_dropped": amount,
                "cgroup_id": bottleneck,
                "code": "E_OVER_QUOTA",
                "resource": resource,
                "seq": seq,
            })
            counters["rejected_consumes"] += 1
            counters["total_violations"] += 1
            _bump_violation(bottleneck)
        else:  # "throttle"
            bumped = headroom
            cgroups[cid][used_field] += bumped
            if resource == "cpu":
                cgroups[cid]["peak_cpu_ms"] = max(cgroups[cid]["peak_cpu_ms"], cgroups[cid]["cpu_used_ms"])
            elif resource == "mem":
                cgroups[cid]["peak_mem_kb"] = max(cgroups[cid]["peak_mem_kb"], cgroups[cid]["mem_used_kb"])
            violations.append({
                "amount": amount,
                "amount_dropped": amount - bumped,
                "cgroup_id": cid,
                "code": "W_THROTTLED",
                "resource": resource,
                "seq": seq,
            })
            counters["throttled_consumes"] += 1
            counters["total_violations"] += 1
            _bump_violation(cid)

    def _do_release(cid: str, resource: str, amount: int):
        """Returns nothing; mutates cgroups."""
        used_field = f"{resource}_used_{'ms' if resource == 'cpu' else 'kb'}"
        if amount == 0 or cid not in cgroups:
            return
        cur = cgroups[cid][used_field]
        if amount > cur:
            cgroups[cid][used_field] = 0
        else:
            cgroups[cid][used_field] = cur - amount

    for ev in events_in["events"]:
        seq = ev["seq"]
        op = ev["op"]
        eid = ev["id"]

        if op == "create":
            new_id = eid
            new_parent = ev["parent_id"]
            cpu_q = ev["cpu_quota_ms"]
            mem_q = ev["mem_quota_kb"]
            io_q = ev["io_quota_iops"]
            # 1. duplicate id
            if new_id in cgroups:
                counters["creates_rejected"] += 1
                continue
            # 2. parent missing
            if new_parent is not None and new_parent not in cgroups:
                counters["creates_rejected"] += 1
                continue
            # 3. below min mem
            if mem_q < min_quota_kb:
                counters["creates_rejected"] += 1
                continue
            # 4. sum-children-capped under that mode
            if quota_inheritance == "sum_children_capped":
                ok = _check_sum_children_capped_for_parent(
                    cgroups, new_parent, exclude_id=None,
                    replacement=(new_id, mem_q),
                )
                if not ok:
                    counters["creates_rejected"] += 1
                    continue
            cgroups[new_id] = {
                "id": new_id,
                "parent_id": new_parent,
                "cpu_quota_ms": cpu_q,
                "mem_quota_kb": mem_q,
                "io_quota_iops": io_q,
                "cpu_used_ms": 0,
                "mem_used_kb": 0,
                "io_used_iops": 0,
                "peak_cpu_ms": 0,
                "peak_mem_kb": 0,
                "tasks": set(),
            }
            observed_ids.add(new_id)
            counters["creates_succeeded"] += 1

        elif op == "delete":
            del_id = eid
            if del_id not in cgroups:
                continue  # E_CGROUP_NOT_FOUND, no state change
            kids = _children_of(cgroups, del_id)
            if kids:
                continue  # E_HAS_CHILDREN
            cur = cgroups[del_id]
            if cur["tasks"]:
                if delete_action == "reject_if_tasks":
                    continue  # E_HAS_TASKS_REJECT
                # reparent_to_parent
                parent_id = cur["parent_id"]
                if parent_id is not None:
                    # reparent every task to parent
                    for t in list(cur["tasks"]):
                        task_to_cgroup[t] = parent_id
                        cgroups[parent_id]["tasks"].add(t)
                else:
                    # detach silently
                    for t in list(cur["tasks"]):
                        task_to_cgroup.pop(t, None)
                cur["tasks"].clear()
            del cgroups[del_id]
            counters["deletes_succeeded"] += 1

        elif op == "attach_task":
            cid = eid
            tid = ev["task_id"]
            if cid not in cgroups:
                continue
            if tid in task_to_cgroup:
                continue  # E_TASK_ALREADY_ATTACHED
            cgroups[cid]["tasks"].add(tid)
            task_to_cgroup[tid] = cid

        elif op == "detach_task":
            cid = eid
            tid = ev["task_id"]
            if cid not in cgroups:
                continue
            if tid not in cgroups[cid]["tasks"]:
                continue  # E_TASK_NOT_FOUND
            cgroups[cid]["tasks"].remove(tid)
            task_to_cgroup.pop(tid, None)

        elif op in ("consume_cpu", "consume_mem", "consume_io"):
            resource = op.split("_")[1]
            cid = eid
            amt = ev["amount"]
            _do_consume(seq, cid, resource, amt)

        elif op in ("release_cpu", "release_mem"):
            resource = op.split("_")[1]
            cid = eid
            amt = ev["amount"]
            _do_release(cid, resource, amt)

        elif op == "update_quota":
            cid = eid
            cpu_q = ev["cpu_quota_ms"]
            mem_q = ev["mem_quota_kb"]
            io_q = ev["io_quota_iops"]
            if cid not in cgroups:
                continue
            if mem_q < min_quota_kb:
                continue  # E_BELOW_MIN_QUOTA
            if quota_inheritance == "sum_children_capped":
                # Check parent's sum constraint with cid's new mem_q
                parent_id = cgroups[cid]["parent_id"]
                ok = _check_sum_children_capped_for_parent(
                    cgroups, parent_id, exclude_id=None,
                    replacement=(cid, mem_q),
                )
                if not ok:
                    continue
                # Also: cid's children are unaffected by cpu/io quota
                # changes; we don't re-check the cid-as-parent constraint
                # because its children's mem_quota_kb did not change. But
                # we DO check that cid's children sum still fits if cid's
                # mem_quota_kb decreased.
                kid_sum = sum(c["mem_quota_kb"] for c in cgroups.values() if c["parent_id"] == cid)
                if kid_sum > mem_q:
                    continue  # children would now exceed cid's new quota
            cgroups[cid]["cpu_quota_ms"] = cpu_q
            cgroups[cid]["mem_quota_kb"] = mem_q
            cgroups[cid]["io_quota_iops"] = io_q

        elif op == "move_subtree":
            cid = eid
            new_parent = ev["target_parent_id"]
            if cid not in cgroups:
                continue
            if new_parent is not None and new_parent not in cgroups:
                continue
            # cycle: target equals self or is descendant
            if new_parent is not None and (new_parent == cid or _is_descendant(cgroups, cid, new_parent)):
                continue
            # sum-children-capped: moving cid under new_parent might
            # exceed new_parent's mem_quota_kb (cid's current mem_q gets
            # added). For root (new_parent is None), no constraint.
            if quota_inheritance == "sum_children_capped" and new_parent is not None:
                old_parent = cgroups[cid]["parent_id"]
                if old_parent != new_parent:
                    ok = _check_sum_children_capped_for_parent(
                        cgroups, new_parent, exclude_id=None,
                        replacement=(cid, cgroups[cid]["mem_quota_kb"]),
                    )
                    if not ok:
                        continue
            old_parent = cgroups[cid]["parent_id"]
            cgroups[cid]["parent_id"] = new_parent
            counters["moves_succeeded"] += 1
            if track_lineage:
                src = old_parent if old_parent is not None else ROOT_NODE
                if src == ROOT_NODE:
                    root_node_used = True
                if src != cid:
                    lineage_edges.add((src, cid))
                    observed_ids.add(cid)
                    if old_parent is not None:
                        observed_ids.add(old_parent)
        else:
            raise ValueError(f"unknown op: {op}")

    # Build cgroup_state
    cgroup_state = {
        "cgroups": sorted(
            (
                {
                    "cpu_quota_ms": c["cpu_quota_ms"],
                    "cpu_used_ms": c["cpu_used_ms"],
                    "id": c["id"],
                    "io_quota_iops": c["io_quota_iops"],
                    "io_used_iops": c["io_used_iops"],
                    "mem_quota_kb": c["mem_quota_kb"],
                    "mem_used_kb": c["mem_used_kb"],
                    "parent_id": c["parent_id"],
                    "peak_cpu_ms": c["peak_cpu_ms"],
                    "peak_mem_kb": c["peak_mem_kb"],
                    "tasks": sorted(c["tasks"]),
                }
                for c in cgroups.values()
            ),
            key=lambda x: x["id"],
        )
    }

    # task_assignments
    task_assignments = {
        "tasks": sorted(
            (
                {"cgroup_id": cg, "task_id": t}
                for t, cg in task_to_cgroup.items()
            ),
            key=lambda x: x["task_id"],
        )
    }

    # quota_violation_log (chronological order; we appended in seq order,
    # which is the order events ran in)
    quota_violation_log = {"violations": violations}

    # lineage_graph
    if track_lineage:
        all_nodes = set(observed_ids)
        if root_node_used:
            all_nodes.add(ROOT_NODE)
        # Compute degrees from edges
        in_deg: dict[str, int] = {n: 0 for n in all_nodes}
        out_deg: dict[str, int] = {n: 0 for n in all_nodes}
        for f, t in lineage_edges:
            all_nodes.add(f)
            all_nodes.add(t)
            in_deg.setdefault(f, 0)
            in_deg.setdefault(t, 0)
            out_deg.setdefault(f, 0)
            out_deg.setdefault(t, 0)
            out_deg[f] += 1
            in_deg[t] += 1
        # Tarjan SCCs
        nodes_sorted = sorted(all_nodes)
        edges_sorted = sorted(lineage_edges)
        scc_cycles = _multi_vertex_sccs(nodes_sorted, edges_sorted)
        lineage_graph = {
            "cycles": scc_cycles,
            "edges": [{"from": f, "to": t} for f, t in edges_sorted],
            "nodes": [
                {"id": n, "in_degree": in_deg[n], "out_degree": out_deg[n]}
                for n in nodes_sorted
            ],
        }
    else:
        lineage_graph = {"cycles": [], "edges": [], "nodes": []}

    # summary
    hot = sorted(
        violation_count_by_cgroup.items(),
        key=lambda kv: (-kv[1], kv[0]),
    )
    summary = {
        "creates_rejected": counters["creates_rejected"],
        "creates_succeeded": counters["creates_succeeded"],
        "deletes_succeeded": counters["deletes_succeeded"],
        "final_cgroup_count": len(cgroup_state["cgroups"]),
        "final_task_count": len(task_assignments["tasks"]),
        "hot_cgroups": [
            {"id": cid, "violation_count": cnt} for cid, cnt in hot
        ],
        "moves_succeeded": counters["moves_succeeded"],
        "rejected_consumes": counters["rejected_consumes"],
        "throttled_consumes": counters["throttled_consumes"],
        "total_events": len(events_in["events"]),
        "total_violations": counters["total_violations"],
    }

    return {
        "cgroup_state": cgroup_state,
        "quota_violation_log": quota_violation_log,
        "task_assignments": task_assignments,
        "lineage_graph": lineage_graph,
        "summary": summary,
    }


def _multi_vertex_sccs(nodes: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Iterative Tarjan that returns multi-vertex SCCs as sorted lists, with
    the outer list sorted by lex-smallest member."""
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for f, t in edges:
        adj.setdefault(f, []).append(t)
        adj.setdefault(t, [])
    index_counter = [0]
    stack: list[str] = []
    on_stack: dict[str, bool] = {}
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str):
        # iterative
        work_stack: list[tuple[str, int]] = [(v, 0)]
        call_stack: list[str] = []
        while work_stack:
            node, pi = work_stack[-1]
            if pi == 0:
                indices[node] = index_counter[0]
                lowlink[node] = index_counter[0]
                index_counter[0] += 1
                stack.append(node)
                on_stack[node] = True
                call_stack.append(node)
            neighbours = adj.get(node, [])
            if pi < len(neighbours):
                w = neighbours[pi]
                work_stack[-1] = (node, pi + 1)
                if w not in indices:
                    work_stack.append((w, 0))
                elif on_stack.get(w):
                    lowlink[node] = min(lowlink[node], indices[w])
            else:
                if lowlink[node] == indices[node]:
                    comp: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        comp.append(w)
                        if w == node:
                            break
                    if len(comp) > 1:
                        sccs.append(sorted(comp))
                work_stack.pop()
                if work_stack:
                    parent = work_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                call_stack.pop()

    for n in nodes:
        if n not in indices:
            strongconnect(n)
    sccs.sort(key=lambda s: s[0])
    return sccs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def input_data() -> dict[str, Any]:
    return {
        "cgroups": load_json(CGROUPS_PATH),
        "events": load_json(EVENTS_PATH),
        "policy": load_json(POLICY_PATH),
    }


@pytest.fixture(scope="session")
def expected_outputs(input_data) -> dict[str, Any]:
    return simulate(
        input_data["cgroups"],
        input_data["events"],
        input_data["policy"],
    )


@pytest.fixture(scope="session")
def precomputed_input_hashes() -> dict[Path, str]:
    return {p: sha256_of(p) for p in (CGROUPS_PATH, EVENTS_PATH, POLICY_PATH)}


@pytest.fixture(scope="session")
def binary_run_outputs(precomputed_input_hashes) -> dict[Path, Any]:
    """Wipes /app/output and runs the agent binary fresh against
    /app/data, then loads each output document. Subsequent tests use the
    loaded documents."""
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert BINARY_PATH.exists(), f"agent binary missing at {BINARY_PATH}"
    assert BINARY_PATH.stat().st_mode & stat.S_IXUSR, "binary not executable"
    res = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode == 0, (
        f"binary failed: rc={res.returncode}\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    out: dict[Path, Any] = {}
    for p in ALL_OUT_PATHS:
        assert p.exists(), f"missing output: {p}"
        out[p] = load_json(p)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inputs_unchanged(precomputed_input_hashes):
    for p, h in precomputed_input_hashes.items():
        assert sha256_of(p) == h, f"{p} content mutated"


def test_binary_built_and_executable():
    assert BINARY_PATH.exists(), f"missing {BINARY_PATH}"
    assert BINARY_PATH.stat().st_mode & stat.S_IXUSR, "binary not executable"




def test_binary_runs_cleanly_and_outputs_are_fresh(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        assert p in binary_run_outputs


def test_binary_rejects_wrong_arg_counts():
    res = subprocess.run([str(BINARY_PATH)], capture_output=True, text=True, timeout=30)
    assert res.returncode != 0
    res = subprocess.run([str(BINARY_PATH), str(DATA_DIR)], capture_output=True, text=True, timeout=30)
    assert res.returncode != 0
    res = subprocess.run([str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR), "extra"], capture_output=True, text=True, timeout=30)
    assert res.returncode != 0


def test_binary_uses_argv_paths_not_hardcoded(tmp_path, input_data):
    """Run the binary with a custom out_dir to prove it doesn't write to a
    hardcoded /app/output. We pass /app/data as input and a temp dir as
    output, then check the temp dir got populated."""
    tmp_out = tmp_path / "altout"
    tmp_out.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(tmp_out)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode == 0, f"binary failed under alt out_dir: {res.stderr}"
    for name in (
        "cgroup_state.json", "quota_violation_log.json",
        "task_assignments.json", "lineage_graph.json", "summary.json",
    ):
        assert (tmp_out / name).exists(), f"binary did not write {name} to argv[2]"


def test_outputs_strict_json_formatting(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(p)
        assert ok, msg


def test_outputs_are_ascii_at_every_depth(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        text = p.read_text(encoding="utf-8")
        text.encode("ascii")  # raises if any non-ascii


def test_cgroup_state_match_reference(binary_run_outputs, expected_outputs):
    actual = binary_run_outputs[CGROUP_STATE_PATH]
    assert actual == expected_outputs["cgroup_state"]


def test_quota_violation_log_match_reference(binary_run_outputs, expected_outputs):
    actual = binary_run_outputs[VIOLATION_PATH]
    assert actual == expected_outputs["quota_violation_log"]


def test_task_assignments_match_reference(binary_run_outputs, expected_outputs):
    actual = binary_run_outputs[TASKS_PATH]
    assert actual == expected_outputs["task_assignments"]


def test_lineage_graph_match_reference(binary_run_outputs, expected_outputs):
    actual = binary_run_outputs[LINEAGE_PATH]
    assert actual == expected_outputs["lineage_graph"]


def test_summary_match_reference(binary_run_outputs, expected_outputs):
    actual = binary_run_outputs[SUMMARY_PATH]
    assert actual == expected_outputs["summary"]


def test_violation_codes_are_legal(binary_run_outputs):
    log = binary_run_outputs[VIOLATION_PATH]
    legal = {"E_OVER_QUOTA", "W_THROTTLED"}
    legal_resources = {"cpu", "mem", "io"}
    for v in log["violations"]:
        assert v["code"] in legal, v
        assert v["resource"] in legal_resources, v
        assert v["amount_dropped"] <= v["amount"]
        assert v["amount_dropped"] >= 0


def test_cgroup_state_no_duplicate_ids(binary_run_outputs):
    state = binary_run_outputs[CGROUP_STATE_PATH]
    ids = [c["id"] for c in state["cgroups"]]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)


def test_cgroup_state_parent_ids_are_resolvable(binary_run_outputs):
    state = binary_run_outputs[CGROUP_STATE_PATH]
    ids = {c["id"] for c in state["cgroups"]}
    for c in state["cgroups"]:
        if c["parent_id"] is not None:
            assert c["parent_id"] in ids, (
                f"cgroup {c['id']!r} points to missing parent {c['parent_id']!r}"
            )


def test_cgroup_state_no_parent_cycle(binary_run_outputs):
    state = binary_run_outputs[CGROUP_STATE_PATH]
    parent = {c["id"]: c["parent_id"] for c in state["cgroups"]}
    for cid in parent:
        seen = set()
        cur = cid
        while parent.get(cur) is not None:
            cur = parent[cur]
            assert cur not in seen, f"cycle through {cid}"
            seen.add(cur)


def test_task_assignments_each_task_in_exactly_one_cgroup(binary_run_outputs):
    state = binary_run_outputs[CGROUP_STATE_PATH]
    tasks = binary_run_outputs[TASKS_PATH]
    tid_to_cid = {t["task_id"]: t["cgroup_id"] for t in tasks["tasks"]}
    assert len(tid_to_cid) == len(tasks["tasks"])
    for c in state["cgroups"]:
        for t in c["tasks"]:
            assert tid_to_cid.get(t) == c["id"], (
                f"task {t} listed under {c['id']} but mapped to {tid_to_cid.get(t)}"
            )


def test_summary_consistency_with_other_outputs(binary_run_outputs):
    state = binary_run_outputs[CGROUP_STATE_PATH]
    log = binary_run_outputs[VIOLATION_PATH]
    tasks = binary_run_outputs[TASKS_PATH]
    summary = binary_run_outputs[SUMMARY_PATH]
    assert summary["final_cgroup_count"] == len(state["cgroups"])
    assert summary["final_task_count"] == len(tasks["tasks"])
    assert summary["total_violations"] == len(log["violations"])
    rej = sum(1 for v in log["violations"] if v["code"] == "E_OVER_QUOTA")
    thr = sum(1 for v in log["violations"] if v["code"] == "W_THROTTLED")
    assert summary["rejected_consumes"] == rej
    assert summary["throttled_consumes"] == thr


def test_dataset_invariants_have_diagnostics_and_lineage(input_data, expected_outputs):
    """Sanity check that the visible dataset exercises the interesting
    branches: at least one E_OVER_QUOTA, at least one W_THROTTLED, at
    least one move_subtree, at least one create_rejected, at least one
    delete_succeeded."""
    log = expected_outputs["quota_violation_log"]
    summary = expected_outputs["summary"]
    codes = {v["code"] for v in log["violations"]}
    assert "E_OVER_QUOTA" in codes or "W_THROTTLED" in codes, (
        "dataset never exercises the over-quota path"
    )
    assert summary["moves_succeeded"] > 0
    assert summary["creates_rejected"] > 0
    assert summary["deletes_succeeded"] > 0


def test_data_dir_tree_unchanged_after_run(precomputed_input_hashes, binary_run_outputs):
    for p, h in precomputed_input_hashes.items():
        assert sha256_of(p) == h, f"{p} mutated by binary run"


def test_binary_rejects_missing_input_files(tmp_path):
    bad_data = tmp_path / "nodata"
    bad_data.mkdir()
    bad_out = tmp_path / "noout"
    bad_out.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(bad_data), str(bad_out)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_binary_rejects_malformed_json(tmp_path, input_data):
    """Pass a data dir whose policy.json is not valid JSON; the binary
    must exit non-zero rather than producing outputs."""
    bad_data = tmp_path / "baddata"
    bad_data.mkdir()
    (bad_data / "cgroups.json").write_text(json.dumps(input_data["cgroups"]))
    (bad_data / "events.json").write_text(json.dumps(input_data["events"]))
    (bad_data / "policy.json").write_text("{not valid json")
    bad_out = tmp_path / "badout"
    bad_out.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(bad_data), str(bad_out)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_determinism_two_runs_byte_identical(tmp_path):
    """Run the binary twice into two different out-dirs and check the
    five output files are byte-identical."""
    out_a = tmp_path / "a"
    out_a.mkdir()
    out_b = tmp_path / "b"
    out_b.mkdir()
    for out in (out_a, out_b):
        res = subprocess.run(
            [str(BINARY_PATH), str(DATA_DIR), str(out)],
            capture_output=True, text=True, timeout=60,
        )
        assert res.returncode == 0
    for name in (
        "cgroup_state.json", "quota_violation_log.json",
        "task_assignments.json", "lineage_graph.json", "summary.json",
    ):
        a = (out_a / name).read_bytes()
        b = (out_b / name).read_bytes()
        assert a == b, f"{name} differs between two runs"


