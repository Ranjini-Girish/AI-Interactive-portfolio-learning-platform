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

def run_zen(root: Path) -> dict[str, Any]:
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    weights = {str(k): int(v) for k, v in policy["weights"].items()}
    banned: set[str] = set()
    for ev in inc.get("events", []):
        if ev.get("accepted") and ev.get("kind") == "ban_feature":
            banned.add(str(ev["feature"]))
    pieces: list[dict[str, Any]] = []
    for it in _items(root):
        pid = str(it["piece_id"])
        feats = {str(k): int(v) for k, v in it["features"].items()}
        score = 0
        for k, w in weights.items():
            if k in banned:
                continue
            score += w * feats.get(k, 0)
        pieces.append({"piece_id": pid, "score": score})
    pieces.sort(key=lambda r: (-r["score"], r["piece_id"]))
    return {
        "piece_scores.json": {"pieces": pieces},
        "summary.json": {"pieces": len(pieces), "current_day": int(pool["current_day"])},
    }


def main() -> None:
    root = Path(os.environ["ZEN_DATA_DIR"])
    out = Path(os.environ["ZEN_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_zen(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
