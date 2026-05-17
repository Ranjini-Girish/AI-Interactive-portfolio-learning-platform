#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_hcl_build
cp "$SOL_DIR/main.go" /app/_hcl_build/main.go
cd /app/_hcl_build
if [ ! -f go.mod ]; then
  go mod init hcl >/dev/null 2>&1
fi
export PATH="/usr/local/go/bin:${PATH:-}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_hcl_build/hcl .

HCL_DATA_DIR="${HCL_DATA_DIR:-/app/hedgecalls}" \
HCL_AUDIT_DIR="${HCL_AUDIT_DIR:-/app/audit}" \
/app/_hcl_build/hcl
