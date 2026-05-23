#!/bin/bash
set -euo pipefail

export CLASSPATH=/opt/gson.jar

DATA_DIR="${CST_DATA_DIR:-/app/dumps}"
TRIAGE_DIR="${CST_TRIAGE_DIR:-/app/triage}"

mkdir -p "$TRIAGE_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

javac -encoding UTF-8 -cp "$CLASSPATH" -d "$BUILD_DIR" "$SCRIPT_DIR/CrashSigTriageAudit.java"
java -cp "$CLASSPATH:$BUILD_DIR" CrashSigTriageAudit "$DATA_DIR" "$TRIAGE_DIR"
