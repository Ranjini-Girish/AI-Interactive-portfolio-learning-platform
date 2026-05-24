#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_tgc_build
cp "$SOL_DIR/tgc.go" /app/_tgc_build/main.go
cp "$SOL_DIR/go.mod" /app/_tgc_build/go.mod
cd /app/_tgc_build
export PATH="/usr/local/go/bin:${PATH}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_tgc_build/tgc .

TGC_DATA_DIR="${TGC_DATA_DIR:-/app/trapgrid}" \
TGC_AUDIT_DIR="${TGC_AUDIT_DIR:-/app/audit}" \
/app/_tgc_build/tgc
