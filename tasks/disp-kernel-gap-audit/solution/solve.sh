#!/bin/bash
set -euo pipefail
export PATH="/usr/local/go/bin:${PATH:-}"
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/dispbin /app/dispkg-src
cp "$SOL_DIR/dispkg.go" /app/dispkg-src/main.go
cp "$SOL_DIR/go.mod" /app/dispkg-src/go.mod
cd /app/dispkg-src
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/dispbin/dispkernel .
DISPK_DATA_DIR="${DISPK_DATA_DIR:-/app/disp_kernel_lab}" \
DISPK_AUDIT_DIR="${DISPK_AUDIT_DIR:-/app/audit}" \
mkdir -p "$DISPK_AUDIT_DIR"
/app/dispbin/dispkernel
