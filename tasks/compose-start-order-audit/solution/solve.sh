#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_csoa_build
cp "$SOL_DIR/main.go" /app/_csoa_build/main.go
cd /app/_csoa_build
if [ ! -f go.mod ]; then
  go mod init csoa >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_csoa_build/csoa .

CSOA_DATA_DIR="${CSOA_DATA_DIR:-/app/compose_plans}" \
CSOA_AUDIT_DIR="${CSOA_AUDIT_DIR:-/app/audit}" \
/app/_csoa_build/csoa
