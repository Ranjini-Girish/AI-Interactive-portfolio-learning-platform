#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export ISC_DATA_DIR="${ISC_DATA_DIR:-}"
export ISC_AUDIT_DIR="${ISC_AUDIT_DIR:-}"
if [ -z "${ISC_DATA_DIR}" ]; then export ISC_DATA_DIR="/app/isc_lat"; fi
if [ -z "${ISC_AUDIT_DIR}" ]; then export ISC_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
