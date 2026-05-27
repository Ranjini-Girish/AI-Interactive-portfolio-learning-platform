#!/usr/bin/env bash
set -euo pipefail

DATA="${QUOTA_DATA_DIR:-/app/quota_lab}"
AUDIT="${QUOTA_AUDIT_DIR:-/app/audit}"
mkdir -p "$AUDIT"

python3 - "$DATA" "$AUDIT" <<'PY'
import json, os, sys
from pathlib import Path

data, audit = Path(sys.argv[1]), Path(sys.argv[2])
policy = json.loads((data / "policy.json").read_text())
events = json.loads((data / "events.json").read_text())
day = policy["audit_day"]
order = policy["tier_order"]
caps = {k: int(v) for k, v in policy["tier_caps"].items()}
for d in events.get("tier_derates", []):
    if d["start_day"] <= day <= d["end_day"] and d["tier"] in caps:
        caps[d["tier"]] = caps[d["tier"]] * d["factor_bp"] // 10000
frozen = {f["item_id"] for f in events.get("item_freezes", []) if f["start_day"] <= day <= f["end_day"]}

def tier_key(t):
    return (order.index(t), t) if t in order else (len(order), t)

items = []
for p in sorted((data / "items").glob("*.json")):
    items.append(json.loads(p.read_text()))
items.sort(key=lambda x: (tier_key(x["tier"]), x["item_id"]))

tier_rem = dict(caps)
rows, sc = [], {"frozen": 0, "ok": 0, "shortfall": 0}
for it in items:
    iid, tier, demand = it["item_id"], it["tier"], int(it["demand"])
    if iid in frozen:
        rows.append({"item_id": iid, "tier": tier, "status": "frozen", "demand": demand, "allocated": 0})
        sc["frozen"] += 1
        continue
    left = tier_rem.get(tier, 0)
    alloc = min(demand, left)
    tier_rem[tier] = left - alloc
    st = "ok" if alloc == demand else "shortfall"
    sc[st] += 1
    rows.append({"item_id": iid, "tier": tier, "status": st, "demand": demand, "allocated": alloc})

touched = sorted({r["tier"] for r in rows if r["allocated"] > 0})
summary = {
    "audit_day": day,
    "items_processed": len(items),
    "frozen_items": sc["frozen"],
    "status_counts": sc,
    "tiers_touched": touched,
}

def write(name, obj):
    (audit / name).write_text(json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n")

write("allocations.json", {"items": rows})
write("summary.json", summary)
PY
