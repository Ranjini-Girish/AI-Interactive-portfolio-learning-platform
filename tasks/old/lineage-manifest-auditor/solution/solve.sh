#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_lma_build
cp "$SOL_DIR/main.go" /app/_lma_build/main.go
cp "$SOL_DIR/go.mod" /app/_lma_build/go.mod
cd /app/_lma_build
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_lma_build/lma .

LMA_DATA_DIR="${LMA_DATA_DIR:-/app/lineage_manifests}" \
LMA_AUDIT_DIR="${LMA_AUDIT_DIR:-/app/audit}" \
/app/_lma_build/lma
