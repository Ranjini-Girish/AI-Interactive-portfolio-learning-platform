# TLS Cert Chain Auditor — Output Contract

This file is part of the read-only input dataset under `/app/certs/`. It defines exactly how the five output JSON files at `/app/audit/` must be derived from the inputs. Every requirement in this file is binding.

## Inputs

The dataset under `/app/certs/` contains:

- `pool_state.json` — `{"current_day": <int>, "audit_version": "<str>"}`. `current_day` is the audit reference day; all `not_before_day`, `not_after_day`, `produced_day` fields elsewhere are integers measured on the same scale.
- `chain_config.json` — global trust and policy configuration (described below).
- `incident_log.json` — `{"events": [...]}` (described below).
- `domains/<tier>/<domain>.json` — per-domain spec, with `<tier>` ∈ {`production`, `staging`, `internal`}. The set of domains audited is exactly the union of these directories.
- `leafs/<serial>.json` — synthetic leaf certificate metadata.
- `intermediates/<serial>.json` — synthetic intermediate certificate metadata.

`chain_config.json` has the shape:

```
{
  "trusted_roots": ["<serial>", ...],
  "expiry_warn_days": <int>,
  "ocsp_stale_days": <int>,
  "max_chain_depth": <int>,
  "key_size_min_per_tier": {"production": 2048, "staging": 2048, "internal": 1024},
  "san_policy_per_tier": {"production": "exact", "staging": "wildcard_ok", "internal": "cn_only"}
}
```

A domain file `domains/<tier>/<domain>.json` is `{"domain": "<str>", "tier": "<str>", "leaf_serial": "<str>", "expected_san": ["<str>", ...]}`.

A leaf or intermediate certificate file at `leafs/<serial>.json` or `intermediates/<serial>.json` is:

```
{
  "serial": "<str>",
  "subject_cn": "<str>",
  "san": ["<str>", ...],
  "issuer_serial": "<str>",
  "not_before_day": <int>,
  "not_after_day": <int>,
  "key_size": <int>,
  "signature_algo": "<str>"
}
```

`ocsp_responses.json` is `{"responses": [{"serial": "<str>", "status": "good"|"revoked"|"unknown", "produced_day": <int>}, ...]}`.

## Incident-log filtering

An entry of `incident_log.events` is **accepted** iff **all** of the following hold:

- `kind` is one of `"key_compromise"`, `"ca_compromise"`, `"audit_review"`.
- `day` is an integer and `day <= pool_state.current_day`.
- For `"key_compromise"`: `serial` matches the `serial` of some leaf certificate.
- For `"ca_compromise"`: `serial` matches the `serial` of some intermediate certificate or appears in `chain_config.trusted_roots`.
- For `"audit_review"`: `domain` is the `domain` field of some `domains/<tier>/<domain>.json` AND `target_verdict` is one of `"valid"`, `"untrusted"`.

Every other event is silently ignored and counted in `summary.ignored_incident_events`.

## OCSP interpretation

An OCSP response is **stale** iff `pool_state.current_day - produced_day > chain_config.ocsp_stale_days`. For each leaf (referenced by domain), look up the OCSP response with the matching `serial` (if multiple match, use the one with the largest `produced_day`; if still tied, the one whose `produced_day` is smallest in the input list — last-tied wins). The leaf's `ocsp_state` is:

- `"valid"` if the response has `status == "good"` and is not stale.
- `"revoked"` if the response has `status == "revoked"`.
- `"soft_fail"` if the response has `status == "unknown"` OR the matched response is stale OR no matching response exists.

## Chain validation

For each domain, attempt to walk the chain starting at the leaf:

1. Begin with the leaf identified by `domain.leaf_serial`. If `leafs/<leaf_serial>.json` is missing, the chain is `untrusted` with reason `leaf_missing`; the chain list is `[leaf_serial]` and stops.
2. Walk via `issuer_serial` to the corresponding `intermediates/<issuer>.json`. If the intermediate is missing AND the issuer is not in `trusted_roots`, the chain is `untrusted` with reason `intermediate_missing`.
3. Continue walking via `issuer_serial` until reaching a serial that appears in `chain_config.trusted_roots` (success), or until the walk would exceed `chain_config.max_chain_depth` (chain length, including leaf and root).
4. If the depth is exceeded before reaching a trusted root, the chain is `untrusted` with reason `chain_too_long`.

The chain list `chain` for a domain is the ordered list of serials encountered, starting at the leaf, ending at the trusted root (when the walk succeeds) or at the failure point (when the walk fails). Cycles in the issuer graph are treated as `untrusted` with reason `cycle_detected`; the chain list ends at the first repeated serial (inclusive).

## Validity windows and SAN matching

For each leaf:

- The leaf is **expired** iff `pool_state.current_day > leaf.not_after_day`.
- The leaf is **not_yet_valid** iff `pool_state.current_day < leaf.not_before_day`.
- `expiry_bucket` is `"expired"` if expired; `"warning"` if `0 <= leaf.not_after_day - pool_state.current_day <= chain_config.expiry_warn_days`; `"ok"` otherwise. `not_yet_valid` is bucketed as `"expired"`.
- The leaf's `key_size_ok` is true iff `leaf.key_size >= chain_config.key_size_min_per_tier[domain.tier]`.

SAN matching depends on tier:

- `production` (`"exact"`): every entry of `domain.expected_san` must appear (case-sensitively) in `leaf.san`. Wildcards are not matched.
- `staging` (`"wildcard_ok"`): every entry of `domain.expected_san` must either appear in `leaf.san`, or be matched by a wildcard pattern in `leaf.san` of the form `*.<rest>` where `<expected> == "<host>.<rest>"` (single-label wildcard).
- `internal` (`"cn_only"`): only `leaf.subject_cn` matters; every entry of `domain.expected_san` must equal `leaf.subject_cn`.

If SAN matching fails, the leaf has `san_ok == false`.

## Per-domain verdict

Compute a preliminary verdict for each domain in the order below; the **first** matching label wins:

- `"chain_unreachable"` — the chain walk failed (any of `leaf_missing`, `intermediate_missing`, `chain_too_long`, `cycle_detected`).
- `"expired"` — the leaf is expired or not yet valid.
- `"revoked"` — `ocsp_state == "revoked"`.
- `"untrusted"` — `key_size_ok` is false OR `san_ok` is false.
- `"warning"` — `expiry_bucket == "warning"` OR `ocsp_state == "soft_fail"`.
- `"valid"` — none of the above.

## Compromise cascade (cross-cutting)

For a leaf with at least one accepted `key_compromise` event, the domain's verdict becomes `"compromised"` overriding any preliminary verdict.

For an intermediate or root with at least one accepted `ca_compromise` event:

- Every domain whose chain walk visits that serial (anywhere in `chain`, leaf to root inclusive) gets verdict `"compromised"` overriding any preliminary verdict.
- Every other domain whose chain shares **at least one** intermediate (not a root, not the leaf) with a compromised chain gets verdict `"tainted"` overriding any preliminary verdict that is not already `"compromised"`. Tainting does not propagate transitively beyond one shared intermediate.

After the compromise cascade, an accepted `audit_review` event with the largest `day` for a given domain (ties broken by largest list index) sets the final verdict to `target_verdict`, **unless** the domain is currently `"compromised"` (compromise overrides audit_review unconditionally). For non-compromised domains, whenever such a winning event exists, `audit_review_override` must appear in that domain's `reasons` in `/app/audit/chain_audit.json`, including when `target_verdict` equals the preliminary verdict.

## Output schemas

All five outputs are written under `/app/audit/`. List ordering is part of the contract.

### `/app/audit/chain_audit.json`

```
{"domains": [{"domain": "<str>", "tier": "<str>", "verdict": "valid"|"warning"|"expired"|"revoked"|"untrusted"|"chain_unreachable"|"compromised"|"tainted", "chain": ["<serial>", ...], "reasons": ["<str>", ...]}]}
```

`domains` is sorted by `domain` ascending. `reasons` is sorted ascending and contains every applicable label from the table below; the `reasons` list is collected even when one of them already determined the preliminary verdict (for example, a chain whose walk fails AND whose key size is too small lists both reasons, even though only the first label decides the preliminary verdict). For `valid` verdicts that were not produced via `audit_review_override`, `reasons` is the empty list. The `chain` list includes the leaf as the first element and (when the walk succeeds) the trusted root as the last element.

| reason label              | applies when                                                                                                                                     |
|---------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| `leaf_missing`            | the leaf JSON file does not exist                                                                                                                |
| `intermediate_missing`    | the chain walk hits a serial that is neither in `intermediates/` nor in `trusted_roots`                                                          |
| `chain_too_long`          | the chain walk would exceed `max_chain_depth` before anchoring in a trusted root                                                                 |
| `cycle_detected`          | the chain walk revisits a serial it has already seen                                                                                             |
| `expired`                 | `current_day > leaf.not_after_day`                                                                                                               |
| `not_yet_valid`           | `current_day < leaf.not_before_day`                                                                                                              |
| `revoked`                 | the leaf's `ocsp_state` is `"revoked"`                                                                                                           |
| `key_size_too_small`      | `leaf.key_size < key_size_min_per_tier[domain.tier]`                                                                                             |
| `san_mismatch`            | SAN matching for the domain's tier policy fails                                                                                                  |
| `expiry_warning`          | `0 <= leaf.not_after_day - current_day <= expiry_warn_days`                                                                                      |
| `ocsp_soft_fail`          | the leaf's `ocsp_state` is `"soft_fail"`                                                                                                         |
| `key_compromise`          | the leaf has at least one accepted `key_compromise` event                                                                                        |
| `ca_compromise`           | the chain visits an intermediate or root that has an accepted `ca_compromise` event, OR the chain shares an intermediate with such a compromised chain |
| `audit_review_override`   | a non-compromised domain has a winning accepted `audit_review` event after the tie-break above, including when `target_verdict` equals the preliminary verdict |

### `/app/audit/expiry_report.json`

```
{"buckets": {"ok": [{"domain": "<str>", "days_to_expiry": <int>}, ...], "warning": [...], "expired": [...]}}
```

Each bucket list is sorted by `(days_to_expiry ascending, domain ascending)`. `days_to_expiry = leaf.not_after_day - pool_state.current_day`; for `expired` and `not_yet_valid` leafs this can be negative or refer to a future not_before_day.

### `/app/audit/ocsp_summary.json`

```
{"by_state": {"valid": <int>, "revoked": <int>, "soft_fail": <int>}, "details": [{"domain": "<str>", "leaf_serial": "<str>", "ocsp_state": "<str>"}]}
```

`details` is sorted by `domain` ascending. `by_state` has all three keys.

### `/app/audit/ca_risk.json`

```
{"intermediates": [{"serial": "<str>", "trusted_root_anchor": "<serial>"|null, "compromised": <bool>, "domains_signed": <int>, "tainted_domains": ["<str>", ...]}]}
```

`intermediates` is sorted by `serial` ascending and lists every intermediate file under `intermediates/`. `trusted_root_anchor` is the `serial` (in `trusted_roots`) the intermediate's chain reaches, or `null` if the chain does not anchor in any trusted root. `domains_signed` is the count of domains whose chain visits this intermediate. `tainted_domains` is sorted ascending and lists domains whose final verdict is `"tainted"` due to sharing this intermediate; `compromised` itself is true when the intermediate has an accepted `ca_compromise` event.

### `/app/audit/summary.json`

```
{"current_day": <int>, "audit_version": "<str>", "total_domains": <int>, "total_intermediates": <int>, "ignored_incident_events": <int>, "by_verdict": {"valid": <int>, "warning": <int>, "expired": <int>, "revoked": <int>, "untrusted": <int>, "chain_unreachable": <int>, "compromised": <int>, "tainted": <int>}, "by_ocsp_state": {"valid": <int>, "revoked": <int>, "soft_fail": <int>}, "compromised_cas": ["<serial>", ...]}
```

`compromised_cas` is sorted ascending. Every key in `by_verdict` and `by_ocsp_state` must appear with an integer value (zero if absent).

## Canonical encoding

Every output JSON file is encoded with `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)` followed by exactly one trailing newline byte. Two correct implementations of this contract must produce byte-identical output for the same input. Do not modify any file under `/app/certs/` while computing the report.
