# Integrity Hash

The summary `integrity_hash` is SHA-256 hex over UTF-8 lines:

`saga_id|event_id|sequence|status`

- Process sagas in ascending `saga_id`.
- Within each saga, use replay order after deduplication (not lexicographic `event_id` order).
- Join lines with `\n`; do not append a trailing newline before hashing.
