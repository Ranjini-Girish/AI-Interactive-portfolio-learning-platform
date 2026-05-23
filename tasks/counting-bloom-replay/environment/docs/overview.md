# Overview

A counting Bloom filter is a fixed-length array of `m` non-negative integer
counters (each at most `2^counter_bits - 1`) that represents an approximate
multiset of keys. Membership is tested by hashing the key to `k` distinct
positions in the counter array; if any of those `k` positions is zero the
key is definitely absent, otherwise it is present with some false-positive
probability.

The simulator reads `/app/data/keys.json`, `/app/data/events.json`, and
`/app/data/policy.json`, replays the event stream against an initially-empty
counter array, and emits five canonical JSON files into `/app/output/`.

## Data model

The simulator carries three pieces of mutable state across the run.

- `counters` is a vector of length `m` with each entry in
  `[0, 2^counter_bits - 1]`. All entries start at zero.
- `multiset_count[key]` is a per-key non-negative integer that records the
  *ground-truth* number of times each key has been added but not yet
  removed. It is used (a) to classify each `query` event as a true or false
  positive and (b) to rebuild the counter array on `resize`.
- A flat counter struct of cumulative successes:
  `successful_adds`, `successful_removes`, `successful_queries`,
  `rejected_saturate`, `rejected_negative`, `clamped_remove`, `clears`,
  `resizes`. The names are documented in `/app/docs/output_format.md`.

## Closed key universe

Every event references a key by `key_idx` — an integer index into
`keys.json["keys"]`. The simulator looks up the corresponding string and
hashes that string. The literal `key_idx` is never hashed; only the
resolved string is. Keys outside the closed universe (negative `key_idx`
or `key_idx >= len(keys)`) are malformed input and the binary must exit
non-zero on encountering them.

## Determinism

For a given `(keys, events, policy)` triple the entire run is
byte-deterministic: the counter array, ground-truth multiset, query log,
event diagnostics, dump snapshots, and summary are all functions of the
input alone. There is no time, no randomness, no hardware dependence.
