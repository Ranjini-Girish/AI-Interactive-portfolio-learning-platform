#!/bin/bash
set -euo pipefail

export VHR_DATA_DIR="${VHR_DATA_DIR:-/app/vnodering}"
export VHR_AUDIT_DIR="${VHR_AUDIT_DIR:-/app/audit}"
mkdir -p "${VHR_AUDIT_DIR}"

python3 - <<'PYEOF'
import json
import os
from pathlib import Path

def dump_pretty(path: Path, obj: object) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def solve_vnode(data_dir: Path) -> dict[str, object]:
    policy = json.loads((data_dir / "policy.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    epochs = json.loads((data_dir / "epochs.json").read_text(encoding="utf-8"))
    moves_doc = json.loads((data_dir / "moves.json").read_text(encoding="utf-8"))
    keys_doc = json.loads((data_dir / "keys.json").read_text(encoding="utf-8"))

    vote_ratio = float(policy["vote_ratio"])
    warmup = int(policy["warmup_moves"])
    ring_mod = int(policy["ring_modulus"])
    spill_penalty = float(policy["spill_penalty"])

    if manifest["shard_tag"] != manifest["active_shard"]:
        vote_ratio = min(1.0, round(vote_ratio + spill_penalty, 6))

    current_epoch = int(epochs["current_epoch"])

    vnodes: dict[str, dict] = {}
    for path in sorted((data_dir / "vnodes").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        vnodes[row["vnode_id"]] = row

    active_vnodes = {
        vid
        for vid, row in vnodes.items()
        if int(row["epoch"]) >= current_epoch - 1
    }
    total_weight = sum(float(vnodes[v]["weight"]) for v in active_vnodes)

    key_owner: dict[str, str] = {}
    for entry in keys_doc["keys"]:
        slot = int(entry["hash_slot"]) % ring_mod
        owner = None
        best_weight = -1.0
        for vid, row in vnodes.items():
            if vid not in active_vnodes:
                continue
            start = int(row["range_start"]) % ring_mod
            end = int(row["range_end"]) % ring_mod
            in_range = start <= end and start <= slot <= end
            if start > end:
                in_range = slot >= start or slot <= end
            if in_range and float(row["weight"]) > best_weight:
                best_weight = float(row["weight"])
                owner = vid
        if owner:
            key_owner[entry["key_id"]] = owner

    move_rows = []
    violation_rows = []
    handoff_rows = []

    reject_total = 0
    accept_total = 0
    stale_skipped_total = 0
    warmup_skipped_total = 0
    orphan_key_total = 0

    moves = sorted(
        moves_doc["moves"],
        key=lambda m: (int(m["step"]), m["key_id"]),
    )

    for mv in moves:
        step = int(mv["step"])
        kid = mv["key_id"]
        target = mv["target_vnode"]
        outcome = "ok"

        owner = key_owner.get(kid)
        target_stale = target not in active_vnodes

        if kid not in key_owner:
            orphan_key_total += 1
            outcome = "orphan_key"
            violation_rows.append(
                {
                    "key_id": kid,
                    "outcome": outcome,
                    "step": step,
                    "violation": "orphan_key",
                }
            )
        elif step <= warmup:
            warmup_skipped_total += 1
            outcome = "warmup_skipped"
        elif target_stale:
            stale_skipped_total += 1
            outcome = "stale_skipped"
        else:
            same_step = [x for x in moves if int(x["step"]) == step]
            agree_weight = sum(
                float(vnodes[x["target_vnode"]]["weight"])
                for x in same_step
                if x["target_vnode"] in active_vnodes
            )
            accepted = (
                total_weight > 0 and agree_weight >= vote_ratio * total_weight
            )
            if not accepted:
                reject_total += 1
                outcome = "handoff_rejected"
                violation_rows.append(
                    {
                        "agree_weight": round(agree_weight, 6),
                        "key_id": kid,
                        "outcome": outcome,
                        "step": step,
                        "target_vnode": target,
                        "violation": "handoff_rejected",
                    }
                )
            elif owner != target:
                accept_total += 1
                key_owner[kid] = target
                handoff_rows.append(
                    {
                        "from_vnode": owner,
                        "key_id": kid,
                        "step": step,
                        "to_vnode": target,
                    }
                )
            else:
                outcome = "noop_handoff"

        move_rows.append(
            {
                "current_owner": owner,
                "key_id": kid,
                "outcome": outcome,
                "step": step,
                "target_vnode": target,
            }
        )

    vnode_states = []
    for vid in sorted(vnodes):
        row = vnodes[vid]
        vnode_states.append(
            {
                "epoch": int(row["epoch"]),
                "range_end": int(row["range_end"]),
                "range_start": int(row["range_start"]),
                "stale": vid not in active_vnodes,
                "vnode_id": vid,
                "weight": float(row["weight"]),
            }
        )

    violations_sorted = sorted(
        violation_rows,
        key=lambda r: (int(r["step"]), r["key_id"]),
    )
    handoffs_sorted = sorted(
        handoff_rows,
        key=lambda r: (int(r["step"]), r["key_id"]),
    )

    summary = {
        "accept_total": accept_total,
        "current_epoch": current_epoch,
        "effective_vote_ratio": vote_ratio,
        "orphan_key_total": orphan_key_total,
        "reject_total": reject_total,
        "stale_skipped_total": stale_skipped_total,
        "step_total": len(moves),
        "warmup_skipped_total": warmup_skipped_total,
    }

    return {
        "handoff_plan.json": {"handoffs": handoffs_sorted},
        "move_outcomes.json": {"moves": move_rows},
        "ring_violations.json": {"violations": violations_sorted},
        "summary.json": summary,
        "vnode_states.json": {"vnodes": vnode_states},
    }


data_dir = Path(os.environ["VHR_DATA_DIR"])
audit_dir = Path(os.environ["VHR_AUDIT_DIR"])
audit_dir.mkdir(parents=True, exist_ok=True)
for fname, obj in solve_vnode(data_dir).items():
    dump_pretty(audit_dir / fname, obj)
PYEOF
