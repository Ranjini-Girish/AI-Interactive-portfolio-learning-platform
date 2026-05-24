# Memory layout rules (x86_64 platform)

This task models a fixed **x86_64 data layout**: pointer width 8, primitive sizes/alignments taken from `config/platform.json`. Nested types and arrays are resolved recursively.

## Primitives and arrays

- Scalar layout is always `(size, align)` from the platform file.
- Fixed-size array `[T; N]` has `size = N * size(T)` and `align = align(T)`.
- A field type may reference another record by id string (e.g. `type_01_simple`).

## Structs

### `repr(C)` and `repr(align(N))`

- Fields are laid out in **declaration order**.
- Before each field, insert padding so the field offset is a multiple of the field’s natural alignment.
- Struct natural alignment is the **maximum** of field alignments.
- For `repr(align(N))`, struct alignment becomes `max(natural_struct_alignment, N)`.
- **Trailing padding** rounds the total size up to a multiple of the struct alignment.
- **Zero-sized struct** (`fields: []`, `repr(C)`): `size = 0`, `alignment = 1`, `is_zst = true`.

### `repr(Rust)` (struct field reordering)

- Compute each field’s natural `(size, align)`.
- Order fields by **descending alignment**, then **descending size**, then **ascending field name** (lexicographic).
- After reordering, apply the same padding rules as `repr(C)` using the new order.
- `field_order` in the report must list field names in this **reordered** sequence.

### `repr(packed)`

- Fields stay in **declaration order**.
- **No padding** between fields; each field immediately follows the previous in memory.
- Struct **alignment is 1**.
- Total size is the **sum of field sizes** with **no trailing padding**.

## Enums (`repr(C)` only in inputs)

**Discriminant width** (unsigned, little-endian; alignment equals its size):

- `1..=256` variants → `u8` (size 1, align 1)
- `257..=65536` variants → `u16` (size 2, align 2)
- beyond that → `u32`, then `u8`/`u16`/`u32` chain as needed by range (not used in this dataset)

Each variant’s payload is laid out as a **`repr(C)` struct** of its `fields` in declaration order, including that payload’s trailing padding to its payload alignment. The **union** holds the **maximum** payload size among variants. Enum alignment is `max(discriminant_alignment, max_variant_payload_alignment)`.

**Payload start offset**: `align_up(size(discriminant), max_variant_payload_alignment)`.

**Enum size**: `align_up(payload_start + max_payload_size, enum_alignment)`.

**Enum padding accounting** (report fields):

- `total_padding` (enums only): bytes **between end of discriminant storage and start of payload union** (the inserted gap for union alignment).
- `trailing_padding`: bytes after the last used byte of the payload union up to the final enum size (structural tail padding).

## Niche optimization (pointer-like `Option`)

Applies only when **all** hold:

- The type is an **enum** with **exactly two** variants.
- One variant has **no fields**; the other has **exactly one** field whose type is `pointer` or `reference`.
- The enum’s `repr` is **not** `C` (i.e. not explicitly `repr(C)` in the input).

When it applies: the enum is **pointer-sized** with **pointer alignment**; a null pointer represents the empty variant. Set `niche_optimized: true`, `discriminant: null`, and `total_padding: 0`. Variant entries still report logical payload sizes/alignments for the non-empty arm.

## Summary metrics (report)

- `total_padding` for **structs**: sum of each field’s `padding_before` plus `trailing_padding`.
- Sort `types` by increasing `id`.
