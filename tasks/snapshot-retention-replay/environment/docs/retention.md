# retention.md -- keep / prune algorithm

A `retention_run` event names a single dataset. The algorithm chooses
which snapshots in that dataset survive and which are pruned.

## Rule resolution

The simulator first selects an effective rule set:

- If `policy.datasets[dataset]` exists, use it verbatim.
- Otherwise use `policy.default_rules`.

Each rule is a non-negative integer; missing fields default to `0`.

If every effective rule is `0`, emit `W_NO_RULES_DEFINED` (with
`snapshot_id = null`). The retention run still executes -- every
non-held snapshot in the dataset will be pruned because no rule keeps
it.

## Bucket math

Four of the five rules group snapshots into time buckets and keep the
*latest* snapshot inside the most recent N buckets:

| rule           | bucket size (sec) |
|----------------|-------------------|
| `keep_hourly`  | 3600              |
| `keep_daily`   | 86400             |
| `keep_weekly`  | 604800            |
| `keep_monthly` | 2592000           |

For a snapshot whose `created_at_sec` is `t`, its bucket number under
rule `R` is `t // bucket_size(R)` (integer division, so `1210000 //
86400 == 14`).

For a given rule `R` with non-zero count `n`:

1. Group all snapshots in the dataset by bucket number.
2. Take the `n` largest distinct bucket numbers (so the most recent
   `n` buckets that contain at least one snapshot).
3. In each selected bucket, choose the snapshot with the largest
   `created_at_sec`. Break ties by id descending (the lexicographically
   *larger* id wins).
4. Mark each chosen snapshot as kept by `R`.

If the dataset has fewer distinct buckets than `n`, every existing
bucket is selected (this is not an error).

## `keep_last_n`

`keep_last_n` is the only rule that ignores buckets entirely. With
non-zero `n`, sort all snapshots in the dataset by `(created_at_sec
desc, id desc)` and mark the first `n` entries as kept by
`keep_last_n`.

## Held snapshots

Any snapshot whose `holders` list is non-empty at the moment of the
retention run is unconditionally kept. It receives `held` in its
`kept_by` list, in addition to any retention rule that also kept it.

## Final keep set

A snapshot is kept iff its `kept_by` set is non-empty. All others are
pruned: they are removed from `state` and from the `(dataset, name)`
index, and `snapshots_pruned_by_retention` is incremented for each.

## Empty datasets

If the dataset has no snapshots in `state` at the moment of the
retention run, emit `W_DATASET_EMPTY` (with `snapshot_id = null`)
**before** appending the `prune_log` entry. The entry is still
appended, with `kept = []` and `pruned = []`.

## `prune_log` entry

For every `retention_run`, append one record:

```
{
  "dataset": <string>,
  "kept": [<KeptEntry>, ...],
  "pruned": [<PrunedEntry>, ...],
  "seq": <int>
}
```

- `kept` is sorted by `(created_at_sec desc, id desc)`.
- `pruned` is sorted by `id asc`.
- `KeptEntry` contains `id`, `name`, `kept_by` (sorted ASCII array of
  rule names; possible values: `held`, `keep_daily`, `keep_hourly`,
  `keep_last_n`, `keep_monthly`, `keep_weekly`).
- `PrunedEntry` contains `id` and `name`.

The retention runs themselves appear in `runs[]` in chronological
order (i.e. the order their events fired).
