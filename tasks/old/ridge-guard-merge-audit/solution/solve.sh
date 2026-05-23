#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -z "${RGMA_DATA_DIR:-}" ]; then
  export RGMA_DATA_DIR="/app/rgma_lab"
fi
if [ -z "${RGMA_AUDIT_DIR:-}" ]; then
  export RGMA_AUDIT_DIR="/app/audit"
fi

python3 "$SOL_DIR/audit.py"
