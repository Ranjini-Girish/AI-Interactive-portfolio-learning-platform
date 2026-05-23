#!/usr/bin/env python3
from __future__ import annotations

from typing import Any
import json
import os
from pathlib import Path

def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))

def _items(root: Path) -> list[dict[str, Any]]:
    d = root / "items"
    rows: list[dict[str, Any]] = []
    for fp in sorted(d.glob("*.json")):
        rows.append(_load(fp))
    return rows

def run_isc(root: Path) -> dict[str, Any]:
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    day = int(pool["current_day"])
    pts = [int(x) for x in policy.get("candidate_points", [])]
    pts = sorted(set(pts))
    intervals = [(int(it["lo"]), int(it["hi"]), int(it["weight"])) for it in _items(root)]
    if not pts:
        return {
            "stab_pick.json": {"best_point": None, "cover_weight": 0, "intervals_touching": 0},
            "summary.json": {"candidates": 0, "current_day": day},
        }
    best: int | None = None
    best_cov = 10**9
    for p in pts:
        cov = 0
        for lo, hi, w in intervals:
            if lo <= p <= hi:
                cov += w
        if cov < best_cov or (cov == best_cov and best is not None and p < best):
            best_cov = cov
            best = p
        elif best is None:
            best_cov = cov
            best = p
    covered = sum(1 for lo, hi, _w in intervals if lo <= best <= hi)
    return {
        "stab_pick.json": {"best_point": best, "cover_weight": best_cov, "intervals_touching": covered},
        "summary.json": {"candidates": len(pts), "current_day": day},
    }


def main() -> None:
    root = Path(os.environ["ISC_DATA_DIR"])
    out = Path(os.environ["ISC_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_isc(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
