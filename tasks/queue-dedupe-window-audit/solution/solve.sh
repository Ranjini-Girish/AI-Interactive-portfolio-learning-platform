#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export QDW_DATA_DIR="${QDW_DATA_DIR:-}"
export QDW_AUDIT_DIR="${QDW_AUDIT_DIR:-}"
if [ -z "${QDW_DATA_DIR}" ]; then export QDW_DATA_DIR="/app/qdw_lat"; fi
if [ -z "${QDW_AUDIT_DIR}" ]; then export QDW_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
