# Cipher suite lattice audit — normative contract

All paths below are rooted at `CSL_DATA_DIR` (default `/app/cipher_lattice`). Read `policy.json`, `pool_state.json`, `base_lattice/nodes.json`, `base_lattice/edges.json`, `incidents/incident_log.json`, every `suites/*.json`, every `hosts/*.json`, and every JSON file under `anchors/` for advisory context only; anchors never change merge math but must be listed in `summary.json` under `anchor_files` sorted lexicographically by relative POSIX path from the data root.

## Grease stripping (hosts)

For each host, copy `offered_suite_ids` in file order. Remove any element whose string value has the prefix given by `policy.cipher_grease_prefix`. Remove any element equal to the empty string if present. Count removed cipher tokens as `grease_stripped_cipher`. From `ech_client_configs`, drop every object whose `label` equals any string in `policy.ech_grease_labels` (case-sensitive equality). Count removed ECH objects as `grease_stripped_ech`. The post-strip ordered list drives downgrade screening. Retention uses the same post-strip list.

## Registry and sentinels

Suite metadata lives only in `suites/*.json`. Each suite record contains `suite_id`, `family`, `fs_band`, and integer `lattice_rank` (non-negative). Sentinel identifiers appear only inside `policy.sentinel_suite_ids`; they are never suite registry rows, never appear in lattice nodes, and are ignored for cap retention except for downgrade screening order.

## Incident ledger

Let `S` be the mutable revocation set, initially empty. Consider only incident `events` whose `seq` is less than or equal to `pool_state.current_seq`. Sort those events by increasing `seq`, breaking ties by the lexical order of `kind`, then by any `suite_id`, then by any `family` field present (empty string if absent). Apply in that order:

- `revoke_suite`: insert `suite_id` into `S`.
- `revoke_family`: insert every `suite_id` from the registry whose `family` equals the event `family` value.
- `clear_revocation`: delete the event `suite_id` from `S` if present.

## Host retention

For each host, start from the grease-stripped cipher list. A cipher id is **retained** if it exists in the registry, its `lattice_rank` is less than or equal to the host `cap_rank`, and its `suite_id` is not in `S`. Sentinel ids are never retained. `retained_count` is the count of retained ids. `strongest_retained_suite_id` is the retained registry id with the largest `lattice_rank`; if there is a tie, pick the lexicographically smallest `suite_id`; if none retained, use the empty string.

## Active lattice

`active_suite_ids` is the sorted set (ascending `suite_id`) of all retained ids across hosts. `merged_lattice.json` contains `nodes`, `edges`, and `meta`. Each `nodes` entry is an object with keys `family`, `fs_band`, `lattice_rank`, and `suite_id` (alphabetical key order inside each object) drawn from the registry for every id in `active_suite_ids`, sorted by `suite_id`. Each `edges` entry is an object with keys `strong`, `weak` (alphabetical key order) taken from `base_lattice/edges.json` where both endpoints appear in `active_suite_ids`; sort `edges` by `weak` then `strong`. `meta` contains `active_suite_count` equal to the length of `active_suite_ids`, `audit_window` copied from `pool_state.audit_window`, and `edge_count` equal to the length of `edges`.

## Forward secrecy tiers

Map `fs_band` through `policy.fs_band_to_tier` to obtain `base_tier` (`T1`, `T2`, or `T3`). Let `co_worsen` be true when `policy.fs_co_worsen` exists and, after incidents, at least one id in `S` has registry `family` equal to `policy.fs_co_worsen.guard_revoked_family`. When `co_worsen` is true, every active suite whose registry `family` appears in `policy.fs_co_worsen.affects_suite_families` must shift its displayed tier down by `policy.fs_co_worsen.steps` steps where one step is `T1`→`T2`, `T2`→`T3`, and `T3` remains `T3`. Suites outside that family list keep `effective_tier` equal to `base_tier`. When `co_worsen` is false, `effective_tier` equals `base_tier`. Emit `fs_tier_report.json` with key `suites`: a list sorted by `suite_id` of objects with keys `base_tier`, `effective_tier`, `family`, `suite_id` (alphabetical key order per object).

## Downgrade screen

If `policy.sentinel_trailing_strong_fs` is true, scan each host’s post-strip cipher list in order. Whenever indices `i < j` satisfy that list[i] is a member of `policy.sentinel_suite_ids` and list[j] is a registry suite whose `base_tier` (before co-worsen) is `T1`, emit a finding object with keys `host_id`, `index_sentinel`, `index_witness`, `pattern` (literal `sentinel_before_strong_fs`), `sentinel`, `witness` (alphabetical key order). Sort the `findings` array by `host_id`, then `index_sentinel`, then `index_witness`, then `sentinel`, then `witness`. If the flag is false, emit an empty `findings` list.

## Revocation lattice

`revocation_lattice.json` contains `revoked_suite_ids` sorted ascending, and `trace` sorted by `seq` ascending where each object has keys `kind`, `revoked_count_after`, `seq` (alphabetical key order) recording `S` cardinality after applying that event.

## Summary

`summary.json` keys: `active_suite_count` (same as meta), `anchor_files`, `audit_window`, `downgrade_finding_count`, `edge_count`, `hosts`, `revoked_suite_count`. `hosts` is sorted by `host_id` and each object includes `cap_rank`, `grease_stripped_cipher`, `grease_stripped_ech`, `host_id`, `retained_count`, `strongest_retained_suite_id` (alphabetical key order). `downgrade_finding_count` is the length of downgrade findings. `revoked_suite_count` is the size of `S` after processing.

## Canonical JSON on disk

Write exactly these five files under `CSL_AUDIT_DIR` (default `/app/audit/`): `downgrade_screen.json`, `fs_tier_report.json`, `merged_lattice.json`, `revocation_lattice.json`, `summary.json`. UTF-8, one trailing newline at EOF, indent two ASCII spaces, objects sorted by key at every depth, arrays sorted as specified per section.
