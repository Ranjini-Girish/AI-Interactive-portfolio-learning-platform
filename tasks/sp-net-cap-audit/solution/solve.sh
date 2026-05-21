#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOL="/app/spn_tool"
mkdir -p "$TOOL"
cp "$SOL_DIR/main.go" "$TOOL/main.go"
cp "$SOL_DIR/go.mod" "$TOOL/go.mod"
cd "$TOOL"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o "$TOOL/spnaudit" .

SPN_DATA_DIR="${SPN_DATA_DIR:-/app/spn_lab}" \
SPN_AUDIT_DIR="${SPN_AUDIT_DIR:-/app/spn_audit}" \
"$TOOL/spnaudit"
