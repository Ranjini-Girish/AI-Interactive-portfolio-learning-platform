#!/bin/bash
set -euo pipefail
source /app/lib/common.sh
ensure_audit_tmp

matched='[]'
unmatched=0

while IFS= read -r dep; do
  nref=$(echo "$dep" | jq -r '.norm_ref')
  art=$(jq -c --arg n "$nref" '.[] | select(.norm_id == $n) | .artifact' \
    "$AUDIT_TMP/artifacts_by_norm.json" | head -1)
  if [[ -z "$art" ]]; then
    unmatched=$((unmatched + 1))
    continue
  fi
  row=$(echo "$dep" | jq --argjson art "$art" \
    '. + {artifact_sha256: $art.sha256, actual_size_bytes: $art.size_bytes, bundle_path: $art.bundle_path}')
  matched=$(echo "$matched" | jq --argjson row "$row" '. + [$row]')
done < <(jq -c '.[]' "$AUDIT_TMP/deployments.json")

echo "$matched" | jq '.' > "$AUDIT_TMP/matched.json"
echo "$unmatched" > "$AUDIT_TMP/unmatched.count"
