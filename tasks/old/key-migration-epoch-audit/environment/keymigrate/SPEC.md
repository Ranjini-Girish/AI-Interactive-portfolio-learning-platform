# Key migration epoch audit

Inputs live beside this file. Read `policy.json`, `pool_state.json`, `incidents.json`, every `*.json` under `overlays/`, every `*.json` under `nodes/`, every `*.json` under `keys/`, every `*.json` under `migrations/`, and every non-empty line in `anchors/*.txt`. Paths under `ledger/` are packaging noise only.

## Canonical JSON

Emit every artifact as JSON with `indent=2`, `sort_keys=true`, `ensure_ascii=true`, `separators=(",", ": ")`, and exactly one trailing newline.

## Policy

- `epoch_span` (positive integer): width of each epoch bucket.
- `grace_epochs` (non-negative integer): node staleness threshold.
- `weight_floor` (integer): keys whose `weight` is strictly less than this value are `dropped` and never appear in migration rollups.

## Pool state

- `current_epoch`, `epoch_start`, `epoch_end` (integers): inclusive audit window on the epoch axis.

A **complete bucket** starts at `epoch_start + k * epoch_span` for `k = 0, 1, …` while `bucket_start + epoch_span - 1 <= epoch_end`. Partial trailing buckets are ignored everywhere.

## Overlay merge

Walk `overlays/*.json` in ascending ASCII basename order. Later files overwrite earlier values for the same key:

- `min_migrations_per_bucket` (integer, default 1)
- `bucket_cap` (integer, default unlimited)
- `exclude_nodes` (array of node_id strings): union every listed id

## Incidents and anchors

Parse `incidents.json` `events` with `kind`, `node_id`, `epoch`, and `accepted`. Collect `anchors/*.txt` lines as two whitespace-separated tokens: `node_id` then `forced_status`. Sort the combined anchor list by ascending `node_id`; when the same id appears more than once, the later line wins. Apply anchors only for ids present in the node set.

Accepted `node_compromise` events quarantine that node. `forced_status` value `hold` sets profile status `hold` when not quarantined.

## Migration application

Load every migration with `epoch_start <= epoch <= epoch_end`. For each key, sort its migrations by ascending `epoch`, then ascending `migration_id`. Start from the key file's `owner_node`. For each migration in order, if `from_node` equals the current owner, set the owner to `to_node` (this chains within the same epoch).

## Per-key profile

For each key file (basename without `.json` must equal `key_hash`):

- `dropped` is true when `weight < weight_floor`.
- `status` is `quarantined` when the initial owner, final owner, or any applied migration's `from_node` or `to_node` is a compromised node; else `hold` when the final owner has anchor `hold` and is not quarantined; else `dropped` when `dropped` is true; else `ok`.
- `final_owner` is the owner after all applied migrations.
- `migration_count` is the number of migrations that actually advanced ownership.

Sort the `keys` array by ascending `key_hash`.

## Per-node profile

For each node file (basename without `.json` must equal `node_id`):

- `stale_flag` is true when `current_epoch - last_seen_epoch > grace_epochs`.
- `status` is `quarantined` when the node is compromised, else `hold` when anchor forces hold, else `stale` when `stale_flag`, else `ok`.
- `keys_held` lists `key_hash` values whose `final_owner` equals this node and whose status is not `quarantined` or `dropped`, sorted ascending.
- `effective_weight` is JSON `null` when quarantined, else the node `weight`.

Sort the `nodes` array by ascending `node_id`.

## Migration rollups

For each complete bucket, collect migrations whose `epoch` lies inside the bucket day range, whose `from_node` and `to_node` are not in `exclude_nodes`, and whose key is not `quarantined` or `dropped`. Sort by `migration_id` ascending, keep the first `bucket_cap` entries, and emit objects with `migration_id`, `key_hash`, `from_node`, `to_node`, and `epoch`. Include the bucket only when at least `min_migrations_per_bucket` migrations remain after filtering. Sort the top-level `buckets` array by `epoch_start` ascending.

## Stale and compromise reports

`stale_report.json` lists every node with `stale_flag` true and status not `quarantined`, sorted by `node_id`, each row carrying `node_id` and `last_seen_epoch`.

`compromise_report.json` carries `nodes` (distinct compromised node_id values, sorted) and `keys` (quarantined key rows sorted by `key_hash` with `key_hash`, `final_owner`, and `initial_owner`).

## Summary

`summary.json` keys: `complete_epoch_starts`, `current_epoch`, `dropped_total`, `epoch_count`, `epoch_end`, `epoch_start`, `keys_total`, `quarantined_total`, `stale_total`. `complete_epoch_starts` lists every complete bucket start ascending. `dropped_total` counts keys with status `dropped`. `quarantined_total` counts keys with status `quarantined`. `stale_total` counts node profiles with `stale_flag` true.

## Outputs

Write five files to the audit directory:

1. `key_profiles.json` with keys `epoch_end`, `epoch_start`, then `keys`.
2. `migration_rollups.json` with keys `buckets`, `epoch_end`, `epoch_start`.
3. `stale_report.json` with key `nodes`.
4. `compromise_report.json` with keys `keys` then `nodes`.
5. `summary.json` as above.

## Tooling

Read `KME_DATA_DIR` defaulting to `/app/keymigrate` and `KME_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
