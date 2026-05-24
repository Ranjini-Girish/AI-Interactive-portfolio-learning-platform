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

def run_bsp(root: Path) -> dict[str, Any]:
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    nudge: dict[str, int] = {}
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "nudge_beam":
            bid = str(ev["beam_id"])
            nudge[bid] = (nudge.get(bid, 0) + int(ev.get("delta_deg", 0))) % 360
    num = 0
    den = 0
    beams: list[dict[str, Any]] = []
    for it in _items(root):
        bid = str(it["beam_id"])
        ph = (int(it["phase_deg"]) + nudge.get(bid, 0)) % 360
        w = int(it["weight"])
        num += ph * w
        den += w
        beams.append({"beam_id": bid, "phase_effective": ph, "weight": w})
    beams.sort(key=lambda r: r["beam_id"])
    combined = (num // den) % 360 if den else 0
    return {
        "beam_combine.json": {"beams": beams, "combined_phase": combined},
        "summary.json": {"beams": len(beams), "current_day": int(pool["current_day"])},
    }


def main() -> None:
    root = Path(os.environ["BSP_DATA_DIR"])
    out = Path(os.environ["BSP_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_bsp(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
