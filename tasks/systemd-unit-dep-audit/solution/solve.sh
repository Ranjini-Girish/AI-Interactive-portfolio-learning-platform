#!/bin/bash
set -euo pipefail

export CLASSPATH=/opt/gson.jar

UNITS_DIR="${SUD_UNITS_DIR:-/app/units}"
REPORT_PATH="${SUD_REPORT_PATH:-/app/report.json}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

javac -cp "$CLASSPATH" -d "$BUILD_DIR" "$SCRIPT_DIR/SystemdUnitDepAudit.java"
java -cp "$CLASSPATH:$BUILD_DIR" SystemdUnitDepAudit "$UNITS_DIR" "$REPORT_PATH"
