# Data model

Manifests live in `/app/data/manifests/*.json`. Each file has `manifest_id` and a `deployments` array.

Deployment fields: `deployment_id`, `environment`, `artifact_ref`, `build_duration_sec`, `deploy_duration_sec`, `declared_size_bytes`, `overlay`.

Artifact registry: `/app/data/artifacts/registry.json` with `artifacts[]` entries (`artifact_id`, `bundle_path`, `size_bytes`, `sha256`).

Checksum sidecars: `/app/data/checksums/` — one file per bundle, line format `HASH  bundles/name.pkg`.

Overlays: `/app/data/overlays/{base,staging,production}.json` — flat key/value maps merged per policy.
