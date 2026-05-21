#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from collections import defaultdict
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

_Q4 = Decimal("0.0001")


def _d(x: object) -> Decimal:
    return Decimal(str(x))


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _items(root: Path) -> list[dict[str, Any]]:
    d = root / "items"
    rows: list[dict[str, Any]] = []
    for fp in sorted(d.glob("*.json")):
        rows.append(_load(fp))
    return rows


def _quantize4(v: Decimal) -> float:
    return float(v.quantize(_Q4, rounding=ROUND_HALF_EVEN))


def run_tpm(root: Path) -> dict[str, Any]:
    for rel in ("anchors/a.json", "anchors/b.json", "ancillary/x.json"):
        _load(root / rel)

    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    cap_mul = _d(policy.get("burst_cap_multiplier", 1.0))
    day = _d(int(pool["current_day"]))
    bonus: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "refill_host":
            bonus[str(ev["host_id"])] += _d(ev.get("tokens", 0.0))

    rows: list[dict[str, Any]] = []
    for it in _items(root):
        hid = str(it["host_id"])
        rate = _d(it["tokens_per_day"])
        cap = _d(it["bucket_cap"]) * cap_mul
        raw = _d(it["starting_tokens"]) + rate * day + bonus.get(hid, Decimal(0))
        fill = min(cap, raw)
        rows.append(
            {
                "host_id": hid,
                "effective_tokens": _quantize4(fill),
                "capped_at": _quantize4(cap),
            }
        )
    rows.sort(key=lambda r: r["host_id"])
    return {
        "pail_levels.json": {"hosts": rows},
        "summary.json": {"hosts": len(rows), "current_day": int(day)},
    }


def _env_path(name: str, default: str) -> Path:
    raw = os.environ.get(name, "")
    stripped = raw.strip()
    return Path(stripped if stripped else default)


def main() -> None:
    root = _env_path("TPM_DATA_DIR", "/app/tpm_lat")
    out = _env_path("TPM_AUDIT_DIR", "/app/audit")
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_tpm(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
