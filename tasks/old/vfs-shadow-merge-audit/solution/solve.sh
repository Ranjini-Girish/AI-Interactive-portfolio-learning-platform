#!/bin/bash
set -euo pipefail

export PATH="/usr/local/go/bin:${PATH}"

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_vfs_build
cp "$SOL_DIR/main.go" /app/_vfs_build/main.go
cp "$SOL_DIR/go.mod" /app/_vfs_build/go.mod
cd /app/_vfs_build
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_vfs_build/vfs .

VFS_DATA_DIR="${VFS_DATA_DIR:-/app/vfs_shadow}" \
VFS_AUDIT_DIR="${VFS_AUDIT_DIR:-/app/audit}" \
/app/_vfs_build/vfs
