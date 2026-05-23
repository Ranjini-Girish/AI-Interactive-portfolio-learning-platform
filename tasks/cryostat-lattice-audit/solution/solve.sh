#!/bin/bash
set -euo pipefail

export CLASSPATH=/opt/gson.jar

DATA_DIR="${CLR_DATA_DIR:-/app/cryostat}"
AUDIT_DIR="${CLR_AUDIT_DIR:-/app/audit}"

mkdir -p "$AUDIT_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

javac -encoding UTF-8 -cp "$CLASSPATH" -d "$BUILD_DIR" "$SCRIPT_DIR/CryostatLatticeAudit.java"
java -cp "$CLASSPATH:$BUILD_DIR" CryostatLatticeAudit "$DATA_DIR" "$AUDIT_DIR"
