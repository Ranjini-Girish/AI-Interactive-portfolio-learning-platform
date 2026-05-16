#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/bin /app/_sbwa_build
cp "$SOL_DIR/main.go" /app/_sbwa_build/main.go
cd /app/_sbwa_build
if [ ! -f go.mod ]; then
  go mod init sbwa >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/bin/slo-burn-auditor .

SBWA_DATA_DIR="${SBWA_DATA_DIR:-/app/slo-matrix}" \
SBWA_AUDIT_DIR="${SBWA_AUDIT_DIR:-/app/audit}" \
/app/bin/slo-burn-auditor
