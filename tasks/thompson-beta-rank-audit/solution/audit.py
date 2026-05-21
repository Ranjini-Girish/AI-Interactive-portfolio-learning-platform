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

def run_tbr(root: Path) -> dict[str, Any]:
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    wins: dict[str, int] = {}
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "observe_win":
            aid = str(ev["arm_id"])
            wins[aid] = wins.get(aid, 0) + 1
    rows: list[dict[str, Any]] = []
    for it in _items(root):
        aid = str(it["arm_id"])
        s = int(it["successes"]) + wins.get(aid, 0)
        f = int(it["failures"])
        den = s + f + 2
        score = (s + 1) * 1_000_000 // den
        rows.append({"arm_id": aid, "successes_effective": s, "failures": f, "score": score})
    rows.sort(key=lambda r: (-r["score"], r["arm_id"]))
    order = [r["arm_id"] for r in rows]
    return {
        "arm_rank.json": {"ranked": rows, "order": order},
        "summary.json": {"arms": len(rows), "current_day": int(pool["current_day"])},
    }


def main() -> None:
    root = Path(os.environ["TBR_DATA_DIR"])
    out = Path(os.environ["TBR_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_tbr(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
