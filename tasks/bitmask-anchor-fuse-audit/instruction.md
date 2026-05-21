Security review automation needs a reproducible audit of the frozen bitmask fuse bundle under `/app/baf_lat/` after XOR-accumulator incidents, fuse masks, and per-node scaling are applied together. Keep the bundle read-only and write only the UTF-8 JSON artifacts named in `/app/baf_lat/SPEC.md` into the audit directory using the canonical serializer described there.

The specification also defines XOR chaining for accepted incidents, how masks combine with the fuse and base OR, and how scores round. When `BAF_DATA_DIR` is non-empty, read inputs from that directory instead of `/app/baf_lat/`. When `BAF_AUDIT_DIR` is non-empty, write outputs there instead of `/app/audit/`. If a variable is unset or empty, use `/app/baf_lat/` for reads and `/app/audit/` for writes. Create the audit directory when missing.

Anchors and ancillary JSON under `/app/baf_lat/anchors/` and `/app/baf_lat/ancillary/` stay untouched but must remain present for integrity checks bundled with the dataset.

`pool_state.json` and `domain_layout.json` are witness files for this bundle revision. They must remain byte-identical to the shipped copies and still parse as JSON if your tooling reads them. The fuse math, XOR incident chain, and score rounding are fully defined in `/app/baf_lat/SPEC.md`.
