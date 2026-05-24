# Event Pipeline Processor — Specification

## Overview

The pipeline processor reads events from `/app/data/events.json` and a DAG pipeline definition from `/app/data/pipeline.json`. It simulates event flow through the pipeline graph, computing per-node and aggregate statistics, then writes a report to `/app/output/pipeline_report.json`.

## Event Processing

Events are processed in timestamp order (ascending). When two events share the same timestamp, break ties by `event_id` ascending (lexicographic).

Each event enters the pipeline at the source node (`type: "source"`) and flows through the graph along the edges defined by each node's `outputs` array.

## Node Latency

Each node adds latency to an event passing through it. The latency for a node is:

    node_latency_ms = Math.round(weight * latency_per_unit_weight_ms)

where `weight` is the node's weight from the pipeline definition, and `latency_per_unit_weight_ms` is the global constant from the pipeline config.

An event's cumulative latency at a given node equals the sum of latencies of all nodes on the path from the source to that node (inclusive).

## Routing

When an event reaches a `router` node, it is forwarded to exactly one output based on the routing rule. The rule specifies a `field` in the event payload, a `threshold`, and two destinations:
- If `payload[field] > threshold`: route to `above`
- If `payload[field] <= threshold`: route to `at_or_below`

## Sliding Window Statistics

For each sink node, compute a sliding-window throughput. The window size is `sliding_window_ms` from the pipeline config.

For each event arriving at a sink, the window covers timestamps `[event.timestamp - sliding_window_ms + 1, event.timestamp]` (inclusive on both ends). The throughput for that window position equals the count of events arriving at that specific sink whose arrival timestamps fall within the window.

An event's "arrival timestamp" at a sink is `event.timestamp + cumulative_latency_to_sink`.

After processing all events, each sink reports `max_window_throughput`: the maximum throughput observed across all window positions for that sink.

## Aggregate Statistics

### Per-node statistics

For each node, compute:
- `events_processed`: count of events that passed through this node
- `total_latency_contribution_ms`: `events_processed * node_latency_ms`

### Per-category statistics

Group events by `payload.category`. For each category:
- `count`: number of events in this category
- `avg_priority`: arithmetic mean of priority values, rounded to 4 decimal places
- `weighted_avg_latency_ms`: the weighted harmonic mean of each event's end-to-end latency (from source to its final sink), weighted by the event's priority. Formula:

      weighted_harmonic_mean = sum(weights) / sum(weight_i / latency_i)

  where `weight_i = priority` and `latency_i = end-to-end latency` for event i. Round to 4 decimal places.

### Summary statistics

- `total_events`: total events processed
- `total_to_sink_a`: events routed to sink_a
- `total_to_sink_b`: events routed to sink_b  
- `total_to_archive`: events reaching the archive node
- `avg_end_to_end_latency_ms`: arithmetic mean of all events' end-to-end latency (source to final sink), rounded to 4 decimal places
- `max_end_to_end_latency_ms`: maximum end-to-end latency across all events
- `min_end_to_end_latency_ms`: minimum end-to-end latency across all events

## Integrity Hash

Compute a SHA-256 hex digest over a canonical string built from the processing results. The canonical string is constructed by concatenating lines, one per event processed (in processing order — timestamp ascending, event_id ascending for ties), each line formatted as:

    {event_id}|{final_sink_node_id}|{end_to_end_latency_ms}|{priority}

Lines are joined with newline characters (`\n`). No trailing newline. The SHA-256 is computed over the UTF-8 encoding of this string.

Note: Each event may reach multiple sink nodes (e.g., an event goes through both the `enrich→archive` path and the `validate→aggregate→score→route→sink_X` path). The integrity hash must include one line per (event, sink) pair, ordered first by event processing order then by sink node_id ascending.

## Output Format

Write `/app/output/pipeline_report.json` with 2-space indentation and a trailing newline. Top-level keys in this order:

1. `pipeline_id` — string from the pipeline config
2. `total_events` — integer
3. `node_stats` — object keyed by node_id (sorted alphabetically), each containing `events_processed` and `total_latency_contribution_ms`
4. `sink_stats` — object keyed by sink node_id (sorted alphabetically), each containing `events_received` and `max_window_throughput`
5. `category_stats` — object keyed by category (sorted alphabetically), each containing `count`, `avg_priority`, and `weighted_avg_latency_ms`
6. `routing_summary` — object with `sink_a_count`, `sink_b_count`, `archive_count`
7. `latency_summary` — object with `avg_end_to_end_latency_ms`, `max_end_to_end_latency_ms`, `min_end_to_end_latency_ms`
8. `integrity_hash` — the SHA-256 hex digest string
