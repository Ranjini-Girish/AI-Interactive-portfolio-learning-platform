// @ts-nocheck
import fs from "node:fs";
import path from "node:path";

const data = process.env.QUOTA_DATA_DIR ?? "/app/quota_lab";
const audit = process.env.QUOTA_AUDIT_DIR ?? "/app/audit";
fs.mkdirSync(audit, { recursive: true });

type ItemRow = {
  item_id: string;
  tier: string;
  status: string;
  demand: number;
  allocated: number;
};

const policy = JSON.parse(
  fs.readFileSync(path.join(data, "policy.json"), "utf8")
) as { audit_day: number; tier_order: string[]; tier_caps: Record<string, number> };
const events = JSON.parse(
  fs.readFileSync(path.join(data, "events.json"), "utf8")
) as {
  tier_derates?: { tier: string; factor_bp: number; start_day: number; end_day: number }[];
  item_freezes?: { item_id: string; start_day: number; end_day: number }[];
};

const day = policy.audit_day;
const order = policy.tier_order;
const caps: Record<string, number> = {};
for (const [k, v] of Object.entries(policy.tier_caps)) caps[k] = Number(v);

for (const d of events.tier_derates ?? []) {
  if (d.start_day <= day && day <= d.end_day && caps[d.tier] !== undefined) {
    caps[d.tier] = Math.floor((caps[d.tier] * d.factor_bp) / 10000);
  }
}

const frozen = new Set(
  (events.item_freezes ?? [])
    .filter((f) => f.start_day <= day && day <= f.end_day)
    .map((f) => f.item_id)
);

const tierKey = (tier: string): [number, string] => {
  const idx = order.indexOf(tier);
  return idx >= 0 ? [idx, tier] : [order.length, tier];
};

const items = fs
  .readdirSync(path.join(data, "items"))
  .filter((f) => f.endsWith(".json"))
  .sort()
  .map((f) =>
    JSON.parse(fs.readFileSync(path.join(data, "items", f), "utf8")) as {
      item_id: string;
      tier: string;
      demand: number;
    }
  )
  .sort((a, b) => {
    const [ra, ta] = tierKey(a.tier);
    const [rb, tb] = tierKey(b.tier);
    if (ra !== rb) return ra - rb;
    if (ta !== tb) return ta.localeCompare(tb);
    return a.item_id.localeCompare(b.item_id);
  });

const tierRem = { ...caps };
const rows: ItemRow[] = [];
const sc = { frozen: 0, ok: 0, shortfall: 0 };

for (const it of items) {
  const demand = Number(it.demand);
  if (frozen.has(it.item_id)) {
    rows.push({
      item_id: it.item_id,
      tier: it.tier,
      status: "frozen",
      demand,
      allocated: 0,
    });
    sc.frozen += 1;
    continue;
  }
  const left = tierRem[it.tier] ?? 0;
  const alloc = Math.min(demand, left);
  tierRem[it.tier] = left - alloc;
  const st = alloc === demand ? "ok" : "shortfall";
  sc[st] += 1;
  rows.push({
    item_id: it.item_id,
    tier: it.tier,
    status: st,
    demand,
    allocated: alloc,
  });
}

const touched = [...new Set(rows.filter((r) => r.allocated > 0).map((r) => r.tier))].sort();
const summary = {
  audit_day: day,
  items_processed: items.length,
  frozen_items: sc.frozen,
  status_counts: sc,
  tiers_touched: touched,
};

const write = (name: string, obj: object): void => {
  fs.writeFileSync(path.join(audit, name), `${JSON.stringify(obj, null, 2)}\n`, "utf8");
};

write("allocations.json", { items: rows });
write("summary.json", summary);
