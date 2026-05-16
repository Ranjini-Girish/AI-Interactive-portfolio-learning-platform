#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_cla_build
cp "$SOL_DIR/main.go" /app/_cla_build/main.go
cd /app/_cla_build
if [ ! -f go.mod ]; then
  go mod init cla >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_cla_build/cla .

CLA_DATA_DIR="${CLA_DATA_DIR:-/app/connhelix}" \
CLA_AUDIT_DIR="${CLA_AUDIT_DIR:-/app/audit}" \
/app/_cla_build/cla
