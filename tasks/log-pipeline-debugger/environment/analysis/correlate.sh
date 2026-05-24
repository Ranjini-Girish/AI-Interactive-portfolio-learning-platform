#!/bin/bash
# Correlate events by trace_id and produce per-trace summary
source "$(dirname "$0")/../lib/logging.sh"

input_file="${1:?Usage: correlate.sh <input> <output>}"
output_file="${2:?Usage: correlate.sh <input> <output>}"

log_info "Correlating events by trace_id"

# Get unique trace IDs
trace_ids=$(cut -f4 "$input_file" | sort -u)

> "$output_file"
for trace_id in $trace_ids; do
    event_count=0
    has_error="false"
    services=()
    min_ts=999999999999
    max_ts=0

    # Collect events for this trace
    grep "$trace_id" "$input_file" | while IFS=$'\t' read -r ts svc evt tid lat status det; do
        event_count=$((event_count + 1))

        # Track unique services
        local found=false
        for s in "${services[@]}"; do
            [[ "$s" == "$svc" ]] && found=true && break
        done
        $found || services+=("$svc")

        # Track error status
        [[ "$status" == "ERROR" ]] && has_error="true"

        # Track time range
        (( ts < min_ts )) && min_ts=$ts
        (( ts > max_ts )) && max_ts=$ts
    done

    svc_count=${#services[@]}
    printf '%s\t%d\t%d\t%s\n' "$trace_id" "$event_count" "$svc_count" "$has_error" >> "$output_file"
done

log_info "Correlated $(wc -l < "$output_file" | tr -d ' ') traces"
