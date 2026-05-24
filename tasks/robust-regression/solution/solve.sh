#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${1:-/app/data}"
OUT_DIR="${2:-/app/output}"
mkdir -p /app/build /app/src "${OUT_DIR}"
export CLASSPATH="/opt/gson.jar"
if [[ -f "${SOL_DIR}/Replay.java" ]]; then
  cp "${SOL_DIR}/Replay.java" /app/src/Replay.java
fi
javac -encoding UTF-8 -cp "${CLASSPATH}" -d /app/build /app/src/Replay.java
exec java -cp "/app/build:${CLASSPATH}" Replay "${DATA_DIR}" "${OUT_DIR}"
