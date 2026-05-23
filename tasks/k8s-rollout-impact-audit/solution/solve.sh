#!/bin/bash
set -euo pipefail

export CLASSPATH=/opt/gson.jar:/opt/snakeyaml.jar

DATA_DIR="${KRI_APP_DATA:-/app/data}"
OUT_DIR="${KRI_APP_OUTPUT:-/app/output}"

mkdir -p "$OUT_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

javac -encoding UTF-8 -cp "$CLASSPATH" -d "$BUILD_DIR" "$SCRIPT_DIR/K8sRolloutImpactAudit.java"
java -cp "$CLASSPATH:$BUILD_DIR" K8sRolloutImpactAudit "$DATA_DIR" "$OUT_DIR"
