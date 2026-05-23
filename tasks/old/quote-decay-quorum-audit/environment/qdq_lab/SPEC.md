# Quote decay quorum audit (normative)

All JSON on disk uses UTF-8. Parse errors, unknown enum strings, or missing required fields are malformed input: the auditor must exit non-zero and must not create any output file listed in `instruction.md`.

## Inputs (under the data directory)

- `policy.json` — object fields:
  - `eval_day` (integer, may be negative).
  - `min_floor` (number >= 0).
  - `epsilon` (number > 0).
  - `quorum_min_active` (integer >= 1): minimum count of kept quotes with `stance` in `{-1,1}` required before a subject may receive verdict `pass` or `fail` (otherwise `split`).
  - `tier_weights` (object): keys are tier names; values are numbers > 0.
  - `frozen_anchors` (array of strings, possibly empty): anchor ids whose linked quotes are always excluded with reason `anchor_freeze`.
  - `pool_cap` (integer >= 1): maximum kept quotes per subject after ranking.
- `pool_state.json` — object with `schema_version` (string) and `notes` (string); no algorithmic fields.
- `domain_layout.json` — object `quote_to_anchor`: maps every `quote_id` to an `anchor_id` string.
- `anchors/*.json` — each file is one object with `anchor_id` (string) and `label` (string); anchors are informational only except for freeze membership in `policy.frozen_anchors`.
- `quotes/*.json` — each file one quote object, required fields:
  - `quote_id` (string), `subject_id` (string), `issuer` (string), `tier` (string, must exist in `policy.tier_weights`).
  - `issued_day` (integer), `half_life_days` (number > 0).
  - `raw_strength` (number), `stance` (exactly one of `-1`, `0`, `1` in JSON number type).
- `incident_log.json` — array of objects, each with:
  - `subject_id` (string), `issuer` (string), `factor` (number > 0).
  - `from_day` (integer), `to_day` (integer, inclusive range). Incidents apply only when `policy.eval_day` lies within `[from_day, to_day]`.

## Effective and adjusted strength

Let `D = policy.eval_day - quote.issued_day`.

Per-quote decayed value (before floor): `decayed = quote.raw_strength * pow(0.5, D / quote.half_life_days)` using real division.

Then `effective = max(policy.min_floor, decayed)`.

For each quote, start `adjusted = effective`. Apply every incident where `incident.subject_id == quote.subject_id`, `incident.issuer == quote.issuer`, and `eval_day` is within the incident inclusive day range: multiply `adjusted` by `incident.factor`.

If `domain_layout.quote_to_anchor[quote_id]` is listed in `policy.frozen_anchors`, the quote is excluded with reason `anchor_freeze` and does not participate further.

Otherwise the quote is a candidate. Rank all candidates for a fixed `subject_id` by descending `adjusted`, then ascending `quote_id`, and keep the first `policy.pool_cap` as **kept**; any later candidate for that subject is excluded with reason `pool_cap`.

Excluded quotes (anchor freeze or pool cap) do not contribute to totals. Quotes with `stance == 0` may be kept but never count toward `quorum_min_active`.

## Weighted total and verdict

For each kept quote with non-freeze exclusion path: contribution = `adjusted * policy.tier_weights[quote.tier] * quote.stance`.

`weighted_total` is the sum of contributions for that subject.

Let `active_kept` be the count of kept quotes for that subject where `stance` is `-1` or `1`.

Verdict rules for that subject:

- If `active_kept < policy.quorum_min_active`, verdict is `split` (regardless of weighted sum).
- Else if `weighted_total > policy.epsilon`, verdict `pass`.
- Else if `weighted_total < -policy.epsilon`, verdict `fail`.
- Else `split`.

## Outputs (under the audit directory)

Write exactly three files, each canonical JSON: indent exactly two ASCII spaces, sorted object keys, no trailing spaces at line ends, ASCII-only text, single trailing newline at EOF.

1. `subjects.json` — object keyed by `subject_id` (every subject appearing in any quote file). Each value object fields in sorted key order:
   - `active_kept` (integer)
   - `kept_quote_ids` (array of strings, sorted ascending, deduplicated)
   - `verdict` (one of `pass`, `fail`, `split`)
   - `weighted_total` (number; round to exactly six digits after the decimal point, including trailing zeros)

2. `quotes_eval.json` — object keyed by `quote_id` ascending. Each value object fields:
   - `adjusted` (number rounded to six decimals after the decimal point; compute after incidents, even when the quote is later excluded)
   - `effective` (number rounded the same way)
   - `excluded_reason` (one of `none`, `anchor_freeze`, `pool_cap`)

Frozen-anchor quotes still emit `effective` and `adjusted`, use `anchor_freeze` as the reason, and stay out of the pool_cap ranking and weighted totals.

3. `summary.json` — object with keys:
   - `subjects` (integer count)
   - `verdict_counts` (object with keys `fail`, `pass`, `split` each integer, sorted keys)
   - `weighted_sum_abs` (sum over subjects of `abs(weighted_total)` from the rounded subject totals, rounded itself to 6 decimals)

## Subject and quote ordering

Discover `quotes/*.json` in ascending filename order for stable iteration when tie-breaking is not already fixed by spec.

Subject ids: union of all quotes' `subject_id`, sorted ascending.
