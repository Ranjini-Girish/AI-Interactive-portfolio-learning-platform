#!/bin/bash
set -euo pipefail

export RLR_DATA_DIR="${RLR_DATA_DIR:-/app/lockrank}"
export RLR_AUDIT_DIR="${RLR_AUDIT_DIR:-/app/audit}"
mkdir -p "${RLR_AUDIT_DIR}"

python3 - <<'PYEOF'
import json
import os
from pathlib import Path


def dump_pretty(path: Path, obj: object) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def solve(data_dir: Path) -> dict[str, object]:
    policy = json.loads((data_dir / "policy.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    epochs = json.loads((data_dir / "epochs.json").read_text(encoding="utf-8"))
    trace_doc = json.loads((data_dir / "trace.json").read_text(encoding="utf-8"))

    rank_base = float(policy["rank_base"])
    fence_boost = int(policy["fence_boost"])
    warmup = int(policy["warmup_steps"])
    groups = [tuple(g) for g in policy["conflict_groups"]]
    lock_to_group: dict[str, int] = {}
    for idx, grp in enumerate(groups):
        for lid in grp:
            lock_to_group[lid] = idx

    if manifest["profile_tag"] != manifest["run_tag"]:
        rank_base = rank_base * 0.5

    current_epoch = int(epochs["current_epoch"])

    locks: dict[str, dict] = {}
    for path in sorted((data_dir / "locks").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        locks[row["lock_id"]] = row

    threads: dict[str, dict] = {}
    for path in sorted((data_dir / "threads").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        threads[row["thread_id"]] = row

    active_locks = {
        lid
        for lid, row in locks.items()
        if int(row["epoch"]) >= current_epoch - 1
    }
    active_threads = {
        tid
        for tid, row in threads.items()
        if int(row["epoch"]) >= current_epoch - 1
    }

    events = sorted(
        trace_doc["events"],
        key=lambda e: (int(e["step"]), e["thread_id"], e["lock_id"]),
    )

    held: dict[str, list[str]] = {tid: [] for tid in threads}
    fenced: dict[str, bool] = {tid: False for tid in threads}

    trace_rows = []
    violation_rows = []
    graph_edges: set[tuple[str, str]] = set()

    rank_inversion_total = 0
    conflict_hold_total = 0
    orphan_release_total = 0
    unknown_lock_total = 0
    stale_skipped_total = 0
    warmup_skipped_total = 0

    for ev in events:
        step = int(ev["step"])
        tid = ev["thread_id"]
        lid = ev["lock_id"]
        op = ev["op"]

        lock_stale = lid not in active_locks
        thread_stale = tid not in active_threads
        stale = lock_stale or thread_stale

        outcome = "ok"
        violation_kind = None

        if lid not in locks and op in ("acquire", "release"):
            unknown_lock_total += 1
            outcome = "unknown_lock"
            violation_kind = "unknown_lock"
            violation_rows.append(
                {
                    "lock_id": lid,
                    "outcome": outcome,
                    "step": step,
                    "thread_id": tid,
                    "violation": violation_kind,
                }
            )
        elif stale:
            stale_skipped_total += 1
            outcome = "stale_skipped"
        elif step <= warmup:
            warmup_skipped_total += 1
            outcome = "warmup_skipped"
            if op == "fence_enter":
                fenced[tid] = True
            elif op == "fence_exit":
                fenced[tid] = False
            elif op == "acquire" and lid in locks:
                held[tid].append(lid)
            elif op == "release" and lid in held[tid]:
                stack = held[tid]
                if stack[-1] == lid:
                    stack.pop()
                else:
                    stack.remove(lid)
        elif op == "fence_enter":
            fenced[tid] = True
        elif op == "fence_exit":
            fenced[tid] = False
        elif op == "acquire":
            boost = fence_boost if fenced[tid] else 0
            new_rank = int(locks[lid]["base_rank"]) + boost
            held_ranks = []
            for h in held[tid]:
                hb = fence_boost if fenced[tid] else 0
                held_ranks.append(int(locks[h]["base_rank"]) + hb)
            if held_ranks and new_rank < max(held_ranks):
                rank_inversion_total += 1
                outcome = "violation"
                violation_kind = "rank_inversion"
                violation_rows.append(
                    {
                        "held_max_rank": max(held_ranks),
                        "lock_id": lid,
                        "new_rank": new_rank,
                        "outcome": outcome,
                        "step": step,
                        "thread_id": tid,
                        "violation": violation_kind,
                    }
                )
            grp = lock_to_group.get(lid)
            if grp is not None:
                for h in held[tid]:
                    if lock_to_group.get(h) == grp:
                        conflict_hold_total += 1
                        outcome = "violation"
                        violation_kind = "conflict_hold"
                        violation_rows.append(
                            {
                                "conflict_group": grp,
                                "lock_id": lid,
                                "outcome": outcome,
                                "peer_lock": h,
                                "step": step,
                                "thread_id": tid,
                                "violation": violation_kind,
                            }
                        )
                        break
            if outcome == "ok":
                for h in held[tid]:
                    graph_edges.add((h, lid))
                held[tid].append(lid)
        elif op == "release":
            if lid not in held[tid]:
                orphan_release_total += 1
                outcome = "orphan_release"
                violation_kind = "orphan_release"
                violation_rows.append(
                    {
                        "lock_id": lid,
                        "outcome": outcome,
                        "step": step,
                        "thread_id": tid,
                        "violation": violation_kind,
                    }
                )
            else:
                stack = held[tid]
                if stack[-1] == lid:
                    stack.pop()
                else:
                    stack.remove(lid)

        trace_rows.append(
            {
                "fenced": fenced[tid],
                "held_count": len(held[tid]),
                "lock_id": lid,
                "op": op,
                "outcome": outcome,
                "stale": stale,
                "step": step,
                "thread_id": tid,
            }
        )

    lock_states = []
    for lid in sorted(locks):
        row = locks[lid]
        lock_states.append(
            {
                "base_rank": int(row["base_rank"]),
                "epoch": int(row["epoch"]),
                "lock_id": lid,
                "stale": lid not in active_locks,
            }
        )

    thread_holds = []
    for tid in sorted(threads):
        thread_holds.append(
            {
                "held_locks": list(held[tid]),
                "thread_id": tid,
            }
        )

    edges = [{"from_lock": a, "to_lock": b} for a, b in sorted(graph_edges)]

    violations_sorted = sorted(
        violation_rows,
        key=lambda r: (int(r["step"]), r["thread_id"], r["lock_id"]),
    )

    summary = {
        "conflict_hold_total": conflict_hold_total,
        "current_epoch": current_epoch,
        "effective_rank_base": round(rank_base, 6),
        "orphan_release_total": orphan_release_total,
        "rank_inversion_total": rank_inversion_total,
        "stale_skipped_total": stale_skipped_total,
        "step_total": len(events),
        "unknown_lock_total": unknown_lock_total,
        "warmup_skipped_total": warmup_skipped_total,
    }

    return {
        "hold_graph.json": {"edges": edges},
        "lock_states.json": {"locks": lock_states},
        "summary.json": summary,
        "thread_holds.json": {"threads": thread_holds},
        "trace_outcomes.json": {"events": trace_rows},
        "violations.json": {"violations": violations_sorted},
    }


data_dir = Path(os.environ["RLR_DATA_DIR"])
audit_dir = Path(os.environ["RLR_AUDIT_DIR"])
audit_dir.mkdir(parents=True, exist_ok=True)
for fname, obj in solve(data_dir).items():
    dump_pretty(audit_dir / fname, obj)
PYEOF
