Lab automation needs a reproducible audit of the frozen thermal guard bundle under `/app/tgr_lat/` after ramp-per-day growth, additive incident deltas, and the hard ceiling are applied together. Keep the bundle read-only and write only the UTF-8 JSON artifacts named in `/app/tgr_lat/SPEC.md` into the audit directory using the canonical serializer described there.

The specification also defines ordering of entries, rounding for emitted temperatures, and how the summary counts zones. When `TGR_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/tgr_lat/`. When `TGR_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. If a variable is unset or empty, use `/app/tgr_lat/` for reads and `/app/audit/` for writes. Create the audit directory when missing.

Anchors and ancillary JSON under `/app/tgr_lat/anchors/` and `/app/tgr_lat/ancillary/` stay untouched but must remain present for integrity checks bundled with the dataset.

`domain_layout.json` is a witness file for this bundle revision alongside the pool snapshot. It must remain byte-identical to the shipped copy and still parse as JSON if your tooling reads it. The ramp, additive incidents, ceiling, and per-zone rounding are fully defined in `/app/tgr_lat/SPEC.md`.
