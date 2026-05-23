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

def run_clf(root: Path) -> dict[str, Any]:
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    floors = {str(k): float(v) for k, v in policy["floors"].items()}
    grants: dict[str, float] = {}
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "credit_grant":
            uid = str(ev["user_id"])
            grants[uid] = grants.get(uid, 0.0) + float(ev.get("amount", 0.0))
    day = int(pool["current_day"])
    rows: list[dict[str, Any]] = []
    for it in _items(root):
        uid = str(it["user_id"])
        cls = str(it["user_class"])
        daily = float(it["daily_cred"])
        spent = float(it["spent"])
        raw = daily * day - spent + grants.get(uid, 0.0)
        floor = floors.get(cls, 0.0)
        bal = max(raw, floor)
        rows.append({"user_id": uid, "user_class": cls, "balance": round(bal, 4), "floor_hit": raw <= floor})
    rows.sort(key=lambda r: r["user_id"])
    return {
        "cred_ledger.json": {"users": rows},
        "summary.json": {"users": len(rows), "current_day": day},
    }


def main() -> None:
    root = Path(os.environ["CLF_DATA_DIR"])
    out = Path(os.environ["CLF_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_clf(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
