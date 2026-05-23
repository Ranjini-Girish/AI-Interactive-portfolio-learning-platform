#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_rwm_build
cp "$SOL_DIR/main.go" /app/_rwm_build/main.go
cd /app/_rwm_build
if [ ! -f go.mod ]; then
  go mod init rwm >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_rwm_build/rwm .

RWM_DATA_DIR="${RWM_DATA_DIR:-/app/rollupmerge}" \
RWM_AUDIT_DIR="${RWM_AUDIT_DIR:-/app/audit}" \
/app/_rwm_build/rwm
