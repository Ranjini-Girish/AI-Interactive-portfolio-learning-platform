#!/bin/bash
set -euo pipefail

export PATH="/usr/local/go/bin:${PATH}"

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_fsf_build
cp "$SOL_DIR/main.go" /app/_fsf_build/main.go
cd /app/_fsf_build
if [ ! -f go.mod ]; then
  go mod init fsf >/dev/null 2>&1
fi
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_fsf_build/fsf .

FSF_DATA_DIR="${FSF_DATA_DIR:-/app/featstore}" \
FSF_AUDIT_DIR="${FSF_AUDIT_DIR:-/app/audit}" \
/app/_fsf_build/fsf
