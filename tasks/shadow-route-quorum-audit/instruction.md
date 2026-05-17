The ML platform team needs a frozen shadow-route quorum audit that scores canary routes against tier weights, dependency holds, latency drift inside the audit window, and compromise quarantine without rewriting the bundled evidence tree.

Produce five UTF-8 JSON documents under `/app/audit/` named `route_profiles.json`, `dependency_report.json`, `degrade_report.json`, `compromise_report.json`, and `summary.json`. Status vocabulary, tier quorum math, overlay merge order, median-latency degradation, dependency blocking, and canonical JSON layout are defined in `/app/shadowroute/SPEC.md`.

Bundled inputs live under `/app/shadowroute/`. When `SRQ_DATA_DIR` is set to a non-empty value it replaces the input root; when `SRQ_AUDIT_DIR` is set to a non-empty value it replaces the output directory. If either variable is unset or empty, reads default to `/app/shadowroute/` and writes to `/app/audit/`. Create the output directory when missing. Do not modify the bundled `/app/shadowroute/` tree.
