# Span shard reconciliation

All JSON consumed and emitted by the tool uses UTF-8, two-space indentation, sorted object keys at every object level, ASCII-only text, and a single trailing newline after the closing value.

## Inputs

The data directory is `/app/data/`. Read every file matching `shards/*.json` (non-recursive; only the immediate `shards` directory). Sort paths by their file name string ascending (the `*.json` stem sort, not inode order). Each file must contain a JSON array at the top level; if a file is missing, unreadable, not valid JSON, or its top-level value is not an array, treat that file as contributing zero rows.

Each array element must be a JSON object to be considered a **row**. A row is **well-formed** when all of the following hold:

- `trace_id` is a non-empty ASCII string.
- `span_id` is a non-empty ASCII string.
- `parent_id` is either JSON `null` or a string (the empty string is allowed as a string value).
- `start_ms` and `end_ms` are JSON numbers that are integers (no fractional part). They may be negative.

Process rows in global order: iterate sorted shard filenames, and within each file iterate the array from first element to last. Only well-formed rows receive a zero-based **global index** in that combined order starting at 0 and increasing by one for each subsequent well-formed row. Objects that are not well-formed are ignored and do not receive an index and do not shift the index counter.

## Duplicate handling

Maintain, per `trace_id`, the set of `span_id` values already **claimed** by an earlier well-formed row. When a well-formed row arrives:

- If its `span_id` is not yet claimed for that `trace_id`, **claim** it: this row is the **canonical row** for `(trace_id, span_id)`.
- If its `span_id` is already claimed, the row is a **duplicate row**. Record a duplicate event with fields `trace_id`, `span_id`, `first_index` (the global index of the canonical row), and `later_index` (the global index of this duplicate row). Duplicate rows never change the claimed canonical row and never participate in tree structure, orphan detection, depth, or self-parent classification.

## Time validity

For every well-formed row (including duplicates), if `end_ms < start_ms`, count one **invalid time** occurrence for its `trace_id` and `span_id` at that row's global index.

## Structural classification (canonical rows only)

Only canonical rows participate in the graph model below.

Define **self-parent** when `parent_id` is a string equal to `span_id`.

Otherwise, when `parent_id` is a non-null string **P**:

- If **P** is not equal to any claimed `span_id` in the same `trace_id`, the canonical row is an **orphan** (missing parent).

When `parent_id` is JSON `null`, the canonical row is a **root**.

## Children and depth

For each trace, build directed edges **parent_span_id → child_span_id** for every canonical row that is not self-parent and not orphan, where `parent_id` equals the parent's `span_id` and both sides are canonical ids inside the trace.

Roots are canonical rows with `parent_id` equal to JSON `null`. The **depth** of a root is 0. The depth of any other canonical row that is not self-parent and not orphan is one plus the depth of its parent, computed only along edges where the parent is also non-orphan and non-self-parent. If a depth would be undefined because a parent is missing from the edge construction, treat depth as undefined for that row (it should not occur for non-orphan rows).

`max_depth` for a trace is the maximum depth among all canonical rows that have a defined depth; if none have defined depth, use 0.

## Outputs

Write exactly three files under `/app/output/` as regular files and nowhere else at the top level:

1. `summary.json` with integer fields:
   - `duplicate_events`: number of duplicate rows recorded.
   - `ingested_well_formed_rows`: count of well-formed rows across all shards in global order.
   - `invalid_time_events`: count of invalid time occurrences across all well-formed rows.
   - `orphan_canonical_rows`: number of canonical rows classified as orphan.
   - `self_parent_canonical_rows`: number of canonical rows classified as self-parent.
   - `trace_count`: number of distinct `trace_id` values that appear on at least one well-formed row.

2. `duplicates.json` with key `events`, an array of objects sorted ascending by the tuple (`trace_id`, `span_id`, `later_index`, `first_index`). Each object carries the four string/integer fields `trace_id`, `span_id`, `first_index`, `later_index`.

3. `traces.json` with key `traces`, an array of objects sorted ascending by `trace_id`. Each object has:
   - `trace_id` (string)
   - `canonical_span_count`: number of canonical rows for this trace
   - `duplicate_events_in_trace`: duplicate events whose `trace_id` equals this trace
   - `invalid_time_events_in_trace`: invalid time events whose `trace_id` equals this trace
   - `max_depth` (integer)
   - `orphan_span_ids`: sorted list of `span_id` for canonical orphan rows in this trace
   - `roots`: sorted list of `span_id` for canonical roots in this trace
   - `self_parent_span_ids`: sorted list of `span_id` for canonical self-parent rows in this trace

If no well-formed rows are ingested, emit `summary.json` with every counter field set to 0, `duplicates.json` with `events: []`, and `traces.json` with `traces: []`.

## Determinism

When multiple valid orderings could exist, the shard filename sort and the rules above define the unique reference behaviour.
