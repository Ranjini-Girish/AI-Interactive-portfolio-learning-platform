#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_leb_build
cp "$SOL_DIR/main.go" /app/_leb_build/main.go
cp "$SOL_DIR/go.mod" /app/_leb_build/go.mod
cd /app/_leb_build
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_leb_build/leb .

LEB_DATA_DIR="${LEB_DATA_DIR:-/app/leb_lab}" \
LEB_AUDIT_DIR="${LEB_AUDIT_DIR:-/app/audit}" \
/app/_leb_build/leb
