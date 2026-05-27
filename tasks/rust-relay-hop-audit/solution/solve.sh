#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export RRH_DATA_DIR="${RRH_DATA_DIR:-/app/relayhop}"
export RRH_AUDIT_DIR="${RRH_AUDIT_DIR:-/app/audit}"

mkdir -p /app/_rrh_build/src
cp "$SOL_DIR/Cargo.toml" /app/_rrh_build/
cp "$SOL_DIR/src/main.rs" /app/_rrh_build/src/
cd /app/_rrh_build
cargo build --release
/app/_rrh_build/target/release/relay_audit

python3 <<'CANON'
import json
import os
from pathlib import Path

audit = Path(os.environ.get("RRH_AUDIT_DIR", "/app/audit"))
for name in ("admissions.json", "denials.json", "carry_ledgers.json", "summary.json"):
    p = audit / name
    obj = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(
        json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
CANON
