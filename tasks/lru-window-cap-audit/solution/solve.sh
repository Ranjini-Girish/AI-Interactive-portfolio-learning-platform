#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export LWC_DATA_DIR="${LWC_DATA_DIR:-}"
export LWC_AUDIT_DIR="${LWC_AUDIT_DIR:-}"
if [ -z "${LWC_DATA_DIR}" ]; then export LWC_DATA_DIR="/app/lwc_lat"; fi
if [ -z "${LWC_AUDIT_DIR}" ]; then export LWC_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
