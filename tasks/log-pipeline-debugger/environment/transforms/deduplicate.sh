#!/bin/bash
# Remove duplicate events (same timestamp + service + trace_id)
source "$(dirname "$0")/../lib/logging.sh"

input_file="${1:?Usage: deduplicate.sh <input> <output>}"
output_file="${2:?Usage: deduplicate.sh <input> <output>}"

log_info "Deduplicating events"

before=$(wc -l < "$input_file" | tr -d ' ')

# Sort by timestamp, trace_id, and remove duplicates
sort -t$'\t' -k1,1n -k4,4 -u "$input_file" > "$output_file"

after=$(wc -l < "$output_file" | tr -d ' ')
log_info "Dedup: $before -> $after events (removed $((before - after)))"
