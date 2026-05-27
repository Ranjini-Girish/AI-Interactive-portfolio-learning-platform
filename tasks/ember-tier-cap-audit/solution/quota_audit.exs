data = System.get_env("QUOTA_DATA_DIR", "/app/quota_lab")
audit = System.get_env("QUOTA_AUDIT_DIR", "/app/audit")
File.mkdir_p!(audit)

policy = data |> Path.join("policy.json") |> File.read!() |> Jason.decode!()
events = data |> Path.join("events.json") |> File.read!() |> Jason.decode!()
day = policy["audit_day"]
order = policy["tier_order"]

caps =
  policy["tier_caps"]
  |> Enum.map(fn {k, v} -> {k, trunc(v)} end)
  |> Map.new()

caps =
  Enum.reduce(events["tier_derates"] || [], caps, fn d, acc ->
    if d["start_day"] <= day and day <= d["end_day"] do
      t = d["tier"]
      if Map.has_key?(acc, t) do
        Map.put(acc, t, div(Map.fetch!(acc, t) * d["factor_bp"], 10000))
      else
        acc
      end
    else
      acc
    end
  end)

frozen =
  (events["item_freezes"] || [])
  |> Enum.filter(fn f -> f["start_day"] <= day and day <= f["end_day"] end)
  |> Enum.map(& &1["item_id"])
  |> MapSet.new()

tier_key = fn tier ->
  idx = Enum.find_index(order, &(&1 == tier))
  if idx, do: {idx, tier}, else: {length(order), tier}
end

items =
  data
  |> Path.join("items")
  |> File.ls!()
  |> Enum.filter(&String.ends_with?(&1, ".json"))
  |> Enum.sort()
  |> Enum.map(fn f ->
    [data, "items", f] |> Path.join() |> File.read!() |> Jason.decode!()
  end)
  |> Enum.sort_by(fn it -> Tuple.append(tier_key.(it["tier"]), it["item_id"]) end)

{tier_rem, rows, sc} =
  Enum.reduce(items, {caps, [], %{"frozen" => 0, "ok" => 0, "shortfall" => 0}}, fn it, {rem, acc, counts} ->
    iid = it["item_id"]
    tier = it["tier"]
    demand = trunc(it["demand"])

    if MapSet.member?(frozen, iid) do
      row = %{"item_id" => iid, "tier" => tier, "status" => "frozen", "demand" => demand, "allocated" => 0}
      {rem, acc ++ [row], Map.update!(counts, "frozen", &(&1 + 1))}
    else
      left = Map.get(rem, tier, 0)
      alloc = min(demand, left)
      rem2 = Map.put(rem, tier, left - alloc)
      st = if alloc == demand, do: "ok", else: "shortfall"
      row = %{"item_id" => iid, "tier" => tier, "status" => st, "demand" => demand, "allocated" => alloc}
      {rem2, acc ++ [row], Map.update!(counts, st, &(&1 + 1))}
    end
  end)

touched =
  rows
  |> Enum.filter(fn r -> r["allocated"] > 0 end)
  |> Enum.map(& &1["tier"])
  |> Enum.uniq()
  |> Enum.sort()

summary = %{
  "audit_day" => day,
  "items_processed" => length(items),
  "frozen_items" => sc["frozen"],
  "status_counts" => sc,
  "tiers_touched" => touched
}

encode = fn obj ->
  Jason.encode!(obj, pretty: true) <> "\n"
end

File.write!(Path.join(audit, "allocations.json"), encode.(%{"items" => rows}))
File.write!(Path.join(audit, "summary.json"), encode.(summary))
