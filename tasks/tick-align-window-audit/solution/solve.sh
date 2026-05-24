#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_taw_build
cp "$SOL_DIR/taw.go" /app/_taw_build/main.go
cp "$SOL_DIR/go.mod" /app/_taw_build/go.mod
cd /app/_taw_build
export PATH="/usr/local/go/bin:${PATH}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_taw_build/taw .

TAW_DATA_DIR="${TAW_DATA_DIR:-/app/taw_lab}" \
TAW_AUDIT_DIR="${TAW_AUDIT_DIR:-/app/audit}" \
/app/_taw_build/taw
