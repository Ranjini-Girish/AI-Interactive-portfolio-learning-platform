#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="/app/data"
AUDIT_DIR="/app/audit"
mkdir -p /app/build /app/src "${AUDIT_DIR}"
export CLASSPATH="/opt/gson.jar"
cp "${SOL_DIR}/KeytabRotationAudit.java" /app/src/KeytabRotationAudit.java
javac -encoding UTF-8 -cp "${CLASSPATH}" -d /app/build /app/src/KeytabRotationAudit.java
exec java -cp "/app/build:${CLASSPATH}" KeytabRotationAudit "${DATA_DIR}" "${AUDIT_DIR}"
