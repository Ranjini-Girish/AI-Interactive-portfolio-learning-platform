#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export LEP_DATA_DIR="${LEP_DATA_DIR:-}"
export LEP_AUDIT_DIR="${LEP_AUDIT_DIR:-}"
if [ -z "${LEP_DATA_DIR}" ]; then export LEP_DATA_DIR="/app/lep_lat"; fi
if [ -z "${LEP_AUDIT_DIR}" ]; then export LEP_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
