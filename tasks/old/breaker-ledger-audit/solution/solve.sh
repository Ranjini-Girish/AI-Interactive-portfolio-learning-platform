#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_cbsa_build
cp "$SOL_DIR/Main.java" /app/_cbsa_build/Main.java
GSON_JAR="$(find /usr/share/java -maxdepth 1 -name '*gson*.jar' | head -n 1)"
if [ -z "$GSON_JAR" ]; then
  echo "missing Gson jar under /usr/share/java" >&2
  exit 1
fi
javac -cp "$GSON_JAR" -d /app/_cbsa_build /app/_cbsa_build/Main.java

CBSA_DATA_DIR="${CBSA_DATA_DIR:-/app/breakers}" \
CBSA_AUDIT_DIR="${CBSA_AUDIT_DIR:-/app/audit}" \
java -cp "/app/_cbsa_build:$GSON_JAR" Main
