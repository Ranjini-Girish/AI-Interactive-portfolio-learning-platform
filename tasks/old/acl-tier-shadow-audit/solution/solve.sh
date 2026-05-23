#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export ATSA_DATA_DIR="${ATSA_DATA_DIR:-/app/acl_tier}"
export ATSA_AUDIT_DIR="${ATSA_AUDIT_DIR:-/app/audit}"
mkdir -p "$ATSA_AUDIT_DIR"
python3 "$SOL_DIR/atsa.py"
