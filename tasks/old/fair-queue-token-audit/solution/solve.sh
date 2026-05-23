#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export FQT_DATA_DIR="${FQT_DATA_DIR:-}"
export FQT_AUDIT_DIR="${FQT_AUDIT_DIR:-}"
if [ -z "${FQT_DATA_DIR}" ]; then export FQT_DATA_DIR="/app/fqt_lab"; fi
if [ -z "${FQT_AUDIT_DIR}" ]; then export FQT_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
