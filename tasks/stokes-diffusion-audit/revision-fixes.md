# Revision fixes — 49f2e499-d969-4241-986b-074919b78452

## Wave 1 hardening (2026-05-23)

- [x] **CRLF→LF** — `environment/Dockerfile` normalized to Unix LF (`solve.sh` and `test.sh` were already LF).
- [x] **Harness deps** — Dockerfile already ships `tmux`, `asciinema`, `pytest==8.4.1`, `pytest-json-ctrf==0.3.5` at image build; no changes required.
- [x] **No runtime pip in solve.sh** — oracle is Java-only (`javac` + `java`); confirmed no `pip install` in wrapper.
- [x] **Leakage clean** — `instruction.md`, `tests/test_outputs.py`, `environment/stokes_lab/SPEC.md`, `rubrics.txt`: zero matches for `solve.sh|solution/|oracle`.
- [x] **python symlink** — `RUN ln -sf /usr/bin/python3 /usr/bin/python` already present.
- [x] **Cleanup** — removed dev cruft: `SCAFFOLD.md`, stray `main.go`, `go.mod`, `solution/diffusion.go` (Go draft not in submission zip).

## Verification

| Gate | Result |
|---|---|
| `terminus_zip.py preflight` | **PASS** (ruff, leakage, env file count 31/small, workdir + allow_internet, test.sh, tmux/asciinema) |
| Docker oracle (`solve.sh`) + local pytest | **27/27 passed** |

## Notes

- Local host Java 8 cannot compile the Java 21 oracle; verification used Docker image `sda-oracle` (Temurin 21) with mounted `solution/` and `local-audit/` output dir.
- `task.toml` retains `workdir = "/app"` per repo preflight static-check requirement.
