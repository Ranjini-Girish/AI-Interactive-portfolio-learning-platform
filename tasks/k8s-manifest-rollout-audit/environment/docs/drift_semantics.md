# Drift semantics

Read both manifest files with `yaml.safe_load`. The top-level shape is a list of namespace-groups; each group has a `namespace` and a `manifests` list.

## Identity

A workload's identity is the tuple `(workload_name, namespace)`.

- `namespace` = `group.namespace` stripped if it is a non-empty, non-whitespace string; otherwise the literal string `"default"`. Missing, null, empty, or whitespace-only namespaces all collapse to `"default"`.
- `workload_name` = `manifest.name` stripped if it is a non-empty, non-whitespace string. Otherwise the manifest falls back to `manifest.image` if that key is present and is a non-empty string. If neither rule yields a name, the manifest is silently dropped.

Within a single namespace, the **first** occurrence of a duplicate `(workload_name, namespace)` wins; later duplicates are silently dropped. This applies independently inside baseline and current.

## Spec extraction

For each kept manifest, build the `spec` object by copying keys in this exact order:

1. `kind` — if present.
2. `image` — if present.
3. Then the eight workload-level keys, in this fixed order, only if present on the manifest:

   `replicas, ports, env, probes, resources, schedule, condition, volumeClaim`

Do not copy `name` or `namespace` into `spec`. Do not sort the keys; preserve the head-then-fixed-order layout.

## Diff

Compute three lists by comparing baseline-identity-set with current-identity-set:

- `added_workloads` — identities in current only. Each entry is `{workload_name, namespace, spec}` (the current spec).
- `removed_workloads` — identities in baseline only. Each entry is `{workload_name, namespace, spec}` (the baseline spec).
- `modified_workloads` — identities present in both whose specs differ. Each entry is `{workload_name, namespace, changed_fields}` where `changed_fields` is a map keyed by every key whose old and new values are unequal, ASCII-sorted across the union of old and new keys, with values `{old_value, new_value}`. Workloads with no differing keys are omitted.

Each of the three lists is sorted by `(workload_name, namespace)`.
