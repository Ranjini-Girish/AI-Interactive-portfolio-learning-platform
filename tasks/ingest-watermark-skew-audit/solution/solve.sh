#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_iwsa_build
cp "$SOL_DIR/main.go" /app/_iwsa_build/main.go
cd /app/_iwsa_build
if [ ! -f go.mod ]; then
  go mod init iwsa >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_iwsa_build/iwsa .

IWSA_DATA_DIR="${IWSA_DATA_DIR:-/app/ingest_buffers}" \
IWSA_AUDIT_DIR="${IWSA_AUDIT_DIR:-/app/audit}" \
/app/_iwsa_build/iwsa
