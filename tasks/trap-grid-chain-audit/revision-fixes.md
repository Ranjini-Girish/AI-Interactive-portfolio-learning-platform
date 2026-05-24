# trap-grid-chain-audit — revision fixes

**UUID:** `d13b444b-40f6-46d9-8632-b89bf88ae7ee`  
**Date:** 2026-05-24

## Platform issues (prior submit)

| Issue | Detail |
|---|---|
| AutoEval build | **FAILED** — prior image used full `golang:1.23-bookworm` (~1GB+), likely Build Completion Timeout / build failure |
| Difficulty | **TRIVIAL** — `terminus-claude-opus-4-6` 100% (5/5), `terminus-gpt5-2` 100% (5/5); requires at least MEDIUM |
| Quality checks | Mostly passing (behavior in task description, solvable) |

## Fixes applied

### Infrastructure / static CI

1. **Dockerfile** — migrated `FROM golang:1.23-bookworm` → `debian:bookworm-slim@sha256:f9c6a2…` with `golang-go`, `tmux`, `asciinema`, and preinstalled `pytest==8.4.1` / `pytest-json-ctrf==0.3.5`.
2. **solve.sh** — uses system `go` from apt (removed `/usr/local/go/bin` dependency).
3. **task.toml** — already had `allow_internet = false`, canonical `test.sh` reward suffix, and harness packages; unchanged.
4. **Leakage / ruff** — clean on resubmit.

### Difficulty hardening (three interacting rules)

Added to `environment/trapgrid/SPEC.md`, mirrored in `instruction.md`, with fixture + test coverage:

1. **Incremental jam-echo muting cleared by force pulse** — walk incidents in sort order; `jam_echo` adds to `outbound_muted`, later `force_pulse` removes the same trap id. Fixture: day-9 `jam_echo` on `t03`, day-10 `force_pulse` on `t03`.
2. **Tag-alignment gate for boost and disarm cap** — `disarm_boost` applies only when `evaluation_tag == bundle`; tag mismatch also reduces `effective_disarm_cap` by one (floor 0). Bundled tags remain mismatched so cap is 2, not 4.
3. **Cross-room hop surcharge with minimum-hop relaxation** — same-room neighbors at `h+1`, cross-room at `h+2`; relax until stable; emit non-empty hop groups only. Fixture: edge `t03`–`t07`; `t07` lands at hop 2 in wave index 2.

Supporting fixture edits: `links.json` (t03–t07 edge), `incidents.json` (t03 jam_echo), tertiary `kind` tie-break for targetless events.

### Oracle & verifier

- Updated `solution/tgc.go` for all three rules.
- Refreshed SHA-256 input/output/field hashes in `tests/test_outputs.py`.
- Added/updated semantic tests for force-pulse mute clearing, cross-room hop grouping, tag-mismatch cap, and hall-c hazardous from cross-room trigger.
- **Local oracle verification:** 21/21 pytest passed with `TGC_DATA_DIR` / `TGC_AUDIT_DIR` env vars.

## Preflight result

```
All checks passed!
- ruff: OK
- leakage grep: OK
- environment file count: 23 (small)
- allow_internet / workdir: OK
- test.sh reward suffix: OK
- tmux + asciinema: OK
```

## Zip

- **Path:** `tasks/trap-grid-chain-audit.zip`
- **Entries:** 32 (flat root, forward slashes)

## Remaining risks

1. **Difficulty not re-measured locally** — hardening targets MEDIUM/HARD but agent pass rates require platform CodeBuild trials after upload.
2. **Docker build untimed on this host** — slim base should build within budget; recommend monitoring first AutoEval build artifact.
3. **Compound rules may still be solvable if agents read SPEC.md end-to-end** — if both models remain >80%, consider a fourth interaction (e.g., inbound mute or retroactive seal) on next revision.
