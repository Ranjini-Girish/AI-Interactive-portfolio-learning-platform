#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_tsm_build
cp "$SOL_DIR/main.go" /app/_tsm_build/main.go
cp "$SOL_DIR/go.mod" /app/_tsm_build/go.mod
cd /app/_tsm_build
export PATH="/usr/local/go/bin:${PATH}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_tsm_build/tsm .

TSM_DATA_DIR="${TSM_DATA_DIR:-/app/tracespan}" \
TSM_AUDIT_DIR="${TSM_AUDIT_DIR:-/app/audit}" \
/app/_tsm_build/tsm
