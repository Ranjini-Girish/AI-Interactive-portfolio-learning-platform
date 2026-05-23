# Output Format

All five output files are canonical JSON: UTF-8, ASCII-only, two-space
indent, keys lexicographically sorted at every depth, single trailing
newline. They are byte-exactly the result of
`json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"`.

## `key_states.json`

```json
{
  "keys": [
    {
      "algorithm": "aes-gcm-128",
      "compromised_seq": null,
      "exhausted_seq": null,
      "installed_seq": 0,
      "key_id": "k-alpha",
      "last_use_tick": 12,
      "max_uses": 100,
      "retired_seq": null,
      "state": "ACTIVE",
      "uses_count": 3
    },
    ...
  ]
}
```

`keys` is sorted by `key_id` ASCII ascending. `state` is one of
`ACTIVE`, `RETIRED`, `EXHAUSTED`, `COMPROMISED`. The four `*_seq`
fields are either an integer (when the key reached that state) or
`null`; exactly the matching one is non-`null` for terminal states
(except `COMPROMISED` always has `compromised_seq` set).

## `encryption_log.json`

```json
{
  "encryptions": [
    {
      "key_id": "k-alpha",
      "nonce": 42,
      "outcome": "accepted",
      "reason": null,
      "seq": 5,
      "tick": 10
    },
    {
      "key_id": "k-alpha",
      "nonce": 42,
      "outcome": "rejected",
      "reason": "NONCE_REUSE",
      "seq": 9,
      "tick": 11
    },
    ...
  ]
}
```

`encryptions` is sorted by `seq` ascending. `outcome` is `"accepted"`
or `"rejected"`. `reason` is `null` when `outcome == "accepted"` and
one of `UNKNOWN_KEY`, `RETIRED`, `EXHAUSTED`, `COMPROMISED`,
`NONCE_REUSE` when rejected.

## `audit_log.json`

```json
{
  "transitions": [
    {
      "evidence": {"algorithm": "aes-gcm-128", "max_uses": 100},
      "key_id": "k-alpha",
      "kind": "installed",
      "seq": 0,
      "tick": 0
    },
    {
      "evidence": {"trigger": "key_retire"},
      "key_id": "k-alpha",
      "kind": "retired",
      "seq": 22,
      "tick": 25
    },
    ...
  ]
}
```

`transitions` is sorted by `(seq, key_id)` ascending. `kind` is one of
`installed`, `retired`, `idle_retired`, `exhausted`, `compromised`.
`evidence` mirrors the matching diagnostic's evidence object.

## `diagnostics.json`

```json
{
  "diagnostics": [
    {
      "code": "E_NONCE_REUSE",
      "evidence": {"first_seq": 5, "first_tick": 10},
      "key_id": "k-alpha",
      "seq": 9,
      "severity": "error",
      "severity_rank": 0
    },
    ...
  ]
}
```

`diagnostics` is sorted by
`(severity_rank, seq, code, key_id_or_empty)`.

## `summary.json`

```json
{
  "totals": {
    "encryptions_accepted": 17,
    "encryptions_rejected": 3,
    "encryptions_total": 20,
    "errors": 4,
    "events_total": 28,
    "keys_total": 5,
    "notices": 9,
    "warnings": 2
  }
}
```

`keys_total` counts every key the engine ever registered (seed +
successfully installed). `events_total` is the number of input
events (ignored or otherwise).
