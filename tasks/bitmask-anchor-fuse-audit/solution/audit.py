#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _items(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fp in sorted((root / "items").glob("item_*.json")):
        rows.append(_load(fp))
    return rows


def _round4(x: float) -> float:
    return float(format(x, ".4f"))


def _popcount(x: int) -> int:
    return int(x).bit_count()


def run_baf(root: Path) -> dict[str, Any]:
    _load(root / "pool_state.json")
    _load(root / "domain_layout.json")
    policy = _load(root / "policy.json")
    inc = _load(root / "incident_log.json")
    fuse = int(policy["fuse_mask"])
    base_or = int(policy["base_or"])
    tier_factor = float(policy["tier_factor"])
    xor_acc = 0
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "xor_acc":
            xor_acc ^= int(ev.get("value", 0))
    rows: list[dict[str, Any]] = []
    total = 0.0
    for it in _items(root):
        ident = str(it["id"])
        mask = int(it["mask"])
        scale = float(it["scale"])
        eff = ((mask ^ xor_acc) & fuse) | base_or
        score = _popcount(eff) * scale * tier_factor
        score_r = _round4(score)
        total += score_r
        rows.append({"effective_mask": int(eff), "id": ident, "score": score_r})
    rows.sort(key=lambda r: str(r["id"]))
    return {
        "fuse_ledger.json": {"entries": rows},
        "summary.json": {
            "entries": len(rows),
            "total_score": _round4(total),
            "xor_acc": int(xor_acc),
        },
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
