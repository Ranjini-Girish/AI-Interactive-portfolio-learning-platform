#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_cmp_build
cp "$SOL_DIR/main.go" /app/_cmp_build/main.go
cd /app/_cmp_build
if [ ! -f go.mod ]; then
  go mod init cmp >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_cmp_build/cmp .

CMP_DATA_DIR="${CMP_DATA_DIR:-/app/cspmerge}" \
CMP_AUDIT_DIR="${CMP_AUDIT_DIR:-/app/audit}" \
/app/_cmp_build/cmp
