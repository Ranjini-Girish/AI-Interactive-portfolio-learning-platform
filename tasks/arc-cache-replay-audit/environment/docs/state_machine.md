# State machine

W-ARC tracks four ordered lists keyed by `key`, plus an adaptive
parameter `p` and per-entry weight counters.

## The four lists

* `T1`: resident keys seen exactly once (recency-side). Each entry
  carries an integer `cum_weight >= 1`.
* `T2`: resident keys seen at least twice (frequency-side). Each
  entry carries an integer `cum_weight >= 1`.
* `B1`: ghost entries (keys recently demoted from `T1` or dropped
  from `T1` directly in the miss case). Each carries an
  `entry_weight >= 1` snapshot of the `cum_weight` at the moment the
  entry left the resident side.
* `B2`: ghost entries (keys recently demoted from `T2`). Each
  carries an `entry_weight >= 1` snapshot.

All four lists are MRU->LRU (index 0 is the most-recently-used
entry). A key resides in **at most one** of the four lists at any
moment. Initial state: all lists empty, adaptive parameter `p = 0`.

Invariants enforced after every operation:

* `|T1| + |T2| <= c`
* `|T1| + |B1| <= c` (per ARC recency-side invariant)
* `|T2| + |B2| <= 2c` (per ARC frequency-side invariant)
* `|T1| + |B1| + |T2| + |B2| <= 2c`
* `0 <= p <= c`

## Per-entry weight semantics

* On a `miss` insertion into `T1`: the new entry's `cum_weight` is
  the access event's `weight` field.
* On a ghost-hit promotion from `B1` or `B2` to `T2`: the new T2
  entry's `cum_weight` is the access event's `weight` (a fresh
  tenure starts; the ghost's `entry_weight` is discarded).
* On a `hit_t1` or `hit_t2`: the entry's `cum_weight` is increased
  by the access event's `weight`. On `hit_t1` the entry also moves
  from T1 to MRU of T2.
* On demotion by `REPLACE` from `T1` (or `T2`): the entry leaves the
  resident list as a ghost in `B1` (or `B2`) with
  `entry_weight = cum_weight` at the moment of demotion.
* On the miss-case "drop LRU of T1 directly" branch: the entry is
  fully evicted (it does NOT enter `B1`).
* On `evict`: the entry is fully removed from its T1/T2 list and
  does NOT enter B1/B2. Its `cum_weight` is lost.

## The REPLACE subroutine (weighted)

`REPLACE(x, c, p, in_b2)` is used by `access` cases 2-4.

```
if |T1| >= 1 and ((in_b2 and |T1| == p) or |T1| > p):
    pick victim = min-cum_weight entry of T1, LRU as tiebreak
    move victim -> MRU of B1 (with entry_weight = its cum_weight)
else:
    pick victim = min-cum_weight entry of T2, LRU as tiebreak
    move victim -> MRU of B2 (with entry_weight = its cum_weight)
```

"LRU as tiebreak" means: among the entries that share the smallest
`cum_weight` in the chosen list, select the one furthest from MRU
(the LRU-most of the tied set).

## Event processing

Events are processed strictly in input order. For each event the
binary records an audit row with `accepted` and `reason_ignored`,
and (when accepted) updates state and emits a `decisions` row.

### access(x, w)

Four cases, evaluated in this exact order:

1. **`x` in T1 or T2.** Outcome `hit_t1` or `hit_t2`. Remove `x`
   from its current list; insert at MRU of `T2` with
   `cum_weight = (old cum_weight) + w`. `p` unchanged.
2. **`x` in B1.** Outcome `ghost_hit_b1`. Set
   `delta = max(|B2| / |B1|, 1)` (integer division; `|B1| > 0`
   here). Set `p = min(p + delta, c)`. Run
   `REPLACE(x, c, p, in_b2 = false)`. Remove `x` from `B1`; insert
   at MRU of `T2` with `cum_weight = w`.
3. **`x` in B2.** Outcome `ghost_hit_b2`. Set
   `delta = max(|B1| / |B2|, 1)` (`|B2| > 0` here). Set
   `p = max(p - delta, 0)`. Run `REPLACE(x, c, p, in_b2 = true)`.
   Remove `x` from `B2`; insert at MRU of `T2` with `cum_weight = w`.
4. **`x` not in any list.** Outcome `miss`.
   * If `|T1| + |B1| == c`:
       * if `|T1| < c`: drop LRU of `B1` (plain LRU on B1; the
         dropped ghost's `entry_weight` is the `dropped_weight` of
         this decision row); then `REPLACE(x, c, p, false)`.
       * else (`|T1| == c`): drop the min-`cum_weight` entry of
         `T1` directly (LRU tiebreak), no REPLACE, no ghost. The
         dropped resident's `cum_weight` is the `dropped_weight`.
   * Else if `|T1| + |B1| < c` and
     `|T1| + |T2| + |B1| + |B2| >= c`:
       * if total `== 2c`: drop LRU of `B2` (plain LRU; the
         dropped ghost's `entry_weight` becomes `dropped_weight`).
       * Then `REPLACE(x, c, p, false)`.
   Insert `x` at MRU of `T1` with `cum_weight = w`.

In all four cases, the per-event decision row records:

* `replaced_key, replaced_from` -- the key demoted by `REPLACE`
  ("t1" or "t2"). Both `null` if no REPLACE ran.
* `replaced_weight` -- the `cum_weight` of the demoted entry at the
  moment of REPLACE. `null` if no REPLACE ran.
* `dropped_key, dropped_from` -- the key fully dropped in the miss
  case ("b1", "b2", or "t1"). All `null` otherwise.
* `dropped_weight` -- the dropped entry's stored weight at the
  moment of drop (`entry_weight` for B1/B2 drops; `cum_weight` for
  the T1 direct drop). `null` otherwise.
* `cum_weight_after` -- the `cum_weight` of the entry just installed
  or updated by this `access`.

### evict(x)

* If `x` is in `T1` or `T2`: remove it from its current list.
  Outcome `evicted`. `replaced_*` and `dropped_*` are all `null` for
  `evict` events; the removed key is identified by the decision
  row's `key` field. Ghost lists (`B1`, `B2`) and `p` are
  unchanged. `cum_weight_after` is `null` (the entry was destroyed,
  not updated).
* Else: reject with `reason_ignored = "unknown_resident"`.

### clear()

* If all four lists are empty: reject with
  `reason_ignored = "cache_empty"`.
* Otherwise: empty `T1`, `T2`, `B1`, `B2`; set `p = 0`. Outcome
  `cleared`. `replaced_*`, `dropped_*`, and `cum_weight_after` are
  `null`. The `key` field of the decision row is `null`.

## Invariants

* Rejected events never change cache state, `p`, or any
  `cum_weight`/`entry_weight`.
* `p` only changes on ghost hits (cases 2, 3) and on `clear`.
* The decision row's `t1_size, t2_size, b1_size, b2_size, p_after,
  cum_weight_after` reflect the state immediately **after** the
  event was applied.
