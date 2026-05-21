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

def run_rbm(root: Path) -> dict[str, Any]:
    pool = _load(root / "pool_state.json")
    day = int(pool["current_day"])
    runs: list[dict[str, Any]] = []
    for it in _items(root):
        ch = str(it["symbol"])
        n = int(it["run_length"])
        tier = int(it["tier"])
        runs.append({"symbol": ch, "run_length": n, "tier": tier, "burst_id": str(it["burst_id"])})
    runs.sort(key=lambda r: (r["tier"], r["symbol"], r["burst_id"]))
    merged: list[dict[str, Any]] = []
    for r in runs:
        if merged and merged[-1]["symbol"] == r["symbol"] and merged[-1]["tier"] == r["tier"]:
            merged[-1]["run_length"] += r["run_length"]
            merged[-1]["sources"].append(r["burst_id"])
        else:
            merged.append(
                {
                    "symbol": r["symbol"],
                    "tier": r["tier"],
                    "run_length": r["run_length"],
                    "sources": [r["burst_id"]],
                }
            )
    return {
        "rle_merge.json": {"runs": merged},
        "summary.json": {"runs_in": len(runs), "runs_out": len(merged), "current_day": day},
    }


def main() -> None:
    root = Path(os.environ["RBM_DATA_DIR"])
    out = Path(os.environ["RBM_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_rbm(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
