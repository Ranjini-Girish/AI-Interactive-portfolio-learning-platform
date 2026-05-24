#!/bin/bash
# Parse cache.log (CSV with header)
source "$(dirname "$0")/../lib/common.sh"
source "$(dirname "$0")/../lib/logging.sh"

input_file="${1:?Usage: parse_cache.sh <logfile>}"

log_info "Parsing cache log: $input_file"

first_line=true
while IFS=',' read -r timestamp_ms operation key result latency_us trace_id; do
    if $first_line; then
        first_line=false
        continue
    fi
    [[ -z "$timestamp_ms" ]] && continue

    # Convert epoch ms to ISO-ish format for later normalization
    epoch_sec=$(( timestamp_ms / 1000 ))

    # Convert latency from microseconds to milliseconds
    latency_ms=$(awk "BEGIN {printf \"%.3f\", $latency_us / 1000.0}")

    emit_event "$epoch_sec" "cache" "$operation $key" "$trace_id" "$latency_ms" "$result" ""
done < "$input_file"
