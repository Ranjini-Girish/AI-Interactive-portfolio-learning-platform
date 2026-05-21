#!/bin/bash
set -euo pipefail

export PATH="/usr/local/go/bin:${PATH}"

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p /app/src /app/bin /app/audit

cp "$SOL_DIR/main.go" /app/src/main.go
cp "$SOL_DIR/go.mod" /app/src/go.mod

cd /app/src
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/bin/i2caudit .

IMX_BUS_DIR="${IMX_BUS_DIR:-/app/i2c_bus}" \
IMX_AUDIT_DIR="${IMX_AUDIT_DIR:-/app/audit}" \
/app/bin/i2caudit
