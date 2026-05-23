# Malformed Input

The binary MUST exit with a non-zero status code and write **nothing**
under `argv[2]` on any of the following conditions.

## CLI

* `argv` count is not exactly 3 (program name + input dir + output
  dir).
* `argv[1]` does not exist or is not a readable directory.

## Files

Any of `namespaces.json`, `allocations.json`, `config.json` that is
missing, unreadable, or fails JSON parsing.

## `namespaces.json`

* `namespaces` is not an array.
* Any entry is not an object, or is missing `name`, `parent`, or
  `limits`.
* `name` is not a non-empty string.
* Two entries share the same `name`.
* `parent` is neither `null` nor a string referencing another declared
  namespace.
* Zero roots (no entry with `parent == null`) or more than one root.
* The tree contains a cycle.
* `limits` is not an object or is missing any of `cpu`, `memory`,
  `storage`.
* Any `limits[r]` is not a non-negative integer.

## `allocations.json`

* `events` is not an array.
* Any entry is missing `event_id`, `ts_unix_ms`, `namespace`, `op`, or
  `resources`.
* `event_id` not a non-empty string; duplicate `event_id` across
  events.
* `ts_unix_ms` not a non-negative integer.
* `namespace` not a non-empty string.
* `op` not in `{"allocate","release"}`.
* `resources` not an object or missing `cpu`, `memory`, `storage`.
* Any `resources[r]` is not a non-negative integer.

## `config.json`

* Missing `now_unix_ms` or `release_unknown_action`.
* `now_unix_ms` not a non-negative integer.
* `release_unknown_action` not in `{"ignore","reject"}`.

## Other

Any internal failure (allocation error, file write error, rename
failure) MUST also result in a non-zero exit and no output files.
