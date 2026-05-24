# webhook_audit.json

Top-level keys in order: `schema_version`, `summary`, `source_hashes`, `endpoint_audits`, `findings`.

`schema_version` is integer 1.

`summary` keys: `total_endpoints`, `total_deliveries`, `total_findings`, `findings_by_severity`, `aggregate_risk_score`. `findings_by_severity` always includes all five severity keys.

`source_hashes`: SHA-256 hex of normalized UTF-8 for every file under `config/`, `endpoints/`, `deliveries/` (relative path keys sorted). Normalization: CRLF to LF, strip one trailing LF if present.

`endpoint_audits` sorted by `endpoint_id`. Each audit: `endpoint_id`, `name`, `retry_policy`, `metrics`, `deliveries`, `findings`.

`metrics`: `total_deliveries`, `success_count`, `failure_rate`, `avg_attempts_to_success`, `invalid_signature_count`.

`deliveries` sorted by `delivery_id`. Each: `delivery_id`, `attempt_count`, `final_status`, `signature_valid`, `attempts` (sorted by attempt_number).

`attempts` entries include: `attempt_number`, `status`, `sent_at`, `received_at`, `signature_valid`, `expected_signature`, `actual_signature`.

`findings` global list as in findings_catalog.md.
