#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /app/planner/src
cp "${ROOT}/planner.ts" /app/planner/src/main.ts
cd /app/planner && npx tsx src/main.ts
