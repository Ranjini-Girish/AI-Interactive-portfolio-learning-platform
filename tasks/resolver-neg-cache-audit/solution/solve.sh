#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_rnca_build
cp "$SOL_DIR/main.go" /app/_rnca_build/main.go
cd /app/_rnca_build
if [ ! -f go.mod ]; then
  go mod init rnca >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_rnca_build/rnca .

RNCA_DATA_DIR="${RNCA_DATA_DIR:-/app/resolver_negcache}" \
RNCA_AUDIT_DIR="${RNCA_AUDIT_DIR:-/app/audit}" \
/app/_rnca_build/rnca
