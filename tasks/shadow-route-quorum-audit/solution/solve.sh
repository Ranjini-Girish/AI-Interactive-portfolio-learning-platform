#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_srq_build
cp "$SOL_DIR/main.go" /app/_srq_build/main.go
cd /app/_srq_build
if [ ! -f go.mod ]; then
  go mod init srq >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_srq_build/srq .

SRQ_DATA_DIR="${SRQ_DATA_DIR:-/app/shadowroute}" \
SRQ_AUDIT_DIR="${SRQ_AUDIT_DIR:-/app/audit}" \
/app/_srq_build/srq
