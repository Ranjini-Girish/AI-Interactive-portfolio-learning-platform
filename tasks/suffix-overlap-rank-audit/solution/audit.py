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

def run_sor(root: Path) -> dict[str, Any]:
    pool = _load(root / "pool_state.json")
    strings = [(str(it["id"]), str(it["text"])) for it in _items(root)]
    strings.sort(key=lambda t: t[0])
    scores: dict[str, int] = {sid: len(tx) for sid, tx in strings}
    best_id = max(scores.keys(), key=lambda sid: (scores[sid], sid))
    overlaps: list[dict[str, Any]] = []
    for i, (a, sa) in enumerate(strings):
        for b, sb in strings[i + 1 :]:
            a_ends_b0 = sa.endswith(sb[:1]) and len(sb) > 1
            b_ends_a0 = sb.endswith(sa[:1]) and len(sa) > 1
            if a_ends_b0 or b_ends_a0:
                overlaps.append({"pair": sorted([a, b]), "overlap_len": 1})
    overlaps.sort(key=lambda r: (r["pair"][0], r["pair"][1]))
    return {
        "suffix_rank.json": {"best_id": best_id, "best_score": scores[best_id], "edge_overlaps": overlaps},
        "summary.json": {"strings": len(strings), "current_day": int(pool["current_day"])},
    }


def main() -> None:
    root = Path(os.environ["SOR_DATA_DIR"])
    out = Path(os.environ["SOR_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_sor(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
