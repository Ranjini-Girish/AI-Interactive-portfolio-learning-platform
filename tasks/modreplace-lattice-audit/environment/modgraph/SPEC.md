# Modgraph lattice (normative)

All paths below are rooted at `/app/modgraph/`. JSON must be decoded with a JSON decoder that preserves key order only for tie-breaking explicitly defined here; output encoding is defined in the Output encoding section.

## Inputs

1. `pool_state.json` — object with integer field `as_of_day` (inclusive calendar day counter); array field `global_revoke_prefixes` (possibly empty; when absent, treat as empty); optional string field `local_strip_after_manifest` (when absent or empty, treat as absent).
2. `policy/strip_prefixes.json` — object with array field `prefixes` (possibly empty). Each element is a string prefix. Used only for the global replace map and for classifying entries counted in `strip_excluded_entries`.
3. `policy/local_strip_prefixes.json` — object with array field `prefixes` (possibly empty). Each element is a string prefix. Used only for the tail local-strip rule below.
4. `workspace/scan_order.json` — object with array field `module_manifests`. Each element is a relative file path from `/app/modgraph/` to a module JSON file. Order is significant for the global replace map and for the tail local-strip anchor.
5. Each module JSON file — object with required string fields `module_id`, `module_path`; required array fields `replaces`, `requires`. Elements of `requires` are module path strings. Each element of `replaces` is an object with required string fields `from`, `to`; optional number field `expires_on_day`. Where `expires_on_day` is present as a number, it is compared as an integer to `pool_state.json` field `as_of_day`. Each `from` string is tested against each element of `policy/strip_prefixes.json` field `prefixes` as a UTF-8 byte-wise prefix using Go `strings.HasPrefix(from, prefix)`.

## Tail local-strip anchor

Let `manifests` be `workspace/scan_order.json` field `module_manifests` in order, with indices `0 .. len(manifests)-1`. Let `anchor` be `pool_state.json` field `local_strip_after_manifest` when present and non-empty after trimming ASCII whitespace; otherwise there is no anchor. When an anchor is present, let `anchor_idx` be the smallest index `i` such that `manifests[i]` equals `anchor` as a string; if no such index exists, set `anchor_idx = len(manifests)`. When no anchor is present, set `anchor_idx = len(manifests)`.

A manifest at index `i` is in the **tail** when `i > anchor_idx`.

## Global replace map

Initialize an empty map `G` from string `from` to pair `(to string, won_manifest string)` where `won_manifest` is the manifest path string from `module_manifests`.

Process `module_manifests` in array order with zero-based index `i`. For each manifest path `M` at index `i`, load its JSON. Iterate that file’s `replaces` array from first element to last. For each entry after dropping those where numeric `expires_on_day` is present and `as_of_day` > `expires_on_day`:

- Always count the entry toward `union_replace_edge_count` / `union_vertex_count` / `cycle_report.json` edge materialization as described later (after the same expiry removal).
- If the entry’s `from` is not a prefix hit against `policy/strip_prefixes.json` field `prefixes` as in input item 5, and `i` is in the tail and `from` is a prefix hit against `policy/local_strip_prefixes.json` field `prefixes` using the same UTF-8 `strings.HasPrefix` rule, do not modify `G` for this entry and increment `local_strip_skipped_entries` by one (count each such array element once).
- Else if the entry’s `from` is not a prefix hit against `policy/strip_prefixes.json` field `prefixes` as in input item 5, assign `G[from] = (to, M)` (overwriting any previous value for the same `from`).
- Else it is a prefix hit against `policy/strip_prefixes.json` field `prefixes`; do not modify `G` for this entry.

After all manifests are processed, apply the **global revoke pass**: iterate every key `k` currently present in `G`. If any string `p` in `pool_state.json` field `global_revoke_prefixes` satisfies UTF-8 byte-wise `strings.HasPrefix(k, p)`, delete `k` from `G`. Each deleted key increments `global_revoke_drops` by exactly one (even if multiple prefixes match the same key).

The emitted `global_replace.json` file contains a single object with field `final` whose value is an object. For every key `k` in `G` sorted lexicographically after the revoke pass, emit `k: {"to": <to>, "won_manifest": <won_manifest>}`. The `final` object’s keys must appear in sorted order.

## Local effective map per module

For each loaded module manifest `M` with id `I` at manifest index `i`, build map `E_I` as follows. Start as a shallow copy of all `from -> to` pairs from `G` (only the `to` string is needed for resolution). Then iterate `M.replaces` in forward array order after dropping entries by the same expiry rule as in the global map. For each remaining entry:

- If `i` is in the tail and `from` is a prefix hit against `policy/local_strip_prefixes.json` field `prefixes` and `from` is **not** a prefix hit against `policy/strip_prefixes.json` field `prefixes`, do not modify `E_I` for this entry.
- Else assign `E_I[from] = to` (local entries always participate in `E_I`, including prefix-hit entries against `policy/strip_prefixes.json` field `prefixes`).

## Resolution

For module id `I` and required path `R`, walk starting at `cur = R` using `E_I`. While `cur` is a key in `E_I`, set `next = E_I[cur]`. If `next` equals `cur`, the resolved path is the string `__self_loop__` and walking stops. If `next` appears anywhere in the walk chain already visited (including `R` as the start), the resolved path is the string `__cycle__` and walking stops. Otherwise append implicitly by setting `cur = next` and continue. Maximum iterations allowed are `1024`; if exceeded without hitting a terminal rule, use resolved path `__cycle__`. When no key applies, the resolved path is the current `cur` string.

The walk chain for diagnostics is not emitted in the required outputs; only the final resolved string per `(I, R)` pair is used downstream.

## Skew pairs

Consider all distinct `module_id` values sorted lexicographically. For every unordered pair `(A, B)` with `A < B` lexicographically, let `Req(A)` and `Req(B)` be the `requires` arrays of those modules (exact string contents). For every string `R` that appears in both lists (set intersection), compute `resA` using `E_A` and `resB` using `E_B`. If `resA != resB`, emit object `{"module_a": A, "module_b": B, "require_path": R, "resolved_a": resA, "resolved_b": resB}`. Collect all such objects into array `pairs` sorted by `(module_a, module_b, require_path)` lexicographically as tuples of strings.

Emit `skew_pairs.json` as `{"pairs": [...]}`.

## cycle_report.json

Object fields:

- `components`: JSON array of JSON arrays of distinct module-path strings. Each inner array sorted lexicographically. The outer array sorted lexicographically by comparing inner arrays as string tuples in index order (shorter inner array first when one is a prefix of the other). Each inner array is the sorted vertex list of one SCC on the directed graph whose edge set is the set of distinct ordered pairs `(from, to)` from every manifest’s `replaces` after the same expiry removal as elsewhere (prefix-hit entries included). An SCC is listed when it has more than one distinct vertex, or when it is a single vertex `v` and `(v, v)` is in that edge set.
- `has_cycle`: boolean, true if and only if `components` is non-empty.

Emit `cycle_report.json` as:

- `components`: as above.
- `has_cycle`: as above.

## Resolution table

Emit `resolution.json` as object field `by_module` whose keys are every `module_id` sorted lexicographically. Each value is an array of objects `{"require": <r>, "resolved": <resolved string>, "used_local": <bool>}` sorted by `require` then `resolved` then `used_local` (false sorts before true). The `requires` array for that module must be iterated in the file’s original order to determine `used_local`: `used_local` is true if and only if the resolved string for `r` is different from the resolved string produced when walking `r` using **only** the global map `G` (not `E_I`), using the same resolution rules as above but looking keys up only in `G` (treat missing key as stop). If both walks yield identical strings, `used_local` is false.

## Summary counters

Emit `summary.json` with integer fields only:

- `cycle_component_count` — length of `components` in `cycle_report.json`.
- `expired_replace_drops` — count of `replaces` array elements across all manifests where numeric `expires_on_day` is present and `as_of_day` > `expires_on_day` (count each array element once).
- `global_replace_keys` — number of keys in `G` after the global revoke pass.
- `global_revoke_drops` — number of keys removed from `G` by the global revoke pass.
- `local_strip_skipped_entries` — total defined in the Global replace map section (counted during manifest processing before the revoke pass).
- `module_manifests_read` — length of `module_manifests`.
- `modules_with_used_local` — number of distinct `module_id` values for which at least one emitted resolution row has `used_local` equal to true.
- `skew_distinct_require_paths` — number of distinct `require_path` strings that appear in at least one object inside `skew_pairs.json`’s `pairs` array (count each unique path once even if multiple module pairs disagree on it).
- `skew_pair_count` — length of `pairs` in `skew_pairs.json`.
- `strip_excluded_entries` — count of replace entries not dropped by the expiry rule in input item 5 whose `from` was a prefix hit against `policy/strip_prefixes.json` field `prefixes` across all manifests.
- `union_replace_edge_count` — after the same expiry filtering used everywhere else, collect every remaining replace entry from every manifest (including prefix-hit entries) as a directed edge `(from, to)` on module path strings. Deduplicate parallel edges so each ordered pair appears at most once; this integer is the cardinality of that deduplicated edge set.
- `union_vertex_count` — number of distinct module path strings that appear as either endpoint of at least one edge counted toward `union_replace_edge_count`.
- `used_local_true_rows` — total number of emitted resolution rows (counting across every module’s sorted array) whose `used_local` field is true.

Keys in `summary.json` must be sorted lexicographically.

## Output encoding

Write every output file under `/app/audit/` as UTF-8 JSON pretty-printed with two-space indentation, object keys sorted at every object level, and exactly one trailing newline after the closing brace. No byte order mark.

## Output filenames

Produce exactly these five files: `global_replace.json`, `resolution.json`, `skew_pairs.json`, `cycle_report.json`, `summary.json`.

Whenever a module has no requirement rows after sorting, its `by_module` entry must still be a JSON array value `[]`, never `null`.
