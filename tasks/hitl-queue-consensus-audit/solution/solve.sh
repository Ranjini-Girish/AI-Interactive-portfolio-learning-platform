#!/bin/bash
set -euo pipefail

export CLASSPATH=/opt/gson.jar

mkdir -p "${HCQ_AUDIT_DIR:-/app/audit}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

javac -encoding UTF-8 -cp "$CLASSPATH" -d "$BUILD_DIR" "$SCRIPT_DIR/HitlQueueConsensusAudit.java"
java -cp "$CLASSPATH:$BUILD_DIR" HitlQueueConsensusAudit
