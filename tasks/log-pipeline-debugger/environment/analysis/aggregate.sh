#!/bin/bash
# Compute per-service statistics
source "$(dirname "$0")/../lib/common.sh"
source "$(dirname "$0")/../lib/logging.sh"

input_file="${1:?Usage: aggregate.sh <input> <output>}"
output_file="${2:?Usage: aggregate.sh <input> <output>}"

log_info "Aggregating per-service statistics"

services=$(cut -f2 "$input_file" | sort -u)

> "$output_file"
for service in $services; do
    events=0
    errors=0
    total_latency=0

    while IFS=$'\t' read -r ts svc evt tid lat status det; do
        events=$((events + 1))
        [[ "$status" == "ERROR" ]] && errors=$((errors + 1))
        total_latency=$(awk "BEGIN {printf \"%.6f\", $total_latency + $lat}")
    done < <(grep "	${service}	" "$input_file")

    error_rate=$(safe_divide "$errors" "$events")
    avg_latency=$(safe_divide "$total_latency" "$events")

    printf '%s\t%d\t%d\t%s\t%s\n' "$service" "$events" "$errors" "$error_rate" "$avg_latency" >> "$output_file"
done

log_info "Aggregated stats for $(echo "$services" | wc -w | tr -d ' ') services"
