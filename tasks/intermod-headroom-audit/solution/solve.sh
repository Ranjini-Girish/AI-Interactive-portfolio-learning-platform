#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_imha_build
cp "$SOL_DIR/imha.go" /app/_imha_build/main.go
cp "$SOL_DIR/go.mod" /app/_imha_build/go.mod
cd /app/_imha_build
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_imha_build/imha .

IMHA_DATA_DIR="${IMHA_DATA_DIR:-/app/imhr_lab}" \
IMHA_AUDIT_DIR="${IMHA_AUDIT_DIR:-/app/audit}" \
/app/_imha_build/imha
