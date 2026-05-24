# Gossip ledger replay specification

This document is normative. Treat every rule as exact unless it explicitly says otherwise.

## Inputs

The lab root is `/app/gossip_lab/`. Read exactly two UTF-8 text files:

1. `/app/gossip_lab/inbox/events.log`
2. `/app/gossip_lab/inbox/events_overflow.log`

Ignore every other path under `/app/gossip_lab/` for computation. Those artefacts are ambient noise.

### Line grammar

Each non-empty line after trimming horizontal whitespace may contain an inline comment starting with `#` that runs to end-of-line. The comment payload is ignored. Blank lines are ignored.

A **record line** matches this pattern after stripping comments and trimming:

`ROUND INIT PEER VERB UPDATE`

Where:

- `ROUND` is a positive decimal integer with no leading sign.
- `INIT` and `PEER` are non-empty tokens without ASCII whitespace. They are case-sensitive.
- `VERB` is exactly `push` or `pull`.
- `UPDATE` is a non-empty token without ASCII whitespace.

Any other non-blank line is a **parse error**; the auditor must not emit a report when any parse error exists (exit non-zero is allowed for your tool; the verifier only checks successful runs on the bundled corpus, which contains no parse errors).

### Merge order

Build the **merged stream** by appending all valid record lines from `events.log` in file order, then all valid record lines from `events_overflow.log` in file order. No deduplication.

## Presence ledger model

This is an intentionally coarse witness model (not a full message-level epidemic simulation).

For each merged record `(r, a, b, v, u)` where `r` is round, `a` is initiator, `b` is peer, `v` is verb, and `u` is update id:

- Mark both `(a, u)` and `(b, u)` as **present**.
- Track `first_round[u]` as the minimum `r` among merged records mentioning `u`.
- Track `last_round[u]` as the maximum `r` among merged records mentioning `u`.

Let `N` be the sorted list of distinct node names (ASCII lexicographic order). Let `U` be the sorted list of distinct update ids using **numeric sort** when every character of the id is a decimal digit (compare by integer value), otherwise fall back to ASCII lexicographic order on the raw token.

Let `max_round` be the maximum `r` appearing in the merged stream (or zero if empty).

### Directed edge totals

For each merged record, increment the counter for the directed edge key `INIT>PEER` using the literal `>` separator. Emit the totals as a JSON object whose keys are sorted ASCII lexicographically.

### Canonical replay strings

Emit `canonical_replay` as a JSON array of strings, one per merged record, each exactly:

`ROUND INIT PEER VERB UPDATE`

with a single ASCII space between tokens, `ROUND` printed in decimal with no leading zeros except the single digit zero (which does not occur here), verbs lowercased as `push` or `pull`.

### Round snapshots

For each integer `k` from `1` through `max_round` inclusive, compute a mapping from node name to the list of update ids `u` such that:

1. `first_round[u] <= k`, and
2. `(node, u)` is present.

The per-node list must list ids in the same order they appear in the global sorted list `U` (filter `U`, do not resort only the subset).

The `round_snapshots` object must use outer keys `"1"` … `"max_round"` as decimal strings without padding, sorted numerically by the integer value (which matches ASCII order for these sizes).

### Per-update metrics

For each `u` in `U`, emit:

- `first_round` as the tracked minimum.
- `last_round` as the tracked maximum.
- `propagation_delay` as `last_round - first_round + 1`.

Store them under `per_update` keyed by the raw update token string.

### Pull tail score

Let the merged stream be zero-indexed in order. For each update id `u`, let `L(u)` be the index of the **last** merged record whose `UPDATE` field equals `u` (ties cannot happen across different updates on one line; each line has exactly one update).

Define `pull_last_hits` as the count of ids `u` in `U` such that the verb on merged record `L(u)` equals `pull`.

## Output artefact

Write exactly one file `/app/output/gossip_report.json` as UTF-8 JSON.

### Canonical JSON encoding

Serialize with:

- UTF-8 without BOM.
- Pretty-printed with two ASCII space characters per indent level.
- Every JSON object must have its keys sorted lexicographically at every nesting depth.
- Arrays preserve the order defined in this spec (do not sort `canonical_replay` or per-node update lists beyond the filtering rule already given).
- Numbers are emitted as JSON numbers without padding.
- The file ends with a single newline (`U+000A`) and nothing after it.

Top-level keys, alphabetically by key name, are:

- `canonical_replay` (array of strings)
- `edge_totals` (object string→integer)
- `max_round` (integer)
- `nodes` (array of strings)
- `per_update` (object of objects)
- `pull_last_hits` (integer)
- `round_snapshots` (object of objects of arrays of strings)

No additional top-level keys are permitted.
