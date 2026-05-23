#!/bin/bash
set -euo pipefail

export CLASSPATH="/opt/gson.jar:/opt/sqlite-jdbc.jar"

SEEDED_DB="${AUDIT_SEEDED_DB:-/var/lib/audit/state.db}"
SEEDED_POLICY="${AUDIT_SEEDED_POLICY:-/app/data/policy.json}"
APP_ROOT="${AUDIT_APP_ROOT:-/app}"
OUT_REPORT="${APP_ROOT}/out/reconciliation.json"

mkdir -p "${APP_ROOT}/out" "${APP_ROOT}/lib/oracle"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

javac -encoding UTF-8 -cp "$CLASSPATH" -d "$BUILD_DIR" "$SCRIPT_DIR/PayLedgerReconAudit.java"
cp -a "$BUILD_DIR"/. "${APP_ROOT}/lib/oracle/"

export AUDIT_ORACLE_CLASSPATH="${CLASSPATH}:${APP_ROOT}/lib/oracle"

cat > "${APP_ROOT}/audit/cli.py" <<'PYEOF'
"""CLI entry point; oracle delegates to PayLedgerReconAudit."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multi-merchant payments-ledger reconciliation auditor."
    )
    parser.add_argument("--db", required=True, help="Path to state.db")
    parser.add_argument("--policy", required=True, help="Path to policy.json")
    parser.add_argument("--out", required=True, help="Output report path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    classpath = os.environ.get(
        "AUDIT_ORACLE_CLASSPATH",
        "/opt/gson.jar:/opt/sqlite-jdbc.jar:/app/lib/oracle",
    )
    cmd = [
        "java",
        "-cp",
        classpath,
        "PayLedgerReconAudit",
        "--db",
        args.db,
        "--policy",
        args.policy,
        "--out",
        args.out,
    ]
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
PYEOF

rm -rf "${APP_ROOT}/audit/__pycache__"

python -m audit \
    --db "$SEEDED_DB" \
    --policy "$SEEDED_POLICY" \
    --out "$OUT_REPORT"
