from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> None:
    data = Path(os.environ.get("CFL_DATA_DIR", "/app/flux_lat"))
    out = Path(os.environ.get("CFL_AUDIT_DIR", "/app/audit"))
    out.mkdir(parents=True, exist_ok=True)

    policy = json.loads((data / "policy.json").read_text(encoding="utf-8"))
    pool = json.loads((data / "pool_state.json").read_text(encoding="utf-8"))
    incs = json.loads((data / "incidents.json").read_text(encoding="utf-8"))["incidents"]

    cells: dict[str, int] = {}
    for path in sorted((data / "cells").glob("*.json")):
        cell = json.loads(path.read_text(encoding="utf-8"))
        cells[str(cell["id"])] = int(cell["prior"])

    nodes: list[dict[str, object]] = []
    for path in sorted((data / "nodes").glob("*.json")):
        nodes.append(json.loads(path.read_text(encoding="utf-8")))
    nodes.sort(key=lambda n: str(n["id"]))

    by_id = {str(n["id"]): n for n in nodes}
    children: dict[str, list[str]] = {}
    for node in nodes:
        parent = node.get("parent")
        if parent is None:
            continue
        children.setdefault(str(parent), []).append(str(node["id"]))
    for key in children:
        children[key].sort()

    horizon = int(policy["horizon_day"])
    tier_mult = policy["tier_mult"]
    tier_cap = policy["tier_cap"]
    bonus = pool["bonus"]
    eff_cap = {t: int(tier_cap[t]) + int(bonus.get(t, 0)) for t in tier_cap}
    freeze_floor = int(policy["freeze_floor"])

    anchored: set[str] = set()
    frozen: set[str] = set()
    compromised_targets: list[str] = []
    for event in sorted(incs, key=lambda e: (int(e["day"]), str(e["id"]))):
        if not event.get("accepted"):
            continue
        if int(event["day"]) > horizon:
            continue
        kind = str(event["kind"])
        target = str(event["target"])
        if kind == "anchor_ok":
            anchored.add(target)
        elif kind == "freeze":
            frozen.add(target)
        elif kind == "compromise":
            compromised_targets.append(target)

    stamped: set[str] = set()

    def dfs(node_id: str) -> None:
        node = by_id.get(node_id)
        if node is None:
            return
        if node.get("shield"):
            return
        if node_id in anchored:
            return
        stamped.add(node_id)
        for child_id in children.get(node_id, []):
            dfs(child_id)

    for target in compromised_targets:
        if target in anchored:
            continue
        dfs(target)

    rows: list[dict[str, object]] = []
    sum_final = 0
    for node in nodes:
        node_id = str(node["id"])
        tier = str(node["tier"])
        base = int(node["base"])
        prior = int(cells[str(node["cell"])])
        is_anchored = node_id in anchored
        is_frozen = node_id in frozen
        compromised = node_id in stamped
        if compromised:
            raw = 0
        else:
            raw = min((base + prior) * int(tier_mult[tier]), int(eff_cap[tier]))
        final = min(raw, freeze_floor) if is_frozen else raw
        sum_final += int(final)
        rows.append(
            {
                "id": node_id,
                "tier": tier,
                "raw_score": raw,
                "final_score": final,
                "compromised": bool(compromised),
                "anchored": bool(is_anchored),
                "frozen": bool(is_frozen),
            }
        )

    rows.sort(key=lambda row: (-int(row["final_score"]), str(row["id"])))
    summary = {
        "total_nodes": len(nodes),
        "stamped": sum(1 for row in rows if row["compromised"]),
        "anchored_live": sum(1 for row in rows if row["anchored"]),
        "frozen_live": sum(1 for row in rows if row["frozen"]),
        "sum_final_scores": sum_final,
        "max_id": max(rows, key=lambda row: (int(row["final_score"]), str(row["id"])))["id"],
    }

    def dump(path: Path, payload: object) -> None:
        path.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(",", ": ")) + "\n",
            encoding="utf-8",
        )

    dump(out / "ledger.json", {"nodes": rows})
    dump(out / "summary.json", summary)


if __name__ == "__main__":
    main()
