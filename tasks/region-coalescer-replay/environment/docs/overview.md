# Region Replay Overview

The simulator models a flat virtual address space with non-overlapping mapped
regions. Each region carries an opaque string `id`, a half-open address range
`[base, base + size)`, a protection flag `prot` drawn from
`{"r","rw","rx","rwx"}`, and a string `owner` (think of it as the process or
arena that owns the mapping).

The initial state is `regions.json`. Region ids are unique across the whole
trace -- once a region's id is removed (by `unmap` or by being merged away),
that id may not be reintroduced by a later `map` or `split`.

`events.json` is a strictly ascending list of operations (`seq` 0..N-1, dense)
that mutate the map. Events are processed in `seq` order, one at a time. After
every event the global invariant must hold:

- regions never overlap,
- regions are sorted lexicographically by `(base, id)` for output purposes,
- ids that currently appear in `region_state` are unique.

Diagnostic-emitting events do not change state -- when an event fails its
preconditions, the simulator emits the documented diagnostic for that event and
moves on without touching the region table.
