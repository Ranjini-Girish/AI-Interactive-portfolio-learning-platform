#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${LER_APP_DATA:-/app/data}"
OUT_DIR="${LER_APP_OUTPUT:-/app/output}"
BUILD_DIR="${LER_APP_BUILD:-/app/build}"
mkdir -p "${BUILD_DIR}" /app/src "${OUT_DIR}"
export CLASSPATH="/opt/gson.jar"
cp "${SOL_DIR}/LedgerEventReconAudit.java" /app/src/LedgerEventReconAudit.java
javac -encoding UTF-8 -cp "${CLASSPATH}" -d "${BUILD_DIR}" /app/src/LedgerEventReconAudit.java
exec java -cp "${BUILD_DIR}:${CLASSPATH}" LedgerEventReconAudit "${DATA_DIR}" "${OUT_DIR}"
