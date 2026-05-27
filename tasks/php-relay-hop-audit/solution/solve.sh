#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export PRH_DATA_DIR="${PRH_DATA_DIR:-/app/relayhop}"
export PRH_AUDIT_DIR="${PRH_AUDIT_DIR:-/app/audit}"

php "$SOL_DIR/relay_audit.php"

python3 <<'CANON'
import json
import os
from pathlib import Path

audit = Path(os.environ.get("PRH_AUDIT_DIR", "/app/audit"))
for name in ("admissions.json", "denials.json", "carry_ledgers.json", "summary.json"):
    p = audit / name
    obj = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(
        json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
CANON
