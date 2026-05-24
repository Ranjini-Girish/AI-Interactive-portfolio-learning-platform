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

def run_pbc(root: Path) -> dict[str, Any]:
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    flips: dict[str, int] = {}
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "flip_edge":
            eid = str(ev["edge_id"])
            flips[eid] = flips.get(eid, 0) + 1
    edges: list[tuple[str, str, int]] = []
    xor_sum = 0
    for it in _items(root):
        eid = str(it["edge_id"])
        u = str(it["u"])
        v = str(it["v"])
        par = int(it.get("parity", 0)) ^ (flips.get(eid, 0) % 2)
        xor_sum ^= par
        edges.append((u, v, par))
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            if ra < rb:
                parent[rb] = ra
            else:
                parent[ra] = rb

    for u, v, _p in edges:
        union(u, v)
    roots = sorted({find(n) for n in parent.keys()})
    comps: dict[str, list[str]] = {r: [] for r in roots}
    for n in sorted(parent.keys()):
        comps[find(n)].append(n)
    for r in comps:
        comps[r].sort()
    comp_rows = [{"root": r, "members": comps[r]} for r in sorted(comps.keys())]
    return {
        "bridge_parity.json": {"components": comp_rows},
        "summary.json": {
            "edge_count": len(edges),
            "xor_all_edges": xor_sum,
            "components": len(comp_rows),
            "current_day": int(pool["current_day"]),
        },
    }


def main() -> None:
    root = Path(os.environ["PBC_DATA_DIR"])
    out = Path(os.environ["PBC_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_pbc(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
