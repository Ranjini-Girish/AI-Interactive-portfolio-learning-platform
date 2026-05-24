# Error Detection Specification

The allocator must detect and record the following error conditions. Errors do not halt processing; the allocator continues with the next operation.

## Double Free

A `dealloc` operation on an ID that has already been freed. The second and subsequent frees of the same ID are each recorded as a double-free error.

## Use After Free

A `realloc` operation on an ID that has been freed (or was never allocated). Each such operation is recorded as a use-after-free error.

## Out of Memory (OOM)

An `alloc` or `realloc` (when falling back to alloc-copy-free) that cannot find a free block large enough. The allocation fails; for `alloc`, no block is created. For `realloc`, the original block is unchanged.

## Unknown ID

A `dealloc` or `realloc` on an ID that was never allocated is treated as a double-free or use-after-free error respectively.

## Error Recording

Each error is recorded in the trace result's `errors` array as an object:
```json
{
  "operation_index": 3,
  "error_type": "double_free",
  "id": "p1"
}
```

`operation_index` is the zero-based index of the operation in the trace's operations array. Valid `error_type` values are: `"double_free"`, `"use_after_free"`, `"oom"`.
