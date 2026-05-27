#!/bin/bash
set -euo pipefail
cd /work
for t in bash-tier-quota-audit c-tier-quota-audit cpp-tier-quota-audit elixir-tier-quota-audit go-tier-quota-audit hs-tier-quota-audit java-tier-quota-audit js-tier-quota-audit kotlin-tier-quota-audit py-tier-quota-audit ruby-tier-quota-audit rust-tier-quota-audit ts-tier-quota-audit; do
  python tools/terminus-task-tools/terminus_zip.py build "tasks/$t"
done
echo REBUILD_OK
