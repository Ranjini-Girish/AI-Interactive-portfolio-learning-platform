#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_gbl_build
cp "$SOL_DIR/bounty.go" /app/_gbl_build/main.go
cp "$SOL_DIR/go.mod" /app/_gbl_build/go.mod
cd /app/_gbl_build
export PATH="/usr/local/go/bin:${PATH:-}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_gbl_build/bounty .

GBL_DATA_DIR="${GBL_DATA_DIR:-/app/bounty}" \
GBL_AUDIT_DIR="${GBL_AUDIT_DIR:-/app/audit}" \
/app/_gbl_build/bounty
