# Prior blend rank audit

Normative contract for `/app/pbr_lab`. Canonical JSON on disk uses UTF-8, `json.dumps(..., sort_keys=True, indent=2, separators=(", ", ": "))`, and exactly one trailing newline after the closing brace.

## Input inventory

Required files: `policy.json`, `pool_state.json`, `incident_log.json`, `domain_layout.json`, `anchors/a.json`, `anchors/b.json`, `ancillary/meta.json`, `ancillary/notes.json`, `ancillary/stub.json`, every `lanes/lNN.json` for `NN` from `01` through `08`, and every `items/item_NN.json` for `NN` from `00` through `09`.

## policy.json

Object fields:

- `active_regions` (array of strings, non-empty): only items whose `region` string is listed survive the initial filter.
- `blend_gamma` (integer in `0..1000` inclusive): weight on the prior score in the blend defined below.
- `lane_floor` (integer `>= 0`): lower clamp applied to integer scores after blending.
- `witness_cap` (integer `>= 0`): upper clamp applied to raw witness ranks read from lane files before blending.
- `quarantine_region` (string): region label compared against pool flags.

## pool_state.json

- `current_day` (integer `>= 0`)
- `budget` (integer `>= 0`): total units to allocate across surviving items after incidents.
- `flags` object with booleans `experiment_compromised` and `holdout_breach`.

## incident_log.json

- `events` array processed in file order. Each event is an object with string `kind`.

Supported kinds:

- `prior_boost`: fields `item_id` (string), `delta_a` (integer, may be negative), `delta_b` (integer, may be negative). After applying, clamp each of `prior_a` and `prior_b` on that item to be at least `1`.
- `lane_witness_nudge`: fields `lane_code` (string matching `lanes/lNN.json` basename without extension, e.g. `l03`), `delta` (integer). Add `delta` to that lane file's `witness_rank`, then clamp to `0..witness_cap` inclusive using the policy's `witness_cap` value current at the start of the audit (policy.json is static).
- `drop_item`: field `item_id` (string) removes that item from the working set if present.

Unknown kinds are ignored aside from the global `applied_events` counter (see summary).

## Lanes and items

Each `lanes/lNN.json` contains string `lane_code` (must equal `lNN`) and integer `witness_rank` (initially `>= 0`).

Each `items/item_NN.json` contains string `item_id`, string `region`, string `lane_code`, integers `prior_a`, `prior_b` (both `>= 1` initially), and integer `weight` (`>= 0`).

## domain_layout and anchors

Read `domain_layout.json` object field `anchor_weight` (integer, default `0` if missing or wrong type). Read integers `bonus_a` and `bonus_b` from `anchors/a.json` and `anchors/b.json`. If any of these three integers is missing or not an integer, treat the missing ones as `0`.

Add `(anchor_weight + bonus_a + bonus_b)` to every surviving item's `prior_a` after incidents and before scores (still clamp each prior to `>= 1` after this addition).

## Scoring

Let `s = floor(1000 * prior_a / (prior_a + prior_b))` using integer floor division.

Let `w_raw` be the witness rank of the item's `lane_code` after all lane nudges from incidents.

Let `w = min(w_raw, witness_cap)`.

If `flags.experiment_compromised` is true, redefine `w = 0` before blending.

Let `b = (blend_gamma * s + (1000 - blend_gamma) * w) // 1000`.

Replace `b` with `max(b, lane_floor)`.

The item's allocation weight is `score = b * item_weight` where `item_weight` is the item's `weight` field.

## Quarantine

If `flags.holdout_breach` is true, remove every item whose `region` equals `quarantine_region` from the working set before scoring and allocation (after incidents).

## Allocation

Distribute `budget` across surviving items using the largest-remainder method on the fractional shares proportional to each `score`. If the working set is empty, every allocation is `0` and `unallocated` equals the full `budget`. If `budget` is `0`, every allocation is `0`.

Tie-break when comparing fractional remainders: larger remainder wins; if equal, lexicographically smaller `item_id` wins. When assigning the integer parts before remainders, use the same tie-break for equal integer parts (though integer parts from floor should be handled with the same tie order for zero shares: items with `score == 0` receive `0` until remainder passes).

Deterministic ordering for every sorted list in outputs: ASCII ascending on the relevant string key.

## Outputs under `/app/audit`

Write exactly two files.

### allocation_table.json

```json
{
  "allocations": [
    {"item_id": "...", "lane_code": "...", "region": "...", "prior_a": 1, "prior_b": 1, "witness_used": 0, "score": 0, "allocated": 0}
  ]
}
```

`witness_used` is the `w` value after compromise zeroing and witness cap clamp. `allocations` is sorted by `item_id`.

### summary.json

Top-level keys:

- `applied_events` (integer): total events in `incident_log.json` whether recognized or not.
- `survivors` (integer): count of items after incidents, anchor prior bump, and optional quarantine removal.
- `unallocated` (integer): `budget - sum(allocated)`.
- `regions` (object): map each region string appearing among survivors to the sum of `allocated` for that region.

Sort keys ASCII ascending inside `regions`.
