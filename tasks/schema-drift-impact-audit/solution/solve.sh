#!/bin/bash
set -euo pipefail

export CLASSPATH=/opt/gson.jar

DATA_DIR="${SDI_APP_DATA:-/app/data}"
OUT_DIR="${SDI_APP_OUTPUT:-/app/output}"

mkdir -p "$OUT_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

javac -encoding UTF-8 -cp "$CLASSPATH" -d "$BUILD_DIR" "$SCRIPT_DIR/SchemaDriftImpactAudit.java"
java -cp "$CLASSPATH:$BUILD_DIR" SchemaDriftImpactAudit "$DATA_DIR" "$OUT_DIR"
