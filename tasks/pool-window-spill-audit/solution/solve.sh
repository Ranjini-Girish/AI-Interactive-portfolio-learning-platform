#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_pws_build
cp "$SOL_DIR/main.go" /app/_pws_build/main.go
cd /app/_pws_build
if [ ! -f go.mod ]; then
  go mod init pws >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_pws_build/pws .

PWS_DATA_DIR="${PWS_DATA_DIR:-/app/poolspill}" \
PWS_AUDIT_DIR="${PWS_AUDIT_DIR:-/app/audit}" \
/app/_pws_build/pws
