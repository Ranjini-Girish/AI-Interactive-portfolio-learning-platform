#!/usr/bin/env python3
import json
import os
from pathlib import Path


def tier_key(tier: str, order: list[str]) -> tuple[int, str]:
    if tier in order:
        return (order.index(tier), tier)
    return (len(order), tier)


def main() -> None:
    data = Path(os.environ.get("QUOTA_DATA_DIR", "/app/quota_lab"))
    audit = Path(os.environ.get("QUOTA_AUDIT_DIR", "/app/audit"))
    audit.mkdir(parents=True, exist_ok=True)

    policy = json.loads((data / "policy.json").read_text(encoding="utf-8"))
    events = json.loads((data / "events.json").read_text(encoding="utf-8"))
    day = int(policy["audit_day"])
    order = list(policy["tier_order"])
    caps = {k: int(v) for k, v in policy["tier_caps"].items()}

    for derate in events.get("tier_derates", []):
        if int(derate["start_day"]) <= day <= int(derate["end_day"]):
            t = derate["tier"]
            if t in caps:
                caps[t] = caps[t] * int(derate["factor_bp"]) // 10000

    frozen: set[str] = set()
    for fr in events.get("item_freezes", []):
        if int(fr["start_day"]) <= day <= int(fr["end_day"]):
            frozen.add(fr["item_id"])

    items: list[dict] = []
    for path in sorted((data / "items").glob("*.json")):
        items.append(json.loads(path.read_text(encoding="utf-8")))
    items.sort(key=lambda x: (tier_key(x["tier"], order), x["item_id"]))

    tier_rem = dict(caps)
    rows: list[dict] = []
    status_counts = {"frozen": 0, "ok": 0, "shortfall": 0}

    for it in items:
        iid, tier, demand = it["item_id"], it["tier"], int(it["demand"])
        if iid in frozen:
            rows.append(
                {
                    "item_id": iid,
                    "tier": tier,
                    "status": "frozen",
                    "demand": demand,
                    "allocated": 0,
                }
            )
            status_counts["frozen"] += 1
            continue
        left = tier_rem.get(tier, 0)
        alloc = min(demand, left)
        tier_rem[tier] = left - alloc
        st = "ok" if alloc == demand else "shortfall"
        status_counts[st] += 1
        rows.append(
            {
                "item_id": iid,
                "tier": tier,
                "status": st,
                "demand": demand,
                "allocated": alloc,
            }
        )

    allocations = {"items": rows}
    summary = {
        "audit_day": day,
        "items_processed": len(items),
        "frozen_items": status_counts["frozen"],
        "status_counts": status_counts,
        "tiers_touched": sorted({r["tier"] for r in rows if r["allocated"] > 0}),
    }

    def write(name: str, obj: dict) -> None:
        text = json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        (audit / name).write_text(text, encoding="utf-8")

    write("allocations.json", allocations)
    write("summary.json", summary)


if __name__ == "__main__":
    main()
