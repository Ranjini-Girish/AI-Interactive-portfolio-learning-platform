#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit /app/_tq_build
cp "$SOL_DIR/quota_audit.ts" /app/_tq_build/
cd /app/_tq_build
tsc --skipLibCheck --target ES2022 --module nodenext --moduleResolution nodenext quota_audit.ts
export QUOTA_DATA_DIR="${QUOTA_DATA_DIR:-/app/quota_lab}"
export QUOTA_AUDIT_DIR="${QUOTA_AUDIT_DIR:-/app/audit}"
node quota_audit.js

python3 <<'CANON'
import json, os
from pathlib import Path
audit = Path(os.environ.get("QUOTA_AUDIT_DIR", "/app/audit"))
for name in ("allocations.json", "summary.json"):
    p = audit / name
    obj = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
CANON
