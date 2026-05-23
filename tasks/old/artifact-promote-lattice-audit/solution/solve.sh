#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_apla_build
cp "$SOL_DIR/main.go" /app/_apla_build/main.go
cd /app/_apla_build
if [ ! -f go.mod ]; then
  go mod init apla >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_apla_build/apla .

APLA_DATA_DIR="${APLA_DATA_DIR:-/app/promote_lattice}" \
APLA_AUDIT_DIR="${APLA_AUDIT_DIR:-/app/audit}" \
/app/_apla_build/apla
