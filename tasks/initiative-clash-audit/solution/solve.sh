#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_ica_build
cp "$SOL_DIR/ica.go" /app/_ica_build/main.go
cp "$SOL_DIR/go.mod" /app/_ica_build/go.mod
cd /app/_ica_build
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_ica_build/ica .

ICA_DATA_DIR="${ICA_DATA_DIR:-/app/init_clash}" \
ICA_AUDIT_DIR="${ICA_AUDIT_DIR:-/app/audit}" \
/app/_ica_build/ica
