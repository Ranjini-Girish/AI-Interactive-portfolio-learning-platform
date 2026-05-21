#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export SBM_DATA_DIR="${SBM_DATA_DIR:-/app/sbm_lab}"
export SBM_AUDIT_DIR="${SBM_AUDIT_DIR:-/app/audit}"
python "$SOL_DIR/audit.py"
