#!/bin/bash
# Parse webserver.log (pipe-delimited)
source "$(dirname "$0")/../lib/common.sh"
source "$(dirname "$0")/../lib/logging.sh"

input_file="${1:?Usage: parse_webserver.sh <logfile>}"

log_info "Parsing webserver log: $input_file"

while IFS='|' read -r timestamp method path status_code latency_ms trace_id; do
    [[ -z "$timestamp" ]] && continue
    status=$(map_http_status "$status_code")
    emit_event "$timestamp" "webserver" "$method $path" "$trace_id" "$latency_ms" "$status" "code=$status_code"
done < "$input_file"
