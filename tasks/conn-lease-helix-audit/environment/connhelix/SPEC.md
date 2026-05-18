# Conn helix lease audit

Normative inputs live under the connhelix bundle root next to this file. The audit evaluates one frozen tick and emits five UTF-8 JSON documents with no byte-order mark.

## Canonical JSON

Every output file MUST be serialized as JSON with `sort_keys=true`, `indent=2`, `separators=(",", ": ")`, `ensure_ascii=true`, and exactly one trailing newline (`0x0a`) after the closing brace or bracket. Object key ordering follows lexical sort because `sort_keys` is required.

## Primary inputs

Read `policy.json`, `pool_state.json`, `freeze_windows.json`, every `*.json` file directly under `wrappers/` (ignore subdirectories and non-json files), and every `*.txt` file directly under `anchors/` (ignore subdirectories and non-txt files). Ignore `ledger/` and `ancillary/` for semantics (those paths exist only to mirror fleet packaging noise).

### policy.json fields

- `max_lease_ms` (integer, positive): maximum permitted effective lease span for a leased helix slot. See "Effective lease" below for how anchor renewals fold into this.
- `idle_timeout_ms` (integer, non-negative): idle slots unused longer than this span become eviction candidates when allowed by the live-count guards.
- `min_size` (integer, non-negative): minimum live helix slots fleet-wide that must remain after all reclaim passes complete.
- `max_size` (integer, positive): carried through to counters only; it MUST NOT cap evictions for this audit (the dataset is already bounded).
- `segment_floors` (object, string → non-negative integer): per-segment minimum live slot count that must remain after all reclaim passes complete. A segment not listed here has floor 0. Both `min_size` and the segment floor must hold for any idle eviction to proceed.

A live slot is any wrapper whose final verdict is `healthy_idle`, `healthy_leased`, `idle_preserved_freeze`, or `idle_retained_cap`. Reclaimed slots (`reclaimed_leak`, `reclaimed_cascade`, `reclaimed_idle`) are not live.

### pool_state.json fields

- `eval_tick_ms` (integer): the audit clock value used for every duration comparison.

### freeze_windows.json

`windows` is an array. Each window has `start_tick_ms`, `end_tick_ms`, and `scope`. Depending on `scope`:

- `scope == "segment"`: the window also carries a `segment` (string) and applies to every wrapper whose `segment` equals that value.
- `scope == "wrapper"`: the window also carries a `wrapper_id` (string) and applies to that wrapper only.
- Any other `scope` value never matches any wrapper.

A window is active at `eval_tick_ms` when `start_tick_ms <= eval_tick_ms` AND `eval_tick_ms <= end_tick_ms` (inclusive on both ends). While any active window covers a wrapper at `eval_tick_ms`, that wrapper is frozen for idle eviction only. Frozen wrappers still participate in lease accounting, leak reclaim, and cascade reclaim.

### Wrapper files

Each wrapper JSON object has:

- `wrapper_id` (string, unique)
- `segment` (string)
- `phase`: either `leased` or `idle`
- `checkout_tick_ms`: integer when `phase` is `leased`, otherwise JSON `null`
- `entered_idle_tick_ms`: integer when `phase` is `idle`, otherwise JSON `null`
- `parent_wrapper_id`: optional string referring to another wrapper id, or JSON `null` / absent when the wrapper has no parent

Malformed wrapper files (unknown `phase`, missing required tick for the active phase, duplicate `wrapper_id`, or a non-null `parent_wrapper_id` that does not refer to a known wrapper) MUST cause the audit tool to exit non-zero. A cycle in the parent chain (walking `parent_wrapper_id` upward revisits a wrapper id) MUST also cause non-zero exit.

### Anchor files

Each file directly under `anchors/` with a `.txt` extension is a UTF-8 renewal log. Each non-empty line is a renewal record formatted `<wrapper_id> <renewal_tick_ms>` (one or more whitespace characters separate the two fields). Lines whose first non-whitespace character is `#` are treated as comments and ignored. Lines containing only whitespace are ignored. The renewal tick MUST parse as a base-10 integer; malformed records MUST cause non-zero exit.

A renewal record is applicable when its `wrapper_id` refers to a known wrapper AND that wrapper has phase `leased`. When multiple applicable renewals target the same wrapper, the latest (numerically largest) `renewal_tick_ms` wins.

A renewal whose `wrapper_id` does not match any known wrapper, OR whose target wrapper has phase `idle`, is ignored. The wrapper id from every ignored renewal record MUST appear exactly once in `summary.ignored_renewals` (sorted ASCII ascending, duplicates collapsed).

## Effective lease

For a leased wrapper, `effective_checkout_tick_ms = max(checkout_tick_ms, latest_applicable_renewal_tick_ms)` when at least one applicable renewal exists, otherwise `checkout_tick_ms`. Then `effective_lease_ms = eval_tick_ms - effective_checkout_tick_ms`. The leak rule fires when `effective_lease_ms > max_lease_ms` (strictly greater). Every `lease_ms` value written to the outputs is the `effective_lease_ms` of the leaked wrapper.

For an idle wrapper, `idle_ms = eval_tick_ms - entered_idle_tick_ms`. An idle eviction candidate exists when `idle_ms > idle_timeout_ms` (strictly greater).

## Processing passes

1. **Anchor pass.** Read every applicable renewal record and build the per-wrapper map of latest renewal tick. Build the sorted unique set of wrapper ids whose records were ignored.

2. **Leak pass.** Classify every leased wrapper for leak reclaim using the effective lease rule. Leak reclaims always emit `reclaimed_leak`.

3. **Cascade pass.** For every wrapper `W` (leased or idle) that is NOT itself leak-reclaimed, walk upward through `parent_wrapper_id` links. If the walk encounters a leak-reclaimed wrapper, classify `W` as `reclaimed_cascade`, attribute it to that closest leak ancestor as `parent_leak_id`, and record the depth as the number of `parent_wrapper_id` hops needed to reach the leak ancestor (1 for a direct parent). If the walk terminates at a wrapper with no parent without encountering any leak ancestor, `W` is not cascaded. If the walk revisits any wrapper id, the input is cyclic and the audit MUST exit non-zero.

4. **Live recount.** After the leak and cascade passes settle, the running guard counters are seeded as:
   - `leased_live`: leased wrappers that are neither leak-reclaimed nor cascade-reclaimed (fixed from this point on).
   - `idle_live`: idle wrappers that are neither leak-reclaimed nor cascade-reclaimed (decremented as idle reclaims occur).
   - `segment_live[s]`: for each segment `s`, the count of wrappers in `s` that are neither leak-reclaimed nor cascade-reclaimed (decremented as idle reclaims occur within `s`).

5. **Idle eviction walk.** Build the ordered candidate list of all idle wrappers that are neither leak-reclaimed nor cascade-reclaimed and that satisfy `idle_ms > idle_timeout_ms`. Sort the list by `entered_idle_tick_ms` ascending, then `wrapper_id` ascending. Walk the list once. For each wrapper `W`:
   - If at least one active freeze window covers `W` (a segment-scope window whose `segment` equals `W.segment`, OR a wrapper-scope window whose `wrapper_id` equals `W.wrapper_id`), assign `idle_preserved_freeze`. Guard counters are unchanged.
   - Otherwise compute the two guard conditions using the running counters from step 4 (which already reflect every prior idle reclaim in this walk):
     - `global_ok = (leased_live + idle_live - 1) >= min_size`
     - `segment_ok = (segment_live[W.segment] - 1) >= segment_floors.get(W.segment, 0)`
     - If both `global_ok` and `segment_ok` are true, emit `reclaimed_idle`, decrement `idle_live` and `segment_live[W.segment]`, and append an idle reclaim event in the walk order.
     - Otherwise assign `idle_retained_cap`. Classify the cause as `segment` when `segment_ok` is false (whether or not `global_ok` is also false), or as `global` when `segment_ok` is true and `global_ok` is false.

6. **Healthy assignments.** Any leased wrapper not classified by the leak or cascade pass receives `healthy_leased`; any idle wrapper not classified by leak, cascade, or the idle walk receives `healthy_idle`.

## Outputs (under the audit directory)

### wrapper_verdicts.json

Top-level keys sorted lexicographically:

- `eval_tick_ms`: copy from pool state
- `wrappers`: array of objects each containing `segment`, `verdict`, `wrapper_id`, sorted by `wrapper_id` ascending

`verdict` is one of `healthy_idle`, `healthy_leased`, `idle_preserved_freeze`, `idle_retained_cap`, `reclaimed_cascade`, `reclaimed_idle`, `reclaimed_leak`.

### reclaim_events.json

Top-level object with sorted keys:

- `events`: array ordered as follows.
  1. Every `leak_reclaim` event first, sorted by `lease_ms` descending, then `wrapper_id` ascending. Each carries `kind` (`leak_reclaim`), `lease_ms` (the effective lease), `reason` (`lease_exceeded`), `wrapper_id`.
  2. Every `cascade_reclaim` event next, grouped by `parent_leak_id` in the same order as the leak group appeared in part 1. Within each `parent_leak_id` group, sort by `depth` ascending then `wrapper_id` ascending. Each carries `depth`, `kind` (`cascade_reclaim`), `parent_leak_id`, `reason` (`parent_leaked`), `wrapper_id`.
  3. Every `idle_reclaim` event last, in the exact idle walk order from step 5. Each carries `idle_ms`, `kind` (`idle_reclaim`), `reason` (`idle_timeout`), `wrapper_id`.

### pool_counters.json

Include sorted keys:

- `cascade_reclaims`: count of `reclaimed_cascade` verdicts
- `eval_tick_ms`
- `healthy_idle_remaining`, `healthy_leased_remaining`: counts of those verdicts
- `idle_evictions`: count of `reclaimed_idle` verdicts
- `idle_preserved_freeze`: count of that verdict
- `idle_retained_cap`: count of that verdict
- `idle_retained_cap_global`: count of `idle_retained_cap` decisions classified as `global` per step 5
- `idle_retained_cap_segment`: count of `idle_retained_cap` decisions classified as `segment` per step 5
- `leak_reclaims`: count of `reclaimed_leak` verdicts
- `max_size`, `min_size`: copied through from policy
- `wrappers_total`: total wrapper count

The invariant `idle_retained_cap_global + idle_retained_cap_segment == idle_retained_cap` always holds.

### freeze_echo.json

Object with sorted keys:

- `windows`: array copying each input window. Each echoed window has sorted keys `end_tick_ms`, `scope`, `segment`, `start_tick_ms`, `wrapper_id`. `segment` is the input value when `scope == "segment"`, otherwise JSON `null`. `wrapper_id` is the input value when `scope == "wrapper"`, otherwise JSON `null`. Sort the windows by `start_tick_ms` ascending, then `end_tick_ms`, then `scope`, then the printed form of `segment` (use the literal string `null` when the JSON value is null), then the printed form of `wrapper_id` (same null handling).

### summary.json

Sorted keys:

- `eval_tick_ms`
- `ignored_renewals`: sorted unique list of wrapper ids whose renewal records were ignored
- `segments`: distinct wrapper segments sorted lexicographically
- `unique_verdicts`: distinct verdict strings sorted lexicographically

## Tooling contract

The audit entrypoint must read the bundle root from `CLA_DATA_DIR` defaulting to `/app/connhelix` and write outputs to `CLA_AUDIT_DIR` defaulting to `/app/audit`. It must create the audit directory when missing and must never mutate inputs.
