#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export WRM_DATA_DIR="${WRM_DATA_DIR:-}"
export WRM_AUDIT_DIR="${WRM_AUDIT_DIR:-}"
if [ -z "${WRM_DATA_DIR}" ]; then export WRM_DATA_DIR="/app/wrm_lat"; fi
if [ -z "${WRM_AUDIT_DIR}" ]; then export WRM_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
