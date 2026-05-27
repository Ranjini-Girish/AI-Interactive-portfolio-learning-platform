#!/bin/bash
set -euo pipefail
cd /work
pip install -q ruff 2>/dev/null || pip install -q ruff
TASKS=(
  bash-tier-quota-audit
  c-tier-quota-audit
  cpp-tier-quota-audit
  elixir-tier-quota-audit
  go-tier-quota-audit
  hs-tier-quota-audit
  java-tier-quota-audit
  js-tier-quota-audit
  kotlin-tier-quota-audit
  py-tier-quota-audit
  ruby-tier-quota-audit
  rust-tier-quota-audit
  ts-tier-quota-audit
)
for t in "${TASKS[@]}"; do
  echo "=== $t ==="
  python tools/terminus-task-tools/terminus_zip.py clean "tasks/$t"
  python tools/terminus-task-tools/terminus_zip.py preflight "tasks/$t"
  python tools/terminus-task-tools/terminus_zip.py build "tasks/$t"
  python tools/terminus-task-tools/terminus_zip.py verify-task "tasks/$t"
done
echo ALL_ZIP_OK
