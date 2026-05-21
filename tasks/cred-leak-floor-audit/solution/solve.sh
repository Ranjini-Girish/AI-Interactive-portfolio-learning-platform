#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export CLF_DATA_DIR="${CLF_DATA_DIR:-}"
export CLF_AUDIT_DIR="${CLF_AUDIT_DIR:-}"
if [ -z "${CLF_DATA_DIR}" ]; then export CLF_DATA_DIR="/app/clf_lat"; fi
if [ -z "${CLF_AUDIT_DIR}" ]; then export CLF_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
