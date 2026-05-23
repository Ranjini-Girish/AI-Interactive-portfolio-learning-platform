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

def run_lwc(root: Path) -> dict[str, Any]:
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    cap = int(policy["capacity"])
    window = int(policy["touch_window_days"])
    day = int(pool["current_day"])
    rows: list[dict[str, Any]] = []
    for it in _items(root):
        key = str(it["cache_key"])
        touches = [int(x) for x in it["touch_days"]]
        recent = [t for t in touches if day - t <= window]
        recent.sort()
        evict_score = len(recent)
        rows.append({"cache_key": key, "recent_touches": recent, "evict_score": evict_score})
    rows.sort(key=lambda r: (-r["evict_score"], r["cache_key"]))
    kept = rows[:cap]
    evicted = rows[cap:]
    kept.sort(key=lambda r: r["cache_key"])
    evicted.sort(key=lambda r: r["cache_key"])
    return {
        "lru_scores.json": {"ranked": rows},
        "cache_partition.json": {"kept": kept, "evicted": evicted},
        "summary.json": {"capacity": cap, "kept_count": len(kept), "evicted_count": len(evicted), "current_day": day},
    }


def main() -> None:
    root = Path(os.environ["LWC_DATA_DIR"])
    out = Path(os.environ["LWC_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_lwc(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
