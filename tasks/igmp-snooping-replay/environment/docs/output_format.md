# Output Format

The binary writes exactly four files into `OUT_DIR/` (the second
positional argument). All four are *canonical JSON*: UTF-8, ASCII-only,
two-space indent, lexicographically sorted object keys at every depth,
single trailing newline. No other files may appear in `OUT_DIR/` after
the run.

## `mcast_table.json`

```
{
  "groups": [
    {
      "group": "<dotted-quad multicast IPv4>",
      "members": [
        {
          "last_seen_time": <uint>,
          "port": "<port_id>"
        },
        ...
      ],
      "vlan": <uint>
    },
    ...
  ]
}
```

Sorted by `vlan` ascending, then by `group` (ASCII string ascending).
Within each entry, `members` is sorted by `port` ASCII ascending. Only
groups with at least one member are listed; empty `(vlan, group)`
buckets are omitted.

## `forward_log.json`

```
{
  "forwards": [
    {
      "decision": "forwarded" | "flooded" | "dropped",
      "egress_ports": ["<port_id>", ...],   // sorted ASCII; empty for "dropped"
      "group": "<dotted-quad multicast IPv4>",
      "ingress_port": "<port_id>",
      "reason": "<reason-string>" | null,    // see below; non-null for dropped, null otherwise
      "seq": <uint>,
      "vlan": <uint>
    },
    ...
  ]
}
```

Allowed `reason` strings: `"ingress_port_down"`, `"vlan_mismatch"`,
`"no_members"`. For `decision != "dropped"`, `reason` MUST be `null`.

Sorted by `seq` ascending. If `policy.track_forwarding` is `false`,
this file MUST be exactly `{"forwards": []}`.

## `igmp_diagnostics.json`

```
{
  "diagnostics": [
    {
      "code": "<closed-set>",
      "name": "<string>",
      "seq": <uint>,
      "severity": "error" | "warning" | "note"
    },
    ...
  ]
}
```

Sparse: only events that emitted diagnostics contribute entries.
Sorted by `seq` ascending, then `(severity_rank descending, code
ascending, name ascending)`.

## `summary.json`

```
{
  "active_groups": ["<dotted-quad>", ...],
  "totals": {
    "diagnostic_count": <uint>,
    "frames_dropped": <uint>,
    "frames_flooded": <uint>,
    "frames_forwarded": <uint>,
    "leave_events": <uint>,
    "mcast_frame_events": <uint>,
    "member_count": <uint>,
    "report_events": <uint>,
    "tick_events": <uint>,
    "total_ticks_advanced_sec": <uint>
  }
}
```

* `active_groups` is the sorted distinct list of `group` strings still
  present in the final `mcast_table` (i.e. groups with at least one
  member). Sorted ASCII ascending.
* `member_count` equals the total number of `(vlan, group, port)`
  membership entries in the final `mcast_table`.
* `mcast_frame_events` counts every `mcast_frame` event (including
  dropped ones).
* `frames_dropped + frames_flooded + frames_forwarded` MUST equal
  `mcast_frame_events`.
* `report_events` counts `igmp_report` events; `leave_events` counts
  `igmp_leave` events.
* `tick_events` counts `tick` events; `total_ticks_advanced_sec` is
  the sum of `delta_sec` across all `tick` events.
* `diagnostic_count` equals `len(igmp_diagnostics.diagnostics)`.
