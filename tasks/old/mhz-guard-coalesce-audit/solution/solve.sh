#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/sga_tool
cp "$SOL_DIR/main.go" /app/sga_tool/main.go
cp "$SOL_DIR/go.mod" /app/sga_tool/go.mod
cd /app/sga_tool
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/sga_tool/sgaudit .

SGA_DATA_DIR="${SGA_DATA_DIR:-/app/sga_data}" \
SGA_AUDIT_DIR="${SGA_AUDIT_DIR:-/app/sga_audit}" \
/app/sga_tool/sgaudit
