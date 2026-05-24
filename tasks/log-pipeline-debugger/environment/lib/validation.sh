#!/bin/bash
# Input validation utilities

validate_file_exists() {
    local path="$1"
    local desc="${2:-file}"
    if [[ ! -f "$path" ]]; then
        echo "ERROR: $desc not found: $path" >&2
        return 1
    fi
}

validate_directory() {
    local path="$1"
    if [[ ! -d "$path" ]]; then
        mkdir -p "$path" || { echo "ERROR: Cannot create $path" >&2; return 1; }
    fi
}

count_lines() {
    local file="$1"
    wc -l < "$file" | tr -d ' '
}

validate_tsv_columns() {
    local file="$1"
    local expected="$2"
    local actual
    actual=$(head -1 "$file" | awk -F'\t' '{print NF}')
    if [[ "$actual" != "$expected" ]]; then
        echo "ERROR: Expected $expected columns, got $actual in $file" >&2
        return 1
    fi
}
