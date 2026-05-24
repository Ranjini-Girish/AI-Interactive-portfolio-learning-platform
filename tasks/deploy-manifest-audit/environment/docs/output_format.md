# Audit report format

Output path: `/app/output/audit_report.json`

## summary

| Field | Type | Description |
|-------|------|-------------|
| manifest_count | int | JSON files in `/app/data/manifests/` |
| artifact_count | int | Entries in artifact registry |
| matched_deployments | int | Deployments linked to a registry artifact |
| unmatched_deployments | int | Deployments with no registry match |
| checksum_failures | int | Matched deployments whose sidecar hash mismatches registry |
| total_bytes_declared | int | Sum of `declared_size_bytes` across all manifest deployments |
| median_deploy_duration_sec | float | Median of `effective_duration_sec` over matched deployments (one decimal) |

## deployments

Sorted by `deployment_id` ascending. Only matched deployments appear.

## checksum_audit

| Field | Type |
|-------|------|
| verified | int |
| failed | int |
| failed_ids | string[] sorted |

## environment_overlay

| Field | Type |
|-------|------|
| conflicts | int | Keys whose value differs across overlay layers when merged in policy order |
| conflict_keys | string[] sorted |

Overlay merge order is `overlay_priority` in `/app/config/policy.json`.

## integrity_chain

| Field | Type |
|-------|------|
| chain_hash | string | SHA-256 hex of newline-joined artifact SHA-256 values |
| link_count | int | Number of hashes in the chain |

Chain includes only checksum-verified matched deployments, ordered by `deployment_id` ascending.
