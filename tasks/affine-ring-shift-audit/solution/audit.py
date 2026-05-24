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

def run_ars(root: Path) -> dict[str, Any]:
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    a = int(policy["mult_a"]) % 26
    b = int(policy["add_b"]) % 26
    rot = 0
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "rotate_key":
            rot = (rot + int(ev.get("delta", 0))) % 26
    aa = (a + rot) % 26
    bb = (b + rot) % 26
    try:
        inv_a = pow(aa, -1, 26)
    except ValueError:
        inv_a = 1
    rows: list[dict[str, Any]] = []
    for it in _items(root):
        y = int(it["cipher_value"]) % 26
        x = (inv_a * (y - bb)) % 26
        rows.append({"item_id": str(it["item_id"]), "plain_mod26": x})
    rows.sort(key=lambda r: r["item_id"])
    return {
        "plain_ring.json": {"items": rows},
        "summary.json": {"current_day": int(pool["current_day"]), "effective_rot": rot, "items": len(rows)},
    }


def main() -> None:
    root = Path(os.environ["ARS_DATA_DIR"])
    out = Path(os.environ["ARS_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_ars(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
