#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_wca_build
cp "$SOL_DIR/main.go" /app/_wca_build/main.go
cd /app/_wca_build
if [ ! -f go.mod ]; then
  go mod init wca >/dev/null 2>&1
fi
export PATH="/usr/local/go/bin:${PATH:-}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_wca_build/wca .

WCA_DATA_DIR="${WCA_DATA_DIR:-/app/wasmcaps}" \
WCA_AUDIT_DIR="${WCA_AUDIT_DIR:-/app/audit}" \
/app/_wca_build/wca
