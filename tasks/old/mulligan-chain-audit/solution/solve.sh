#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_mca_build
cp "$SOL_DIR/main.go" /app/_mca_build/main.go
cd /app/_mca_build
if [ ! -f go.mod ]; then
  go mod init mca >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_mca_build/mca .

MCA_DATA_DIR="${MCA_DATA_DIR:-/app/mulligan_pool}" \
MCA_AUDIT_DIR="${MCA_AUDIT_DIR:-/app/audit}" \
/app/_mca_build/mca
