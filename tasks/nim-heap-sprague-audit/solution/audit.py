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

def run_nhs(root: Path) -> dict[str, Any]:
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    misere = bool(policy.get("misere", False))
    heaps = [int(it["stones"]) for it in _items(root)]
    x = 0
    for h in heaps:
        x ^= h
    if misere:
        verdict = "P2_wins" if x == 0 else "P1_wins"
    else:
        verdict = "P1_wins" if x != 0 else "P2_wins"
    return {
        "nim_report.json": {
            "heap_sizes": sorted(heaps),
            "nim_sum": x,
            "misere": misere,
            "verdict_next_player": verdict,
        },
        "summary.json": {
            "heaps_count": len(heaps),
            "current_day": int(pool["current_day"]),
        },
    }


def main() -> None:
    root = Path(os.environ["NHS_DATA_DIR"])
    out = Path(os.environ["NHS_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_nhs(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
