#!/bin/bash
set -euo pipefail

export CLASSPATH=/opt/gson.jar

DATA_DIR="${GHA_DATA_DIR:-/app/repos}"
AUDIT_DIR="${GHA_AUDIT_DIR:-/app/audit}"

mkdir -p "$AUDIT_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

javac -cp "$CLASSPATH" -d "$BUILD_DIR" "$SCRIPT_DIR/GitHookGateAudit.java"
java -cp "$CLASSPATH:$BUILD_DIR" GitHookGateAudit "$DATA_DIR" "$AUDIT_DIR"
