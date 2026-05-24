#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "${PQB_AUDIT_DIR:-/app/audit}"

cp "${ROOT}/oracle_main.rs" /app/pqb_auditor/src/main.rs

cd /app/pqb_auditor
cargo build --release --quiet

mkdir -p /app/bin
cp /app/pqb_auditor/target/release/posterior_quorum_bandit /app/bin/pqb-audit

PQB_DATA_DIR="${PQB_DATA_DIR:-/app/pqb_lab}"
PQB_AUDIT_DIR="${PQB_AUDIT_DIR:-/app/audit}"

exec /app/bin/pqb-audit "${PQB_DATA_DIR}" "${PQB_AUDIT_DIR}"
