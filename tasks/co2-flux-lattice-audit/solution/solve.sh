#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export CFL_DATA_DIR="${CFL_DATA_DIR:-/app/flux_lat}"
export CFL_AUDIT_DIR="${CFL_AUDIT_DIR:-/app/audit}"

python3 "$SOL_DIR/audit.py"
