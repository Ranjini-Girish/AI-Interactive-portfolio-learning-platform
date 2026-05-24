#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_jrma_build
cp "$SOL_DIR/main.go" /app/_jrma_build/main.go
cd /app/_jrma_build
if [ ! -f go.mod ]; then
  go mod init jrma >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_jrma_build/jrma .

JRMA_DATA_DIR="${JRMA_DATA_DIR:-/app/rate_merge_lab}" \
JRMA_AUDIT_DIR="${JRMA_AUDIT_DIR:-/app/audit}" \
/app/_jrma_build/jrma
