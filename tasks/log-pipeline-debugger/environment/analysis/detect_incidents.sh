#!/bin/bash
# Detect incidents based on thresholds
source "$(dirname "$0")/../lib/logging.sh"

stats_file="${1:?Usage: detect_incidents.sh <stats> <thresholds> <output>}"
thresholds_file="${2:?Usage: detect_incidents.sh <stats> <thresholds> <output>}"
output_file="${3:?Usage: detect_incidents.sh <stats> <thresholds> <output>}"

log_info "Detecting incidents"

source "$thresholds_file"
err_threshold="${ERROR_RATE_THRESHOLD:-0.1}"
lat_threshold="${AVG_LATENCY_THRESHOLD:-200.0}"

> "$output_file"
while IFS=$'\t' read -r service events errors error_rate avg_latency; do
    [[ -z "$service" ]] && continue

    # Check error rate threshold
    if [[ "$error_rate" > "$err_threshold" ]]; then
        printf 'high_error_rate\t%s\t%s\t%s\n' "$service" "$error_rate" "$err_threshold" >> "$output_file"
    fi

    # Check latency threshold
    if [[ "$avg_latency" > "$lat_threshold" ]]; then
        printf 'high_avg_latency\t%s\t%s\t%s\n' "$service" "$avg_latency" "$lat_threshold" >> "$output_file"
    fi
done < "$stats_file"

log_info "Detected $(wc -l < "$output_file" | tr -d ' ') incidents"
