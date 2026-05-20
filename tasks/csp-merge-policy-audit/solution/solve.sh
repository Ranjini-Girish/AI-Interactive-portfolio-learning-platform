#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_cspma_build
cp "$SOL_DIR/main.go" /app/_cspma_build/main.go
cd /app/_cspma_build
if [ ! -f go.mod ]; then
  go mod init cspma >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_cspma_build/cspma .

CMP_DATA_DIR="${CMP_DATA_DIR:-/app/cspmerge}" \
CMP_AUDIT_DIR="${CMP_AUDIT_DIR:-/app/audit}" \
/app/_cspma_build/cspma
