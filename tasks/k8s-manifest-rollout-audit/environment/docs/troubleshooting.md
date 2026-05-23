# Troubleshooting

## "My output differs from the expected JSON byte-for-byte"

- Confirm `json.dumps(payload, indent=2) + "\n"` and UTF-8 encoding.
- Confirm you did not introduce extra trailing whitespace.
- Confirm you preserve the head-then-fixed-order layout for `spec` (do **not** call `sorted()` on it).

## "My SHA-256 fields are wrong"

The hashes are computed from the raw bytes of `/app/data/baseline-manifests.yml` and `/app/data/current-manifests.yml`. Do not parse and re-emit the YAML before hashing — that breaks the digest.

## "The resolver picks the wrong version"

- Replace is applied **once** and **non-transitively**. Do not chain replace rules.
- Replace is applied **before** exclude. The exclude check uses the post-replace pair.
- Once a name is in `selected`, replace is **not** re-applied to it during expansion.
- Max-version wins across all seed sources for a single name.

## "My cycle count is off"

- Singleton SCCs with a self-edge **are** cycle groups.
- Singleton SCCs without a self-edge are **not** cycle groups.
- Cycles must be detected on the build-set graph after replace + exclude resolution, not on the raw registry.

## "My build_order has steps in the wrong order"

- Tie-break by smallest member name (ASCII ascending) when multiple SCCs are simultaneously eligible.
- Within a step, members must be ASCII-ascending.
- All transitive dependencies of a step must already have appeared in earlier steps.
