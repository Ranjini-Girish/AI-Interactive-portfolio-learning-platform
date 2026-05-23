# Closed Diagnostic Catalogue

Every diagnostic carries:

- `severity` -- exactly one of `"error"`, `"warning"`, `"notice"`.
- `severity_rank` -- looked up at runtime in `policy.severity_ranks`
  (`severity_ranks[severity]`); used as the primary sort key.
- `seq` -- the event `seq` that produced the diagnostic.
- `code` -- one of the codes below; no other strings are allowed.
- `key_id` -- the key identifier when applicable; `null` for
  catalogue-level events such as `E_INVALID_EVENT`.
- `evidence` -- a JSON object with the documented fields. Unspecified
  evidence fields are forbidden.

## Errors (severity `"error"`)

| code                      | when                                            | evidence                                     |
| ------------------------- | ----------------------------------------------- | -------------------------------------------- |
| `E_INVALID_EVENT`         | unknown `kind`, missing per-kind field, non-positive `max_uses` | `{"reason": "missing_field"\|"unknown_kind"\|"non_positive_max_uses"}` |
| `E_DUPLICATE_KEY`         | `key_install` collides with an existing key     | `{"prior_state": "<state>"}`                  |
| `E_ALGORITHM_UNKNOWN`     | `key_install` with `algorithm` not in policy    | `{"algorithm": "<value>"}`                    |
| `E_KEY_UNKNOWN`           | `encrypt` on a `key_id` the engine never saw    | `{}`                                          |
| `E_KEY_NOT_ACTIVE`        | `encrypt` on a `RETIRED` key                    | `{"key_state": "RETIRED"}`                    |
| `E_KEY_EXHAUSTED`         | `encrypt` on an `EXHAUSTED` key                 | `{}`                                          |
| `E_KEY_COMPROMISED`       | `encrypt` on a `COMPROMISED` key                | `{}`                                          |
| `E_NONCE_REUSE`           | `encrypt` repeats a `(key_id, nonce)` pair      | `{"first_seq": <int>, "first_tick": <int>}`   |
| `E_RETIRE_UNKNOWN`        | `key_retire` on an unknown key                  | `{}`                                          |
| `E_RETIRE_NOT_ACTIVE`     | `key_retire` on `EXHAUSTED` or `COMPROMISED`    | `{"key_state": "<state>"}`                    |
| `E_COMPROMISE_UNKNOWN`    | `key_compromise` on an unknown key              | `{}`                                          |

## Warnings (severity `"warning"`)

| code                       | when                                                                       | evidence                                       |
| -------------------------- | -------------------------------------------------------------------------- | ---------------------------------------------- |
| `W_KEY_NEAR_EXHAUSTION`    | first `encrypt` for which `uses_count / max_uses >= near_exhaustion_ratio` and the key has not yet hit `EXHAUSTED`; emitted **at most once per key** | `{"uses_count": <int>, "max_uses": <int>}`     |
| `W_RETIRE_ALREADY_RETIRED` | `key_retire` on a key already in `RETIRED`                                 | `{}`                                           |
| `W_COMPROMISE_REDUNDANT`   | `key_compromise` on a key already in `COMPROMISED`                         | `{}`                                           |

## Notices (severity `"notice"`)

| code                  | when                                                                       | evidence                                                                         |
| --------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `N_KEY_INSTALLED`     | `key_install` succeeds                                                     | `{"algorithm": "<algo>", "max_uses": <int>}`                                     |
| `N_KEY_RETIRED`       | `ACTIVE` key transitions to `RETIRED` via explicit retire                  | `{"trigger": "key_retire"}`                                                      |
| `N_KEY_IDLE_RETIRED`  | idle-retire sweep fires                                                    | `{"last_use_tick": <int>, "now": <int>}`                                         |
| `N_KEY_EXHAUSTED`     | `ACTIVE` key transitions to `EXHAUSTED` after a successful encrypt         | `{"uses_count": <int>, "max_uses": <int>}`                                       |
| `N_KEY_COMPROMISED`   | `ACTIVE` (or any non-`COMPROMISED`) key becomes `COMPROMISED`              | `{"trigger": "nonce_reuse"\|"key_compromise", ...}` (`reason`/`nonce` per case)  |

## Sort order

`diagnostics.json` ships an array sorted by the tuple:

```
(severity_rank, seq, code, key_id_or_empty)
```

`severity_rank` is the integer looked up in `policy.severity_ranks`
(`error=0, warning=1, notice=2` in the supplied corpus, but you MUST
read from the policy at runtime); `key_id_or_empty` is the empty
string for diagnostics with `key_id: null`.

No code outside this catalogue is allowed. Outputs that introduce
unknown codes, missing-evidence fields, or extra evidence keys are
non-conformant.
