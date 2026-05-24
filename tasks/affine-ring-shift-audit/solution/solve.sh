#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export ARS_DATA_DIR="${ARS_DATA_DIR:-}"
export ARS_AUDIT_DIR="${ARS_AUDIT_DIR:-}"
if [ -z "${ARS_DATA_DIR}" ]; then export ARS_DATA_DIR="/app/ars_lat"; fi
if [ -z "${ARS_AUDIT_DIR}" ]; then export ARS_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
