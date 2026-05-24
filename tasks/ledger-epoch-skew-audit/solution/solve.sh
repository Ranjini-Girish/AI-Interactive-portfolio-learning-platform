#!/bin/bash
set -euo pipefail

export PATH="/usr/local/go/bin:${PATH}"

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_les_build
cp "$SOL_DIR/main.go" /app/_les_build/main.go
cp "$SOL_DIR/go.mod" /app/_les_build/go.mod
cd /app/_les_build
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_les_build/les .

LES_DATA_DIR="${LES_DATA_DIR:-/app/ledger_epoch}" \
LES_AUDIT_DIR="${LES_AUDIT_DIR:-/app/audit}" \
/app/_les_build/les
