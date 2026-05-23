#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_kvepochtrima_build
cp "$SOL_DIR/main.go" /app/_kvepochtrima_build/main.go
cp "$SOL_DIR/go.mod" /app/_kvepochtrima_build/go.mod
cd /app/_kvepochtrima_build
export PATH="/usr/local/go/bin:${PATH}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_kvepochtrima_build/aud .

KET_DATA_DIR="${KET_DATA_DIR:-/app/ket_lab}" \
KET_AUDIT_DIR="${KET_AUDIT_DIR:-/app/audit}" \
/app/_kvepochtrima_build/aud
