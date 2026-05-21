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

def run_rbs(root: Path) -> dict[str, Any]:
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    n = int(policy["num_buckets"])
    cap = int(policy["per_bucket_cap"])
    bump: dict[int, int] = {}
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "mass_nudge_bucket":
            b = int(ev["bucket"])
            bump[b] = bump.get(b, 0) + int(ev.get("delta", 0))
    totals = [0 for _ in range(n)]
    rows: list[dict[str, Any]] = []
    for it in _items(root):
        rid = str(it["record_id"])
        key = int(it["key"])
        mass = int(it["mass"])
        b = key % n
        mass2 = mass + bump.get(b, 0)
        totals[b] += mass2
        rows.append({"record_id": rid, "key": key, "bucket": b, "mass_effective": mass2})
    rows.sort(key=lambda r: (r["bucket"], r["record_id"]))
    spill = sum(max(0, totals[i] - cap) for i in range(n))
    buckets = [
        {"bucket": i, "total_mass": totals[i], "spill": max(0, totals[i] - cap)} for i in range(n)
    ]
    return {
        "bucket_fill.json": {"rows": rows, "buckets": buckets, "spill_total": spill},
        "summary.json": {"buckets": n, "cap": cap, "current_day": int(pool["current_day"])},
    }


def main() -> None:
    root = Path(os.environ["RBS_DATA_DIR"])
    out = Path(os.environ["RBS_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_rbs(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
