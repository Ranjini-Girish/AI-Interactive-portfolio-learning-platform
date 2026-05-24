#!/bin/bash
# Normalize all timestamps to Unix epoch seconds
source "$(dirname "$0")/../lib/logging.sh"

input_file="${1:?Usage: normalize_timestamps.sh <input> <output>}"
output_file="${2:?Usage: normalize_timestamps.sh <input> <output>}"

log_info "Normalizing timestamps"

iso_to_epoch() {
    local ts="$1"
    # Handle ISO format: 2024-01-15T08:01:05Z or 2024-01-15T08:01:06+00:00
    local date_part="${ts%%T*}"
    local time_part="${ts#*T}"
    time_part="${time_part%%Z*}"
    time_part="${time_part%%+*}"

    local year="${date_part%%-*}"
    local rest="${date_part#*-}"
    local month="${rest%%-*}"
    local day="${rest#*-}"

    local hour="${time_part%%:*}"
    local rest2="${time_part#*:}"
    local minute="${rest2%%:*}"
    local second="${rest2#*:}"

    # 2024-01-01T00:00:00Z = 1704067200
    local base=1704067200
    local day_offset
    if (( 10#$month == 1 )); then
        day_offset=$(( 10#$day - 1 ))
    else
        day_offset=$(( (10#$month - 1) * 30 + 10#$day - 1 ))
    fi

    # BUG: $hour, $minute, $second may have leading zeros (e.g., "08", "09")
    # which bash interprets as octal — "08" and "09" are invalid octal values
    local seconds_in_day=$(( $hour * 3600 + $minute * 60 + $second ))
    echo $(( base + day_offset * 86400 + seconds_in_day ))
}

> "$output_file"
while IFS=$'\t' read -r timestamp service event_type trace_id latency_ms status details; do
    [[ -z "$timestamp" ]] && continue

    local_epoch=""
    if [[ "$timestamp" =~ ^[0-9]{10}$ ]]; then
        local_epoch="$timestamp"
    elif [[ "$timestamp" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T ]]; then
        local_epoch=$(iso_to_epoch "$timestamp" 2>/dev/null) || continue
    else
        log_warn "Unknown timestamp format: $timestamp"
        continue
    fi

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$local_epoch" "$service" "$event_type" "$trace_id" "$latency_ms" "$status" "$details" \
        >> "$output_file"
done < "$input_file"

log_info "Normalized $(wc -l < "$output_file" | tr -d ' ') events"
