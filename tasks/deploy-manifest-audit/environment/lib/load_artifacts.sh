#!/bin/bash
set -euo pipefail
source /app/lib/common.sh
ensure_audit_tmp

cp /app/data/artifacts/registry.json "$AUDIT_TMP/registry.json"

jq '[.artifacts[] | {norm_id: (.artifact_id | ascii_upcase), artifact: .}]' \
  "$AUDIT_TMP/registry.json" > "$AUDIT_TMP/artifacts_by_norm.json"
