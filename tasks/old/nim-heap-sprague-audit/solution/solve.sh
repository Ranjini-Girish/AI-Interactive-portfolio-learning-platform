#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export NHS_DATA_DIR="${NHS_DATA_DIR:-}"
export NHS_AUDIT_DIR="${NHS_AUDIT_DIR:-}"
if [ -z "${NHS_DATA_DIR}" ]; then export NHS_DATA_DIR="/app/nhs_lat"; fi
if [ -z "${NHS_AUDIT_DIR}" ]; then export NHS_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
