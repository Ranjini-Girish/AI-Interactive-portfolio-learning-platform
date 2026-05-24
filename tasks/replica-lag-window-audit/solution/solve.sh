#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_rla_build
cp "$SOL_DIR/replag.go" /app/_rla_build/main.go
cp "$SOL_DIR/go.mod" /app/_rla_build/go.mod
cd /app/_rla_build
export PATH="/usr/local/go/bin:${PATH:-}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_rla_build/replag .

RLA_DATA_DIR="${RLA_DATA_DIR:-/app/replag}" \
RLA_AUDIT_DIR="${RLA_AUDIT_DIR:-/app/audit}" \
/app/_rla_build/replag
