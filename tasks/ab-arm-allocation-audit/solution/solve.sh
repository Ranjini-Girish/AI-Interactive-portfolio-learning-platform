#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_aaa_build
cp "$SOL_DIR/main.go" /app/_aaa_build/main.go
cd /app/_aaa_build
if [ ! -f go.mod ]; then
  go mod init aaa >/dev/null 2>&1
fi
export PATH="/usr/local/go/bin:${PATH:-}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_aaa_build/aaa .

AAA_DATA_DIR="${AAA_DATA_DIR:-/app/abarmalloc}" \
AAA_AUDIT_DIR="${AAA_AUDIT_DIR:-/app/audit}" \
/app/_aaa_build/aaa
