#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="/app/data"
OUT_DIR="/app/output"
mkdir -p /app/build /app/src "${OUT_DIR}"
export CLASSPATH="/opt/gson.jar"
cp "${SOL_DIR}/FirewallRuleShadow.java" /app/src/FirewallRuleShadow.java
javac -encoding UTF-8 -cp "${CLASSPATH}" -d /app/build /app/src/FirewallRuleShadow.java
exec java -cp "/app/build:${CLASSPATH}" FirewallRuleShadow "${DATA_DIR}" "${OUT_DIR}"
