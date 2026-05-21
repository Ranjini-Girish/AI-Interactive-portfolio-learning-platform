#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_psha_build
cp "$SOL_DIR/main.go" /app/_psha_build/main.go
cp "$SOL_DIR/go.mod" /app/_psha_build/go.mod
cd /app/_psha_build
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_psha_build/psha .

PSHA_DATA_DIR="${PSHA_DATA_DIR:-/app/psh_lab}" \
PSHA_AUDIT_DIR="${PSHA_AUDIT_DIR:-/app/audit}" \
/app/_psha_build/psha
