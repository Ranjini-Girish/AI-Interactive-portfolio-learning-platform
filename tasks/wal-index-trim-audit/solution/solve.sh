#!/bin/bash
set -euo pipefail

export WIT_DATA_DIR="${WIT_DATA_DIR:-/app/waltrim}"
export WIT_AUDIT_DIR="${WIT_AUDIT_DIR:-/app/audit}"
mkdir -p "${WIT_AUDIT_DIR}"

python3 - <<'PY'
import json
import os
from pathlib import Path


def dump_pretty(path, obj):
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def solve_wal_trim(data_dir: Path, audit_dir: Path) -> None:
    policy = json.loads((data_dir / "policy.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    epochs = json.loads((data_dir / "epochs.json").read_text(encoding="utf-8"))
    indexes_doc = json.loads((data_dir / "indexes.json").read_text(encoding="utf-8"))
    links_doc = json.loads((data_dir / "links.json").read_text(encoding="utf-8"))

    window = int(policy["window_size"])
    threshold = float(policy["trim_threshold"])
    warmup = int(policy["warmup_indexes"])
    vote_ratio = float(policy["vote_ratio"])
    current_epoch = int(epochs["current_epoch"])

    if manifest["snapshot_tag"] != manifest["live_tag"]:
        threshold *= 0.5

    segments: dict[str, dict] = {}
    for path in sorted((data_dir / "segments").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        segments[row["segment_id"]] = row

    pinned: set[str] = {sid for sid, row in segments.items() if row.get("pin")}
    for link in links_doc.get("links", []):
        if link["from_segment"] in pinned:
            pinned.add(link["to_segment"])

    active = {
        sid
        for sid, row in segments.items()
        if int(row["epoch"]) >= current_epoch - 1
    }
    total_weight = sum(float(segments[s]["weight"]) for s in active)

    events = sorted(
        indexes_doc["indexes"],
        key=lambda e: (int(e["index"]), e["segment_id"]),
    )

    history: dict[str, list[float]] = {sid: [] for sid in segments}
    trim_rows = []
    vote_rows = []
    stat_rows = []
    segment_states = []
    trim_total = 0
    vote_accepted = 0
    stale_skipped = 0

    for ev in events:
        idx = int(ev["index"])
        sid = ev["segment_id"]
        bytes_val = float(ev["payload_bytes"])
        role = ev["role"]

        stale = sid not in active
        if stale:
            stale_skipped += 1

        hist = history[sid]
        hist.append(bytes_val)
        if len(hist) > window:
            hist.pop(0)
        window_mean = sum(hist) / len(hist)

        hard_pin = sid in pinned
        if idx <= warmup or hard_pin:
            factor = 0.0
            trimmed = False
        elif window_mean > threshold and bytes_val > 0:
            factor = min(1.0, (window_mean - threshold) / bytes_val)
            trimmed = factor > 0
        else:
            factor = 0.0
            trimmed = False

        if not stale:
            trim_rows.append(
                {
                    "bytes_trimmed": round(bytes_val * factor, 6),
                    "index": idx,
                    "segment_id": sid,
                    "trim_factor": round(factor, 6),
                    "trimmed": trimmed,
                }
            )
        if trimmed and not stale:
            trim_total += 1

        same_idx = [x for x in events if int(x["index"]) == idx]
        agree_weight = sum(
            float(segments[x["segment_id"]]["weight"])
            for x in same_idx
            if x["role"] == role and x["segment_id"] in active
        )
        accepted = (
            not stale
            and total_weight > 0
            and agree_weight >= vote_ratio * total_weight
        )
        if accepted:
            vote_accepted += 1

        vote_rows.append(
            {
                "accepted": accepted,
                "agree_weight": round(agree_weight, 6),
                "index": idx,
                "role": role,
                "segment_id": sid,
                "stale": stale,
            }
        )
        stat_rows.append(
            {
                "index": idx,
                "segment_id": sid,
                "window_mean_bytes": round(window_mean, 6),
                "window_size": len(hist),
            }
        )

    for sid in sorted(segments):
        row = segments[sid]
        segment_states.append(
            {
                "epoch": int(row["epoch"]),
                "pin": sid in pinned,
                "segment_id": sid,
                "stale": sid not in active,
                "weight": float(row["weight"]),
            }
        )

    summary = {
        "current_epoch": current_epoch,
        "effective_trim_threshold": round(threshold, 6),
        "index_total": len(events),
        "stale_skipped_total": stale_skipped,
        "trim_total": trim_total,
        "vote_accepted_total": vote_accepted,
    }

    audit_dir.mkdir(parents=True, exist_ok=True)
    dump_pretty(audit_dir / "segment_states.json", {"segments": segment_states})
    dump_pretty(audit_dir / "trim_plan.json", {"entries": trim_rows})
    dump_pretty(audit_dir / "role_votes.json", {"votes": vote_rows})
    dump_pretty(audit_dir / "index_stats.json", {"stats": stat_rows})
    dump_pretty(audit_dir / "summary.json", summary)


# ---------------------------------------------------------------------------
# DNS alias chain solver
# ---------------------------------------------------------------------------


data_dir = Path(os.environ.get("WIT_DATA_DIR", "/app/waltrim"))
audit_dir = Path(os.environ.get("WIT_AUDIT_DIR", "/app/audit"))
solve_wal_trim(data_dir, audit_dir)
PY
