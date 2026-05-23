# Diagnostic Codes

`region_diagnostics.json` carries one entry per event that emitted at least
one diagnostic. Events with zero diagnostics are NOT listed -- the array is
sparse, sorted by `seq` ascending. Within an event the `diagnostics` list is
sorted by `(severity_rank, code, region_id)` where `region_id` is sorted
ASCII and `null` sorts as the empty string. Severity ranks: `error` = 0,
`warning` = 1, `note` = 2.

The closed code set is exactly:

| Code                       | Severity | `region_id`                       | Fired by              |
|----------------------------|----------|------------------------------------|-----------------------|
| `E_REGION_NOT_FOUND`       | error    | the missing id                     | `unmap`, `mprotect`, `split`, `merge` |
| `E_DUPLICATE_ID`           | error    | the id that collided               | `map`, `split`        |
| `E_OVERLAP_REJECTED`       | error    | the rejected `map.id`              | `map` under `overlap_action == "reject"` when the new range overlaps any existing region |
| `E_BELOW_MIN_SIZE`         | error    | the id that would be too small (the new id for `map`, the new `target_id` or the leftover source id for `split`) | `map`, `split` |
| `E_SPLIT_OUT_OF_RANGE`     | error    | the source id                      | `split`               |
| `E_MERGE_NOT_ADJACENT`     | error    | the lex-smaller of the two parents | `merge` (covers non-adjacent, owner mismatch, AND prot mismatch under the policy) |
| `W_REPLACED_OVERLAP`       | warning  | each removed region's id           | `map` under `overlap_action == "replace"`, one per removed region |
| `N_AUTO_COALESCED`         | note     | the **kept_id** of the merge       | `map`, `unmap` (one per cascading auto-coalesce) |

There are exactly eight legal codes. Any other code or severity is a bug.

`E_BELOW_MIN_SIZE` for `split`: when the resulting source piece would be too
small AND the new piece would also be too small, emit ONE diagnostic only --
on the SOURCE id (the original surviving id). Single-id reporting keeps the
diagnostic list deterministic.

When a `map` fails with `E_OVERLAP_REJECTED`, do NOT also emit
`E_BELOW_MIN_SIZE` even if `size < min_region_size` -- the priority order in
`events.md` short-circuits.
