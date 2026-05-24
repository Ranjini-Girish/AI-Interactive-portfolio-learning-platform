#!/bin/bash
set -euo pipefail
source /app/lib/common.sh
ensure_audit_tmp

verified=0
failed=0
failed_ids='[]'
updated='[]'

while IFS= read -r row; do
  dep_id=$(echo "$row" | jq -r '.deployment_id')
  bundle=$(echo "$row" | jq -r '.bundle_path')
  expected=$(echo "$row" | jq -r '.artifact_sha256')
  chk_file="/app/data/checksums/${bundle//\//_}.sha256"
  on_disk=$(awk '{print $1}' "$chk_file")
  if [[ "$on_disk" == "$expected" ]]; then
    verified=$((verified + 1))
    updated=$(echo "$updated" | jq --argjson row "$row" '. + [$row + {checksum_ok: true}]')
  else
    failed=$((failed + 1))
    failed_ids=$(echo "$failed_ids" | jq --arg id "$dep_id" '. + [$id]')
    updated=$(echo "$updated" | jq --argjson row "$row" '. + [$row + {checksum_ok: false}]')
  fi
done < <(jq -c '.[]' "$AUDIT_TMP/matched.json")

echo "$updated" | jq '.' > "$AUDIT_TMP/matched_checked.json"
jq -n \
  --argjson verified "$verified" \
  --argjson failed "$failed" \
  --argjson failed_ids "$failed_ids" \
  '{verified:$verified, failed:$failed, failed_ids:$failed_ids}' > "$AUDIT_TMP/checksum_audit.json"

# BUG: chain from all checksum files on disk (ls order), includes failed hashes
chain_body=""
for chk in /app/data/checksums/*.sha256; do
  hash=$(awk '{print $1}' "$chk")
  chain_body+="${hash}"$'\n'
done
chain_body=${chain_body%$'\n'}
chain_hash=$(printf '%s' "$chain_body" | sha256sum | awk '{print $1}')
link_count=$(printf '%s' "$chain_body" | grep -c . || echo 0)

jq -n \
  --arg chain_hash "$chain_hash" \
  --argjson link_count "$link_count" \
  '{chain_hash:$chain_hash, link_count:$link_count}' > "$AUDIT_TMP/integrity_chain.json"
