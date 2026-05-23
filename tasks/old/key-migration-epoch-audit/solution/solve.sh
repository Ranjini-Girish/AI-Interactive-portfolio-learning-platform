#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_kme_build
cp "$SOL_DIR/main.go" /app/_kme_build/main.go
cd /app/_kme_build
if [ ! -f go.mod ]; then
  go mod init kme >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_kme_build/kme .

KME_DATA_DIR="${KME_DATA_DIR:-/app/keymigrate}" \
KME_AUDIT_DIR="${KME_AUDIT_DIR:-/app/audit}" \
/app/_kme_build/kme
