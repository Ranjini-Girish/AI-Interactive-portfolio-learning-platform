#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_rhc_build
cp "$SOL_DIR/main.go" /app/_rhc_build/main.go
cd /app/_rhc_build
if [ ! -f go.mod ]; then
  go mod init rhc >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_rhc_build/rhc .

RHC_DATA_DIR="${RHC_DATA_DIR:-/app/relayhop}" \
RHC_AUDIT_DIR="${RHC_AUDIT_DIR:-/app/audit}" \
/app/_rhc_build/rhc
