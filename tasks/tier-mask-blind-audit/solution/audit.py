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

def run_tmb(root: Path) -> dict[str, Any]:
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    tier_bits = {str(k): int(v) for k, v in policy["tier_bits"].items()}
    disabled_bits = 0
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "disable_tier":
            t = str(ev["tier"])
            disabled_bits |= tier_bits.get(t, 0)
    rows: list[dict[str, Any]] = []
    pop = 0
    for it in _items(root):
        sid = str(it["scope_id"])
        tier = str(it["tier"])
        base = int(it["base_mask"])
        add = tier_bits.get(tier, 0)
        eff = (base | add) & ~disabled_bits
        c = int(eff).bit_count()
        pop += c
        rows.append({"scope_id": sid, "tier": tier, "effective_mask": eff, "popcount": c})
    rows.sort(key=lambda r: r["scope_id"])
    return {
        "mask_rows.json": {"scopes": rows},
        "summary.json": {
            "current_day": int(pool["current_day"]),
            "scopes": len(rows),
            "popcount_sum": pop,
            "disabled_bits": disabled_bits,
        },
    }


def main() -> None:
    root = Path(os.environ["TMB_DATA_DIR"])
    out = Path(os.environ["TMB_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_tmb(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
