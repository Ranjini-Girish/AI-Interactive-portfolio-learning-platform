#!/bin/bash
# Build the live SQLite payments ledger from the migration files.
# Idempotent: deletes any existing state.db before rebuilding.
set -euo pipefail

DB_PATH="${1:-/var/lib/audit/state.db}"
MIG_DIR="${2:-/app/data/migrations}"

mkdir -p "$(dirname "$DB_PATH")"
rm -f "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm"

for sql_file in $(find "$MIG_DIR" -name '*.sql' | sort); do
    echo "[init_db] applying $sql_file"
    sqlite3 "$DB_PATH" < "$sql_file"
done

# Ensure the file is readable by the audit process.
chmod 0644 "$DB_PATH"
echo "[init_db] state.db built at $DB_PATH"
