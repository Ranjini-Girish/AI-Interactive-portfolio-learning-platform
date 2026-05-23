#!/bin/bash
set -euo pipefail

export PATH="/usr/local/go/bin:${PATH}"

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p /app/out

go run "$SOL_DIR/gateway_audit.go"
