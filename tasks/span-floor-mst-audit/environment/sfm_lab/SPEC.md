# Span-floor minimum wiring audit

This document is normative. All JSON on disk uses UTF-8 without a byte order
mark. Canonical JSON for emitted artifacts matches `json.Encoder` defaults
with two-space indentation, recursively sorted object keys, ASCII-only text,
no trailing spaces on lines, and exactly one trailing newline at end of
file.

## Inputs

Read-only data lives under the task data root (default `/app/sfm_lab/`).

Required files:

- `domain_layout.json` with object key `nodes`, a non-empty array of unique
  string node identifiers sorted ascending in the file as given (the audit
  preserves that order for union state).
- `policy.json` with optional numeric `incident_day_floor`. When the field is
  absent or JSON null, only the anchor floor applies.
- `pool_state.json` with integer `current_day` (inclusive upper bound for
  incidents).
- `anchors/day_floor.json` with integer `start_day` used as the baseline
  incident lower day.
- `anchors/window.json` is informational only and MUST NOT change outcomes.
- `incident_log.json` with `events`, an array of objects. Each event SHOULD
  include string `event_id`, numeric `day`, and string `kind`.
- `edges/*.json` one file per undirected edge with keys `edge_id`, `u`, `v`,
  `w` where `w` is a non-negative integer weight.

## Incident window

Let `floor_day = max(start_day, policy.incident_day_floor when present and
not null, otherwise start_day only)`.

An event is **eligible** when it has both `event_id` and `day`, the `day` is
an integer with `floor_day <= day <= current_day`, and the `kind` is one of
the supported kinds below with well-typed payloads. Otherwise the event is
**ignored** (counted but not applied).

Process **all** events from `incident_log.json` in ascending `(day,
event_id)` order (stable). For each event, either apply it (mutating state)
and append the original event object to `applied`, or increment the ignored
counter without mutation.

### Supported kinds

- `raise_weight_floor` requires numeric `floor`. Sets the running weight
  floor to the maximum of its previous value and `floor` rounded toward zero
  as an integer.
- `freeze_edge` requires string `edge_id` that exists in the edge catalog on
  disk. Frozen edges are excluded from eligibility even if their weight would
  otherwise pass the floor.
- `compromise_node` requires string `node_id` present in `domain_layout.nodes`.
  Any edge touching a compromised node ends (both endpoints are checked).

Unknown kinds, missing identifiers, out-of-window days, malformed payloads,
or `freeze_edge` targets that are not present in the catalog are ignored.

## Edge eligibility

After incidents, an edge is **eligible** when:

1. Its weight `w` is greater than or equal to the final weight floor.
2. Its `edge_id` is not frozen.
3. Neither endpoint appears in the compromised set.

## Span selection

Consider only eligible edges. Sort them by ascending `(w, edge_id)`.
Greedily attempt edges in that order: add an edge if its endpoints lie in
different connected components among the universe of `domain_layout.nodes`.
Skip an edge when it would close a cycle. The selected edges form the
**picked** set.

## Outputs

Write four UTF-8 JSON files to the audit root (default `/app/sfm_audit/`),
creating the directory if missing:

1. `eligible_edges.json` with object key `edge_ids`, the lexicographically
   sorted list of eligible edge identifiers.
2. `mst_pick.json` with object key `edges`, an array of objects with keys
   `edge_id`, `u`, `v`, `w` sorted by ascending `(w, edge_id)` matching the
   greedy order of acceptance (accepted edges only).
3. `incident_trail.json` with keys `applied` (array of applied events in
   processing order) and `ignored` (integer count of ignored events).
4. `summary.json` with integer fields: `eligible_edge_count`,
   `picked_edge_count`, `total_weight` (sum of `w` over picked edges),
   `weight_floor_final`, `frozen_edge_count`, `compromised_node_count`,
   `component_count` (connected components in the full node universe after
   applying the picked edges only), `applied_incidents`, `ignored_incidents`,
   `incident_day_floor_used`, `current_day_used`.

## Canonical emission rules

Emit each output file using the canonical rules in the opening paragraph.
Object keys are sorted recursively. Arrays preserve the order defined above.
