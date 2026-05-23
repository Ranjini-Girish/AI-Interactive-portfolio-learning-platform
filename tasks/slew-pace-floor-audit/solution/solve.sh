#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_spa_build
cp "$SOL_DIR/main.go" /app/_spa_build/main.go
cp "$SOL_DIR/go.mod" /app/_spa_build/go.mod
cd /app/_spa_build
export PATH="/usr/local/go/bin:${PATH}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_spa_build/aud .

SPA_DATA_DIR="${SPA_DATA_DIR:-/app/pace_lab}" \
SPA_AUDIT_DIR="${SPA_AUDIT_DIR:-/app/audit}" \
/app/_spa_build/aud
