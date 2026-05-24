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

def run_lep(root: Path) -> dict[str, Any]:
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    pruned: set[str] = set()
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "prune_pkg":
            pruned.add(str(ev["pkg"]))
    edges: list[dict[str, Any]] = []
    for it in _items(root):
        pkg = str(it["pkg"])
        if pkg in pruned:
            continue
        edges.append({"edge_id": str(it["edge_id"]), "pkg": pkg, "version": str(it["version"])})
    edges.sort(key=lambda e: (e["pkg"], e["version"], e["edge_id"]))
    return {
        "lock_edges.json": {"edges": edges},
        "summary.json": {"edges_kept": len(edges), "current_day": int(pool["current_day"])},
    }


def main() -> None:
    root = Path(os.environ["LEP_DATA_DIR"])
    out = Path(os.environ["LEP_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_lep(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
