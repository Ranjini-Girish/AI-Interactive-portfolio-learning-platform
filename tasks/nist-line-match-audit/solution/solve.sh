#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_nlma_build
cp "$SOL_DIR/lineaudit.go" /app/_nlma_build/main.go
cd /app/_nlma_build
if [ ! -f go.mod ]; then
  go mod init nlma >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_nlma_build/nlma .

NLMA_DATA_DIR="${NLMA_DATA_DIR:-/app/nist_lines}" \
NLMA_AUDIT_DIR="${NLMA_AUDIT_DIR:-/app/audit}" \
/app/_nlma_build/nlma
