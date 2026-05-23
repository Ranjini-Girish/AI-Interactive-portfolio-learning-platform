# Policy Chain — Evaluation Order and Match Predicates

`policies.json` carries an ORDERED list of policy objects. Policy
evaluation runs against a trace only after the trace passed the four
validation checks documented in `validation.md`. Within the chain the
FIRST matching policy wins: its `action` (for non-probabilistic types)
or its per-trace bucket result (for probabilistic) is the decision, its
`name` is recorded as `sampling_decisions[i].matched_policy`, and
`reason` is `"policy_match"`. If no policy matches, the decision is
`"drop"` with `reason = "no_policy_matched"` and `matched_policy = null`.

Every policy carries:

```
{
  "action": "keep" | "drop",   // ignored when type == "probabilistic"
  "name":   <unique string>,
  "type":   "status_match" | "latency" | "attribute" | "service" | "probabilistic"
  ... type-specific fields ...
}
```

## type: status_match

```
"statuses": [<status>, ...]              // subset of {"ok", "error", "timeout"}
"services": [<service>, ...] | optional  // when present, both clauses required
```

Matches if (any span in the trace has `status in statuses`) AND, when
`services` is present, (any span in the trace has `service in services`).
The two clauses can be satisfied by DIFFERENT spans -- e.g. a trace with
one error-status frontend span and one ok-status payments span matches a
status_match with `statuses=["error"]` + `services=["payments"]` even
though no single span carries both attributes.

## type: latency

```
"threshold_ms": <int >= 0>
"mode":         "any_span" | "root_span" | "trace_total"
```

Matches when:

- `any_span`: any span in the trace has `duration_ms >= threshold_ms`.
- `root_span`: the trace's root span (the one with
  `parent_span_id == null`) has `duration_ms >= threshold_ms`. If the
  trace has zero or multiple roots the policy does NOT match -- but
  multi_root would have already fired in validation so the policy chain
  is not reached in that case.
- `trace_total`: the trace's total span comparing
  `max(start_unix_ms + duration_ms) - min(start_unix_ms)` across all
  spans is `>= threshold_ms`.

## type: attribute

```
"key":    <string>
"values": [<string>, ...]
```

Matches if any span in the trace has `attributes[key]` present and its
string value is in `values`. Missing keys do NOT match the empty string
or any value.

## type: service

```
"services": [<service>, ...]
```

Matches if any span in the trace has `service in services`.

## type: probabilistic

```
"hash_seed":               <string>
"sampling_rate_per_mille": <int in [0, 1000]>
```

ALWAYS matches every trace it gates. The action is computed
deterministically from the trace_id:

```
H        = SHA256(hash_seed + ":" + trace_id)   // 32-byte digest, ASCII concat
bucket   = unsigned_big_endian(H[0:8]) modulo 1000
action   = "keep" if bucket < sampling_rate_per_mille else "drop"
```

The `action` field on the JSON policy object is ignored for
probabilistic. The string ":" between `hash_seed` and `trace_id` is a
literal single colon byte (`0x3A`).

`unsigned_big_endian(H[0:8])` is the unsigned 64-bit integer formed by
treating `H[0]` as the most-significant byte: `H[0]*2^56 + H[1]*2^48 +
... + H[7]`.

## Stats accounting

- `policy_stats[p].matched_count` increments every trace whose
  evaluation REACHED `p` and `p` matched, including the probabilistic
  case where the bucket-driven action ended up dropping the trace.
- `policy_stats[p].kept_count` / `dropped_count` split by the FINAL
  decision (kept vs dropped).
- A trace that hit cycle_detected, multi_root, incomplete_trace, or
  orphan_span never reaches the policy chain at all, so no
  policy_stats counter increments for that trace.

## Determinism

Policy match is deterministic on the input data. Two runs against the
same `/app/data/` produce byte-identical `policy_stats.json`.
