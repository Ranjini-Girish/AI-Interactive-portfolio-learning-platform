#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export ZEN_DATA_DIR="${ZEN_DATA_DIR:-}"
export ZEN_AUDIT_DIR="${ZEN_AUDIT_DIR:-}"
if [ -z "${ZEN_DATA_DIR}" ]; then export ZEN_DATA_DIR="/app/zen_lat"; fi
if [ -z "${ZEN_AUDIT_DIR}" ]; then export ZEN_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
