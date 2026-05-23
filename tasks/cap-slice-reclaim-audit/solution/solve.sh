#!/bin/bash
set -euo pipefail

export CSR_DATA_DIR="${CSR_DATA_DIR:-/app/capslice}"
export CSR_AUDIT_DIR="${CSR_AUDIT_DIR:-/app/audit}"
mkdir -p "${CSR_AUDIT_DIR}"

python3 - <<'PY'
import json
import os
from pathlib import Path

def dump_pretty(path, obj):
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def solve_cap_slice(data_dir: Path, audit_dir: Path) -> None:
    policy = json.loads((data_dir / "policy.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    epochs = json.loads((data_dir / "epochs.json").read_text(encoding="utf-8"))
    events_doc = json.loads((data_dir / "events.json").read_text(encoding="utf-8"))

    window = int(policy["window_size"])
    soft_cap = float(policy["soft_cap"])
    warmup = int(policy["warmup_steps"])
    tier_ratio = float(policy["tier_ratio"])
    current_epoch = int(epochs["current_epoch"])

    if manifest["monitor_tag"] != manifest["run_tag"]:
        soft_cap = soft_cap * 0.5

    slices: dict[str, dict] = {}
    for path in sorted((data_dir / "slices").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        slices[row["slice_id"]] = row

    active = {
        sid for sid, row in slices.items() if int(row["epoch"]) >= current_epoch - 1
    }
    total_weight = sum(float(slices[s]["weight"]) for s in active)

    events = sorted(
        events_doc["events"],
        key=lambda e: (int(e["step"]), e["slice_id"]),
    )

    history: dict[str, list[float]] = {sid: [] for sid in slices}
    reclaim_rows = []
    vote_rows = []
    window_rows = []
    slice_states = []

    reclaimed_total = 0
    tier_accepted = 0
    stale_skipped = 0

    for ev in events:
        step = int(ev["step"])
        sid = ev["slice_id"]
        used = float(ev["bytes_used"])
        tier = ev["tier"]

        stale = sid not in active
        if stale:
            stale_skipped += 1

        hist = history[sid]
        hist.append(used)
        if len(hist) > window:
            hist.pop(0)
        window_mean = sum(hist) / len(hist)

        if step <= warmup:
            factor = 0.0
            reclaimed_flag = False
        elif window_mean > soft_cap and used > 0:
            factor = min(1.0, (window_mean - soft_cap) / used)
            reclaimed_flag = factor > 0
        else:
            factor = 0.0
            reclaimed_flag = False

        if not stale:
            reclaim_rows.append(
                {
                    "bytes_used": used,
                    "reclaim_factor": round(factor, 6),
                    "reclaimed": reclaimed_flag,
                    "slice_id": sid,
                    "step": step,
                }
            )
        if reclaimed_flag and not stale:
            reclaimed_total += 1

        same_step = [x for x in events if int(x["step"]) == step]
        agree_weight = sum(
            float(slices[x["slice_id"]]["weight"])
            for x in same_step
            if x["tier"] == tier and x["slice_id"] in active
        )
        accepted_flag = (
            not stale
            and total_weight > 0
            and agree_weight >= tier_ratio * total_weight
        )
        if accepted_flag:
            tier_accepted += 1

        vote_rows.append(
            {
                "accepted": accepted_flag,
                "agree_weight": round(agree_weight, 6),
                "slice_id": sid,
                "step": step,
                "stale": stale,
                "tier": tier,
            }
        )
        window_rows.append(
            {
                "slice_id": sid,
                "step": step,
                "window_mean_bytes": round(window_mean, 6),
                "window_size": len(hist),
            }
        )

    for sid in sorted(slices):
        row = slices[sid]
        slice_states.append(
            {
                "epoch": int(row["epoch"]),
                "slice_id": sid,
                "stale": sid not in active,
                "weight": float(row["weight"]),
            }
        )

    summary = {
        "current_epoch": current_epoch,
        "effective_soft_cap": round(soft_cap, 6),
        "reclaimed_total": reclaimed_total,
        "stale_skipped_total": stale_skipped,
        "step_total": len(events),
        "tier_accepted_total": tier_accepted,
    }

    audit_dir.mkdir(parents=True, exist_ok=True)
    dump_pretty(audit_dir / "slice_states.json", {"slices": slice_states})
    dump_pretty(audit_dir / "reclaim_plan.json", {"entries": reclaim_rows})
    dump_pretty(audit_dir / "tier_votes.json", {"votes": vote_rows})
    dump_pretty(audit_dir / "window_stats.json", {"windows": window_rows})
    dump_pretty(audit_dir / "summary.json", summary)




data_dir = Path(os.environ.get("CSR_DATA_DIR", "/app/capslice"))
audit_dir = Path(os.environ.get("CSR_AUDIT_DIR", "/app/audit"))
solve_cap_slice(data_dir, audit_dir)
PY
