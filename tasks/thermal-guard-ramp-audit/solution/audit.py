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


def _round3(x: float) -> float:
    return float(format(x, ".3f"))


def run_tgr(root: Path) -> dict[str, Any]:
    _load(root / "domain_layout.json")
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    ramp = float(policy["ramp_per_day"])
    ceiling = float(policy["ceiling"])
    day = int(pool["current_day"])
    add = 0.0
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "delta_k":
            add += float(ev.get("value", 0.0))
    rows: list[dict[str, Any]] = []
    for it in _items(root):
        zone = str(it["zone"])
        base = float(it["base_temp"])
        guard = float(it["guard"])
        raw = base + guard + ramp * float(day) + add
        eff = raw if raw < ceiling else ceiling
        rows.append({"effective_temp": _round3(eff), "zone": zone})
    rows.sort(key=lambda r: str(r["zone"]))
    return {
        "summary.json": {
            "ceiling": ceiling,
            "day": day,
            "global_add": _round3(add),
            "zones": len(rows),
        },
        "thermal_ledger.json": {"entries": rows},
    }


def main() -> None:
    root = Path(os.environ["TGR_DATA_DIR"])
    out = Path(os.environ["TGR_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_tgr(root)
    for name, payload in payloads.items():
        (out / name).write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
