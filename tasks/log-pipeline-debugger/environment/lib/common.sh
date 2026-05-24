#!/bin/bash
# Common utility functions for the pipeline

emit_event() {
    local timestamp="$1"
    local service="$2"
    local event_type="$3"
    local trace_id="$4"
    local latency_ms="$5"
    local status="$6"
    local details="${7:-}"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$timestamp" "$service" "$event_type" "$trace_id" "$latency_ms" "$status" "$details"
}

extract_kv() {
    local input="$1"
    local key="$2"
    echo "$input" | grep -oP "${key}=\K[^ ]+"
}

map_http_status() {
    local code="$1"
    if (( code >= 500 )); then
        echo "ERROR"
    elif (( code >= 400 )); then
        echo "CLIENT_ERROR"
    else
        echo "OK"
    fi
}

safe_divide() {
    local numerator="$1"
    local denominator="$2"
    if [[ "$denominator" == "0" ]] || [[ -z "$denominator" ]]; then
        echo "0.000000"
    else
        awk "BEGIN {printf \"%.6f\", $numerator / $denominator}"
    fi
}
