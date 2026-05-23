#!/bin/bash
set -euo pipefail

export CLASSPATH=/opt/gson.jar

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

mkdir -p /app/plan /app/planner/src

cat > /app/planner/Cargo.toml <<'CARGO_END'
[package]
name = "planner"
version = "0.1.0"
edition = "2021"

[dependencies]
serde_json = "1"

[[bin]]
name = "planner"
path = "src/main.rs"
CARGO_END

cat > /app/planner/src/main.rs <<'RUST_END'
fn main() {}
RUST_END

javac -encoding UTF-8 -cp "$CLASSPATH" -d "$BUILD_DIR" "$SCRIPT_DIR/CargoWsBumpAudit.java"
java -cp "$CLASSPATH:$BUILD_DIR" CargoWsBumpAudit
