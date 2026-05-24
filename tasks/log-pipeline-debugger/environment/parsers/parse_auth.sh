#!/bin/bash
# Parse auth.log (JSON lines)
source "$(dirname "$0")/../lib/common.sh"
source "$(dirname "$0")/../lib/logging.sh"

input_file="${1:?Usage: parse_auth.sh <logfile>}"

log_info "Parsing auth log: $input_file"

while read line; do
    [[ -z "$line" ]] && continue

    timestamp=$(echo "$line" | jq -r '.ts // empty' 2>/dev/null) || continue
    [[ -z "$timestamp" ]] && continue

    event=$(echo "$line" | jq -r '.event // ""' 2>/dev/null)
    user=$(echo "$line" | jq -r '.user // ""' 2>/dev/null)
    result=$(echo "$line" | jq -r '.result // ""' 2>/dev/null)
    latency=$(echo "$line" | jq -r '.latency_ms // 0' 2>/dev/null)
    trace_id=$(echo "$line" | jq -r '.trace_id // ""' 2>/dev/null)

    emit_event "$timestamp" "auth" "$event" "$trace_id" "$latency" "$result" "user=$user"
done < "$input_file"
