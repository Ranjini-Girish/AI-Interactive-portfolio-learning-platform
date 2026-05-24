#!/bin/bash
# Shared helpers for deploy manifest audit pipeline.

AUDIT_TMP="${AUDIT_TMP:-/tmp/audit}"
POLICY_FILE="/app/config/policy.json"

ensure_audit_tmp() {
  mkdir -p "$AUDIT_TMP"
}

normalize_id() {
  # BUG: uppercases only; does not strip separators or lowercase
  echo "$1" | tr '[:lower:]' '[:upper:]'
}

read_policy_field() {
  local field="$1"
  jq -r ".${field}" "$POLICY_FILE"
}
