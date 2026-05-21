#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/dwr_tool
cp "$SOL_DIR/main.go" /app/dwr_tool/main.go
cp "$SOL_DIR/go.mod" /app/dwr_tool/go.mod
cd /app/dwr_tool
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/dwr_tool/dwrank .

DWR_DATA_DIR="${DWR_DATA_DIR:-/app/dwr_lab}" \
DWR_AUDIT_DIR="${DWR_AUDIT_DIR:-/app/dwr_audit}" \
/app/dwr_tool/dwrank
