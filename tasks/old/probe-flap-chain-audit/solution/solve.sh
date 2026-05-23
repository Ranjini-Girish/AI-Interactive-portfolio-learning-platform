#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_pfca_build
cp "$SOL_DIR/main.go" /app/_pfca_build/main.go
cd /app/_pfca_build
if [ ! -f go.mod ]; then
  go mod init pfca >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_pfca_build/pfca .

PFCA_DATA_DIR="${PFCA_DATA_DIR:-/app/probeflaps}" \
PFCA_AUDIT_DIR="${PFCA_AUDIT_DIR:-/app/audit}" \
/app/_pfca_build/pfca
