#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_cbsa_build
cp "$SOL_DIR/main.go" /app/_cbsa_build/main.go
cd /app/_cbsa_build
if [ ! -f go.mod ]; then
  go mod init cbsa >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_cbsa_build/cbsa .

CBSA_DATA_DIR="${CBSA_DATA_DIR:-/app/breakers}" \
CBSA_AUDIT_DIR="${CBSA_AUDIT_DIR:-/app/audit}" \
/app/_cbsa_build/cbsa
