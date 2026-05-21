#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export JSA_DATA_DIR="${JSA_DATA_DIR:-}"
export JSA_AUDIT_DIR="${JSA_AUDIT_DIR:-}"
if [ -z "${JSA_DATA_DIR}" ]; then export JSA_DATA_DIR="/app/jsa_lat"; fi
if [ -z "${JSA_AUDIT_DIR}" ]; then export JSA_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
