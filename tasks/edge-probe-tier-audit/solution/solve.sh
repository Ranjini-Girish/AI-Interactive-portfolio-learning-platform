#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_ept_build
cp "$SOL_DIR/main.go" /app/_ept_build/main.go
cd /app/_ept_build
if [ ! -f go.mod ]; then
  go mod init ept >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_ept_build/ept .

EPT_DATA_DIR="${EPT_DATA_DIR:-/app/edgeprobes}" \
EPT_AUDIT_DIR="${EPT_AUDIT_DIR:-/app/audit}" \
/app/_ept_build/ept
