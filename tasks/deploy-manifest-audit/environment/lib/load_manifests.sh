#!/bin/bash
set -euo pipefail
source /app/lib/common.sh
ensure_audit_tmp

: > "$AUDIT_TMP/deployments.raw"

for manifest in /app/data/manifests/*.json; do
  count=$(jq '.deployments | length' "$manifest")
  for ((i = 0; i < count; i++)); do
    dep=$(jq -c ".deployments[$i]" "$manifest")
    dep_id=$(echo "$dep" | jq -r '.deployment_id')
    env=$(echo "$dep" | jq -r '.environment')
    ref=$(echo "$dep" | jq -r '.artifact_ref')
    build=$(echo "$dep" | jq -r '.build_duration_sec')
    deploy=$(echo "$dep" | jq -r '.deploy_duration_sec')
    declared=$(echo "$dep" | jq -r '.declared_size_bytes')
    overlay=$(echo "$dep" | jq -r '.overlay')
    # BUG: uses max instead of sum for effective duration
    if (( build > deploy )); then
      effective=$build
    else
      effective=$deploy
    fi
    norm_ref=$(normalize_id "$ref")
    jq -n \
      --arg id "$dep_id" \
      --arg env "$env" \
      --arg ref "$ref" \
      --arg nref "$norm_ref" \
      --argjson build "$build" \
      --argjson deploy "$deploy" \
      --argjson declared "$declared" \
      --argjson effective "$effective" \
      --arg overlay "$overlay" \
      '{deployment_id:$id, environment:$env, artifact_ref:$ref, norm_ref:$nref,
        build_duration_sec:$build, deploy_duration_sec:$deploy,
        declared_size_bytes:$declared, effective_duration_sec:$effective, overlay:$overlay}' \
      >> "$AUDIT_TMP/deployments.raw"
  done
done

jq -s '.' "$AUDIT_TMP/deployments.raw" > "$AUDIT_TMP/deployments.json"
