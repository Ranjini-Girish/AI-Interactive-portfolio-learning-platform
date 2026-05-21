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

def run_ifg(root: Path) -> dict[str, Any]:
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    skew: dict[str, int] = {}
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "flow_skew":
            fid = str(ev["flow_id"])
            skew[fid] = skew.get(fid, 0) + int(ev.get("delta", 0))
    flows: dict[str, list[int]] = {}
    for it in _items(root):
        fid = str(it["flow_id"])
        seq = int(it["seq"]) + skew.get(fid, 0)
        flows.setdefault(fid, []).append(seq)
    out: list[dict[str, Any]] = []
    for fid in sorted(flows.keys()):
        xs = sorted(flows[fid])
        if len(xs) < 2:
            ming = None
        else:
            ming = min(xs[i + 1] - xs[i] for i in range(len(xs) - 1))
        out.append({"flow_id": fid, "sorted_seq": xs, "min_gap": ming})
    return {
        "flow_gaps.json": {"flows": out},
        "summary.json": {"flows": len(out), "current_day": int(pool["current_day"])},
    }


def main() -> None:
    root = Path(os.environ["IFG_DATA_DIR"])
    out = Path(os.environ["IFG_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_ifg(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
