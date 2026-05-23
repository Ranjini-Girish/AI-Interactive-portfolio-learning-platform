# Event Semantics

Each event has a `seq`, an `op`, and a subset of the optional fields `id`,
`base`, `size`, `prot`, `owner`, and `target_id` (filled with `null` when
unused). Unused fields MUST be present and `null` -- the input file always
emits the same key set per event.

## `map`

Required: `id`, `base`, `size`, `prot`, `owner`. Adds a fresh region. Failure
modes (in priority order):

1. `id` already exists -> emit `E_DUPLICATE_ID`, no state change.
2. `size < policy.min_region_size` -> emit `E_BELOW_MIN_SIZE`, no state change.
3. The new range overlaps an existing region:
   - under `overlap_action == "reject"`: emit `E_OVERLAP_REJECTED`, no state change.
   - under `overlap_action == "replace"`: every existing region whose range
     intersects `[base, base + size)` is removed entirely (no clipping; whole
     regions go), one `W_REPLACED_OVERLAP` warning per removed region (carrying
     the removed region's id), then the new region is added.
4. Otherwise add the region.

After a successful `map` (success path 3.replace or 4) attempt auto-coalesce:
see `coalesce.md`.

## `unmap`

Required: `id`. Removes the region with that id. If the id does not exist,
emit `E_REGION_NOT_FOUND` and no state change. After a successful `unmap`,
when `policy.auto_coalesce_after_unmap` is true, attempt to coalesce the two
regions that now sit on either side of the freed range (only those two; any
other pair already adjacent before the unmap is unaffected).

## `mprotect`

Required: `id`, `prot`. Replaces the named region's protection. If the id
does not exist, emit `E_REGION_NOT_FOUND` (no state change). `mprotect` never
triggers auto-coalesce, even if the new `prot` would now allow it.

## `split`

Required: `id` (existing), `target_id` (must NOT already exist), `base`,
`size`. The new region carved out as `target_id` must sit at exactly the
**low edge** or the **high edge** of the source: either `base == src.base`
(low-edge split: source shrinks from the left) or
`base + size == src.base + src.size` (high-edge split: source shrinks from the
right). Both pieces inherit the source's `prot` and `owner`. Failure modes
(in priority order):

1. source `id` does not exist -> `E_REGION_NOT_FOUND`.
2. `target_id` already exists -> `E_DUPLICATE_ID`.
3. The carve range is not at the low or high edge, or is empty, or extends
   outside the source -> `E_SPLIT_OUT_OF_RANGE`.
4. Either resulting piece would have `size < policy.min_region_size`
   -> `E_BELOW_MIN_SIZE`.

`split` never triggers auto-coalesce. It DOES contribute lineage edges (see
`lineage.md`).

## `merge`

Required: `target_id` is a JSON array of exactly two existing region ids;
`id`, `base`, `size`, `prot`, `owner` are all `null`. The two regions must be
**adjacent** (the lower one's `base + size` must equal the upper one's `base`)
AND share the same `owner`. Their `prot` flags must also be compatible per
`policy.coalesce_mode` -- the same compatibility rule as auto-coalesce in
`coalesce.md`. The kept region's id is the **lex-smallest** of the two; the
other region's id disappears. Failure modes:

1. Either id missing -> `E_REGION_NOT_FOUND`.
2. Not adjacent or owner mismatch or prot mismatch under the policy
   -> `E_MERGE_NOT_ADJACENT`.

`merge` never appears in `coalesce_log.json` (that log is for *auto* coalesces
only) but it DOES contribute lineage edges from each of the two parents to
the kept id.
