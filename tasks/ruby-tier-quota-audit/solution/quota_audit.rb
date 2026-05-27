#!/usr/bin/env ruby
# frozen_string_literal: true

require "json"
require "set"

def tier_key(tier, order)
  idx = order.index(tier)
  idx.nil? ? [order.length, tier] : [idx, tier]
end

data = ENV.fetch("QUOTA_DATA_DIR", "/app/quota_lab")
audit = ENV.fetch("QUOTA_AUDIT_DIR", "/app/audit")
Dir.mkdir(audit) unless Dir.exist?(audit)

policy = JSON.parse(File.read(File.join(data, "policy.json")))
events = JSON.parse(File.read(File.join(data, "events.json")))
day = policy["audit_day"]
order = policy["tier_order"]
caps = policy["tier_caps"].transform_values(&:to_i)

(events["tier_derates"] || []).each do |d|
  next unless d["start_day"] <= day && day <= d["end_day"]

  t = d["tier"]
  caps[t] = caps[t] * d["factor_bp"] / 10000 if caps.key?(t)
end

frozen = Set.new
(events["item_freezes"] || []).each do |f|
  frozen << f["item_id"] if f["start_day"] <= day && day <= f["end_day"]
end

items = Dir.children(File.join(data, "items")).sort.filter_map do |fname|
  next unless fname.end_with?(".json")

  JSON.parse(File.read(File.join(data, "items", fname)))
end
items.sort_by! { |it| tier_key(it["tier"], order) + [it["item_id"]] }

tier_rem = caps.dup
rows = []
sc = { "frozen" => 0, "ok" => 0, "shortfall" => 0 }

items.each do |it|
  iid = it["item_id"]
  tier = it["tier"]
  demand = it["demand"].to_i
  if frozen.include?(iid)
    rows << { "item_id" => iid, "tier" => tier, "status" => "frozen", "demand" => demand, "allocated" => 0 }
    sc["frozen"] += 1
    next
  end
  left = tier_rem.fetch(tier, 0)
  alloc = [demand, left].min
  tier_rem[tier] = left - alloc
  st = alloc == demand ? "ok" : "shortfall"
  sc[st] += 1
  rows << { "item_id" => iid, "tier" => tier, "status" => st, "demand" => demand, "allocated" => alloc }
end

touched = rows.filter_map { |r| r["tier"] if r["allocated"].positive? }.uniq.sort
summary = {
  "audit_day" => day,
  "items_processed" => items.length,
  "frozen_items" => sc["frozen"],
  "status_counts" => sc,
  "tiers_touched" => touched,
}

def write_json(path, obj)
  File.write(path, JSON.pretty_generate(obj) + "\n")
end

write_json(File.join(audit, "allocations.json"), { "items" => rows })
write_json(File.join(audit, "summary.json"), summary)
