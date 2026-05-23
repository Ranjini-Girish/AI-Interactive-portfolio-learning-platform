#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_tsl_build
cp "$SOL_DIR/main.go" /app/_tsl_build/main.go
cp "$SOL_DIR/go.mod" /app/_tsl_build/go.mod
cd /app/_tsl_build
export PATH="/usr/local/go/bin:${PATH}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_tsl_build/tsl .

TSL_DATA_DIR="${TSL_DATA_DIR:-/app/tslattice}" \
TSL_AUDIT_DIR="${TSL_AUDIT_DIR:-/app/audit}" \
/app/_tsl_build/tsl
