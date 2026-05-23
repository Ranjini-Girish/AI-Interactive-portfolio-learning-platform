#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="/app/data"
OUT_DIR="/app/output"
mkdir -p /app/build /app/src "${OUT_DIR}"
export CLASSPATH="/opt/gson.jar"
cp "${SOL_DIR}/ProcTreeReaperAudit.java" /app/src/ProcTreeReaperAudit.java
javac -encoding UTF-8 -cp "${CLASSPATH}" -d /app/build /app/src/ProcTreeReaperAudit.java
cat > "/app/build/proctree" <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
exec java -cp "/app/build:/opt/gson.jar" ProcTreeReaperAudit "$@"
WRAP
chmod +x "/app/build/proctree"
exec java -cp "/app/build:${CLASSPATH}" ProcTreeReaperAudit "${DATA_DIR}" "${OUT_DIR}"
