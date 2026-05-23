# Auto-Coalesce Rules

After a successful `map` or a successful `unmap` (with
`policy.auto_coalesce_after_unmap` true), the simulator scans for adjacent
regions that can be combined.

## Compatibility (drives merge eligibility)

Two adjacent regions A (lower) and B (upper) -- meaning `A.base + A.size ==
B.base` -- are **compatible** under `policy.coalesce_mode`:

- `"strict"`: they must share both `prot` AND `owner`.
- `"prot_match_only"`: they must share `prot` (owner can differ).
- `"prot_and_owner_match"`: identical to `"strict"`.

(Yes, `strict` and `prot_and_owner_match` are aliases. `strict` is provided as
a synonym for the default mode that callers reach for first.)

## Trigger windows

`map` triggers a coalesce sweep over the **just-mapped region** and ITS two
immediate neighbours only, in this order:

1. Try to coalesce with the lower neighbour (the region whose `base + size ==
   new.base`). If they are compatible, merge them: the **lex-smallest** id is
   kept, the other is dropped, and the kept region's range becomes the union.
2. Then try to coalesce the (possibly already-grown) merged region with its
   upper neighbour (the region whose `base == merged.base + merged.size`).
   Same compatibility check, same lex-smallest-kept rule.

That is at most two merges per `map`; they cascade left-then-right, but the
sweep does not jump over non-compatible neighbours to find a third match.

`unmap` triggers a coalesce check over the **two regions that flank the freed
range**: the region whose `base + size == removed.base`, and the region whose
`base == removed.base + removed.size`. If both exist and are compatible, they
merge (lex-smallest id kept). At most one merge per `unmap`.

`split`, `mprotect`, and explicit `merge` events NEVER trigger an auto-
coalesce sweep, even when the resulting layout would be eligible.

## `coalesce_log.json`

Every auto-coalesce produced by the rules above appends a record:

```
{ "kept_id": <str>, "dropped_id": <str>, "seq": <int>, "trigger": "map" | "unmap" }
```

Records are appended in chronological order across the whole trace (no
sorting). Two cascading merges from the same `map` produce two records, both
with the same `seq` and `trigger == "map"`, in low-then-high order.

Each auto-coalesce also emits `N_AUTO_COALESCED` (note severity) on the
triggering event, with `region_id` set to the **kept_id**. If a single `map`
produces two cascading merges, that is two `N_AUTO_COALESCED` notes on the
same event (sorted within the event by `(severity_rank, code, region_id)`).
