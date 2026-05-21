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

def run_wrm(root: Path) -> dict[str, Any]:
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    gap = int(policy["merge_gap_days"])
    rows = sorted(_items(root), key=lambda r: (int(r["day"]), str(r["row_id"])))
    merged: list[dict[str, Any]] = []
    cur: list[dict[str, Any]] = []
    last_day: int | None = None

    def flush() -> None:
        nonlocal cur, merged, last_day
        if not cur:
            return
        merged.append(
            {
                "start_day": int(cur[0]["day"]),
                "end_day": int(cur[-1]["day"]),
                "count": len(cur),
                "row_ids": sorted({str(x["row_id"]) for x in cur}),
            }
        )
        cur = []
        last_day = None

    for r in rows:
        if not r.get("is_reset"):
            flush()
            continue
        d = int(r["day"])
        if cur and last_day is not None and d - last_day > gap:
            flush()
        cur.append(r)
        last_day = d
    flush()
    return {
        "merged_resets.json": {"segments": merged},
        "summary.json": {"segments": len(merged), "current_day": int(pool["current_day"])},
    }


def main() -> None:
    root = Path(os.environ["WRM_DATA_DIR"])
    out = Path(os.environ["WRM_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_wrm(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
