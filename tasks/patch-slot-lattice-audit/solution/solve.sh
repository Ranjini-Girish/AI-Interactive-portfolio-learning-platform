#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_psla_build
cp "$SOL_DIR/main.go" /app/_psla_build/main.go
cd /app/_psla_build
if [ ! -f go.mod ]; then
  go mod init psla >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_psla_build/psla .

PSLA_DATA_DIR="${PSLA_DATA_DIR:-/app/patch_slots}" \
PSLA_AUDIT_DIR="${PSLA_AUDIT_DIR:-/app/audit}" \
/app/_psla_build/psla
