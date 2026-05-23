#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -z "${RGMA_DATA_DIR:-}" ]; then
  export RGMA_DATA_DIR="/app/rgma_lab"
fi
if [ -z "${RGMA_AUDIT_DIR:-}" ]; then
  export RGMA_AUDIT_DIR="/app/audit"
fi

mkdir -p /app/build /app/src
cp "${SOL_DIR}/RgmaAudit.java" /app/src/RgmaAudit.java
javac -encoding UTF-8 -cp "/opt/gson.jar" -d /app/build /app/src/RgmaAudit.java

mkdir -p "${RGMA_AUDIT_DIR}"
java -cp "/app/build:/opt/gson.jar" RgmaAudit "${RGMA_DATA_DIR}" "${RGMA_AUDIT_DIR}"
