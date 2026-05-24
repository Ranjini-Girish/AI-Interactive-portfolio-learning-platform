#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_srl_build
cp "$SOL_DIR/main.go" /app/_srl_build/main.go
cp "$SOL_DIR/go.mod" /app/_srl_build/go.mod
cd /app/_srl_build
export PATH="/usr/local/go/bin:${PATH:-}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_srl_build/srl .

SRL_DATA_DIR="${SRL_DATA_DIR:-/app/srl_lab}" \
SRL_AUDIT_DIR="${SRL_AUDIT_DIR:-/app/srl_audit}" \
/app/_srl_build/srl
