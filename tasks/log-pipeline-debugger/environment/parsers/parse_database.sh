#!/bin/bash
# Parse database.log (bracket-timestamp key-value pairs)
source "$(dirname "$0")/../lib/common.sh"
source "$(dirname "$0")/../lib/logging.sh"

input_file="${1:?Usage: parse_database.sh <logfile>}"

log_info "Parsing database log: $input_file"

while IFS= read -r line; do
    [[ -z "$line" ]] && continue

    # Extract timestamp from brackets
    timestamp="${line%%]*}"
    timestamp="${timestamp#\[}"

    # Extract key-value content after the bracket
    content="${line#*] }"

    query=$(extract_kv "$content" "query")
    table=$(extract_kv "$content" "table")
    duration=$(extract_kv "$content" "duration_ms")
    status=$(extract_kv "$content" "status")
    trace_id=$(extract_kv "$content" "trace_id")

    # Convert bracket-style timestamp to ISO-like format
    iso_ts="${timestamp/ /T}"
    emit_event "$iso_ts" "database" "$query $table" "$trace_id" "$duration" "$status" ""
done < "$input_file"
