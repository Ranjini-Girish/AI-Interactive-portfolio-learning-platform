#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/wmc_tool
cp "$SOL_DIR/main.go" /app/wmc_tool/main.go
cp "$SOL_DIR/go.mod" /app/wmc_tool/go.mod
cd /app/wmc_tool
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/wmc_tool/wmcap .

WMC_DATA_DIR="${WMC_DATA_DIR:-/app/wmc_lab}" \
WMC_AUDIT_DIR="${WMC_AUDIT_DIR:-/app/wmc_audit}" \
/app/wmc_tool/wmcap
