#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export RBH_DATA_DIR="${RBH_DATA_DIR:-/app/relayhop}"
export RBH_AUDIT_DIR="${RBH_AUDIT_DIR:-/app/audit}"

ruby "$SOL_DIR/relay_audit.rb"

python3 <<'CANON'
import json
import os
from pathlib import Path

audit = Path(os.environ.get("RBH_AUDIT_DIR", "/app/audit"))
for name in ("admissions.json", "denials.json", "carry_ledgers.json", "summary.json"):
    p = audit / name
    obj = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(
        json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
CANON
