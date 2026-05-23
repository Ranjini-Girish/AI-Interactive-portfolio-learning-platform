#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export HBA_DATA_DIR="${HBA_DATA_DIR:-}"
export HBA_AUDIT_DIR="${HBA_AUDIT_DIR:-}"
if [ -z "${HBA_DATA_DIR}" ]; then export HBA_DATA_DIR="/app/hba_lab"; fi
if [ -z "${HBA_AUDIT_DIR}" ]; then export HBA_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
