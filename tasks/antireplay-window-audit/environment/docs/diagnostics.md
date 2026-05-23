# Diagnostic Codes

Diagnostics are emitted as part of `packet_decisions.json` and
`replay_log.json`. The closed code set is exactly:

| Code                        | Severity | `sa_id`                  | Fired by |
|-----------------------------|----------|--------------------------|----------|
| `E_DUPLICATE_SA`            | error    | the colliding `sa_id`    | `add_sa` when the id already exists |
| `E_INVALID_WINDOW`          | error    | the requested `sa_id`    | `add_sa` or `rekey` when `window_size` is not in `policy.window_sizes_allowed` |
| `E_INVALID_INITIAL_TOP`     | error    | the requested `sa_id`    | `add_sa` when `top < 0` |
| `E_UNKNOWN_SA`              | error    | the missing `sa_id`      | `delete_sa`, `rekey`, or `recv` (only when `policy.on_unknown_sa == "drop"`) |
| `W_REPLAY`                  | warning  | the recv'd `sa_id`       | `recv` whose `esp_seq` is inside the window and the bit was already set (or `esp_seq == sa.top`) |
| `W_TOO_OLD`                 | warning  | the recv'd `sa_id`       | `recv` whose `esp_seq` falls below the window |
| `N_PASSIVE_CREATED`         | note     | the recv'd `sa_id`       | `recv` against an unknown SA when `policy.on_unknown_sa == "create_passive"` |

There are exactly seven legal codes. Any other code or severity is a bug.

`add_sa` priority is `E_DUPLICATE_SA` first, then `E_INVALID_WINDOW`, then
`E_INVALID_INITIAL_TOP`. A single failing `add_sa` event emits at most one
diagnostic.

`rekey` priority is `E_UNKNOWN_SA` first, then `E_INVALID_WINDOW`. A single
failing `rekey` event emits at most one diagnostic.

`recv` emits AT MOST one diagnostic per event in `packet_decisions.json`. The
`N_PASSIVE_CREATED` note that precedes a passive-create accept is recorded
inline in the same decision row (see `output_format.md` for the exact field).
