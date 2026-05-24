#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_ibl_build
cp "$SOL_DIR/main.go" /app/_ibl_build/main.go
cd /app/_ibl_build
if [ ! -f go.mod ]; then
  go mod init ibl >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_ibl_build/ibl .

IBL_DATA_DIR="${IBL_DATA_DIR:-/app/ivybuild}" \
IBL_AUDIT_DIR="${IBL_AUDIT_DIR:-/app/audit}" \
/app/_ibl_build/ibl
