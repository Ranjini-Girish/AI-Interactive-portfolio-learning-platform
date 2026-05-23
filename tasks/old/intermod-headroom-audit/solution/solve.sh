#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/imha-src /app/bin
cp "$SOL_DIR/imha.go" /app/imha-src/main.go
cp "$SOL_DIR/go.mod" /app/imha-src/go.mod
cd /app/imha-src
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/bin/imha .

IMHA_DATA_DIR="${IMHA_DATA_DIR:-/app/imhr_lab}" \
IMHA_AUDIT_DIR="${IMHA_AUDIT_DIR:-/app/audit}" \
/app/bin/imha
