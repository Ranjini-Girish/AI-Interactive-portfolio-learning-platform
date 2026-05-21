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

def run_tpm(root: Path) -> dict[str, Any]:
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    cap_mul = float(policy.get("burst_cap_multiplier", 1.0))
    day = int(pool["current_day"])
    bonus: dict[str, float] = {}
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "refill_host":
            bonus[str(ev["host_id"])] = float(ev.get("tokens", 0.0))
    rows: list[dict[str, Any]] = []
    for it in _items(root):
        hid = str(it["host_id"])
        rate = float(it["tokens_per_day"])
        cap = float(it["bucket_cap"]) * cap_mul
        fill = min(cap, float(it["starting_tokens"]) + rate * day + bonus.get(hid, 0.0))
        rows.append({"host_id": hid, "effective_tokens": round(fill, 4), "capped_at": cap})
    rows.sort(key=lambda r: r["host_id"])
    return {
        "pail_levels.json": {"hosts": rows},
        "summary.json": {"hosts": len(rows), "current_day": day},
    }


def main() -> None:
    root = Path(os.environ["TPM_DATA_DIR"])
    out = Path(os.environ["TPM_AUDIT_DIR"])
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
