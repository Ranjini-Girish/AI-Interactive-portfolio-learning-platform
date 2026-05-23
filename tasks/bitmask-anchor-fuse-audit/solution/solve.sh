#!/bin/bash
set -euo pipefail

export BAF_DATA_DIR="${BAF_DATA_DIR:-}"
export BAF_AUDIT_DIR="${BAF_AUDIT_DIR:-}"
if [ -z "${BAF_DATA_DIR}" ]; then export BAF_DATA_DIR="/app/baf_lat"; fi
if [ -z "${BAF_AUDIT_DIR}" ]; then export BAF_AUDIT_DIR="/app/audit"; fi

python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _round4(x: float) -> float:
    return float(format(x, ".4f"))


def _popcount(x: int) -> int:
    return int(x).bit_count()


def _items(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fp in sorted((root / "items").glob("item_*.json")):
        rows.append(_load(fp))
    return rows


def run_baf(root: Path) -> dict[str, Any]:
    _load(root / "pool_state.json")
    layout = _load(root / "domain_layout.json")
    policy = _load(root / "policy.json")
    inc = _load(root / "incident_log.json")
    a = _load(root / "anchors" / "a.json")
    b = _load(root / "anchors" / "b.json")

    or_a = int(a.get("or_mask", 0)) & 0xFF
    or_b = int(b.get("or_mask", 0)) & 0xFF
    anchor_lane = (or_a ^ or_b) & 0xFF
    anchor_or = (or_a | or_b) & 0xFF

    xor_acc = 0
    fuse_active = int(policy["fuse_mask"]) & 0xFF
    tier_live = float(policy["tier_factor"])
    base_or = int(policy["base_or"]) & 0xFF

    segments = layout.get("segments", {})
    if not isinstance(segments, dict):
        segments = {}

    for ev in inc.get("events", []):
        if not ev.get("accepted"):
            continue
        kind = str(ev.get("kind", ""))
        v_raw = ev.get("value", 0)
        try:
            v = int(v_raw)
        except (TypeError, ValueError):
            v = 0
        v &= 0xFF
        if kind == "xor_acc":
            xor_acc = (xor_acc ^ v) & 0xFF
        elif kind == "fuse_xor":
            fuse_active = (fuse_active ^ v) & 0xFF
        elif kind == "tier_skew":
            tier_live = _round4(tier_live * (1.0 + (v / 256.0)))

    rows: list[dict[str, Any]] = []
    total = 0.0
    for it in _items(root):
        ident = str(it["id"])
        mask = int(it["mask"]) & 0xFF
        scale = float(it["scale"])
        segment = str(it.get("segment", "core"))
        seg_obj = segments.get(segment, {})
        if not isinstance(seg_obj, dict):
            seg_obj = {}
        lane_xor = int(seg_obj.get("lane_xor", 0)) & 0xFF
        lane = (anchor_lane ^ lane_xor) & 0xFF
        blended = ((mask ^ xor_acc) & lane) & 0xFF
        eff = (((blended & fuse_active) | base_or) | anchor_or) & 0xFF
        score = _round4(_popcount(eff) * scale * tier_live)
        total += score
        rows.append(
            {
                "blended": int(blended),
                "effective_mask": int(eff),
                "id": ident,
                "lane": int(lane),
                "score": score,
            }
        )

    rows.sort(key=lambda r: (str(r["id"]), int(r["effective_mask"])))

    state = {
        "anchor_lane": int(anchor_lane),
        "anchor_or": int(anchor_or),
        "fuse_mask": int(fuse_active),
        "tier_live": _round4(tier_live),
        "xor_acc": int(xor_acc),
    }

    summary = {
        "anchor_lane": int(anchor_lane),
        "anchor_or": int(anchor_or),
        "entries": len(rows),
        "fuse_mask": int(fuse_active),
        "tier_live": _round4(tier_live),
        "total_score": _round4(total),
        "xor_acc": int(xor_acc),
    }

    return {
        "fuse_ledger.json": {"entries": rows},
        "summary.json": summary,
        "incident_state.json": state,
    }


def main() -> None:
    root = Path(os.environ["BAF_DATA_DIR"])
    out = Path(os.environ["BAF_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_baf(root)
    for name, payload in payloads.items():
        (out / name).write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
PY
