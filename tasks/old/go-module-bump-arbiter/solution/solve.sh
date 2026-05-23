#!/bin/bash
set -euo pipefail

# Login shells (e.g. bash -lc) sometimes start with an empty PATH, which
# hides the Go toolchain shipped in the golang image. Ensure it is visible
# before invoking go.
export PATH="/usr/local/go/bin:${PATH:-/usr/bin:/bin}"

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p /app/src /app/bin /app/decisions

cp "$SOL_DIR"/modarb.go /app/src/main.go

cd /app/src
if [ ! -f go.mod ]; then
  go mod init modarb >/dev/null 2>&1
fi

GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/bin/modarb .

GMBA_MODGRAPH_DIR="${GMBA_MODGRAPH_DIR:-/app/modgraph}" \
GMBA_DECISIONS_DIR="${GMBA_DECISIONS_DIR:-/app/decisions}" \
/app/bin/modarb
