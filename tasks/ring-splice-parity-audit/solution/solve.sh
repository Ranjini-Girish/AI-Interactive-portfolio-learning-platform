#!/bin/bash
set -euo pipefail

export PATH="/usr/local/go/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RSP_DATA_DIR="${RSP_DATA_DIR:-/app/ring_splice}"
export RSP_AUDIT_DIR="${RSP_AUDIT_DIR:-/app/audit}"

mkdir -p "$RSP_AUDIT_DIR"

go run "$SCRIPT_DIR/main.go"
