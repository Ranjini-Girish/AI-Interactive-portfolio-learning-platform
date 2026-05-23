#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_ebwa_build
cp "$SOL_DIR/main.go" /app/_ebwa_build/main.go
cd /app/_ebwa_build
if [ ! -f go.mod ]; then
  go mod init ebwa >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_ebwa_build/ebwa .

EBWA_DATA_DIR="${EBWA_DATA_DIR:-/app/export_batches}" \
EBWA_AUDIT_DIR="${EBWA_AUDIT_DIR:-/app/audit}" \
/app/_ebwa_build/ebwa
