#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit /app/_cra_build
cp "$SOL_DIR/relay_audit.c" /app/_cra_build/
cd /app/_cra_build
gcc -std=c11 -O2 -o craudit relay_audit.c -lcjson

export CRA_DATA_DIR="${CRA_DATA_DIR:-/app/relayhop}"
export CRA_AUDIT_DIR="${CRA_AUDIT_DIR:-/app/audit}"
./craudit

python3 <<'CANON'
import json
import os
from pathlib import Path

audit = Path(os.environ.get("CRA_AUDIT_DIR", "/app/audit"))
for name in ("admissions.json", "denials.json", "carry_ledgers.json", "summary.json"):
    p = audit / name
    obj = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(
        json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
CANON
