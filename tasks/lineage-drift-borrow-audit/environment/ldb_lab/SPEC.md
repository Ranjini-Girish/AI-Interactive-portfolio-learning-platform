# Lineage drift borrow audit

Normative rules for `/app/ldb_lab/`. Read every JSON value as UTF-8. All emitted JSON must use `json.dumps(value, sort_keys=True, separators=(",", ":"))` semantics (sorted object keys, no extra whitespace, no trailing newline in files).

## Inputs

- `anchors/window.json` object with integer fields `start_day` and `end_day` inclusive. Define `window_days = end_day - start_day + 1` (minimum 1).
- `policy.json` fields:
  - `tier_weight_numerators` object mapping each of `gold`, `silver`, `bronze` to a positive integer.
  - `weight_divisor` positive integer.
  - `escalation_line` non-negative integer threshold scaler.
  - `tier_borrow_caps` object mapping each tier to a non-negative integer cap.
- `pool_state.json` object with integer `token_budget` (starting pool before incidents).
- `incident_log.json` must be a JSON array at the file root. Each element is an object with integer `day`, integer `seq`, string `incident_id`, string `kind`, and object `payload`. Only incidents whose `day` lies inside the closed window apply; others are ignored but still listed under `ignored_events` in the journal output.
- `channels/*.json` one object per file with string `channel_id`, tier `gold|silver|bronze`, integer `base_drift` (non-negative), optional `parent` string referencing another `channel_id` or JSON null for none.

## Lineage classification

Build a functional graph using only `parent` edges that reference an existing channel id (including files loaded from `channels/`). If `parent` is missing, null, or names an unknown id, treat the node as having no parent (root semantics).

For each channel determine `lineage`:

- `cyclic` if the node lies on any directed cycle when following `parent` pointers.
- else `chained` if it has a resolved parent.
- else `root`.

## Weighted base drift

Let `num = tier_weight_numerators[tier]` and `div = weight_divisor`. Define `weighted_base = (base_drift * num) / div` using integer division toward zero for the final division.

## Effective drift with inheritance

Compute `effective_drift` for every channel:

- If `lineage` is `cyclic`, set `effective_drift = weighted_base`.
- Otherwise process channels in an order where every parent appears before its child (any valid topological order of the forest). If multiple roots share descendants, any deterministic order consistent with parent-before-child is allowed only if it matches the tie-break below: sort the ready set by ascending `channel_id` whenever picking the next node (Kahn queue ordering).

For a non-cyclic channel with parent `p`, `effective_drift = weighted_base + (effective_drift[p] / 4)` using integer division on the inherited term.

## Incident replay

Start `pool_remaining = token_budget` and `tier_caps` as a deep copy of `tier_borrow_caps`. Sort applicable incidents by `(day ascending, seq ascending, incident_id ascending)` for stability when pairs match.

Kinds:

- `gift_tokens`: add integer `payload.amount` to `pool_remaining` (ignore if amount missing or negative).
- `tighten_tier_cap`: set `tier_caps[payload.tier] = min(tier_caps[payload.tier], int(payload.new_cap))` when `payload.tier` is a known tier key.
- `embargo`: add `payload.channel_id` string to an `embargoed` set (ignored if missing).

Kinds not listed above are ignored for mutation but counted as `ignored_kind` in the summary.

After replay, clamp every `tier_caps` entry to be non-negative.

## Borrowing pass

Let `tier_remaining` be a copy of post-incident `tier_caps`. Sort channels by `(effective_drift descending, channel_id ascending)`.

For each channel in that order:

- If `channel_id` is in `embargoed`, set `borrowed = 0`.
- Else `borrowed = min(effective_drift, pool_remaining, tier_remaining[tier])` with all operands non-negative integers.
- Subtract `borrowed` from `pool_remaining` and `tier_remaining[tier]` when borrowed is positive.

Define `residual = effective_drift - borrowed`.

## Verdicts

Let `cut = escalation_line * window_days`.

For each channel emit verdict string:

- If `channel_id` is embargoed: `embargoed`.
- Else if `borrowed == effective_drift`: `cleared`.
- Else if `residual > cut`: `escalate`.
- Else: `watch`.

## Outputs under `/app/audit/`

Write exactly three files:

1. `channel_verdicts.json` object key `channels` array of objects with keys `channel_id`, `tier`, `lineage`, `weighted_base`, `effective_drift`, `borrowed`, `residual`, `verdict` sorted by ascending `channel_id`.
2. `incident_journal.json` object keys:
   - `applied_events` array of `incident_id` strings in the exact replay order for applicable incidents.
   - `ignored_events` array of `incident_id` for incidents outside the window (preserve original file order among ignored entries).
3. `summary.json` object keys:
   - `window_days` integer.
   - `pool_after_incidents` integer pool remaining before borrowing.
   - `pool_after_borrow` integer pool remaining after borrowing.
   - `embargoed_channels` integer count of distinct embargoed ids.
   - `verdict_counts` object with keys `cleared`, `watch`, `escalate`, `embargoed` mapping to integer counts.
   - `ignored_incident_kinds` integer count of incidents with unknown `kind` that were inside the window (not ignored for day reasons).

## Canonical on-disk bytes

The three output files must match the canonical JSON rule in the first paragraph exactly.
