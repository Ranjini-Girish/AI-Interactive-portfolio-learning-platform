# Conn helix lease audit

Normative inputs live under the connhelix bundle root next to this file. The audit evaluates one frozen tick and emits five UTF-8 JSON documents with no byte-order mark.

## Canonical JSON

Every output file MUST be serialized as JSON with `sort_keys=true`, `indent=2`, `separators=(",", ": ")`, `ensure_ascii=true`, and exactly one trailing newline (`0x0a`) after the closing brace or bracket. Object key ordering follows lexical sort because `sort_keys` is required.

## Primary inputs

Read `policy.json`, `pool_state.json`, `freeze_windows.json`, every `*.json` file directly under `wrappers/` (ignore subdirectories and non-json files), and ignore `ledger/`, `ancillary/`, and `anchors/` for semantics (those paths exist only to mirror fleet packaging noise).

### policy.json fields

- `max_lease_ms` (integer, positive): maximum permitted active lease span for a leased helix slot measured from its checkout tick to `eval_tick_ms`.
- `idle_timeout_ms` (integer, non-negative): idle helix slots unused longer than this span become eviction candidates when allowed by the live-count guard.
- `min_size` (integer, non-negative): minimum live helix slots that must remain after all reclaim passes complete. A live slot is any wrapper that is not `reclaimed_leak` or `reclaimed_idle` in the final verdict set.
- `max_size` (integer, positive): carried through to counters only; it MUST NOT cap evictions for this audit (the dataset is already bounded).

### pool_state.json fields

- `eval_tick_ms` (integer): the audit clock value used for every duration comparison.

### freeze_windows.json

`windows` is an array. Each window has `start_tick_ms`, `end_tick_ms`, `scope`, and optional `segment`. A window is active at `eval_tick_ms` when `start_tick_ms <= eval_tick_ms` AND `eval_tick_ms <= end_tick_ms` (inclusive on both ends). When `scope` equals `segment`, the window applies to every wrapper whose `segment` string equals the window `segment` value. Unknown `scope` values never match. Windows never overlap for the same segment in this dataset; if they did, any matching window is sufficient to freeze.

While a freeze window is active for a wrapper segment at `eval_tick_ms`, that wrapper is frozen for idle eviction only. Frozen wrappers still participate in lease accounting and leak reclaim.

### Wrapper files

Each wrapper JSON object has:

- `wrapper_id` (string, unique)
- `segment` (string)
- `phase`: either `leased` or `idle`
- `checkout_tick_ms`: integer present only when `phase` is `leased`
- `entered_idle_tick_ms`: integer present only when `phase` is `idle`

Malformed wrapper files (unknown `phase`, missing required tick for the phase, or duplicate `wrapper_id`) MUST cause the audit tool to exit non-zero. Nullable ticks are represented as JSON `null` and are ignored for the active phase.

## Derived quantities

For a leased wrapper at `eval_tick_ms`, `lease_ms = eval_tick_ms - checkout_tick_ms`. A leak reclaim applies when `lease_ms > max_lease_ms` (strictly greater).

For an idle wrapper, `idle_ms = eval_tick_ms - entered_idle_tick_ms`. An idle eviction candidate exists when `idle_ms > idle_timeout_ms` (strictly greater).

## Processing passes

1. Classify every wrapper for leak reclaim using the leak rule. Leak reclaims always emit `reclaimed_leak` verdicts regardless of freezes.
2. Recompute live counts: leased wrappers that were not reclaimed count toward leased live; idle wrappers not yet evicted count toward idle live.
3. Build the ordered idle eviction candidate list: all idle wrappers that are not already `reclaimed_leak`, sorted by `entered_idle_tick_ms` ascending, then `wrapper_id` ascending.
4. Walk the list once. For each wrapper:
   - If it is not an idle eviction candidate (`idle_ms <= idle_timeout_ms`), assign `healthy_idle` when still idle.
   - If it is a candidate and any active freeze window covers its `segment` at `eval_tick_ms`, assign `idle_preserved_freeze` and do not change live counts.
   - If it is a candidate, not frozen, and `live_after_eviction >= min_size` would still hold if this idle slot were removed while keeping all currently retained slots, emit `reclaimed_idle`, decrement the idle live counter used for the guard, and record an idle reclaim event.
   - If it is a candidate, not frozen, but the guard would be violated, assign `idle_retained_cap`.
5. Any leased wrapper that did not leak receives `healthy_leased`.

`live_after_eviction` means `current_leased_live + current_idle_live - 1` computed immediately before deciding on that candidate, using counters that already reflect prior idle evictions in this walk and all leak reclaims from pass one. `current_leased_live` is fixed after pass one.

## Outputs (under the audit directory)

### wrapper_verdicts.json

Top-level keys sorted lexicographically:

- `eval_tick_ms`: copy from pool state
- `wrappers`: array of objects each containing `segment`, `verdict`, `wrapper_id` sorted by `wrapper_id` ascending

`verdict` is one of `healthy_idle`, `healthy_leased`, `idle_preserved_freeze`, `idle_retained_cap`, `reclaimed_idle`, `reclaimed_leak`.

### reclaim_events.json

Top-level object with sorted keys:

- `events`: array ordered as follows: every `leak_reclaim` event first, sorted by `lease_ms` descending, then `wrapper_id` ascending; then every `idle_reclaim` event in the exact idle processing order from step 4. Each leak event object includes `kind` (`leak_reclaim`), `lease_ms`, `reason` (`lease_exceeded`), `wrapper_id`. Each idle event includes `kind` (`idle_reclaim`), `idle_ms`, `reason` (`idle_timeout`), `wrapper_id`.

### pool_counters.json

Include sorted keys: `eval_tick_ms`, `healthy_idle_remaining`, `healthy_leased_remaining`, `idle_evictions`, `idle_retained_cap`, `idle_preserved_freeze`, `leak_reclaims`, `max_size`, `min_size`, `wrappers_total`. Counts reflect final verdicts: `idle_evictions` counts `reclaimed_idle`, `leak_reclaims` counts `reclaimed_leak`, `idle_preserved_freeze` counts that verdict, `idle_retained_cap` counts that verdict, `healthy_*` counts match verdict names.

### freeze_echo.json

Object with `windows` array copying each input window sorted by `start_tick_ms` ascending, then `end_tick_ms`, then `segment`, then `scope`. Include `segment` key even when null (use JSON `null`).

### summary.json

Sorted keys: `eval_tick_ms`, `segments`, `unique_verdicts`. `segments` lists distinct wrapper segments sorted lexicographically. `unique_verdicts` lists distinct verdict strings sorted lexicographically.

## Tooling contract

The audit entrypoint must read the bundle root from `CLA_DATA_DIR` defaulting to `/app/connhelix` and write outputs to `CLA_AUDIT_DIR` defaulting to `/app/audit`. It must create the audit directory when missing and must never mutate inputs.
