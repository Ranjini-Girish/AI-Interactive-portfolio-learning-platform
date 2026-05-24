#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_hsg_build
cp "$SOL_DIR/main.go" /app/_hsg_build/main.go
cp "$SOL_DIR/go.mod" /app/_hsg_build/go.mod
cd /app/_hsg_build
export PATH="/usr/local/go/bin:${PATH:-}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_hsg_build/hsg .

HSG_DATA_DIR="${HSG_DATA_DIR:-/app/hsg_lab}" \
HSG_AUDIT_DIR="${HSG_AUDIT_DIR:-/app/hsg_audit}" \
/app/_hsg_build/hsg
