#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit /app/_tq_build/src
cp "$SOL_DIR/Cargo.toml" /app/_tq_build/
cp "$SOL_DIR/main.rs" /app/_tq_build/src/main.rs
cd /app/_tq_build
cargo build --release
export QUOTA_DATA_DIR="${QUOTA_DATA_DIR:-/app/quota_lab}"
export QUOTA_AUDIT_DIR="${QUOTA_AUDIT_DIR:-/app/audit}"
/app/_tq_build/target/release/tqaudit

python3 <<'CANON'
import json, os
from pathlib import Path
audit = Path(os.environ.get("QUOTA_AUDIT_DIR", "/app/audit"))
for name in ("allocations.json", "summary.json"):
    p = audit / name
    obj = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
CANON

