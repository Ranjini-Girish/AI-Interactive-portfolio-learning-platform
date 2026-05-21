#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export TMB_DATA_DIR="${TMB_DATA_DIR:-}"
export TMB_AUDIT_DIR="${TMB_AUDIT_DIR:-}"
if [ -z "${TMB_DATA_DIR}" ]; then export TMB_DATA_DIR="/app/tmb_lat"; fi
if [ -z "${TMB_AUDIT_DIR}" ]; then export TMB_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
