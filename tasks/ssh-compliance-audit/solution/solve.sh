#!/bin/bash
set -euo pipefail

export CLASSPATH=/opt/gson.jar

DATA_DIR="${SSH_COMPLIANCE_DATA_DIR:-/app/data}"
AUDIT_DIR="${SSH_COMPLIANCE_AUDIT_DIR:-/app/audit}"

mkdir -p "$AUDIT_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

javac -encoding UTF-8 -cp "$CLASSPATH" -d "$BUILD_DIR" "$SCRIPT_DIR/SshComplianceAudit.java"
java -cp "$CLASSPATH:$BUILD_DIR" SshComplianceAudit "$DATA_DIR" "$AUDIT_DIR"
