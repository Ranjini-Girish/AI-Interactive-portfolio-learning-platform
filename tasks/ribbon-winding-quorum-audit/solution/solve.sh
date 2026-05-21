#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/bin /app/_rwq_build
cp "$SOL_DIR/main.go" /app/_rwq_build/main.go
cp "$SOL_DIR/go.mod" /app/_rwq_build/go.mod
cd /app/_rwq_build
export PATH="/usr/local/go/bin:${PATH}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/bin/rwqaudit .

mkdir -p "${RWQ_AUDIT_DIR:-/app/audit}"
RWQ_DATA_DIR="${RWQ_DATA_DIR:-/app/rwq_lab}" \
RWQ_AUDIT_DIR="${RWQ_AUDIT_DIR:-/app/audit}" \
/app/bin/rwqaudit
