#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export TBR_DATA_DIR="${TBR_DATA_DIR:-}"
export TBR_AUDIT_DIR="${TBR_AUDIT_DIR:-}"
if [ -z "${TBR_DATA_DIR}" ]; then export TBR_DATA_DIR="/app/tbr_lat"; fi
if [ -z "${TBR_AUDIT_DIR}" ]; then export TBR_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
