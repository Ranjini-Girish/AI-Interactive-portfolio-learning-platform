#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_gcw_build
cp "$SOL_DIR/main.go" /app/_gcw_build/main.go
cp "$SOL_DIR/go.mod" /app/_gcw_build/go.mod
cd /app/_gcw_build
export PATH="/usr/local/go/bin:${PATH}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_gcw_build/gcw .

GCW_DATA_DIR="${GCW_DATA_DIR:-/app/gradclip}" \
GCW_AUDIT_DIR="${GCW_AUDIT_DIR:-/app/audit}" \
/app/_gcw_build/gcw
