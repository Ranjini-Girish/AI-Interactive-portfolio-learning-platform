#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export SLM_DATA_DIR="${SLM_DATA_DIR:-}"
export SLM_AUDIT_DIR="${SLM_AUDIT_DIR:-}"
if [ -z "${SLM_DATA_DIR}" ]; then export SLM_DATA_DIR="/app/slm_lat"; fi
if [ -z "${SLM_AUDIT_DIR}" ]; then export SLM_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
