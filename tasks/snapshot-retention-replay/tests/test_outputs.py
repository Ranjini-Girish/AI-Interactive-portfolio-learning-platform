"""Verifier suite for  (typescript)."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

DATA_DIR  = Path("/app/data")
OUT_DIR   = Path("/app/output")
BUILD_DIR = Path("/app/build")
BINARY_PATH = BUILD_DIR / "snapret"

SNAPSHOTS_PATH = DATA_DIR / "snapshots.json"
EVENTS_PATH    = DATA_DIR / "events.json"
POLICY_PATH    = DATA_DIR / "policy.json"

STATE_PATH   = OUT_DIR / "snapshot_state.json"
PRUNE_PATH   = OUT_DIR / "prune_log.json"
DIAG_PATH    = OUT_DIR / "retention_diagnostics.json"
SUMMARY_PATH = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (STATE_PATH, PRUNE_PATH, DIAG_PATH, SUMMARY_PATH)

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    SNAPSHOTS_PATH: "e4f35cd940928dc0761f02e18fb3837d1df2844472a6720d1b382b64550e71d1",
    EVENTS_PATH:    "ff0f72e016b5f8d3f71f7cde341a0db3f0976ab8927eee9bf76622a6045a29be",
    POLICY_PATH:    "a557186b2e1a4922a0f197654e4bfeb33420985eb14fad4ac5efbceee240acd9",
}

DOCS_DIAG_PATH = Path("/app/docs/diagnostics.md")


def _load_diag_codes_from_docs() -> tuple[frozenset[str], dict[str, str]]:
    """Parse /app/docs/diagnostics.md for the canonical list of
    diagnostic codes and their severities. The single source of truth
    for codes is the docs, not this test file. Lines look like:
        | E_DUPLICATE_ID | error | yes ...
    """
    import re
    text = DOCS_DIAG_PATH.read_text(encoding="utf-8")
    codes: set[str] = set()
    severity: dict[str, str] = {}
    pat = re.compile(
        r"^\s*\|\s*`?(?P<code>[A-Z][A-Z0-9_]+)`?\s*\|\s*"
        r"(?P<severity>error|warning|note)\s*\|"
    )
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            codes.add(m.group("code"))
            severity[m.group("code")] = m.group("severity")
    if not codes:
        raise RuntimeError(
            f"could not parse any diagnostic codes from {DOCS_DIAG_PATH}; "
            "check the docs format"
        )
    return frozenset(codes), severity


VALID_DIAG_CODES, DIAG_SEVERITY = _load_diag_codes_from_docs()
SEVERITY_RANK = {"error": 0, "warning": 1, "note": 2}

BUCKET_SIZE = {
    "keep_hourly":  3600,
    "keep_daily":   86400,
    "keep_weekly":  604800,
    "keep_monthly": 2592000,
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_strictly_formatted(path: Path) -> tuple[bool, str]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        return False, f"{path} missing trailing newline"
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"{path} not utf-8: {exc}"
    payload = json.loads(decoded)
    canonical = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if decoded != canonical:
        return False, f"{path} not in canonical 2-space sorted-keys form"
    return True, ""


# ---------------------------------------------------------------------------
# Reference simulator (mirrors /app/docs/) -- live verifier ground truth
# ---------------------------------------------------------------------------


def _emit(diags, seq, code, snapshot_id):
    diags.setdefault(seq, []).append({
        "code": code,
        "severity": DIAG_SEVERITY[code],
        "snapshot_id": snapshot_id,
    })


def _resolve_rules(policy, dataset):
    return policy.get("datasets", {}).get(dataset, policy["default_rules"])


def _rules_all_zero(rules):
    return all(int(rules.get(k, 0)) == 0 for k in
               ("keep_last_n", "keep_hourly", "keep_daily",
                "keep_weekly", "keep_monthly"))


def run_simulation(initial_snapshots, events, policy):
    state: dict[str, dict[str, Any]] = {}
    name_idx: dict[tuple[str, str], str] = {}
    for s in initial_snapshots:
        sid = s["id"]
        if sid in state:
            raise ValueError(f"duplicate id in initial snapshots: {sid}")
        key = (s["dataset"], s["name"])
        if key in name_idx:
            raise ValueError(f"duplicate (dataset,name) in initial: {key}")
        state[sid] = {
            "id": sid,
            "dataset": s["dataset"],
            "name": s["name"],
            "created_at_sec": int(s["created_at_sec"]),
            "holders": list(s.get("holders", [])),
        }
        name_idx[key] = sid

    now_sec = int(policy["now_sec"])
    held_action_default = policy["held_delete_action"]
    diags: dict[int, list[dict[str, Any]]] = {}
    prune_runs: list[dict[str, Any]] = []
    counters = {
        "snapshots_created": 0,
        "snapshots_deleted_explicitly": 0,
        "snapshots_pruned_by_retention": 0,
        "retention_runs_executed": 0,
    }

    events = sorted(events, key=lambda e: e["seq"])
    for i, ev in enumerate(events):
        if ev["seq"] != i:
            raise ValueError(
                f"events.json: seq must be dense 0..N-1; got {ev['seq']} at index {i}"
            )

    for ev in events:
        seq = ev["seq"]
        kind = ev["kind"]

        if kind == "snapshot_create":
            sid = ev["id"]
            ds  = ev["dataset"]
            nm  = ev["name"]
            if sid in state:
                _emit(diags, seq, "E_DUPLICATE_ID", sid)
                continue
            if (ds, nm) in name_idx:
                _emit(diags, seq, "E_DUPLICATE_NAME", sid)
                continue
            state[sid] = {
                "id": sid, "dataset": ds, "name": nm,
                "created_at_sec": now_sec, "holders": [],
            }
            name_idx[(ds, nm)] = sid
            counters["snapshots_created"] += 1
            continue

        if kind == "snapshot_delete":
            sid = ev["id"]
            force = bool(ev["force"])
            if sid not in state:
                _emit(diags, seq, "E_SNAPSHOT_NOT_FOUND", sid)
                continue
            snap = state[sid]
            if snap["holders"]:
                effective = "break_holds" if force else held_action_default
                if effective == "reject":
                    _emit(diags, seq, "E_HOLD_PREVENTS_DELETE", sid)
                    continue
                if effective == "skip":
                    _emit(diags, seq, "W_SKIP_HELD", sid)
                    continue
                _emit(diags, seq, "W_BREAK_HOLDS", sid)
            del name_idx[(snap["dataset"], snap["name"])]
            del state[sid]
            counters["snapshots_deleted_explicitly"] += 1
            continue

        if kind == "hold_add":
            sid = ev["id"]
            holder = ev["holder"]
            if sid not in state:
                _emit(diags, seq, "E_SNAPSHOT_NOT_FOUND", sid)
                continue
            if holder in state[sid]["holders"]:
                _emit(diags, seq, "W_HOLD_ALREADY_PRESENT", sid)
                continue
            state[sid]["holders"].append(holder)
            continue

        if kind == "hold_release":
            sid = ev["id"]
            holder = ev["holder"]
            if sid not in state:
                _emit(diags, seq, "E_SNAPSHOT_NOT_FOUND", sid)
                continue
            if holder not in state[sid]["holders"]:
                _emit(diags, seq, "W_HOLD_NOT_PRESENT", sid)
                continue
            state[sid]["holders"].remove(holder)
            continue

        if kind == "tick":
            d = int(ev["delta_sec"])
            if d < 0:
                _emit(diags, seq, "E_TICK_NEGATIVE", None)
                continue
            if d == 0:
                _emit(diags, seq, "W_TICK_ZERO", None)
                continue
            now_sec += d
            continue

        if kind == "retention_run":
            ds = ev["dataset"]
            rules = _resolve_rules(policy, ds)
            counters["retention_runs_executed"] += 1
            in_ds = sorted(
                [(sid, state[sid]) for sid in state if state[sid]["dataset"] == ds],
                key=lambda x: x[0],
            )
            if _rules_all_zero(rules):
                _emit(diags, seq, "W_NO_RULES_DEFINED", None)
            if not in_ds:
                _emit(diags, seq, "W_DATASET_EMPTY", None)
                prune_runs.append({
                    "dataset": ds, "kept": [], "pruned": [], "seq": seq,
                })
                continue
            keep_by: dict[str, set[str]] = {sid: set() for sid, _ in in_ds}

            n_last = int(rules.get("keep_last_n", 0))
            if n_last > 0:
                ranked = sorted(
                    in_ds,
                    key=lambda x: (x[1]["created_at_sec"], x[0]),
                    reverse=True,
                )
                for sid, _ in ranked[:n_last]:
                    keep_by[sid].add("keep_last_n")

            for rule in ("keep_hourly", "keep_daily", "keep_weekly", "keep_monthly"):
                n = int(rules.get(rule, 0))
                if n <= 0:
                    continue
                bsize = BUCKET_SIZE[rule]
                buckets: dict[int, list] = {}
                for sid, snap in in_ds:
                    bnum = snap["created_at_sec"] // bsize
                    buckets.setdefault(bnum, []).append((sid, snap))
                ordered_buckets = sorted(buckets.keys(), reverse=True)[:n]
                for bnum in ordered_buckets:
                    members = buckets[bnum]
                    chosen = sorted(
                        members,
                        key=lambda x: (x[1]["created_at_sec"], x[0]),
                        reverse=True,
                    )[0]
                    keep_by[chosen[0]].add(rule)

            for sid, snap in in_ds:
                if snap["holders"]:
                    keep_by[sid].add("held")

            kept_ids   = sorted([sid for sid in keep_by if keep_by[sid]])
            pruned_ids = sorted([sid for sid in keep_by if not keep_by[sid]])

            kept_entries = []
            for sid in kept_ids:
                snap = state[sid]
                kept_entries.append({
                    "id": sid,
                    "kept_by": sorted(keep_by[sid]),
                    "name": snap["name"],
                })
            kept_entries.sort(
                key=lambda e: (state[e["id"]]["created_at_sec"], e["id"]),
                reverse=True,
            )
            pruned_entries = [{"id": sid, "name": state[sid]["name"]} for sid in pruned_ids]

            prune_runs.append({
                "dataset": ds,
                "kept": kept_entries,
                "pruned": pruned_entries,
                "seq": seq,
            })
            for sid in pruned_ids:
                snap = state[sid]
                del name_idx[(snap["dataset"], snap["name"])]
                del state[sid]
                counters["snapshots_pruned_by_retention"] += 1
            continue

        raise ValueError(f"unknown event kind: {kind}")

    return _build_outputs(state, diags, prune_runs, counters, len(events))


def _build_outputs(state, diags, prune_runs, counters, total_events):
    by_ds: dict[str, list] = {}
    for sid, snap in state.items():
        by_ds.setdefault(snap["dataset"], []).append((sid, snap))
    datasets_arr = []
    for ds in sorted(by_ds):
        snaps = sorted(by_ds[ds], key=lambda x: (x[1]["created_at_sec"], x[0]))
        snap_arr = []
        for sid, snap in snaps:
            snap_arr.append({
                "created_at_sec": snap["created_at_sec"],
                "holders": sorted(snap["holders"]),
                "id": sid,
                "name": snap["name"],
            })
        datasets_arr.append({"name": ds, "snapshots": snap_arr})
    snapshot_state = {"datasets": datasets_arr}

    prune_log = {"runs": prune_runs}

    diag_events = []
    for seq in sorted(diags):
        items_sorted = sorted(diags[seq], key=lambda d: (
            SEVERITY_RANK[d["severity"]],
            d["code"],
            "" if d["snapshot_id"] is None else "1" + d["snapshot_id"],
        ))
        diag_events.append({"diagnostics": items_sorted, "seq": seq})
    diagnostics_doc = {"events": diag_events}

    summary = {
        "datasets_with_snapshots": sorted(by_ds.keys()),
        "events_with_diagnostics": len(diag_events),
        "final_snapshot_count": len(state),
        "retention_runs_executed":      counters["retention_runs_executed"],
        "snapshots_created":            counters["snapshots_created"],
        "snapshots_deleted_explicitly": counters["snapshots_deleted_explicitly"],
        "snapshots_pruned_by_retention": counters["snapshots_pruned_by_retention"],
        "total_events": total_events,
    }

    return {
        "snapshot_state":         snapshot_state,
        "prune_log":              prune_log,
        "retention_diagnostics":  diagnostics_doc,
        "summary":                summary,
    }


def reference_outputs() -> dict[str, Any]:
    snaps_doc  = load_json(SNAPSHOTS_PATH)
    events_doc = load_json(EVENTS_PATH)
    policy_doc = load_json(POLICY_PATH)
    return run_simulation(snaps_doc["snapshots"], events_doc["events"], policy_doc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def expected_outputs() -> dict[str, Any]:
    return reference_outputs()


@pytest.fixture(scope="session")
def binary_run_outputs() -> dict[str, Any]:
    """Wipe /app/output and re-run the agent's binary with the canonical
    CLI. Tests asserting against /app/output/*.json depend on this fixture
    so the agent's binary is the only thing that produces those files."""
    assert BINARY_PATH.exists(), (
        f"binary not found at {BINARY_PATH}; agent must build TypeScript sources to "
        f"this path before tests run"
    )
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()
    proc = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    return {"start": start, "returncode": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


# ---------------------------------------------------------------------------
# Tests against the pinned dataset
# ---------------------------------------------------------------------------


def test_inputs_unchanged() -> None:
    """Pinned input files must match the snapshot SHA-256 the task ships
    with. Both prevents agents rewriting inputs to ease the task AND keeps
    the live-recomputed reference deterministic."""
    for path, expected in EXPECTED_INPUT_HASHES.items():
        assert path.exists(), f"input missing: {path}"
        actual = sha256_of(path)
        assert actual == expected, (
            f"input file {path} has unexpected hash {actual}; expected {expected}"
        )


def test_binary_built_and_executable() -> None:
    """The agent must have built their TypeScript program to
    /app/build/snapret and the file must be executable."""
    assert BINARY_PATH.exists(), (
        f"expected compiled binary at {BINARY_PATH}; agent must build TypeScript sources"
    )
    mode = BINARY_PATH.stat().st_mode
    assert mode & stat.S_IXUSR, f"{BINARY_PATH} is not executable"
    src_dir = Path("/app/src")
    src_files = (
        list(src_dir.rglob("*.ts"))
        + list(src_dir.rglob("*.ts"))
        + list(src_dir.rglob("*.ts"))
    )
    assert src_files, (
        "expected agent-authored TypeScript source (.ts) under /app/src; "
        f"found none (src_dir exists: {src_dir.exists()})"
    )




def test_binary_runs_on_pinned_inputs(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Smoke check that the compiled binary actually executed against the
    pinned dataset under /app/data. The binary_run_outputs fixture wipes
    /app/output and reruns the binary every test session so a stale
    prebuilt binary cannot satisfy this -- the binary must produce the
    four outputs from inputs at this very test run."""
    assert binary_run_outputs["returncode"] == 0, (
        f"/app/build/snapret failed to run on /app/data: "
        f"rc={binary_run_outputs['returncode']} "
        f"stderr={binary_run_outputs['stderr']!r}"
    )
    for path in ALL_OUT_PATHS:
        assert path.exists(), f"output missing after binary rerun: {path}"


def test_binary_runs_cleanly_and_outputs_are_fresh(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The agent's binary must run with the canonical two-arg CLI on
    /app/data, exit 0, and produce all four outputs that are mtime-newer
    than the moment the verifier started the run."""
    rc = binary_run_outputs["returncode"]
    assert rc == 0, (
        f"/app/build/snapret exited with rc={rc} when run with canonical "
        f"args /app/data /app/output;\nstdout={binary_run_outputs['stdout']!r}\n"
        f"stderr={binary_run_outputs['stderr']!r}"
    )
    start = binary_run_outputs["start"]
    for path in ALL_OUT_PATHS:
        assert path.exists(), f"output missing after binary run: {path}"
        assert path.stat().st_size > 0, f"output empty after binary run: {path}"
        m = path.stat().st_mtime
        assert m + 1.0 >= start, (
            f"output {path} has mtime {m} older than test start {start}; "
            "looks like a stale/precomputed file rather than fresh output"
        )
        load_json(path)
    expected_names = {p.name for p in ALL_OUT_PATHS}
    actual_names = {p.name for p in OUT_DIR.iterdir() if p.is_file()}
    extras = actual_names - expected_names
    assert not extras, (
        f"binary wrote extra files into /app/output: {sorted(extras)}; "
        "the spec says exactly four JSON outputs and no others"
    )


def test_binary_rejects_wrong_arg_counts(tmp_path: Path) -> None:
    """The binary must enforce exactly two positional args. Calls with
    0/1/3 args must exit non-zero. With the correct two args pointing at
    fresh empty dirs, it would be expected to fail because the inputs are
    missing -- but absence-of-zero-arg is what we check here, not the
    success path."""
    fake_data = tmp_path / "data"
    fake_data.mkdir()
    fake_out = tmp_path / "out"
    fake_out.mkdir()
    for n_args in (0, 1, 3):
        argv = [str(BINARY_PATH)]
        if n_args >= 1:
            argv.append(str(fake_data))
        if n_args >= 2:
            argv.append(str(fake_out))
        if n_args >= 3:
            argv.append("extra")
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        assert proc.returncode != 0, (
            f"binary should exit non-zero on {n_args} arg(s); got rc=0 "
            f"with stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )


def test_outputs_strict_json_formatting(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every output is 2-space, sort-keys, ASCII-only, trailing-newline JSON."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(path)
        assert ok, msg


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def test_outputs_are_ascii_at_every_depth(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every string at every depth in every output JSON must be pure ASCII."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        raw = path.read_bytes()
        for i, b in enumerate(raw):
            assert b < 0x80, (
                f"{path} byte {i} = 0x{b:02x} is non-ASCII; outputs must be "
                "pure ASCII at the byte level"
            )
        doc = json.loads(raw.decode("utf-8"))
        for s in _walk_strings(doc):
            for ch in s:
                assert ord(ch) < 0x80, (
                    f"{path} contains non-ASCII string codepoint U+{ord(ch):04X} "
                    f"in {s!r}"
                )


def test_snapshot_state_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """snapshot_state.json must equal the live-computed reference exactly.

    Stresses:
      - per-snapshot fields (created_at_sec, holders, id, name)
      - snapshots within a dataset sorted by (created_at_sec asc, id asc)
      - datasets sorted by name asc, empty datasets suppressed
      - holders sorted ASCII ascending within each snapshot
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(STATE_PATH)
    assert actual == expected_outputs["snapshot_state"]


def test_prune_log_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """prune_log.json must equal the live-computed reference exactly.

    Stresses:
      - one entry per retention_run in chronological order
      - kept[] sorted by (created_at_sec desc, id desc)
      - pruned[] sorted by id ascending
      - kept_by[] sorted ASCII ascending; "held" appears for held snapshots
      - empty-dataset retention_run appends a kept=[]/pruned=[] entry
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(PRUNE_PATH)
    assert actual == expected_outputs["prune_log"]


def test_retention_diagnostics_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """retention_diagnostics.json must equal the live-computed reference exactly.

    Stresses:
      - sparse layout: only events with diagnostics appear
      - per-event sort by (severity_rank, code, snapshot_id) with null first
      - closed code set; correct severity per code
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(DIAG_PATH)
    assert actual == expected_outputs["retention_diagnostics"]


def test_summary_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """summary.json must equal the live-computed reference exactly.

    Stresses:
      - counters increment correctly across event kinds
      - datasets_with_snapshots is sorted ASCII and excludes empty datasets
      - events_with_diagnostics matches len(retention_diagnostics.events)
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(SUMMARY_PATH)
    assert actual == expected_outputs["summary"]


def test_diagnostic_codes_are_legal(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every diagnostic code is drawn from the closed set with correct
    severity, and within each event the list is sorted by
    (severity_rank, code, snapshot_id) with null sorting first."""
    assert binary_run_outputs["returncode"] == 0
    diag = load_json(DIAG_PATH)
    seqs = [e["seq"] for e in diag["events"]]
    assert seqs == sorted(seqs), f"events not sorted by seq: {seqs}"
    for e in diag["events"]:
        prev = (-1, "", "")
        for d in e["diagnostics"]:
            assert d["code"] in VALID_DIAG_CODES, (
                f"event seq={e['seq']!r}: unknown code {d['code']!r}"
            )
            assert DIAG_SEVERITY[d["code"]] == d["severity"], (
                f"event seq={e['seq']!r}: code {d['code']!r} has wrong "
                f"severity {d['severity']!r}, expected {DIAG_SEVERITY[d['code']]!r}"
            )
            sid = "" if d["snapshot_id"] is None else "1" + d["snapshot_id"]
            key = (SEVERITY_RANK[d["severity"]], d["code"], sid)
            assert key >= prev, (
                f"event seq={e['seq']!r}: diagnostics not sorted by "
                f"(severity_rank, code, snapshot_id); got {key} after {prev}"
            )
            prev = key


def test_dataset_invariants_have_diversity(
    expected_outputs: dict[str, Any],
) -> None:
    """Dataset-level sanity: at least eight distinct diagnostic codes and at
    least one retention run with both kept and pruned entries must be
    exercised. A trivially clean trace would mean the simulator is never
    stressed on the pinned input."""
    diag_doc = expected_outputs["retention_diagnostics"]
    seen_codes: set[str] = set()
    for e in diag_doc["events"]:
        for d in e["diagnostics"]:
            seen_codes.add(d["code"])
    assert len(seen_codes) >= 8, (
        f"dataset invariant: expected at least 8 distinct diagnostic codes "
        f"exercised; got {sorted(seen_codes)}"
    )
    runs = expected_outputs["prune_log"]["runs"]
    assert any(r["kept"] and r["pruned"] for r in runs), (
        "dataset invariant: expected at least one retention_run with both "
        "kept and pruned entries"
    )
    assert expected_outputs["summary"]["snapshots_pruned_by_retention"] >= 3, (
        "dataset invariant: expected at least three snapshots pruned by retention"
    )
    assert expected_outputs["summary"]["snapshots_deleted_explicitly"] >= 1, (
        "dataset invariant: expected at least one explicit delete"
    )


# ---------------------------------------------------------------------------
# Hidden-dataset behavioural tests (exercise branches the pinned dataset
# may not stress directly).
# ---------------------------------------------------------------------------


def _run_binary_on(tmp_path: Path,
                   snaps_doc: dict, events_doc: dict, policy_doc: dict
                   ) -> dict[str, Any]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    (in_dir / "snapshots.json").write_text(json.dumps(snaps_doc), encoding="utf-8")
    (in_dir / "events.json").write_text(json.dumps(events_doc), encoding="utf-8")
    (in_dir / "policy.json").write_text(json.dumps(policy_doc), encoding="utf-8")
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"binary failed on hidden dataset: rc={proc.returncode} "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    docs: dict[str, Any] = {}
    for fname in ("snapshot_state.json", "prune_log.json",
                  "retention_diagnostics.json", "summary.json"):
        docs[fname] = json.loads((out_dir / fname).read_text(encoding="utf-8"))
    return docs


def _ref_for(snaps_doc, events_doc, policy_doc):
    return run_simulation(
        snaps_doc["snapshots"], events_doc["events"], policy_doc,
    )


def _zero_rules():
    return {"keep_last_n": 0, "keep_hourly": 0, "keep_daily": 0,
            "keep_weekly": 0, "keep_monthly": 0}


def test_hidden_dataset_skip_action_no_state_change(tmp_path: Path) -> None:
    """held_delete_action='skip' on a held snapshot emits W_SKIP_HELD and
    leaves the snapshot present (no state change)."""
    snaps = {"snapshots": [
        {"created_at_sec": 100, "dataset": "d", "holders": ["h"],
         "id": "s", "name": "n"},
    ]}
    events = {"events": [
        {"seq": 0, "kind": "snapshot_delete", "id": "s", "force": False},
    ]}
    policy = {
        "now_sec": 100,
        "held_delete_action": "skip",
        "default_rules": _zero_rules(),
        "datasets": {},
    }
    actual = _run_binary_on(tmp_path, snaps, events, policy)
    expected = _ref_for(snaps, events, policy)
    assert actual["snapshot_state.json"]    == expected["snapshot_state"]
    assert actual["retention_diagnostics.json"] == expected["retention_diagnostics"]
    assert actual["summary.json"]           == expected["summary"]
    diag = actual["retention_diagnostics.json"]
    codes = [d["code"] for e in diag["events"] for d in e["diagnostics"]]
    assert codes == ["W_SKIP_HELD"], (
        f"skip mode must emit only W_SKIP_HELD; got {codes}"
    )
    assert actual["summary.json"]["snapshots_deleted_explicitly"] == 0
    assert actual["summary.json"]["final_snapshot_count"] == 1


def test_hidden_dataset_break_holds_via_policy(tmp_path: Path) -> None:
    """held_delete_action='break_holds' with force=false still deletes the
    held snapshot and emits W_BREAK_HOLDS first."""
    snaps = {"snapshots": [
        {"created_at_sec": 100, "dataset": "d", "holders": ["h1", "h2"],
         "id": "s", "name": "n"},
    ]}
    events = {"events": [
        {"seq": 0, "kind": "snapshot_delete", "id": "s", "force": False},
    ]}
    policy = {
        "now_sec": 100,
        "held_delete_action": "break_holds",
        "default_rules": _zero_rules(),
        "datasets": {},
    }
    actual = _run_binary_on(tmp_path, snaps, events, policy)
    expected = _ref_for(snaps, events, policy)
    assert actual == {
        "snapshot_state.json":         expected["snapshot_state"],
        "prune_log.json":              expected["prune_log"],
        "retention_diagnostics.json":  expected["retention_diagnostics"],
        "summary.json":                expected["summary"],
    }
    assert actual["summary.json"]["snapshots_deleted_explicitly"] == 1
    assert actual["summary.json"]["final_snapshot_count"] == 0
    codes = [d["code"]
             for e in actual["retention_diagnostics.json"]["events"]
             for d in e["diagnostics"]]
    assert codes == ["W_BREAK_HOLDS"]


def test_hidden_dataset_force_overrides_reject(tmp_path: Path) -> None:
    """A snapshot_delete with force=true on a held snapshot follows the
    break_holds branch even when held_delete_action is 'reject'."""
    snaps = {"snapshots": [
        {"created_at_sec": 100, "dataset": "d", "holders": ["h"],
         "id": "s", "name": "n"},
    ]}
    events = {"events": [
        {"seq": 0, "kind": "snapshot_delete", "id": "s", "force": True},
    ]}
    policy = {
        "now_sec": 100,
        "held_delete_action": "reject",
        "default_rules": _zero_rules(),
        "datasets": {},
    }
    actual = _run_binary_on(tmp_path, snaps, events, policy)
    expected = _ref_for(snaps, events, policy)
    assert actual["snapshot_state.json"] == expected["snapshot_state"]
    assert actual["summary.json"]["snapshots_deleted_explicitly"] == 1
    codes = [d["code"]
             for e in actual["retention_diagnostics.json"]["events"]
             for d in e["diagnostics"]]
    assert codes == ["W_BREAK_HOLDS"], (
        f"force=true must take the break_holds branch even under reject; got {codes}"
    )


def test_hidden_dataset_bucket_tie_break_id_descending(tmp_path: Path) -> None:
    """Two snapshots sharing the same bucket and same created_at_sec resolve
    in favour of the lex-greater id (id descending)."""
    snaps = {"snapshots": [
        {"created_at_sec": 100, "dataset": "d", "holders": [],
         "id": "snap-a", "name": "a"},
        {"created_at_sec": 100, "dataset": "d", "holders": [],
         "id": "snap-b", "name": "b"},
    ]}
    events = {"events": [
        {"seq": 0, "kind": "retention_run", "dataset": "d"},
    ]}
    policy = {
        "now_sec": 100,
        "held_delete_action": "reject",
        "default_rules": _zero_rules(),
        "datasets": {"d": {"keep_last_n": 0, "keep_hourly": 1,
                            "keep_daily": 0, "keep_weekly": 0,
                            "keep_monthly": 0}},
    }
    actual = _run_binary_on(tmp_path, snaps, events, policy)
    expected = _ref_for(snaps, events, policy)
    assert actual["prune_log.json"] == expected["prune_log"]
    run = actual["prune_log.json"]["runs"][0]
    kept_ids = [k["id"] for k in run["kept"]]
    pruned_ids = [p["id"] for p in run["pruned"]]
    assert kept_ids == ["snap-b"], (
        f"id-descending tie-break should keep snap-b; got kept={kept_ids}"
    )
    assert pruned_ids == ["snap-a"], (
        f"the loser of the tie should be pruned; got pruned={pruned_ids}"
    )


def test_hidden_dataset_held_snapshot_unconditionally_kept(tmp_path: Path) -> None:
    """A snapshot with non-empty holders survives a retention_run even when
    no rule keeps it, and shows kept_by = ['held'] in prune_log."""
    snaps = {"snapshots": [
        {"created_at_sec": 100, "dataset": "d", "holders": ["watch"],
         "id": "snap-1", "name": "one"},
        {"created_at_sec": 200, "dataset": "d", "holders": [],
         "id": "snap-2", "name": "two"},
    ]}
    events = {"events": [
        {"seq": 0, "kind": "retention_run", "dataset": "d"},
    ]}
    policy = {
        "now_sec": 200,
        "held_delete_action": "reject",
        "default_rules": _zero_rules(),
        "datasets": {"d": {"keep_last_n": 1, "keep_hourly": 0,
                            "keep_daily": 0, "keep_weekly": 0,
                            "keep_monthly": 0}},
    }
    actual = _run_binary_on(tmp_path, snaps, events, policy)
    expected = _ref_for(snaps, events, policy)
    assert actual == {
        "snapshot_state.json":         expected["snapshot_state"],
        "prune_log.json":              expected["prune_log"],
        "retention_diagnostics.json":  expected["retention_diagnostics"],
        "summary.json":                expected["summary"],
    }
    run = actual["prune_log.json"]["runs"][0]
    kept_by_id = {k["id"]: k["kept_by"] for k in run["kept"]}
    assert kept_by_id["snap-1"] == ["held"], (
        f"held snapshot kept_by should be ['held'] only; got {kept_by_id['snap-1']}"
    )
    assert kept_by_id["snap-2"] == ["keep_last_n"]
    assert run["pruned"] == []


def test_hidden_dataset_default_rules_used_for_unknown_dataset(tmp_path: Path) -> None:
    """A dataset not in policy.datasets falls back to default_rules during
    retention. A non-empty default_rules can preserve some snapshots."""
    snaps = {"snapshots": [
        {"created_at_sec": 0, "dataset": "rare", "holders": [],
         "id": "r1", "name": "older"},
        {"created_at_sec": 100000, "dataset": "rare", "holders": [],
         "id": "r2", "name": "newer"},
    ]}
    events = {"events": [
        {"seq": 0, "kind": "retention_run", "dataset": "rare"},
    ]}
    policy = {
        "now_sec": 100000,
        "held_delete_action": "reject",
        "default_rules": {"keep_last_n": 1, "keep_hourly": 0,
                           "keep_daily": 0, "keep_weekly": 0,
                           "keep_monthly": 0},
        "datasets": {},
    }
    actual = _run_binary_on(tmp_path, snaps, events, policy)
    expected = _ref_for(snaps, events, policy)
    assert actual == {
        "snapshot_state.json":         expected["snapshot_state"],
        "prune_log.json":              expected["prune_log"],
        "retention_diagnostics.json":  expected["retention_diagnostics"],
        "summary.json":                expected["summary"],
    }
    state_ids = sorted(s["id"]
                       for ds in actual["snapshot_state.json"]["datasets"]
                       for s in ds["snapshots"])
    assert state_ids == ["r2"], (
        f"default_rules.keep_last_n=1 should retain only the newest; got {state_ids}"
    )


def test_hidden_dataset_now_sec_advances_create_timestamp(tmp_path: Path) -> None:
    """A snapshot_create after a tick uses the advanced now_sec as
    created_at_sec, not the original policy.now_sec."""
    snaps = {"snapshots": []}
    events = {"events": [
        {"seq": 0, "kind": "tick", "delta_sec": 7200},
        {"seq": 1, "kind": "snapshot_create", "dataset": "d",
         "id": "s", "name": "after-tick"},
    ]}
    policy = {
        "now_sec": 100,
        "held_delete_action": "reject",
        "default_rules": _zero_rules(),
        "datasets": {},
    }
    actual = _run_binary_on(tmp_path, snaps, events, policy)
    expected = _ref_for(snaps, events, policy)
    assert actual["snapshot_state.json"] == expected["snapshot_state"]
    snap_entry = actual["snapshot_state.json"]["datasets"][0]["snapshots"][0]
    assert snap_entry["created_at_sec"] == 7300, (
        f"created_at_sec should be 100 + 7200 = 7300; got {snap_entry['created_at_sec']}"
    )


def test_hidden_dataset_determinism_two_runs_byte_identical(tmp_path: Path) -> None:
    """Two runs of the binary on the same /app/data inputs into different
    output directories must produce byte-identical files. Catches latent
    nondeterminism (hash-map iteration, address-dependent ordering, etc.).
    """
    in_dir = tmp_path / "data"
    in_dir.mkdir()
    for src in (SNAPSHOTS_PATH, EVENTS_PATH, POLICY_PATH):
        shutil.copy2(src, in_dir / src.name)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    out_a.mkdir()
    out_b.mkdir()
    for out in (out_a, out_b):
        proc = subprocess.run(
            [str(BINARY_PATH), str(in_dir), str(out)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, (
            f"determinism run failed: rc={proc.returncode} stderr={proc.stderr!r}"
        )
    for fname in ("snapshot_state.json", "prune_log.json",
                  "retention_diagnostics.json", "summary.json"):
        a = (out_a / fname).read_bytes()
        b = (out_b / fname).read_bytes()
        assert a == b, (
            f"determinism violated for {fname}: byte-by-byte differs across two runs"
        )


def _snapshot_dir_state(root: Path) -> dict[str, str]:
    """Return {relative_path: sha256_hex} for every regular file under root."""
    state: dict[str, str] = {}
    if not root.exists():
        return state
    for p in sorted(root.rglob("*")):
        if p.is_file():
            state[str(p.relative_to(root))] = sha256_of(p)
    return state


def test_app_data_unchanged_recursively_after_run(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The instruction forbids modifying anything under /app/data/. The
    pinned-hash check covers the three named input files, but this test
    snapshots EVERY regular file under /app/data before the run, then
    verifies that after the binary runs (a) no file was added, (b) no file
    was removed, and (c) every file's sha256 is unchanged.
    """
    assert binary_run_outputs["returncode"] == 0
    after = _snapshot_dir_state(DATA_DIR)
    for path, expected in EXPECTED_INPUT_HASHES.items():
        assert path.exists(), f"input vanished after run: {path}"
        actual = sha256_of(path)
        assert actual == expected, (
            f"input file {path} was modified by the binary "
            f"(hash {actual} != pinned {expected})"
        )
    rel_inputs = {p.name for p in EXPECTED_INPUT_HASHES}
    spurious = sorted(rel_path for rel_path in after if rel_path not in rel_inputs)
    assert not spurious, (
        f"binary created unexpected files under /app/data: {spurious}; "
        "the binary must not write anything under /app/data"
    )


def test_binary_rejects_missing_input_directory(tmp_path: Path) -> None:
    """Passing a nonexistent input directory must yield non-zero exit."""
    missing_in  = tmp_path / "does_not_exist"
    out_dir     = tmp_path / "out"
    out_dir.mkdir()
    proc = subprocess.run(
        [str(BINARY_PATH), str(missing_in), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0, (
        "binary should exit non-zero when the input directory does not exist; "
        f"got rc=0 stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


def test_binary_rejects_missing_input_files(tmp_path: Path) -> None:
    """Empty input directory (no snapshots/events/policy.json) must
    yield non-zero exit. The binary must report that inputs are missing
    rather than silently producing empty outputs."""
    in_dir  = tmp_path / "data"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0, (
        "binary should exit non-zero when input json files are missing; "
        f"got rc=0 stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


def _try_run(tmp_path: Path, snaps_text: str, events_text: str,
             policy_text: str) -> subprocess.CompletedProcess:
    in_dir  = tmp_path / "data"
    out_dir = tmp_path / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    (in_dir / "snapshots.json").write_text(snaps_text,  encoding="utf-8")
    (in_dir / "events.json").write_text(events_text,    encoding="utf-8")
    (in_dir / "policy.json").write_text(policy_text,    encoding="utf-8")
    return subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )


def test_binary_rejects_malformed_inputs(tmp_path: Path) -> None:
    """The binary must exit non-zero on a variety of malformed inputs
    rather than producing partial or junk outputs. The instruction
    explicitly requires non-zero exit on malformed input."""
    good_snaps  = json.dumps({"snapshots": [
        {"id": "s1", "name": "n", "dataset": "d", "created_at_sec": 0,
         "holders": []},
    ]})
    good_events = json.dumps({"events": [
        {"seq": 0, "kind": "retention_run", "dataset": "d"},
    ]})
    good_policy = json.dumps({
        "now_sec": 100,
        "held_delete_action": "reject",
        "default_rules": {"keep_last_n": 0, "keep_hourly": 0,
                           "keep_daily": 0, "keep_weekly": 0,
                           "keep_monthly": 0},
        "datasets": {},
    })
    cases: list[tuple[str, str, str, str]] = [
        ("garbage_snapshots_json", "{not valid json", good_events, good_policy),
        ("garbage_events_json",    good_snaps, "{not valid json", good_policy),
        ("garbage_policy_json",    good_snaps, good_events, "{not valid json"),
        ("missing_snapshots_key",  json.dumps({"shapshots": []}),
                                   good_events, good_policy),
        ("missing_events_key",     good_snaps,
                                   json.dumps({"evenets": []}), good_policy),
        ("snapshot_missing_id",    json.dumps({"snapshots": [
            {"name": "n", "dataset": "d", "created_at_sec": 0, "holders": []},
        ]}), good_events, good_policy),
        ("snapshot_wrong_type",    json.dumps({"snapshots": [
            {"id": 7, "name": "n", "dataset": "d", "created_at_sec": 0,
             "holders": []},
        ]}), good_events, good_policy),
        ("event_unknown_kind",     good_snaps,
                                   json.dumps({"events": [
                                       {"seq": 0, "kind": "wat"},
                                   ]}), good_policy),
        ("event_seq_not_dense",    good_snaps,
                                   json.dumps({"events": [
                                       {"seq": 1, "kind": "retention_run",
                                        "dataset": "d"},
                                   ]}), good_policy),
        ("policy_missing_default_rules", good_snaps, good_events,
                                   json.dumps({
                                       "now_sec": 0,
                                       "held_delete_action": "reject",
                                       "datasets": {},
                                   })),
        ("policy_invalid_action",  good_snaps, good_events,
                                   json.dumps({
                                       "now_sec": 0,
                                       "held_delete_action": "explode",
                                       "default_rules": {
                                           "keep_last_n": 0, "keep_hourly": 0,
                                           "keep_daily":  0, "keep_weekly": 0,
                                           "keep_monthly": 0},
                                       "datasets": {},
                                   })),
        ("duplicate_snapshot_id",  json.dumps({"snapshots": [
            {"id": "s1", "name": "a", "dataset": "d", "created_at_sec": 0,
             "holders": []},
            {"id": "s1", "name": "b", "dataset": "d", "created_at_sec": 1,
             "holders": []},
        ]}), good_events, good_policy),
    ]
    failures: list[str] = []
    for label, snaps, events, policy in cases:
        proc = _try_run(tmp_path / label, snaps, events, policy)
        if proc.returncode == 0:
            failures.append(
                f"{label}: expected non-zero exit on malformed input; "
                f"got rc=0 stdout={proc.stdout!r} stderr={proc.stderr!r}"
            )
    assert not failures, "\n".join(failures)
