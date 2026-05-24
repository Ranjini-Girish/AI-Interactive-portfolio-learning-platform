# Output schema: `/app/output/layout_report.json`

Top-level object:

```json
{
  "platform": "<string architecture id>",
  "types": [ ... ],
  "summary": { ... }
}
```

## Common type object fields

- `id` (string): same as input type id.
- `kind`: `"struct"` or `"enum"`.
- `repr` (string): mirrors input (`C`, `Rust`, `packed`, `align(N)`).
- `size` (integer): total size in bytes.
- `alignment` (integer): alignment requirement in bytes.
- `is_zst` (bool): true iff `kind == struct` and `size == 0`.
- `niche_optimized` (bool): true only for niche-optimized enums.
- `trailing_padding` (integer): tail bytes after logically placed content to satisfy final alignment/size.
- `total_padding`: see per-kind rules below.
- `field_order` (array of strings or `null`): struct field names in layout order (`null` for enums).

### Struct-specific

- `fields`: array of:

```json
{
  "name": "<field name>",
  "offset": <int>,
  "size": <int>,
  "alignment": <int>,
  "padding_before": <int>
}
```

- `discriminant`, `variants`: **omit** or `null` (tests accept absence for structs).

`total_padding` for structs = sum(`padding_before`) + `trailing_padding`.

### Enum-specific

- `fields`: **omit** (not used); layout is summarized via `discriminant` + `variants`.
- `discriminant`: either `{"size": int, "alignment": int}` or `null` when niche optimized.
- `variants`: array of:

```json
{
  "name": "<variant name>",
  "payload_size": <int>,
  "payload_alignment": <int>
}
```

`payload_size` includes intra-payload trailing padding for that variant’s natural payload alignment.

`total_padding` for enums = bytes between the discriminant’s byte range and the payload union offset (excluding niche enums, where it is `0`).

## Summary object

```json
{
  "total_types": <int>,
  "total_size_all_types": <sum of type sizes>,
  "total_padding_all_types": <sum of each type's total_padding>,
  "padding_ratio": <float: total_padding_all_types / total_size_all_types,
                    use 6 decimal places when total_size_all_types > 0;
                    define as 0.0 when total_size_all_types == 0>,
  "zst_count": <structs with size 0>,
  "niche_optimized_count": <enums with niche_optimized true>,
  "max_alignment": <max alignment among all types>,
  "largest_type": "<id with maximum size; tie-break lexicographically smallest id>",
  "most_padded_type": "<id with maximum total_padding; tie-break lexicographically smallest id>"
}
```

## Ordering

Entries in `types` must be sorted by `id` ascending.
