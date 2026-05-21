# sbm_lab bundle

Normative rules for the frozen `/app/sbm_lab/` bundle.

## Canonical JSON
Every emitted audit file is UTF-8 JSON using `json.dumps(..., sort_keys=True, indent=2, separators=(', ', ': '))` plus a single trailing newline.

## Inputs
- `policy.json` fields: `merge_slack_days` int >=0, `accept_band_mask` int bitmask over band ids 0..3, `lanes_rank` list of lane strings (all distinct).
- `pool_state.json` has `ledger_day` int.
- `incident_log.json` has `incidents` array; only `kind == widen_slack` matters: fields `lane`, `start_day`, `end_day`, `extra_slack` int >=0. Active iff `start_day <= ledger_day <= end_day`.
- Items under `items/item_XX.json` with fields: `lane` str, `slot_id` str, `anchor_day` int, `span` int >=1, `priority` int, `band` int 0..3, `tag` str.

## Band filter
An item is eligible iff bit `(accept_band_mask >> band) & 1` is 1.

## Slack
Base slack is `merge_slack_days`. For each active widen_slack incident targeting a lane, add its `extra_slack` to that lane only.

## Merge per lane
Consider only eligible items for that lane. Sort by `(anchor_day, anchor_day+span-1, slot_id, -priority, tag)`. Walk in order maintaining a current group for a `slot_id`. Let `cur_start` be min anchor in group, `cur_end` max end day in group. For the next item with same `slot_id`, compute gap = `next.anchor_day - cur_end - 1`. Merge into the group iff `gap <= lane_slack`. When merging, extend `cur_end` to max prior `cur_end` and `next.anchor_day+next.span-1`, set `cur_start` to min anchors, `priority` to max of priorities, `sources` to sorted unique union of tags. On non-merge, emit prior group and start new. Flush last group.

## Outputs (under audit dir)
- `merge_report.json` object key `groups`: list sorted by `(lane order in lanes_rank), start_day, slot_id` where lane order is index in `lanes_rank` ascending.
Each group: `lane`, `slot_id`, `start_day`, `end_day`, `span`, `priority`, `sources` sorted ascending strings.
`end_day` is inclusive last day; `span = end_day - start_day + 1`.
- `summary.json` keys: `eligible_items` int, `groups` int, `ledger_day` int, `lanes` list of lane strings sorted ascending present in any group.
