#!/bin/bash
set -euo pipefail

export PATH="/usr/local/go/bin:${PATH}"
export SUMLOCK_ROOT="/app/sumlock_audit"

mkdir -p /app/out

go build -o /tmp/sumlock /solution/sumlock.go
/tmp/sumlock > /tmp/sumlock_raw.json
python3 <<'PY'
import json
from pathlib import Path

data = json.loads(Path("/tmp/sumlock_raw.json").read_text(encoding="utf-8"))
Path("/app/out/sumlock.json").write_text(
    json.dumps(data, indent=2, sort_keys=True, separators=(",", ":")),
    encoding="utf-8",
)
PY
