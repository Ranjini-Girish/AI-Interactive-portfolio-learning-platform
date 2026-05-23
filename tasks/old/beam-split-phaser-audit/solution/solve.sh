#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export BSP_DATA_DIR="${BSP_DATA_DIR:-}"
export BSP_AUDIT_DIR="${BSP_AUDIT_DIR:-}"
if [ -z "${BSP_DATA_DIR}" ]; then export BSP_DATA_DIR="/app/bsp_lat"; fi
if [ -z "${BSP_AUDIT_DIR}" ]; then export BSP_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
