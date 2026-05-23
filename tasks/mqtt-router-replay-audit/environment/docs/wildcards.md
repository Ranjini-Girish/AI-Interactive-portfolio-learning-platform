# Wildcards, topics, and filters

Topic levels are split on `/`. A literal level is any non-empty string of
ASCII characters that is neither `+` nor `#` and does not contain `+` or
`#`.

## Valid publish topic

A `publish` event's `topic` must:

* be non-empty, and
* contain no `+` or `#` characters anywhere, and
* split into one or more **non-empty** levels (no leading `/`, trailing
  `/`, or `//`).

If any of those rules fails, emit `E_INVALID_TOPIC` and stop processing
the publish.

## Valid subscription filter

A `subscribe` event's `filter` must:

* be non-empty, and
* split into one or more **non-empty** levels, and
* every level that contains `+` must equal exactly `"+"`, and
* every level that contains `#` must equal exactly `"#"` **and** be the
  last level of the filter.

`policy.wildcard_plus_allowed` and `policy.wildcard_hash_allowed` may
disable `+` or `#` entirely; when disabled, any filter that uses the
disabled token is rejected with `E_INVALID_TOPIC_FILTER`.

If any of those rules fails, emit `E_INVALID_TOPIC_FILTER` and stop.

## Matching algorithm

Walk both `filter.levels()` and `topic.levels()` in parallel:

* If the current filter level is `#`, the filter matches the rest of the
  topic and the match returns true.
* If the current filter level is `+`, consume one topic level and advance
  both pointers.
* If both pointers refer to the same literal string, advance both.
* Any other case is a mismatch.

After the walk, the match returns true iff both pointers reached the end.
A trailing `#` also matches when the topic has been fully consumed.

## Examples

| filter            | topic            | matches |
|-------------------|------------------|---------|
| `sensors/+/temp`  | `sensors/A/temp` | yes     |
| `sensors/+/temp`  | `sensors/A/B/temp` | no    |
| `sensors/#`       | `sensors`        | yes     |
| `sensors/#`       | `sensors/A/B`    | yes     |
| `+`               | `sensors`        | yes     |
| `+`               | `sensors/a`      | no      |
| `a/+/c`           | `a/X/c`          | yes     |
| `a/#`             | `a/b/c`          | yes     |
| `a/#`             | `b/a`            | no      |

## Retained delivery on subscribe

When a `subscribe` event succeeds (no diagnostic), the broker walks the
`retained` map in topic-ascending order, and for each retained entry whose
`topic` matches the new filter it appends one `delivery_log` entry:

* `seq` -- the seq of the subscribe event
* `topic` -- the retained topic
* `publish_qos` -- the retained entry's qos
* `payload_id` -- the retained entry's payload_id
* `recipients` -- single entry for the subscribing client at
  `delivered_qos = min(retained_qos, sub_qos)`

These count toward `publishes_delivered` and `deliveries_total`. They never
emit `W_NO_SUBSCRIBERS` because there is always exactly one recipient.
