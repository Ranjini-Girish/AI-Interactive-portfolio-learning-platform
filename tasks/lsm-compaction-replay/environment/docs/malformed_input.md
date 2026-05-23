# Malformed input

Every condition listed here must cause the binary to exit non-zero
and leave `argv[2]` empty of any output your binary wrote.

## File-level

- `events.json` or `config.json` missing from `argv[1]`.
- Any of those files unreadable (e.g. argv[1] entry is a directory).
- Any of those files does not parse as JSON.
- The top-level value of any input file is not a JSON object.

## `events.json`

- Top-level is not exactly `{"events": [...]}`.
- Any record missing or carrying extra keys.
- `event_id` not a non-empty string; duplicate `event_id`.
- `ts_unix_ms` not a non-negative integer.
- `type` not in `{"flush_memtable","compact"}`.
- `payload` not an object whose key set exactly matches the
  type-specific schema (see state_machine.md).
- `payload.seg_id` (flush_memtable) not a non-empty string.
- `payload.size_bytes` (flush_memtable) not a non-negative integer.
- `payload.level` (compact) not a non-negative integer.

## `config.json`

- Top-level keys are not exactly
  `{"now_unix_ms", "max_level", "compaction_min_segments"}`.
- `now_unix_ms` or `max_level` not non-negative integers.
- `compaction_min_segments` not a positive integer.

## argv

- argv count != 3 (binary name + two positional args).
- `argv[1]` does not exist or is not a directory.
- `argv[2]` does not exist or is not a directory.

## Runtime / internal failures

- A pre-existing entry at any of the five output names in `argv[2]`.
- A pre-existing `.partial` staging entry at any of the five output
  names.
- A failed `write()` or `rename()` while staging or committing.
- Any other condition that prevents emitting all five outputs cleanly.

On any of the above, all staged temporaries are removed and any
already-renamed siblings are unlinked before the binary exits non-zero.
