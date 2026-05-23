#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_ioc_build
cp "$SOL_DIR/ioc.go" /app/_ioc_build/main.go
cp "$SOL_DIR/go.mod" /app/_ioc_build/go.mod
cd /app/_ioc_build
export PATH="/usr/local/go/bin:${PATH:-}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_ioc_build/ioc .

IOC_DATA_DIR="${IOC_DATA_DIR:-/app/ioc_lab}" \
IOC_AUDIT_DIR="${IOC_AUDIT_DIR:-/app/audit}" \
/app/_ioc_build/ioc
