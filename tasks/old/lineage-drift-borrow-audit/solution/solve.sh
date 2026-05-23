#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_ldb_build
cp "$SOL_DIR/main.go" /app/_ldb_build/main.go
cp "$SOL_DIR/go.mod" /app/_ldb_build/go.mod
cd /app/_ldb_build
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_ldb_build/ldb .

LDB_DATA_DIR="${LDB_DATA_DIR:-/app/ldb_lab}" \
LDB_AUDIT_DIR="${LDB_AUDIT_DIR:-/app/audit}" \
/app/_ldb_build/ldb
