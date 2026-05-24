#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export TWC_DATA_DIR="${TWC_DATA_DIR:-}"
export TWC_AUDIT_DIR="${TWC_AUDIT_DIR:-}"
if [ -z "${TWC_DATA_DIR}" ]; then export TWC_DATA_DIR="/app/twc_lab"; fi
if [ -z "${TWC_AUDIT_DIR}" ]; then export TWC_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
