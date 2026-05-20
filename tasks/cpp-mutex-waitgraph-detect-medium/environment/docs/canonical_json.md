# Canonical JSON

Every output file must follow this exact byte-level format. The format is byte-identical to Python's `json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"`.

- Encoding: UTF-8.
- Allowed bytes: ASCII only. Any character outside `0x20..0x7E`, plus the JSON-required control characters, is written as a `\uXXXX` escape.
- Indentation: two spaces per nesting level.
- Object keys: lexicographically sorted at every depth (root keys, keys inside nested objects, and keys inside objects nested in arrays all sort independently).
- Trailing newline: exactly one `\n` at the very end of the file.
- Numbers: integers serialised without a decimal point or trailing zeros.
- Booleans and nulls: lower-case literals `true`, `false`, `null`.

The `wait_edges` array, the `actions` array, and each event's `diagnostics` array preserve the sort order documented in `sort_order.md`; canonical formatting does not re-sort arrays.
