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


def _round4(x: float) -> float:
    return float(format(x, ".4f"))


def run_qdw(root: Path) -> dict[str, Any]:
    _load(root / "pool_state.json")
    _load(root / "domain_layout.json")
    policy = _load(root / "policy.json")
    inc = _load(root / "incident_log.json")
    window = int(policy["window"])
    bump = 0
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "window_bump":
            bump += int(ev.get("delta", 0))
    window_eff = float(window + bump)
    last: dict[str, float] = {}
    entries: list[dict[str, Any]] = []
    total_w = 0.0
    suppressed = 0
    for it in _items(root):
        seq = int(it["seq"])
        key = str(it["key"])
        ts = float(it["ts"])
        weight = float(it["weight"])
        prev = last.get(key)
        if prev is not None and ts - prev <= window_eff:
            suppressed += 1
            entries.append(
                {
                    "key": key,
                    "seq": seq,
                    "suppressed": True,
                    "ts": ts,
                    "weight_applied": _round4(0.0),
                }
            )
            continue
        total_w += weight
        last[key] = ts
        entries.append(
            {
                "key": key,
                "seq": seq,
                "suppressed": False,
                "ts": ts,
                "weight_applied": _round4(weight),
            }
        )
    entries.sort(key=lambda r: (int(r["seq"]), str(r["key"])))
    return {
        "dedupe_ledger.json": {"entries": entries},
        "summary.json": {
            "entries": len(entries),
            "suppressed": suppressed,
            "total_weight": _round4(total_w),
            "window_effective": window_eff,
        },
    }


def main() -> None:
    root = Path(os.environ["QDW_DATA_DIR"])
    out = Path(os.environ["QDW_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_qdw(root)
    for name, payload in payloads.items():
        (out / name).write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
