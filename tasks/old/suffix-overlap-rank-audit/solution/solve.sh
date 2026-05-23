#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export SOR_DATA_DIR="${SOR_DATA_DIR:-}"
export SOR_AUDIT_DIR="${SOR_AUDIT_DIR:-}"
if [ -z "${SOR_DATA_DIR}" ]; then export SOR_DATA_DIR="/app/sor_lat"; fi
if [ -z "${SOR_AUDIT_DIR}" ]; then export SOR_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
