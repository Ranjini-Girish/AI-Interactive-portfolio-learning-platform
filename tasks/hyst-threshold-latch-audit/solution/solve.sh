#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export HTL_DATA_DIR="${HTL_DATA_DIR:-/app/htl_lab}"
export HTL_AUDIT_DIR="${HTL_AUDIT_DIR:-/app/audit}"
python "$SOL_DIR/audit.py"
