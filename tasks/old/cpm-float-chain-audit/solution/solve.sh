#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export CFC_DATA_DIR="${CFC_DATA_DIR:-}"
export CFC_AUDIT_DIR="${CFC_AUDIT_DIR:-}"
if [ -z "${CFC_DATA_DIR}" ]; then export CFC_DATA_DIR="/app/cfc_lat"; fi
if [ -z "${CFC_AUDIT_DIR}" ]; then export CFC_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
