#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export SBR_DATA_DIR="${SBR_DATA_DIR:-/app/sbr_lab}"
export SBR_AUDIT_DIR="${SBR_AUDIT_DIR:-/app/audit}"
python "$SOL_DIR/audit.py"
