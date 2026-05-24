#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${1:-/app/data}"
OUT_DIR="${2:-/app/output}"
mkdir -p /app/build /app/src "${OUT_DIR}"
export CLASSPATH="/opt/gson.jar"
if [[ -f "${SOL_DIR}/Audit.java" ]]; then
  cp "${SOL_DIR}/Audit.java" /app/src/Audit.java
fi
javac -encoding UTF-8 -cp "${CLASSPATH}" -d /app/build /app/src/Audit.java
exec java -cp "/app/build:${CLASSPATH}" Audit "${DATA_DIR}" "${OUT_DIR}"
