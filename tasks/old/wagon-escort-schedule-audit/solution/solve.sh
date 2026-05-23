#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/src /app/bin /app/_wesa_build
cp "$SOL_DIR/main.go" /app/_wesa_build/main.go
cp "$SOL_DIR/main.go" /app/src/main.go
cd /app/_wesa_build
if [ ! -f go.mod ]; then
  go mod init wesa >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/bin/escort-scheduler .

WESA_DATA_DIR="${WESA_DATA_DIR:-/app/escort}" \
WESA_AUDIT_DIR="${WESA_AUDIT_DIR:-/app/schedule}" \
/app/bin/escort-scheduler
