#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export RBS_DATA_DIR="${RBS_DATA_DIR:-}"
export RBS_AUDIT_DIR="${RBS_AUDIT_DIR:-}"
if [ -z "${RBS_DATA_DIR}" ]; then export RBS_DATA_DIR="/app/rbs_lat"; fi
if [ -z "${RBS_AUDIT_DIR}" ]; then export RBS_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
