#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export PBR_DATA_DIR="${PBR_DATA_DIR:-}"
export PBR_AUDIT_DIR="${PBR_AUDIT_DIR:-}"
if [ -z "${PBR_DATA_DIR}" ]; then export PBR_DATA_DIR="/app/pbr_lab"; fi
if [ -z "${PBR_AUDIT_DIR}" ]; then export PBR_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
