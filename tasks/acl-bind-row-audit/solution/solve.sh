#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_abr_build
cp "$SOL_DIR/main.go" /app/_abr_build/main.go
cp "$SOL_DIR/go.mod" /app/_abr_build/go.mod
cd /app/_abr_build
export PATH="/usr/local/go/bin:${PATH:-}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_abr_build/abr .

ABR_DATA_DIR="${ABR_DATA_DIR:-/app/abr_lab}" \
ABR_AUDIT_DIR="${ABR_AUDIT_DIR:-/app/abr_audit}" \
/app/_abr_build/abr
