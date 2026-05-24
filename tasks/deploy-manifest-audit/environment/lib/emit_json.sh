#!/bin/bash
set -euo pipefail
source /app/lib/common.sh
ensure_audit_tmp

# BUG: deployments sorted descending by deployment_id
deployments=$(jq '[.[] | {
  deployment_id,
  environment,
  artifact_sha256,
  declared_size_bytes,
  effective_duration_sec,
  risk_level
}]' "$AUDIT_TMP/classified.json" | jq 'sort_by(.deployment_id) | reverse')

jq -n \
  --argjson summary "$(cat "$AUDIT_TMP/summary.json")" \
  --argjson deployments "$deployments" \
  --argjson checksum_audit "$(cat "$AUDIT_TMP/checksum_audit.json")" \
  --argjson overlay "$(jq -n \
    --argjson conflicts "$(jq 'length' "$AUDIT_TMP/overlay_conflicts.json")" \
    --argjson keys "$(cat "$AUDIT_TMP/overlay_conflicts.json")" \
    '{conflicts:$conflicts, conflict_keys:$keys}')" \
  --argjson integrity "$(cat "$AUDIT_TMP/integrity_chain.json")" \
  '{summary:$summary, deployments:$deployments, checksum_audit:$checksum_audit,
    environment_overlay:$overlay, integrity_chain:$integrity}' \
  | jq '.' > /app/output/audit_report.json

printf '\n' >> /app/output/audit_report.json
