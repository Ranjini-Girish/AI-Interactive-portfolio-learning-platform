#!/bin/bash
set -euo pipefail

export AUDIT_TMP=/tmp/audit
mkdir -p /app/output "$AUDIT_TMP"

source /app/lib/common.sh
ensure_audit_tmp

/app/lib/load_manifests.sh
/app/lib/load_artifacts.sh
/app/lib/merge_overlay.sh
/app/lib/match_deployments.sh
/app/lib/checksum_audit.sh
/app/lib/risk_classify.sh
/app/lib/aggregate_stats.sh
/app/lib/emit_json.sh
