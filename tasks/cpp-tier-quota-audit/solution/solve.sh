#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit /app/_tq_build
cp "$SOL_DIR/quota_audit.cpp" /app/_tq_build/
cd /app/_tq_build
g++ -std=c++17 -O2 -o tqaudit quota_audit.cpp
export QUOTA_DATA_DIR="${QUOTA_DATA_DIR:-/app/quota_lab}"
export QUOTA_AUDIT_DIR="${QUOTA_AUDIT_DIR:-/app/audit}"
./tqaudit

python3 <<'CANON'
import json, os
from pathlib import Path
audit = Path(os.environ.get("QUOTA_AUDIT_DIR", "/app/audit"))
for name in ("allocations.json", "summary.json"):
    p = audit / name
    obj = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
CANON

