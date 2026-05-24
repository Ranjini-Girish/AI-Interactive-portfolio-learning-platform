# Output Format Specification

The output file is `/app/output/allocator_report.json`, formatted with 2-space indentation and a trailing newline.

## Top-Level Structure

```json
{
  "pool_config": { ... },
  "traces": [ ... ],
  "summary": { ... }
}
```

## pool_config

Copy of the input pool configuration:
```json
{
  "pool_size": 1024,
  "header_size": 16,
  "min_alignment": 8
}
```

## traces

Array of trace results, one per input trace file, sorted by `trace_id` lexicographically. Each trace result:

```json
{
  "trace_id": "trace_01",
  "total_operations": 8,
  "successful_allocs": 4,
  "failed_allocs": 0,
  "successful_reallocs": 0,
  "failed_reallocs": 0,
  "deallocs": 4,
  "errors": [],
  "final_state": {
    "live_allocations": 0,
    "free_blocks": 1,
    "largest_free_usable": 1008,
    "total_free_usable": 1008,
    "total_allocated_bytes": 0,
    "pool_utilization": 0.0,
    "external_fragmentation": 0.0,
    "internal_fragmentation": 0.0
  },
  "high_water_mark": 224,
  "peak_live_blocks": 3
}
```

### Field Definitions

- `total_operations`: Total number of operations in the trace.
- `successful_allocs`: Count of alloc operations that succeeded.
- `failed_allocs`: Count of alloc operations that failed (OOM).
- `successful_reallocs`: Count of realloc operations that succeeded.
- `failed_reallocs`: Count of realloc operations that failed (OOM or error).
- `deallocs`: Count of valid (non-error) dealloc operations.
- `errors`: Array of error objects (see `error_detection_spec.md`).
- `final_state.live_allocations`: Number of allocated (not freed) blocks at trace end.
- `final_state.free_blocks`: Number of free blocks in the free list.
- `final_state.largest_free_usable`: Usable bytes in the largest free block.
- `final_state.total_free_usable`: Sum of usable bytes across all free blocks.
- `final_state.total_allocated_bytes`: Sum of block sizes (header + payload) for live allocations.
- `final_state.pool_utilization`: Ratio of allocated block bytes to pool size.
- `final_state.external_fragmentation`: See `metrics_spec.md`.
- `final_state.internal_fragmentation`: See `metrics_spec.md`.
- `high_water_mark`: Maximum sum of user-requested sizes simultaneously alive.
- `peak_live_blocks`: Maximum number of simultaneously live allocations.

## summary

```json
{
  "total_traces": 12,
  "total_operations": 125,
  "total_errors": 5,
  "total_oom_events": 3,
  "traces_with_errors": 2,
  "traces_fully_freed": 4
}
```

- `total_traces`: Number of trace files processed.
- `total_operations`: Sum of `total_operations` across all traces.
- `total_errors`: Sum of error counts across all traces.
- `total_oom_events`: Count of OOM errors across all traces.
- `traces_with_errors`: Number of traces that had at least one error.
- `traces_fully_freed`: Number of traces where `live_allocations == 0` at end.
