#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_lsca_build
cp "$SOL_DIR/main.go" /app/_lsca_build/main.go
cd /app/_lsca_build
if [ ! -f go.mod ]; then
  go mod init lsca >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_lsca_build/lsca .

LSCA_DATA_DIR="${LSCA_DATA_DIR:-/app/leases}" \
LSCA_AUDIT_DIR="${LSCA_AUDIT_DIR:-/app/audit}" \
/app/_lsca_build/lsca
