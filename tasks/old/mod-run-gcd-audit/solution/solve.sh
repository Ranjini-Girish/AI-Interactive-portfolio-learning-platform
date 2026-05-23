#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export MRG_DATA_DIR="${MRG_DATA_DIR:-}"
export MRG_AUDIT_DIR="${MRG_AUDIT_DIR:-}"
if [ -z "${MRG_DATA_DIR}" ]; then export MRG_DATA_DIR="/app/mrg_lab"; fi
if [ -z "${MRG_AUDIT_DIR}" ]; then export MRG_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
