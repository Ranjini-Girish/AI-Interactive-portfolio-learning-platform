#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
export BAF_DATA_DIR="${BAF_DATA_DIR:-}"
export BAF_AUDIT_DIR="${BAF_AUDIT_DIR:-}"
if [ -z "${BAF_DATA_DIR}" ]; then export BAF_DATA_DIR="/app/baf_lat"; fi
if [ -z "${BAF_AUDIT_DIR}" ]; then export BAF_AUDIT_DIR="/app/audit"; fi

python "$SOL_DIR/audit.py"
