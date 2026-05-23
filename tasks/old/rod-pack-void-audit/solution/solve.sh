#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/rpv_tool
cp "$SOL_DIR/main.go" /app/rpv_tool/main.go
cp "$SOL_DIR/go.mod" /app/rpv_tool/go.mod
cd /app/rpv_tool
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/rpv_tool/rpvaudit .

RPV_DATA_DIR="${RPV_DATA_DIR:-/app/rod_lat}" \
RPV_AUDIT_DIR="${RPV_AUDIT_DIR:-/app/rod_audit}" \
/app/rpv_tool/rpvaudit
