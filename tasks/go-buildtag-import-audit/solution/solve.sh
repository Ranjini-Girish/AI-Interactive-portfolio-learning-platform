#!/bin/bash
set -euo pipefail

# Login shells (e.g. bash -lc) sometimes start with an empty PATH, which
# hides the Go toolchain shipped in the golang image. Ensure it is visible
# before invoking go.
export PATH="/usr/local/go/bin:${PATH:-/usr/bin:/bin}"

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p /app/src /app/bin /app/outcome

cp "$SOL_DIR"/btagaudit.go /app/src/main.go

cd /app/src
if [ ! -f go.mod ]; then
  go mod init btagaudit >/dev/null 2>&1
fi

GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/bin/btag-audit .

BTA_BUILDTAG_DIR="${BTA_BUILDTAG_DIR:-/app/buildtag}" \
BTA_OUT_DIR="${BTA_OUT_DIR:-/app/outcome}" \
/app/bin/btag-audit
