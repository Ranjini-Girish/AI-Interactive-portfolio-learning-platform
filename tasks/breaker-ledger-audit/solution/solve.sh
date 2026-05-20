#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_cbsa_build
cp "$SOL_DIR/main.go" /app/_cbsa_build/main.go
cp "$SOL_DIR/go.mod" /app/_cbsa_build/go.mod
cd /app/_cbsa_build
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_cbsa_build/cbsa .

CBSA_DATA_DIR="${CBSA_DATA_DIR:-/app/breakers}" \
CBSA_AUDIT_DIR="${CBSA_AUDIT_DIR:-/app/audit}" \
/app/_cbsa_build/cbsa
