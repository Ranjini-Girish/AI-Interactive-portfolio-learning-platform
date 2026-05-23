#!/bin/bash
set -euo pipefail

ROOT="${SBR_DATA_DIR:-/app/sbr_lab}"
OUT="${SBR_AUDIT_DIR:-/app/audit}"
mkdir -p "$OUT"

SOLVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLASSPATH="/opt/gson.jar"
TMPD="$(mktemp -d)"
trap 'rm -rf "${TMPD}"' EXIT

javac -cp "${CLASSPATH}" -d "${TMPD}" "${SOLVE_DIR}/SkewBinRecalc.java"
java -cp "${TMPD}:${CLASSPATH}" SkewBinRecalc "${ROOT}" "${OUT}"
