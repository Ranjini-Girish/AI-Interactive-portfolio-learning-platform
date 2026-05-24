#!/bin/bash
set -euo pipefail
source /app/lib/common.sh
ensure_audit_tmp

merged='{}'
conflicts='[]'

# BUG: glob order is alphabetical (base, production, staging) not policy priority
for overlay_file in /app/data/overlays/*.json; do
  data=$(cat "$overlay_file")
  keys=$(echo "$data" | jq -r 'keys[]')
  while IFS= read -r key; do
    val=$(echo "$data" | jq -c --arg k "$key" '.[$k]')
    old=$(echo "$merged" | jq -c --arg k "$key" '.[$k] // empty')
    if [[ -n "$old" && "$old" != "$val" ]]; then
      conflicts=$(echo "$conflicts" | jq --arg k "$key" '. + [$k]')
    fi
    merged=$(echo "$merged" | jq --arg k "$key" --argjson v "$val" '. + {($k): $v}')
  done <<< "$keys"
done

echo "$conflicts" | jq 'unique | sort' > "$AUDIT_TMP/overlay_conflicts.json"
echo "$merged" | jq '.' > "$AUDIT_TMP/overlay_merged.json"
