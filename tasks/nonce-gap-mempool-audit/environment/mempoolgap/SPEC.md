Normative contract for the mempool nonce-gap audit. Inputs are UTF-8 JSON with ASCII-only strings. Outputs are UTF-8 JSON, ASCII-only, two-space indentation, recursively sorted object keys at every depth, no trailing spaces at line ends, and exactly one trailing newline after each root closing brace.

Read `policy.json` for integer `gap_limit` (positive), integer `warmup_steps` (non-negative), and float `replace_boost` (at least 1.0). Read `manifest.json` for `channel_tag` and `active_channel`. When they differ, effective gap limit is `max(1, round(gap_limit * 0.5))`. Read `epochs.json` for integer `current_epoch`. Read `txs.json` for array `txs` with integer `step`, string `account_id`, integer `nonce`, float `fee`, and `kind` in `submit`, `replace`, or `cancel`.

Enumerate every `*.json` under `accounts/`. Each account has string `account_id`, integer `base_nonce`, and integer `epoch`. An account is stale when `epoch` is strictly less than `current_epoch - 1`. Packaging under `anchors/`, `ancillary/`, `meta/`, and `grid/` is ignored.

Track per-account `expected_nonce` starting at `base_nonce` and optional `pending_fee` after a gap submit. Process txs in ascending `step`, then `account_id`. Unknown account ids yield `unknown_account`. Warmup and stale rows yield `warmup_skipped` or `stale_skipped` without nonce updates.

For `submit` on active accounts after warmup: when `nonce` equals `expected_nonce`, advance `expected_nonce` by one and clear `pending_fee`. When `nonce` is less than `expected_nonce`, emit `nonce_replay`. When `nonce` is greater than `expected_nonce` but at most `expected_nonce + gap_limit`, set `pending_fee` to `fee` and set `expected_nonce` to `nonce + 1`. When `nonce` exceeds `expected_nonce + gap_limit`, emit `gap_violation`.

For `replace`: when no `pending_fee`, outcome is `replace_rejected`. When `fee >= pending_fee * replace_boost`, update `pending_fee` and outcome is `replace_accepted`; otherwise `replace_rejected`. For `cancel`, clear `pending_fee` with outcome `cancel_ok`.

Emit `tx_outcomes.json` with `txs` in processing order (account_id, fee, kind, nonce, outcome, stale, step). Emit `mempool_violations.json` with `violations` sorted by step then account_id for every non-ok violation row. Emit `account_states.json` with `accounts` sorted by account_id (account_id, base_nonce, epoch, final_nonce, stale). Emit `summary.json` with totals and effective_gap_limit.

Read `NGM_DATA_DIR` defaulting to `/app/mempoolgap` and `NGM_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
