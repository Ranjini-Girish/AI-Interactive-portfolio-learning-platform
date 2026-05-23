#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export RLC_DATA_DIR="${RLC_DATA_DIR:-}"
export RLC_AUDIT_DIR="${RLC_AUDIT_DIR:-}"
if [ -z "${RLC_DATA_DIR}" ]; then export RLC_DATA_DIR="/app/rlc_lab"; fi
if [ -z "${RLC_AUDIT_DIR}" ]; then export RLC_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
