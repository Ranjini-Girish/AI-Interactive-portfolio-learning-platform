#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_vqb_build
cp "$SOL_DIR/main.go" /app/_vqb_build/main.go
cp "$SOL_DIR/go.mod" /app/_vqb_build/go.mod
cd /app/_vqb_build
export PATH="/usr/local/go/bin:${PATH}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_vqb_build/vqb .

VQB_DATA_DIR="${VQB_DATA_DIR:-/app/vqb_lab}" \
VQB_AUDIT_DIR="${VQB_AUDIT_DIR:-/app/audit}" \
/app/_vqb_build/vqb
