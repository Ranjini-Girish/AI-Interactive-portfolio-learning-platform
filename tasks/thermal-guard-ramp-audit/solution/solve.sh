#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export TGR_DATA_DIR="${TGR_DATA_DIR:-}"
export TGR_AUDIT_DIR="${TGR_AUDIT_DIR:-}"
if [ -z "${TGR_DATA_DIR}" ]; then export TGR_DATA_DIR="/app/tgr_lat"; fi
if [ -z "${TGR_AUDIT_DIR}" ]; then export TGR_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
