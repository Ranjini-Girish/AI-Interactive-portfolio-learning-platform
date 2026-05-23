# Dependency Resolver Semantics

The dependency resolver matches requirements to module versions iteratively.

## 1. Registry Concatenation
- The registry is constructed by loading and concatenating the JSON arrays from all files under `/app/data/modules/*.json` in ASCII-ascending order of their filenames.
- For each module entry, validate:
  - `name`: a non-empty string.
  - `version`: a string in strict `MAJOR.MINOR.PATCH` semver format with non-negative integers.
  - `require`: optional list of child requirements, keeping only valid child `{name, version}` pairs.
- For duplicate `name@version` definitions in the concatenated registry, retain only the **first** encountered definition.

## 2. Constraints Setup
Parsed from `/app/data/root.json`:
- `root.require`: Base requirement seed pairs.
- `root.replace`: Array of `{from: {name, version}, to: {name, version}}`. First duplicate `from` wins.
- `root.exclude`: Array of `{name, version}` pairs.

## 3. Resolution Step Rules
For every encountered `(name, version)` pair:
1. **Replace**: If the exact `(name, version)` matches a `from` key in the replace constraints, replace it with the `to` value exactly once. This step is non-transitive (do not chain multiple replaces).
2. **Exclude**: If the post-replace `(name, version)` is in the exclude set, upgrade it to the smallest available version of the same name in the registry that is strictly greater than the current version and is not excluded. This step **does** chain (keep stepping up if the upgraded version is also excluded). If no valid unexcluded upgrade is available, record a conflict `<name>@<version>` and skip the requirement.
3. **Max Version Wins**: For each module `name`, the retained version is the maximum `MAJOR.MINOR.PATCH` value that survives steps 1–2 across all requirements for that module name. Note that retained versions do not re-run the replace rule (replace only triggers on incoming requirements).

## 4. Requirement Seeding & Expansion
- **Incoming Seeds**:
  - All valid requirements in `root.require`.
  - All valid requirements mapped to changed tasks. Changed task references are strings format `<play_name>::<task_name>` (for added, removed, or modified tasks) looked up in `/app/data/task_dependency_map.json`.
- **Iterative Resolution**:
  - Repeat the expansion of requirements for all retained modules until no further changes occur (no new module is selected, and no selected version is upgraded).
  - If a selected `(name, version)` is missing from the registry, record a missing `<name>@<version>` error and do not expand its children.
  - Otherwise, resolve all `require` children of the selected version using the resolution steps.

## 5. Selected Total & Build Set
- The **build set** consists of all selected modules whose resolved version exists in the registry, **excluding `root.name`**.
- `resolver_summary.selected_total` is the exact size of this build set.
