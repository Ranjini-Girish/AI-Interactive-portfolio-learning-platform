#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export PBC_DATA_DIR="${PBC_DATA_DIR:-}"
export PBC_AUDIT_DIR="${PBC_AUDIT_DIR:-}"
if [ -z "${PBC_DATA_DIR}" ]; then export PBC_DATA_DIR="/app/pbc_lat"; fi
if [ -z "${PBC_AUDIT_DIR}" ]; then export PBC_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
