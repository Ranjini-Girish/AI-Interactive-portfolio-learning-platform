Operations wants a frozen replay audit of the dedupe lab bundle under `/app/qdw_lat/` after the sliding window, accepted incident bumps, and per-key last-accept memory are applied together. Keep the bundle read-only and write only the UTF-8 JSON artifacts named in `/app/qdw_lat/SPEC.md` into the audit directory using the canonical serializer described there.

The specification also defines filename iteration order, inclusive window comparisons, and how `weight_applied` rounds. When `QDW_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/qdw_lat/`. When `QDW_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. If a variable is unset or empty, use `/app/qdw_lat/` for reads and `/app/audit/` for writes. Create the audit directory when missing.

Anchors and ancillary JSON under `/app/qdw_lat/anchors/` and `/app/qdw_lat/ancillary/` stay untouched but must remain present for integrity checks bundled with the dataset.

`pool_state.json` and `domain_layout.json` are witness files for this bundle revision. They must remain byte-identical to the shipped copies and still parse as JSON if your tooling reads them, but the dedupe math itself is fully defined in `/app/qdw_lat/SPEC.md` including how float timestamps interact with the inclusive window edge.
