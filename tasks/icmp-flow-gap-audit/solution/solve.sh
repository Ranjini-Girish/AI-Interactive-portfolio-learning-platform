#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export IFG_DATA_DIR="${IFG_DATA_DIR:-}"
export IFG_AUDIT_DIR="${IFG_AUDIT_DIR:-}"
if [ -z "${IFG_DATA_DIR}" ]; then export IFG_DATA_DIR="/app/ifg_lat"; fi
if [ -z "${IFG_AUDIT_DIR}" ]; then export IFG_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
