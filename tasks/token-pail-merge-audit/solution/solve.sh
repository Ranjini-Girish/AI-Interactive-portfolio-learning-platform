#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export TPM_DATA_DIR="${TPM_DATA_DIR:-}"
export TPM_AUDIT_DIR="${TPM_AUDIT_DIR:-}"
if [ -z "${TPM_DATA_DIR}" ]; then export TPM_DATA_DIR="/app/tpm_lat"; fi
if [ -z "${TPM_AUDIT_DIR}" ]; then export TPM_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
