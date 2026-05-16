#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_ibqa_build
cp "$SOL_DIR/ibqa.go" /app/_ibqa_build/main.go
cp "$SOL_DIR/go.mod" /app/_ibqa_build/go.mod
cd /app/_ibqa_build
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_ibqa_build/ibqa .

IBQA_DATA_DIR="${IBQA_DATA_DIR:-/app/infer_blend}" \
IBQA_AUDIT_DIR="${IBQA_AUDIT_DIR:-/app/audit}" \
/app/_ibqa_build/ibqa
