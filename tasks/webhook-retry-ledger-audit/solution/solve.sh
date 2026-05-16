#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_wrla_build
cp "$SOL_DIR/main.go" /app/_wrla_build/main.go
cd /app/_wrla_build
if [ ! -f go.mod ]; then
  go mod init wrla >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_wrla_build/wrla .

WRLA_DATA_DIR="${WRLA_DATA_DIR:-/app/webhooks}" \
WRLA_AUDIT_DIR="${WRLA_AUDIT_DIR:-/app/audit}" \
/app/_wrla_build/wrla
