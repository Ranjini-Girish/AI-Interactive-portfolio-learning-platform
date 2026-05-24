#!/bin/bash
# Enrich events with derived fields (no-op placeholder for extensibility)
source "$(dirname "$0")/../lib/logging.sh"

input_file="${1:?Usage: enrich_events.sh <input> <output>}"
output_file="${2:?Usage: enrich_events.sh <input> <output>}"

log_info "Enriching events (pass-through)"
cp "$input_file" "$output_file"
