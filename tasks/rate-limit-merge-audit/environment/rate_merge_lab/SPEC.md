# Rate limit merge audit (normative)

All inputs are UTF-8 JSON. The audit day is `pool_state.current_day` (integer). Never mutate anything under the data root.

## Unit records

Each file `units/<id>.json` is one object with keys:

- `service_id` (string, equals filename stem)
- `host_id` (string, names `hosts/<id>.json`)
- `unit_class` (string): `standard` or `legacy`
- `dropins` (array of strings): filenames under `dropins/` in listed order

Unknown keys are ignored.

## Class templates

Read `classes/<unit_class>.json`. Each file is one object with non-negative integers `interval_sec` and `burst` (defaults 1 if missing or invalid).

Unknown `unit_class` uses `classes/standard.json` if present, otherwise interval 1 and burst 1.

## Shallow merge

A drop-in object may contain `interval_sec` and/or `burst` (integers). Merging into state `(I, B)` replaces only keys present in the drop-in (missing key leaves previous value).

- `standard`: start from class template, then apply `dropins[0]`, then `dropins[1]`, … in order (later file wins on overlaps).
- `legacy`: start from class template, then apply drop-ins in **reverse list order** (the **first** filename in the array has highest precedence on overlapping keys).

Missing drop-in file is skipped (no merge).

## Host cap

Each `hosts/<host_id>.json` has integer `max_burst` (≥ 1). After all incident steps and compromise replacement rules below, set `burst = min(burst, max_burst)` **unless** the host is compromised at the end, in which case skip this min (quarantine burst is exact).

## Incidents

Read `incident_log.json` object key `events` (array). An event is **kept** iff: `accepted` is boolean true, `event_id` is a non-empty string, `day` is an integer with `day <= current_day`, and `kind` is one of the supported kinds with all required fields of correct types for that kind. Otherwise the event is **ignored**.

Sort kept events by ascending `(day, event_id)` and apply in that order to a mutable fleet copy (every service’s current `interval_sec` and `burst`).

Supported kinds:

1. `burst_add` — requires integer `delta`. Either non-empty `service_ids` (array of strings) **or** `host_id` (string). Targets are: listed services that exist, or every unit whose `host_id` matches, respectively. Add `delta` to `burst` for each targeted service (no floor here).
2. `interval_mult` — requires positive integers `num` and `den`. Optional `host_id`. If `host_id` is absent, apply to every service. Else apply only to units on that host. Update `interval_sec` to `max(1, (interval_sec * num) / den)` using integer division truncating toward zero for the multiplication portion: `interval_sec = max(1, (interval_sec * num) // den)`.
3. `host_compromise` — requires `host_id` (string). Record that host as compromised from this point forward (permanent for later steps and final output flags).
4. `burst_ceiling` — requires integer `ceiling` with `ceiling >= 1`. For **every** service immediately after processing this event, replace `burst` with `min(burst, ceiling)`.

Unknown `kind` or wrong field shapes: ignore the entire event (not kept).

## Compromise replacement

After all kept incidents are applied, every unit whose `host_id` is in the compromised set must have `interval_sec` and `burst` replaced exactly by `pool_state.quarantine.interval_sec` and `pool_state.quarantine.burst` (integers ≥ 1). Then apply the host `max_burst` rule above (min unless compromised host).

## Outputs (four files under audit directory)

Canonical JSON for every output file: UTF-8, two-space indent, ASCII only, object keys sorted lexicographically at every object depth, colon plus single space after each colon, no trailing spaces on lines, exactly one trailing newline at EOF.

### service_limits.json

Top-level object:

- `services`: array of objects, one per `units/*.json` file, sorted by ascending `service_id`.
- Each object keys (sorted): `burst` (int), `compromised_host` (bool, true iff host was compromised at end), `dropins_applied` (array of strings: the unit’s drop-in filenames in **application order** used by the merger), `host_id` (string), `interval_sec` (int), `service_id` (string), `unit_class` (string).

`dropins_applied` lists drop-ins in the order they were merged (standard: forward array order; legacy: reverse array order).

### incident_journal.json

- `applied_events`: array of one object per kept event, in process order. Each object includes keys: `day`, `event_id`, `kind`, plus only the optional fields that exist on the source event for that kind (`delta`, `den`, `host_id`, `num`, `service_ids`, `ceiling`) — omit keys not present in the source. Keys within each object sorted lexicographically.
- `ignored_events`: integer count of non-kept events from the original list.

### host_summary.json

- `hosts`: object keyed by `host_id` ascending. Each value object keys: `compromised` (bool), `max_burst` (int), `service_ids` (array of strings sorted ascending listing units on that host).

### summary.json

Keys (sorted): `applied_incident_events`, `compromised_hosts`, `ignored_incident_events`, `legacy_units`, `max_burst_across_services`, `min_interval_across_services`, `services_total`, `standard_units`.

Counts: `services_total` is number of unit files. `applied_incident_events` is length of `applied_events`. `ignored_events` total = len(events) - kept. `compromised_hosts` counts hosts with `compromised == true` in `host_summary`. `standard_units` / `legacy_units` count units by class. `max_burst_across_services` / `min_interval_across_services` are extrema over final `service_limits.services` after all rules.

## Input layout

`pool_state.json`, `incident_log.json`, `classes/*.json`, `dropins/*.json`, `hosts/*.json`, `units/*.json`, and this `SPEC.md` live under the data root.
