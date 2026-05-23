# Malformed input

The binary must abort with non-zero exit and leave `<out_dir>`
unchanged whenever its inputs fail to conform.

## CLI / filesystem

* The CLI must receive exactly two positional arguments.
* `<in_dir>` and `<out_dir>` must exist and be real directories.
  Symlinks (even symlinks pointing to directories), regular files,
  block devices, FIFOs, sockets, or anything else are rejected.
  Use `lstat(2)` (or an equivalent that does not follow symlinks).
* If any of the five final output paths or their `.partial`
  siblings already exist under `<out_dir>` -- for any file kind --
  the binary refuses to start.

## `events.json`

Schema-level rejections (with non-zero exit and no `<out_dir>`
changes):

* Top-level value is not an object, missing the `events` key, or
  contains any extra top-level key.
* `events` is not an array.
* Any element is not an object, is missing one of the four
  required keys (`event_id`, `ts_unix_ms`, `type`, `payload`), or
  has an extra key.
* `event_id` is not a non-empty string.
* Two events share an `event_id`.
* `ts_unix_ms` is not a JSON integer `>= 0`.
* `type` is not one of `"access"`, `"evict"`, `"clear"`.
* `payload` is not an object, is missing required payload keys,
  has extra keys, or contains values of the wrong type.
* For `access`: `payload` must contain exactly `key` (non-empty
  string) and `weight` (JSON integer in `[1, 16]`). Any other key
  count, missing key, extra key, or out-of-range `weight` rejects.
* For `evict`: `payload` must contain exactly `key` (non-empty
  string). No `weight` field is allowed on evict payloads.
* For `clear`: `payload` is the empty object.

`ts_unix_ms` is allowed to be non-monotonic across events; that is
not a malformed-input condition. Schema enforcement here only
guarantees parseability -- the semantic rejection reasons
(`unknown_resident`, `cache_empty`) are runtime outcomes that
produce `event_audit` and `violations` rows, not abort conditions.

## `config.json`

* Top-level value is not an object, has extra keys, or is missing
  the `cache_size` key.
* `cache_size` is not a JSON integer in `[1, 256]`.

## Other failures

Any IO failure (cannot create staged outputs, cannot rename, cannot
read inputs, etc.) must clean up every staged or already-renamed
file and exit non-zero. Two runs over identical inputs and a freshly
emptied `<out_dir>` must produce byte-identical outputs.
