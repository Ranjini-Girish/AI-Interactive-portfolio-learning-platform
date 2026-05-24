# Output Schema — `dependency_audit.json`

Write to `/app/output/dependency_audit.json`.  
Use 2-space indentation, sorted keys, and a trailing newline.

## Top-level Structure

```json
{
  "findings": [ ... ],
  "query_results": [ ... ],
  "schema_version": 1,
  "source_sha256": { ... },
  "summary": { ... }
}
```

Keys are sorted alphabetically at every nesting level.

## `summary`

```json
{
  "findings_by_severity": {
    "critical": <int>,
    "high": <int>,
    "info": <int>,
    "low": <int>,
    "medium": <int>
  },
  "total_cycles": <int>,
  "total_license_issues": <int>,
  "total_modules_resolved": <int>,
  "total_queries": <int>,
  "total_vulnerabilities_found": <int>
}
```

All five severity levels must appear even if the count is 0.

## `source_sha256`

```json
{
  "config/audit.json": "<hex>",
  "data/queries/query_01.json": "<hex>",
  ...
}
```

Keys: relative paths from `/app/` using forward slashes.  Sorted.

## `query_results`

Array of objects, one per query file, **sorted by `query_id`**:

```json
{
  "build_order": [ "<module_path>", ... ],
  "cycles": [ ["<module_path>", ...], ... ],
  "dependency_tree": {
    "<module_path>@<version>": ["<dep_path>@<dep_ver>", ...],
    ...
  },
  "license_issues": [
    {
      "dependency_license": "<license>",
      "module": "<module_path>",
      "project_license": "<license>",
      "version": "<version>"
    },
    ...
  ],
  "max_depth": <int>,
  "query_id": "<string>",
  "resolution_errors": [ "<description>", ... ],
  "resolved_modules": {
    "<module_path>": "<version>",
    ...
  },
  "retracted_warnings": [
    {
      "module": "<module_path>",
      "version": "<version>"
    },
    ...
  ],
  "total_resolved": <int>,
  "vulnerabilities": [
    {
      "id": "<vuln_id>",
      "module": "<module_path>",
      "severity": "<severity>",
      "title": "<title>",
      "version": "<version>"
    },
    ...
  ]
}
```

### Field Details

- **resolved_modules**: map of module_path → resolved version string.
  Keys sorted alphabetically.  Does **not** include the root module.

- **dependency_tree**: map of `"module@version"` → list of direct
  dependencies as `"dep_module@dep_version"`.  Keys sorted.
  Values (dep lists) sorted.  Only includes modules in the resolved set
  (not the root).

- **build_order**: list of module paths in build order (see algorithms.md §6).
  Omits modules involved in cycles.

- **cycles**: list of cycles.  Each cycle is a sorted list of module paths.
  Outer list sorted by first element of each cycle.

- **max_depth**: integer, maximum depth in the resolved graph (§7).

- **vulnerabilities**: list of vulnerability matches, sorted by `id` then
  `module`.  Each entry includes the resolved version that matched.

- **license_issues**: list of incompatibilities, sorted by `module` then
  `version`.

- **retracted_warnings**: list of retracted version usages, sorted by
  `module`.

- **resolution_errors**: list of error descriptions for unresolvable
  modules.  Sorted alphabetically.  Format: `"<module_path>: no version
  satisfying >= <constraint>"`.

- **total_resolved**: integer count of resolved modules (excluding root).

## `findings`

Global findings list across all queries.  Each finding:

```json
{
  "description": "<human-readable description>",
  "query_id": "<which query>",
  "severity": "<critical|high|medium|low|info>",
  "type": "<finding_type>"
}
```

Finding types and their severities are defined in `config/audit.json`
under `finding_severity`.

Findings are sorted by: severity_rank ascending, then type ascending,
then query_id ascending.

Include a finding for each vulnerability match, license issue, cycle,
retracted version usage, and deep dependency chain (max_depth >=
`deep_chain_threshold`).
