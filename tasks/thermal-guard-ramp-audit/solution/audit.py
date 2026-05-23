#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from decimal import ROUND_HALF_EVEN, Decimal
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
    d = Decimal(str(float(x))).quantize(Decimal("0.001"), rounding=ROUND_HALF_EVEN)
    return float(d)


def run_tgr(root: Path) -> dict[str, Any]:
    _load(root / "domain_layout.json")
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    ramp = float(policy["ramp_per_day"])
    ceiling = float(policy["ceiling"])
    day = int(pool["current_day"])

    global_add = 0.0
    ramp_shave_total = 0.0
    zone_bias: dict[str, float] = {}
    suppressed_zones: set[str] = set()
    guard_suppress_events = 0
    zone_bias_events = 0

    for ev in inc.get("events", []):
        if not ev.get("accepted"):
            continue
        kind = ev.get("kind")
        if kind == "delta_k":
            global_add += float(ev.get("value", 0.0))
        elif kind == "ramp_shave":
            ramp_shave_total += float(ev.get("amount", 0.0))
        elif kind == "zone_bias":
            zone_bias_events += 1
            z = ev.get("zone")
            if not z:
                continue
            z = str(z)
            b = float(ev.get("bias", 0.0))
            zone_bias[z] = zone_bias.get(z, 0.0) + b
        elif kind == "guard_suppress":
            z = ev.get("zone")
            if not z:
                continue
            z = str(z)
            if z not in suppressed_zones:
                suppressed_zones.add(z)
                guard_suppress_events += 1
        else:
            continue

    ramp_linear = ramp * float(day)
    ramp_effective_raw = ramp_linear - ramp_shave_total
    if ramp_effective_raw < 0.0:
        ramp_effective_raw = 0.0

    item_rows = _items(root)
    rows: list[dict[str, Any]] = []
    for it in item_rows:
        zone = str(it["zone"])
        base = float(it["base_temp"])
        guard = float(it["guard"])
        g_use = 0.0 if zone in suppressed_zones else guard
        b = float(zone_bias.get(zone, 0.0))
        raw = base + g_use + ramp_effective_raw + global_add + b
        eff = raw if raw < ceiling else ceiling
        rows.append({"effective_temp": _round3(eff), "zone": zone})
    rows.sort(key=lambda r: str(r["zone"]))

    return {
        "summary.json": {
            "ceiling": ceiling,
            "day": day,
            "global_add": _round3(global_add),
            "guard_suppress_events": guard_suppress_events,
            "ramp_effective": _round3(ramp_effective_raw),
            "ramp_shave_total": _round3(ramp_shave_total),
            "zone_bias_events": zone_bias_events,
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
