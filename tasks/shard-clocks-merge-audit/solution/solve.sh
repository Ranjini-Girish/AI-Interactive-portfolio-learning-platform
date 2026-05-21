#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export SCM_DATA_DIR="${SCM_DATA_DIR:-/app/clk_lat}"
export SCM_AUDIT_DIR="${SCM_AUDIT_DIR:-/app/audit}"

python3 "$SOL_DIR/audit.py"
