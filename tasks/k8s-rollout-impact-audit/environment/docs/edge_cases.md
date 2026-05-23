# Edge cases

The dataset deliberately exercises every corner of the contract. A correct solution must handle each.

## Drift edge cases

- **Whitespace-only `name`** — falls back to `image` value as the workload name.
- **Missing or null `namespace`** — collapses to `"default"`.
- **Duplicate `(workload_name, namespace)` within a namespace** — first occurrence wins; later duplicates are dropped silently.
- **List-valued spec key** — a list under e.g. `env.WARM_KEYS` must be diffed by deep equality. A list that grows by one element produces an `env` delta where both sides are full dicts.
- **Identity collision via namespace rename** — when a workload's namespace changes between revisions, the identity changes too, so the workload appears in both `removed_workloads` (old identity) and `added_workloads` (new identity).
- **Spec key absent on one side only** — appears in `changed_fields` with the missing side reported as `null`.

## Resolver edge cases

- **First replace wins** — when two `replace` rules share the same `from` pair, only the first is honored. The second is silently ignored.
- **Replace is non-transitive** — `A 1.0 -> B 1.0` followed by `B 1.0 -> C 1.0` produces `B 1.0`, never `C 1.0`, when starting from `A 1.0`.
- **Excluded version with valid bump** — `lib/network 1.3.0` is excluded; the resolver bumps to `1.4.0` because `1.4.0` is not excluded.
- **Excluded version with chained excludes** — when consecutive registry versions are all excluded, the resolver chains forward across the exclude run until it finds a valid bump.
- **Excluded version with no bump** — produces a `<name>@<version>` entry in `conflicts`. The pair is dropped from selection.
- **Max-version selection across seeds** — when `release.require` and a workload-map seed disagree on the version of the same name, the max wins.
- **Missing chart entry** — a `(name, version)` pair that is selected but absent from the registry is reported in `missing` and is not expanded.
- **Invalid semver / non-3-int versions** — silently dropped wherever they appear.
- **Self-loop singleton SCC** — counted as a cycle group.
- **Multi-member SCCs** — counted as cycle groups regardless of size.
- **`release.name` excluded from build set** — the release pseudo-chart never appears in `seed_modules`, `impacted_charts`, `cycles`, or `build_order`.

## Output edge cases

- **Trailing newline required** — the file must end with exactly one `\n`.
- **Two-space indent required** — `json.dumps(payload, indent=2)` is the canonical formatter.
- **No mutation of `/app/data/`** — the verifier pins SHA-256 hashes of every input file and re-checks them after solver execution.
