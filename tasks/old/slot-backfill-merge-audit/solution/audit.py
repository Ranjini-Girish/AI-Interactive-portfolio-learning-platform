#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _dump(p: Path, obj: Any) -> None:
    p.write_text(
        json.dumps(obj, sort_keys=True, indent=2, separators=(", ", ": "))
        + "\n",
        encoding="utf-8",
    )


def _items(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fp in sorted((root / "items").glob("item_*.json")):
        rows.append(_load(fp))
    return rows


def _lane_slack(
    policy: dict[str, Any], incidents: dict[str, Any], ledger_day: int, lane: str
) -> int:
    base = int(policy["merge_slack_days"])
    extra = 0
    for inc in incidents.get("incidents", []):
        if str(inc.get("kind")) != "widen_slack":
            continue
        if str(inc.get("lane")) != lane:
            continue
        if int(inc["start_day"]) <= ledger_day <= int(inc["end_day"]):
            extra += int(inc["extra_slack"])
    return base + extra


def _merge_lane(
    lane: str,
    items: list[dict[str, Any]],
    slack: int,
) -> list[dict[str, Any]]:
    eligible = [it for it in items if str(it["lane"]) == lane]
    eligible.sort(
        key=lambda it: (
            int(it["anchor_day"]),
            int(it["anchor_day"]) + int(it["span"]) - 1,
            str(it["slot_id"]),
            -int(it["priority"]),
            str(it["tag"]),
        )
    )
    groups: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal cur
        if cur is None:
            return
        span = int(cur["end_day"]) - int(cur["start_day"]) + 1
        groups.append(
            {
                "lane": lane,
                "slot_id": str(cur["slot_id"]),
                "start_day": int(cur["start_day"]),
                "end_day": int(cur["end_day"]),
                "span": span,
                "priority": int(cur["priority"]),
                "sources": sorted(set(map(str, cur["sources"]))),
            }
        )
        cur = None

    for it in eligible:
        if cur is None:
            cur = {
                "slot_id": str(it["slot_id"]),
                "start_day": int(it["anchor_day"]),
                "end_day": int(it["anchor_day"]) + int(it["span"]) - 1,
                "priority": int(it["priority"]),
                "sources": [str(it["tag"])],
            }
            continue
        if str(it["slot_id"]) != str(cur["slot_id"]):
            flush()
            cur = {
                "slot_id": str(it["slot_id"]),
                "start_day": int(it["anchor_day"]),
                "end_day": int(it["anchor_day"]) + int(it["span"]) - 1,
                "priority": int(it["priority"]),
                "sources": [str(it["tag"])],
            }
            continue
        gap = int(it["anchor_day"]) - int(cur["end_day"]) - 1
        if gap <= slack:
            cur["start_day"] = min(int(cur["start_day"]), int(it["anchor_day"]))
            cur["end_day"] = max(int(cur["end_day"]), int(it["anchor_day"]) + int(it["span"]) - 1)
            cur["priority"] = max(int(cur["priority"]), int(it["priority"]))
            cur["sources"].append(str(it["tag"]))
        else:
            flush()
            cur = {
                "slot_id": str(it["slot_id"]),
                "start_day": int(it["anchor_day"]),
                "end_day": int(it["anchor_day"]) + int(it["span"]) - 1,
                "priority": int(it["priority"]),
                "sources": [str(it["tag"])],
            }
    flush()
    return groups


def run_audit(data_dir: Path, audit_dir: Path) -> None:
    policy = _load(data_dir / "policy.json")
    pool = _load(data_dir / "pool_state.json")
    incidents = _load(data_dir / "incident_log.json")
    ledger_day = int(pool["ledger_day"])
    mask = int(policy["accept_band_mask"])
    lanes_rank = [str(x) for x in policy["lanes_rank"]]

    items_all = _items(data_dir)
    eligible_items = [
        it
        for it in items_all
        if ((mask >> int(it["band"])) & 1) == 1
    ]

    lane_set = sorted({str(it["lane"]) for it in eligible_items})
    groups: list[dict[str, Any]] = []
    for lane in lane_set:
        lane_items = [it for it in eligible_items if str(it["lane"]) == lane]
        slack = _lane_slack(policy, incidents, ledger_day, lane)
        groups.extend(_merge_lane(lane, lane_items, slack))

    rank_index = {lane: i for i, lane in enumerate(lanes_rank)}

    def sort_key(g: dict[str, Any]) -> tuple[int, int, str]:
        lane = str(g["lane"])
        idx = rank_index.get(lane, 10_000)
        return (idx, int(g["start_day"]), str(g["slot_id"]))

    groups.sort(key=sort_key)

    summary = {
        "eligible_items": len(eligible_items),
        "groups": len(groups),
        "ledger_day": ledger_day,
        "lanes": sorted({str(g["lane"]) for g in groups}),
    }
    audit_dir.mkdir(parents=True, exist_ok=True)
    _dump(audit_dir / "merge_report.json", {"groups": groups})
    _dump(audit_dir / "summary.json", summary)


def main() -> None:
    import os

    data = Path(os.environ["SBM_DATA_DIR"])
    audit = Path(os.environ["SBM_AUDIT_DIR"])
    run_audit(data, audit)


if __name__ == "__main__":
    main()
