#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export JRH_DATA_DIR="${JRH_DATA_DIR:-/app/relayhop}"
export JRH_AUDIT_DIR="${JRH_AUDIT_DIR:-/app/audit}"

mkdir -p /app/_jrh_build
cp "$SOL_DIR/RelayHopAudit.java" /app/_jrh_build/
cd /app/_jrh_build
javac RelayHopAudit.java
java -cp "/app/_jrh_build:/usr/share/java/gson.jar" RelayHopAudit

python3 <<'CANON'
import json
import os
from pathlib import Path

audit = Path(os.environ.get("JRH_AUDIT_DIR", "/app/audit"))
for name in ("admissions.json", "denials.json", "carry_ledgers.json", "summary.json"):
    p = audit / name
    obj = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(
        json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
CANON
