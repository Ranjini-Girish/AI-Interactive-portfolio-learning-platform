#!/bin/bash
# Parse queue.log (syslog-style)
source "$(dirname "$0")/../lib/common.sh"
source "$(dirname "$0")/../lib/logging.sh"

input_file="${1:?Usage: parse_queue.sh <logfile>}"
source "$(dirname "$0")/../config/pipeline.conf" 2>/dev/null || true
year="${LOG_YEAR:-2024}"

log_info "Parsing queue log: $input_file"

month_to_num() {
    case "$1" in
        Jan) echo 01 ;; Feb) echo 02 ;; Mar) echo 03 ;;
        Apr) echo 04 ;; May) echo 05 ;; Jun) echo 06 ;;
        Jul) echo 07 ;; Aug) echo 08 ;; Sep) echo 09 ;;
        Oct) echo 10 ;; Nov) echo 11 ;; Dec) echo 12 ;;
    esac
}

while IFS= read -r line; do
    [[ -z "$line" ]] && continue

    month_abbr=$(echo "$line" | awk '{print $1}')
    day=$(echo "$line" | awk '{print $2}')
    time_str=$(echo "$line" | awk '{print $3}')
    month_num=$(month_to_num "$month_abbr")

    # Build ISO-ish timestamp
    timestamp="${year}-${month_num}-$(printf '%02d' "$day")T${time_str}Z"

    # Extract fields from the message portion
    msg="${line#*]: }"
    event_type=$(echo "$msg" | awk '{print $1}')
    trace_id=$(extract_kv "$msg" "trace_id")
    status=$(extract_kv "$msg" "status")
    latency=$(extract_kv "$msg" "latency_ms")

    emit_event "$timestamp" "queue" "$event_type" "$trace_id" "$latency" "$status" ""
done < "$input_file"
