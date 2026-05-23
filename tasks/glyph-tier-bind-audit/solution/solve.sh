#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_glyphtierbin_build
cp "$SOL_DIR/main.go" /app/_glyphtierbin_build/main.go
cp "$SOL_DIR/go.mod" /app/_glyphtierbin_build/go.mod
cd /app/_glyphtierbin_build
export PATH="/usr/local/go/bin:${PATH}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_glyphtierbin_build/aud .

GTB_DATA_DIR="${GTB_DATA_DIR:-/app/gtb_lab}" \
GTB_AUDIT_DIR="${GTB_AUDIT_DIR:-/app/audit}" \
/app/_glyphtierbin_build/aud
