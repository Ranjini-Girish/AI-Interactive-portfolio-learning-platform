#!/bin/bash
set -euo pipefail
source /app/lib/common.sh
ensure_audit_tmp

threshold=$(read_policy_field risk_drift_threshold)
medium=$(read_policy_field medium_drift_threshold)
classified='[]'

while IFS= read -r row; do
  declared=$(echo "$row" | jq -r '.declared_size_bytes')
  actual=$(echo "$row" | jq -r '.actual_size_bytes')
  drift_pct=$(awk -v d="$declared" -v a="$actual" 'BEGIN {
    if (a == 0) print 0; else { diff=(d>a)?d-a:a-d; print diff / a * 100 }
  }')
  # BUG: compares percentage to fraction thresholds (5 vs 0.05)
  if awk -v p="$drift_pct" -v t="$threshold" 'BEGIN { exit !(p > t) }'; then
    risk="high"
  elif awk -v p="$drift_pct" -v m="$medium" 'BEGIN { exit !(p > m) }'; then
    risk="medium"
  else
    risk="low"
  fi
  classified=$(echo "$classified" | jq --arg risk "$risk" --argjson row "$row" \
    '. + [$row + {risk_level: $risk}]')
done < <(jq -c '.[]' "$AUDIT_TMP/matched_checked.json")

echo "$classified" | jq '.' > "$AUDIT_TMP/classified.json"
