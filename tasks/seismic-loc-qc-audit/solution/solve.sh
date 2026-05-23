#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export SEISMIC_ORACLE_SCRIPT_DIR="$SCRIPT_DIR"

cp "$SCRIPT_DIR/seismic_oracle.py" /app/oracle_solver.py
chmod +x /app/oracle_solver.py

mkdir -p /app/bin

cat > /app/bin/seismic_audit <<'WRAPPER'
#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")
from oracle_solver import main
raise SystemExit(main())
WRAPPER
chmod +x /app/bin/seismic_audit

cat > /app/Makefile <<'MK'
.PHONY: build clean
build:
	mkdir -p bin
	chmod +x bin/seismic_audit
clean:
	rm -rf bin
MK

mkdir -p /app/output
python3 /app/oracle_solver.py \
  --data "${SEISMIC_DATA:-/app/data}" \
  --out "${SEISMIC_REPORT:-/app/output/localization_report.json}"
