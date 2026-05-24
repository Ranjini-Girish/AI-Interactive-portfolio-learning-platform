# Architecture

## Data Flow

```
link_config.json ──> Linker ──> link_report.json
data/objects/*.json ─┘
```

## Output Schema (link_report.json)

2-space indented JSON with trailing newline. Top-level keys:

- `entry_point`: object `{symbol, address}`
- `errors`: array of `{type, symbol, message, objects}`
- `merged_sections`: array sorted by section_order, each with `{name, address, total_size, alignment, contributions}` where contributions is `[{object, offset, size}]` in object file order
- `relocations`: array in object-file order, each `{object, offset, section, symbol, symbol_address, type, value}`
- `stats`: `{total_objects, total_sections, total_symbols, weak_resolutions, total_relocations, total_size}`
- `status`: `"success"` or `"error"`
- `symbol_table`: array sorted by address then name, each `{address, binding, name, section, size, source, type}`
- `warnings`: array sorted by symbol, each `{object, symbol, type}`

## Relocation Types

- `R_ABS_32`: `value = symbol_address + addend`
- `R_PC_32`: `value = symbol_address + addend - relocation_site_address` where `relocation_site_address = section_base_of_object + relocation_offset`

## Symbol Resolution

- GLOBAL overrides WEAK (counted as a weak resolution)
- Multiple GLOBAL definitions of the same name produce a `duplicate_symbol` error
- UNDEF references with no definition produce an `undefined_symbol` error
- LOCAL symbols are scoped to their own object file

## Section Merging

Sections are merged in `section_order`. Within each section type, contributions appear in object-file order. Each contribution is aligned to its declared alignment. The merged section address is the address of its first contribution.
