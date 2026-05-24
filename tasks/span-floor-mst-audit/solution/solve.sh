#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/sfm_tool
cp "$SOL_DIR/main.go" /app/sfm_tool/main.go
cp "$SOL_DIR/go.mod" /app/sfm_tool/go.mod
cd /app/sfm_tool
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/sfm_tool/sfmspan .

SFM_DATA_DIR="${SFM_DATA_DIR:-/app/sfm_lab}" \
SFM_AUDIT_DIR="${SFM_AUDIT_DIR:-/app/sfm_audit}" \
/app/sfm_tool/sfmspan
