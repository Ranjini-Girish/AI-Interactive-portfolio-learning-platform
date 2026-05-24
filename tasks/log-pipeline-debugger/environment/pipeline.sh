#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/config/pipeline.conf"

WORK_DIR="${WORK_DIR:-/app/work}"
OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DATA_DIR="${DATA_DIR:-/app/data/logs}"

mkdir -p "$WORK_DIR" "$OUTPUT_DIR"

log_info "=== Log Analysis Pipeline ==="

# ── Stage 1: Parse all log files ──
log_info "Stage 1: Parsing log files"
> "$WORK_DIR/parsed_events.tsv"

for parser in "$SCRIPT_DIR"/parsers/parse_*.sh; do
    service=$(basename "$parser" .sh)
    service="${service#parse_}"
    log_file="$DATA_DIR/${service}.log"
    if [[ -f "$log_file" ]]; then
        bash "$parser" "$log_file" >> "$WORK_DIR/parsed_events.tsv"
    else
        log_warn "No log file for $service: $log_file"
    fi
done

parsed_count=$(wc -l < "$WORK_DIR/parsed_events.tsv" | tr -d ' ')
log_info "Parsed $parsed_count events"

# ── Stage 2: Normalize timestamps ──
log_info "Stage 2: Normalizing timestamps"
bash "$SCRIPT_DIR/transforms/normalize_timestamps.sh" \
    "$WORK_DIR/parsed_events.tsv" "$WORK_DIR/normalized_events.tsv"

# ── Stage 3: Enrich ──
log_info "Stage 3: Enriching events"
bash "$SCRIPT_DIR/transforms/enrich_events.sh" \
    "$WORK_DIR/normalized_events.tsv" "$WORK_DIR/enriched_events.tsv"

# ── Stage 4: Deduplicate ──
log_info "Stage 4: Deduplicating"
bash "$SCRIPT_DIR/transforms/deduplicate.sh" \
    "$WORK_DIR/enriched_events.tsv" "$WORK_DIR/deduped_events.tsv"

# ── Stage 5: Correlate ──
log_info "Stage 5: Correlating traces"
bash "$SCRIPT_DIR/analysis/correlate.sh" \
    "$WORK_DIR/deduped_events.tsv" "$WORK_DIR/trace_summary.tsv"

# ── Stage 6: Aggregate ──
log_info "Stage 6: Aggregating statistics"
bash "$SCRIPT_DIR/analysis/aggregate.sh" \
    "$WORK_DIR/deduped_events.tsv" "$WORK_DIR/service_stats.tsv"

# ── Stage 7: Detect incidents ──
log_info "Stage 7: Detecting incidents"
bash "$SCRIPT_DIR/analysis/detect_incidents.sh" \
    "$WORK_DIR/service_stats.tsv" "$SCRIPT_DIR/config/thresholds.conf" \
    "$WORK_DIR/incidents.tsv"

# ── Stage 8: Generate report ──
log_info "Stage 8: Generating report"
bash "$SCRIPT_DIR/output/generate_report.sh" \
    "$WORK_DIR/deduped_events.tsv" \
    "$WORK_DIR/trace_summary.tsv" \
    "$WORK_DIR/service_stats.tsv" \
    "$WORK_DIR/incidents.tsv" \
    "$OUTPUT_DIR/report.json"

log_info "=== Pipeline complete ==="
