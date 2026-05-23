# Overview

`mqttrtr` is a deterministic C++17 replay tool that simulates a synthetic
MQTT-style pub/sub broker. The broker is **logical only** -- it does not open
any sockets, encode any wire frames, or talk to any real client. Every input
and every output is JSON sitting on disk under `/app/data/` and the output
directory you pass on the command line.

## Inputs

Five JSON files under `/app/data/`:

* `clients.json` -- the broker state at trace start: a list of clients, each
  with an `id`, a `persistent` flag, a `keep_alive_sec` integer, an optional
  `connected` flag (default `true`), and an optional `will` block. A client
  with `connected = false` is a **disconnected-but-persistent** session whose
  subscriptions still live in `persistent_sessions[]`.
* `subscriptions.json` -- initial subscriptions; each entry has `client_id`,
  `filter`, and `qos`. The `client_id` must match either a connected client
  or a persistent session in `clients.json`.
* `retained.json` -- the initial retained-message map; one entry per topic,
  each with `topic`, `payload_id`, `qos`, and `retained_at_sec`.
* `events.json` -- the trace, a strictly ascending dense `seq` log starting
  at `0` and ending at `N-1`. See `events.md` for the per-kind shape.
* `policy.json` -- tunables. See `output_format.md` for every field.

## Outputs

Five JSON files written into the directory passed as the second positional
argument: `broker_state.json`, `delivery_log.json`, `session_log.json`,
`diagnostics.json`, `summary.json`. Every output file is canonical JSON:
two-space indent, lexicographically sorted keys at every depth, ASCII-only
bytes, single trailing newline.

## CLI

```
mqttrtr <data_dir> <out_dir>
```

Exactly two positional arguments. The binary must exit non-zero on missing
arguments, on missing or malformed input files, and on any internal failure.
It must never write outside `<out_dir>`.
