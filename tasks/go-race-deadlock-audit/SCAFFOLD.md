# go-race-deadlock-audit

- Source: `b6180f8d…(perfect task).zip`
- Env files (excl Dockerfile): **6** — below Edition-2 `small` threshold (20+). Oracle phase must split fixtures or add copied-only packaging under `data/` without changing graded CSV/NDJSON hashes.
- Oracle: **pending** — debugging task; verifier runs `go run ./cmd/yardcheck`. Reference fix lives in Go sources, not a Gson audit.
- Languages: agent fixes **Go**; `task.toml` lists `java` for batch alignment — consider `["go", "bash"]` before submission if no Java oracle is shipped.
