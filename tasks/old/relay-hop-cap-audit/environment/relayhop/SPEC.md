# Relay hop capacity audit (normative)

All JSON on disk is UTF-8. Emit UTF-8 JSON under the audit directory with two-space indentation, sorted object keys, ASCII-only strings, and a single trailing newline after the closing brace. Arrays use the ordering rules below.

## Inputs

Read `policy.json`, `incidents.json`, every `hops/*.json`, every `flows/*.json`, and every `anchors/*.txt` under the data directory. Anchor files are evidence only; they do not change numeric outcomes but their SHA-256 digests are pinned by the verifier.

## Policy object

Required keys:

- `epochs` (array of int, length >= 1, strictly ascending): epoch ids that must be processed in ascending order.
- `carry_max` (int, >= 0): upper bound on how many unused bytes may roll from the end of one epoch into the next for a hop.
- `hops_order` (array of string, non-empty): every hop id that appears in hop fixtures must appear exactly once; this is the iteration order for ledger rows and for per-epoch hop bookkeeping.

## Hop object

Each `hops/*.json` file contains one object with:

- `hop_id` (string, non-empty, unique across hop files)
- `base_cap` (int, > 0): baseline per-epoch byte budget for that hop before incident deltas.

## Flow object

Each `flows/*.json` file contains one object with:

- `flow_id` (string, non-empty, unique across flow files)
- `epoch` (int): must equal one entry in `policy.epochs`
- `hop_id` (string): must match a hop id from hop fixtures
- `bytes` (int, > 0): requested admission size

## Incident objects

`incidents.json` holds `{ "incidents": [ ... ] }`. Each incident has `kind` in `noop`, `cap_add`, `halt_hop`, `resume_hop`.

- `noop`: no numeric effect; the kind string still appears in `summary.incidents_applied`.
- `cap_add`: fields `epoch` (int), `hop_id` (string), `delta` (int, > 0). Apply in array order at the **start** of that epoch before any flow for that epoch is evaluated. Each application adds `delta` to `delta_acc[hop_id]` for the remainder of the run.
- `halt_hop`: fields `epoch` (int), `hop_id` (string). At the start of that epoch, mark the hop halted, force its carry bucket to zero before flow processing begins, and treat its cap core as zero for that epoch's flows.
- `resume_hop`: fields `epoch` (int), `hop_id` (string). At the start of that epoch, clear halted for the hop and set its carry bucket to zero before flow processing begins.

If multiple incidents target the same epoch, apply them in file order.

## Flow processing

For each epoch value `e` taken from `policy.epochs` in ascending order:

1. Apply every incident whose `epoch` equals `e` in array order, mutating halted flags, carry buckets, and the running `delta_acc[hop]` map. `delta_acc` starts at zero for every hop before the first epoch and accumulates across the whole run; each `cap_add` adds its `delta` to `delta_acc[hop_id]` when that incident is applied.
2. For each hop `h` in `policy.hops_order`, compute `cap_core(h) = 0` when `halted[h]` is true, otherwise `cap_core(h) = max(1, base_cap[h] + delta_acc[h])`.
3. Let `carry_in[h]` be the hop's carry bucket after step 1 (incidents may have zeroed it). Define `budget(h) = cap_core(h) + carry_in[h]`.
4. Initialise `used[h] = 0` for every hop in `hops_order`.
5. Collect every flow whose `epoch` equals `e`. Sort those flows by `(hop_id ascending ASCII, flow_id ascending ASCII)` and process in that order.
6. All-or-nothing admission: for a flow targeting hop `h` with `bytes = B`, let `avail = max(0, budget(h) - used[h])`. If `B <= avail`, admit `B` bytes: append an admission row and increase `used[h]` by `B`. Otherwise deny the entire flow: append a denial row with `available = avail` and do not change `used[h]`.
7. After every flow for epoch `e` is handled, for each hop `h` in `hops_order` compute `carry_out[h] = min(carry_max, max(0, budget(h) - used[h]))`. If `halted[h]` is true at the end of step 6, set `carry_out[h] = 0`. Store `carry_out[h]` into the hop's carry bucket so it becomes `carry_in` at the next epoch boundary (after incidents for that next epoch run).

## Outputs (under audit directory)

Write these files:

1. `admissions.json`: `{ "admissions": [ { "epoch", "hop_id", "flow_id", "bytes" } ... ] }` sorted by `(epoch asc, hop_id asc, flow_id asc)`.
2. `denials.json`: `{ "denials": [ { "epoch", "hop_id", "flow_id", "requested", "available" } ... ] }` using the same sort key as admissions.
3. `carry_ledgers.json`: `{ "rows": [ { "epoch", "hop_id", "cap_core", "carry_in", "carry_out", "used" } ... ] }` sorted by `(epoch asc, hop_id asc)`. Emit one row for every pair `(e, h)` where `e` is in `policy.epochs` and `h` is in `policy.hops_order`.
4. `summary.json`: `{ "incidents_applied": [kind strings in file order], "total_admissions": int, "total_denials": int, "total_admitted_bytes": int, "total_denied_bytes": int, "max_epoch": int }` where `total_admitted_bytes` sums admitted `bytes`, `total_denials` counts denial rows, `total_denied_bytes` sums each denial's `requested` field, and `max_epoch` is the maximum epoch integer observed in admissions, denials, or any incident's `epoch` field (use `0` when none apply).

## Evidence anchors

`anchors/*.txt` are single-line evidence strings terminated by a newline. They are not parsed for logic.
