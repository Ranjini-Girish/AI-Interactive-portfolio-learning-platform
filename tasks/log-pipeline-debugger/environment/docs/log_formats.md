# Log Formats

## webserver.log — Pipe-delimited

```
<ISO-8601-timestamp>|<method>|<path>|<status_code>|<latency_ms>|<trace_id>
```

Status mapping: 2xx → OK, 4xx → CLIENT_ERROR, 5xx → ERROR

## database.log — Bracket timestamp, key=value

```
[<YYYY-MM-DD HH:MM:SS>] service=database query=<type> table=<name> duration_ms=<int> status=<OK|SLOW|ERROR> trace_id=<id>
```

## auth.log — JSON lines

One JSON object per line. Keys: ts, event, user, result (SUCCESS or ERROR),
latency_ms, trace_id, detail.

## cache.log — CSV with header

```
timestamp_ms,operation,key,result,latency_us,trace_id
```

Note: timestamp is in epoch milliseconds, latency is in microseconds.
Both must be converted (÷1000 and ÷1000 respectively) for the normalized format.

## queue.log — Syslog-style

```
<Mon> <DD> <HH:MM:SS> <hostname>[<pid>]: <EVENT> key=val key=val ...
```

Assumed year comes from pipeline config (LOG_YEAR). Key fields: trace_id,
status, latency_ms.
