#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export JEM_DATA_DIR="${JEM_DATA_DIR:-}"
export JEM_AUDIT_DIR="${JEM_AUDIT_DIR:-}"
if [ -z "${JEM_DATA_DIR}" ]; then export JEM_DATA_DIR="/app/jem_lab"; fi
if [ -z "${JEM_AUDIT_DIR}" ]; then export JEM_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
