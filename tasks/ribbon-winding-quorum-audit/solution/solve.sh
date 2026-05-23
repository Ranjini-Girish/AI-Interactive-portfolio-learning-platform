#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/rwq_tool
cp "$SOL_DIR/main.go" /app/rwq_tool/main.go
cp "$SOL_DIR/go.mod" /app/rwq_tool/go.mod
cd /app/rwq_tool
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/rwq_tool/rwqaudit .

RWQ_DATA_DIR="${RWQ_DATA_DIR:-/app/rwq_lab}" \
RWQ_AUDIT_DIR="${RWQ_AUDIT_DIR:-/app/rwq_audit}" \
/app/rwq_tool/rwqaudit
