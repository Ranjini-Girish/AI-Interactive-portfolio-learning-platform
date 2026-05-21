#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_pnl_build
cp "$SOL_DIR/pnl.go" /app/_pnl_build/main.go
cp "$SOL_DIR/go.mod" /app/_pnl_build/go.mod
cd /app/_pnl_build
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_pnl_build/pnl .

PNL_DATA_DIR="${PNL_DATA_DIR:-/app/pnl_lab}" \
PNL_AUDIT_DIR="${PNL_AUDIT_DIR:-/app/audit}" \
/app/_pnl_build/pnl
