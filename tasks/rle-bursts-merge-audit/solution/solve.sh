#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export RBM_DATA_DIR="${RBM_DATA_DIR:-}"
export RBM_AUDIT_DIR="${RBM_AUDIT_DIR:-}"
if [ -z "${RBM_DATA_DIR}" ]; then export RBM_DATA_DIR="/app/rbm_lat"; fi
if [ -z "${RBM_AUDIT_DIR}" ]; then export RBM_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
