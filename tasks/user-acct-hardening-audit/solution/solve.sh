#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="/app/data"
OUT_DIR="/app/audit"
mkdir -p /app/build /app/src "${OUT_DIR}"
export CLASSPATH="/opt/gson.jar"
cp "${SOL_DIR}/AccountHardening.java" /app/src/AccountHardening.java
javac -encoding UTF-8 -cp "${CLASSPATH}" -d /app/build /app/src/AccountHardening.java
exec java -cp "/app/build:${CLASSPATH}" AccountHardening "${DATA_DIR}" "${OUT_DIR}"
