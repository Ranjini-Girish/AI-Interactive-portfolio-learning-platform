#!/bin/bash
set -euo pipefail
source /app/lib/common.sh
ensure_audit_tmp

manifest_count=$(ls -1 /app/data/manifests/*.json | wc -l)
artifact_count=$(jq '.artifacts | length' "$AUDIT_TMP/registry.json")
matched_count=$(jq 'length' "$AUDIT_TMP/matched.json")
unmatched_count=$(cat "$AUDIT_TMP/unmatched.count")
checksum_failures=$(jq '.failed' "$AUDIT_TMP/checksum_audit.json")
total_declared=$(jq '[.[].declared_size_bytes] | add' "$AUDIT_TMP/deployments.json")

# BUG: lexicographic sort for median
durations=$(jq -r '.[].effective_duration_sec' "$AUDIT_TMP/matched.json" | sort)
count=$(echo "$durations" | grep -c . || echo 0)
if (( count % 2 == 1 )); then
  median=$(echo "$durations" | awk -v n="$count" 'NR == (n+1)/2 {print $1}')
else
  low=$(echo "$durations" | awk -v n="$count" 'NR == n/2 {print $1}')
  high=$(echo "$durations" | awk -v n="$count" 'NR == n/2 + 1 {print $1}')
  median=$(awk -v a="$low" -v b="$high" 'BEGIN { printf "%.1f", (a+b)/2 }')
fi

jq -n \
  --argjson manifest_count "$manifest_count" \
  --argjson artifact_count "$artifact_count" \
  --argjson matched_deployments "$matched_count" \
  --argjson unmatched_deployments "$unmatched_count" \
  --argjson checksum_failures "$checksum_failures" \
  --argjson total_bytes_declared "$total_declared" \
  --argjson median "$median" \
  '{manifest_count:$manifest_count, artifact_count:$artifact_count,
    matched_deployments:$matched_deployments, unmatched_deployments:$unmatched_deployments,
    checksum_failures:$checksum_failures, total_bytes_declared:$total_bytes_declared,
    median_deploy_duration_sec:$median}' > "$AUDIT_TMP/summary.json"
