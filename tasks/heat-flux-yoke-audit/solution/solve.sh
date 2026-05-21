#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export HFY_DATA_DIR="${HFY_DATA_DIR:-}"
export HFY_AUDIT_DIR="${HFY_AUDIT_DIR:-}"
if [ -z "${HFY_DATA_DIR}" ]; then export HFY_DATA_DIR="/app/hfy_lab"; fi
if [ -z "${HFY_AUDIT_DIR}" ]; then export HFY_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
