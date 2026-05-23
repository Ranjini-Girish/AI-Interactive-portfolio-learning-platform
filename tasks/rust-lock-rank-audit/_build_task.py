"""Dev-only: generate fixtures and oracle outputs for rust-lock-rank-audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "environment" / "lockrank"
AUDIT = ROOT / "local-audit"


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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

    edges = [
        {"from_lock": a, "to_lock": b}
        for a, b in sorted(graph_edges)
    ]

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


def write_fixtures() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    dump_pretty(
        DATA / "policy.json",
        {
            "conflict_groups": [["lk_a", "lk_b"], ["lk_g", "lk_h"]],
            "fence_boost": 40,
            "rank_base": 100,
            "warmup_steps": 2,
        },
    )
    dump_pretty(
        DATA / "manifest.json",
        {"profile_tag": "staging", "run_tag": "prod"},
    )
    dump_pretty(DATA / "epochs.json", {"current_epoch": 5})
    dump_pretty(
        DATA / "trace.json",
        {
            "events": [
                {"lock_id": "lk_a", "op": "acquire", "step": 1, "thread_id": "t1"},
                {"lock_id": "lk_c", "op": "acquire", "step": 1, "thread_id": "t2"},
                {"lock_id": "lk_d", "op": "acquire", "step": 2, "thread_id": "t1"},
                {"lock_id": "lk_b", "op": "acquire", "step": 3, "thread_id": "t1"},
                {"lock_id": "lk_e", "op": "fence_enter", "step": 4, "thread_id": "t2"},
                {"lock_id": "lk_f", "op": "acquire", "step": 5, "thread_id": "t2"},
                {"lock_id": "lk_g", "op": "acquire", "step": 6, "thread_id": "t2"},
                {"lock_id": "lk_h", "op": "acquire", "step": 7, "thread_id": "t2"},
                {"lock_id": "lk_old", "op": "acquire", "step": 8, "thread_id": "t3"},
                {"lock_id": "lk_z", "op": "acquire", "step": 9, "thread_id": "t1"},
                {"lock_id": "lk_c", "op": "release", "step": 10, "thread_id": "t1"},
                {"lock_id": "lk_x", "op": "release", "step": 11, "thread_id": "t2"},
                {"lock_id": "lk_e", "op": "fence_exit", "step": 12, "thread_id": "t2"},
            ]
        },
    )
    locks = [
        ("lk_a", 5, 80),
        ("lk_b", 5, 60),
        ("lk_c", 5, 70),
        ("lk_d", 5, 90),
        ("lk_e", 5, 50),
        ("lk_f", 5, 30),
        ("lk_g", 5, 55),
        ("lk_h", 5, 45),
        ("lk_old", 2, 40),
        ("lk_z", 5, 75),
    ]
    for lid, epoch, base_rank in locks:
        dump_pretty(
            DATA / "locks" / f"{lid}.json",
            {"base_rank": base_rank, "epoch": epoch, "lock_id": lid},
        )
    threads = [
        ("t1", 5),
        ("t2", 5),
        ("t3", 5),
        ("t4", 2),
    ]
    for tid, epoch in threads:
        dump_pretty(
            DATA / "threads" / f"{tid}.json",
            {"epoch": epoch, "thread_id": tid},
        )
    for name, content in {
        "anchors/a1.txt": "anchor-a\n",
        "anchors/a2.txt": "anchor-b\n",
        "ancillary/meta.json": {"pack": "lockrank"},
        "ancillary/notes.json": {"note": "read-only"},
        "meta/seq.json": {"seq": 1},
        "grid/dims.json": {"rows": 2, "cols": 2},
    }.items():
        path = DATA / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".json"):
            dump_pretty(path, content)
        else:
            path.write_text(content, encoding="utf-8")


def main() -> None:
    write_fixtures()
    spec = """Normative contract for the lock rank graph audit. Inputs are UTF-8 JSON with ASCII-only strings. Outputs are UTF-8 JSON, ASCII-only, two-space indentation, recursively sorted object keys at every depth, no trailing spaces at line ends, and exactly one trailing newline after each root closing brace.

Read `policy.json` for float `rank_base` (positive), integer `fence_boost` (non-negative), integer `warmup_steps` (non-negative), and array `conflict_groups` of string pairs. Read `manifest.json` for `profile_tag` and `run_tag`. When they differ, multiply `rank_base` by `0.5` for inversion comparisons; round `effective_rank_base` in summary to six decimals. Read `epochs.json` for integer `current_epoch`. Read `trace.json` for array `events` with integer `step`, string `thread_id`, string `lock_id`, and `op` in `acquire`, `release`, `fence_enter`, or `fence_exit`.

Enumerate every `*.json` under `locks/` and `threads/`. Each lock has string `lock_id`, integer `epoch`, and integer `base_rank`. Each thread has string `thread_id` and integer `epoch`. A lock is stale when `epoch` is strictly less than `current_epoch - 1`. A thread is stale under the same rule. Packaging under `anchors/`, `ancillary/`, `meta/`, and `grid/` is ignored.

Process events in ascending `step`, then `thread_id`, then `lock_id`. Track per-thread `held` lock stacks and a boolean `fenced` set by `fence_enter` and cleared by `fence_exit`. Effective rank for a lock is `base_rank` plus `fence_boost` when the acting thread is fenced.

For `acquire` on a known lock: during warmup (`step` <= `warmup_steps`) record `warmup_skipped`, still update held stacks and fence flags, but emit no violations. When stale, record `stale_skipped` without state changes. Otherwise when any held lock has effective rank strictly greater than the acquired lock, emit `rank_inversion`. When the acquired lock shares a `conflict_groups` entry with a held lock, emit `conflict_hold`. On success append a directed edge from each held lock to the acquired lock. Unknown lock ids yield `unknown_lock`.

For `release`: unknown lock id yields `unknown_lock`. When the lock is not held, emit `orphan_release`. Otherwise remove it from the held stack (pop when it is the top lock, else remove the matching entry).

Emit `trace_outcomes.json` with `events` in processing order (fenced, held_count, lock_id, op, outcome, stale, step, thread_id). Outcomes are `ok`, `violation`, `orphan_release`, `unknown_lock`, `stale_skipped`, or `warmup_skipped`. Emit `violations.json` with `violations` sorted by step, thread_id, lock_id for every non-ok violation row including fields documented above. Emit `lock_states.json` with `locks` sorted by lock_id. Emit `thread_holds.json` with final `held_locks` per thread sorted by thread_id. Emit `hold_graph.json` with `edges` sorted by from_lock then to_lock. Emit `summary.json` with totals and effective_rank_base.

Read `RLR_DATA_DIR` defaulting to `/app/lockrank` and `RLR_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
"""
    (DATA / "SPEC.md").write_text(spec, encoding="utf-8")

    AUDIT.mkdir(exist_ok=True)
    for fname, obj in solve(DATA).items():
        dump_pretty(AUDIT / fname, obj)

    print("INPUT HASHES")
    for rel in sorted(p.relative_to(DATA).as_posix() for p in DATA.rglob("*") if p.is_file()):
        digest = sha256_bytes((DATA / rel).read_bytes())
        print(f'    "{rel}": "{digest}",')

    print("OUTPUT CANONICAL")
    for fname in sorted(solve(DATA).keys()):
        canon = canonical(solve(DATA)[fname])
        print(f'    "{fname}": "{sha256_bytes(canon.encode())}",')

    print("OUTPUT RAW")
    for fname in sorted(solve(DATA).keys()):
        raw = (AUDIT / fname).read_bytes()
        print(f'    "{fname}": "{sha256_bytes(raw)}",')

    print("FIELD")
    v = solve(DATA)["violations.json"]
    print('    "violations.rank_inversion":', sha256_bytes(canonical(v).encode()))
    print('    "summary.effective_rank_base":', sha256_bytes(canonical(solve(DATA)["summary.json"]["effective_rank_base"]).encode()))


if __name__ == "__main__":
    main()
