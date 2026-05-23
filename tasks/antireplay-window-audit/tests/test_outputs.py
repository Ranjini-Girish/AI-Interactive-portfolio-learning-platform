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

DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
BUILD_DIR = Path("/app/build")
BINARY_PATH = BUILD_DIR / "arwsim"

SAS_PATH    = DATA_DIR / "sas.json"
EVENTS_PATH = DATA_DIR / "events.json"
POLICY_PATH = DATA_DIR / "policy.json"

SA_STATE_PATH         = OUT_DIR / "sa_state.json"
PACKET_DECISIONS_PATH = OUT_DIR / "packet_decisions.json"
REPLAY_LOG_PATH       = OUT_DIR / "replay_log.json"
SUMMARY_PATH          = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    SA_STATE_PATH,
    PACKET_DECISIONS_PATH,
    REPLAY_LOG_PATH,
    SUMMARY_PATH,
)

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    SAS_PATH:    "7f00d79a2b6dcb11608e4983e9d7670706e51d1f0ab4d630d527de71e57e53b1",
    EVENTS_PATH: "7bf02124b388872b23bf3f904246e23144a92b3b8729072e9ab8663cb7b3fbef",
    POLICY_PATH: "32232e6bcc471bd60e340a9dde4a8b62553c750fd5e4b2a9f5303c34988e61f3",
}

DOCS_DIAG_PATH = Path("/app/docs/diagnostics.md")
DOCS_OUTPUT_FORMAT_PATH = Path("/app/docs/output_format.md")

VALID_DECISIONS = {
    "accept", "accept_passive",
    "replay_logged", "replay_dropped",
    "too_old_logged", "too_old_dropped",
    "unknown_drop",
}
REPLAY_LOG_DECISIONS = {
    "replay_logged", "replay_dropped",
    "too_old_logged", "too_old_dropped",
    "unknown_drop",
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


def _encode_bitmap(bitmap_int: int, window_size: int) -> str:
    nbytes = (window_size + 7) // 8
    out = []
    for i in range(nbytes):
        b = (bitmap_int >> (8 * i)) & 0xFF
        out.append(f"{b:02x}")
    return "".join(out)


def _shift_bitmap(bitmap_int: int, shift: int, window_size: int) -> int:
    new = (bitmap_int << shift) | 1
    return new & ((1 << window_size) - 1)


def run_simulation(initial_sas, events, policy):
    sas: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    counters: dict[str, dict[str, int]] = {}
    decisions: list[dict[str, Any]] = []

    def init_counters(sa_id: str):
        if sa_id not in counters:
            counters[sa_id] = {
                "accepted": 0, "recv_total": 0,
                "replays": 0, "too_old": 0, "rekeys": 0,
            }

    for s in initial_sas:
        sa_id = s["id"]
        sas[sa_id] = {"id": sa_id, "top": s["top"],
                      "window_size": s["window_size"],
                      "owner": s["owner"], "bitmap": 0}
        seen_ids.add(sa_id)
        init_counters(sa_id)

    add_sa_failures = 0
    rekey_failures = 0
    rekey_successes = 0
    drop_unknown_sa = 0
    passive_created_count = 0
    replays_total = 0
    too_old_total = 0

    allowed_windows = list(policy["window_sizes_allowed"])
    allowed_set = set(allowed_windows)

    for ev in events:
        seq = ev["seq"]
        op = ev["op"]
        if op == "add_sa":
            sa_id = ev["sa_id"]
            top = ev["top"]
            window_size = ev["window_size"]
            owner = ev["owner"]
            if sa_id in seen_ids:
                add_sa_failures += 1
                continue
            if window_size not in allowed_set:
                add_sa_failures += 1
                continue
            if top < 0:
                add_sa_failures += 1
                continue
            sas[sa_id] = {"id": sa_id, "top": top, "window_size": window_size,
                          "owner": owner, "bitmap": 0}
            seen_ids.add(sa_id)
            init_counters(sa_id)
            continue
        if op == "delete_sa":
            sa_id = ev["sa_id"]
            if sa_id not in sas:
                continue
            del sas[sa_id]
            continue
        if op == "rekey":
            sa_id = ev["sa_id"]
            window_size = ev["window_size"]
            if sa_id not in sas:
                rekey_failures += 1
                continue
            if window_size not in allowed_set:
                rekey_failures += 1
                continue
            sa = sas[sa_id]
            sa["top"] = 0
            sa["bitmap"] = 0
            sa["window_size"] = window_size
            counters[sa_id]["rekeys"] += 1
            rekey_successes += 1
            continue
        if op == "recv":
            sa_id = ev["sa_id"]
            esp_seq = ev["esp_seq"]
            passive_created = False
            if sa_id not in sas:
                if policy["on_unknown_sa"] == "drop":
                    drop_unknown_sa += 1
                    decisions.append({
                        "decision": "unknown_drop",
                        "diagnostic": "E_UNKNOWN_SA",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                    continue
                w0 = allowed_windows[0]
                sas[sa_id] = {"id": sa_id, "top": 0, "window_size": w0,
                              "owner": "passive", "bitmap": 0}
                seen_ids.add(sa_id)
                init_counters(sa_id)
                passive_created = True
                passive_created_count += 1
            sa = sas[sa_id]
            top = sa["top"]
            ws = sa["window_size"]
            bitmap = sa["bitmap"]
            counters[sa_id]["recv_total"] += 1
            if esp_seq > top:
                shift = esp_seq - top
                sa["bitmap"] = _shift_bitmap(bitmap, shift, ws)
                sa["top"] = esp_seq
                counters[sa_id]["accepted"] += 1
                if passive_created:
                    decisions.append({
                        "decision": "accept_passive",
                        "diagnostic": "N_PASSIVE_CREATED",
                        "esp_seq": esp_seq,
                        "passive_created": True,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                else:
                    decisions.append({
                        "decision": "accept",
                        "diagnostic": None,
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                continue
            if esp_seq == top:
                replays_total += 1
                counters[sa_id]["replays"] += 1
                if policy["on_replay"] == "drop":
                    decisions.append({
                        "decision": "replay_dropped",
                        "diagnostic": "W_REPLAY",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                else:
                    counters[sa_id]["accepted"] += 1
                    decisions.append({
                        "decision": "replay_logged",
                        "diagnostic": "W_REPLAY",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                continue
            offset = top - esp_seq
            if offset >= ws:
                too_old_total += 1
                counters[sa_id]["too_old"] += 1
                if policy["on_too_old"] == "drop":
                    decisions.append({
                        "decision": "too_old_dropped",
                        "diagnostic": "W_TOO_OLD",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                else:
                    counters[sa_id]["accepted"] += 1
                    decisions.append({
                        "decision": "too_old_logged",
                        "diagnostic": "W_TOO_OLD",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                continue
            bit = (bitmap >> offset) & 1
            if bit == 1:
                replays_total += 1
                counters[sa_id]["replays"] += 1
                if policy["on_replay"] == "drop":
                    decisions.append({
                        "decision": "replay_dropped",
                        "diagnostic": "W_REPLAY",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                else:
                    counters[sa_id]["accepted"] += 1
                    decisions.append({
                        "decision": "replay_logged",
                        "diagnostic": "W_REPLAY",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                continue
            sa["bitmap"] = bitmap | (1 << offset)
            counters[sa_id]["accepted"] += 1
            decisions.append({
                "decision": "accept",
                "diagnostic": None,
                "esp_seq": esp_seq,
                "passive_created": False,
                "sa_id": sa_id,
                "seq": seq,
            })

    sa_state_arr = []
    for sa_id in sorted(sas):
        sa = sas[sa_id]
        c = counters[sa_id]
        sa_state_arr.append({
            "accepted":    c["accepted"],
            "bitmap":      _encode_bitmap(sa["bitmap"], sa["window_size"]),
            "id":          sa_id,
            "owner":       sa["owner"],
            "recv_total":  c["recv_total"],
            "rekeys":      c["rekeys"],
            "replays":     c["replays"],
            "too_old":     c["too_old"],
            "top":         sa["top"],
            "window_size": sa["window_size"],
        })

    accepted_total = sum(c["accepted"] for c in counters.values())

    hot = []
    for sa_id in sorted(counters):
        c = counters[sa_id]
        s = c["replays"] + c["too_old"]
        if s > 0 and s >= policy["min_hot_threshold"]:
            hot.append({"id": sa_id, "replays": c["replays"],
                        "too_old": c["too_old"]})
    hot.sort(key=lambda h: (-(h["replays"] + h["too_old"]), h["id"]))

    summary = {
        "accepted_total":        accepted_total,
        "active_sa_count":       len(sas),
        "add_sa_failures":       add_sa_failures,
        "drop_unknown_sa":       drop_unknown_sa,
        "hot_sas":               hot,
        "passive_created_count": passive_created_count,
        "policy_on_replay":      policy["on_replay"],
        "policy_on_too_old":     policy["on_too_old"],
        "policy_on_unknown_sa":  policy["on_unknown_sa"],
        "rekey_failures":        rekey_failures,
        "rekey_successes":       rekey_successes,
        "replays_total":         replays_total,
        "too_old_total":         too_old_total,
        "total_events":          len(events),
    }

    replay_log = []
    for d in decisions:
        if d["decision"] in REPLAY_LOG_DECISIONS:
            replay_log.append({
                "decision":   d["decision"],
                "diagnostic": d["diagnostic"],
                "esp_seq":    d["esp_seq"],
                "sa_id":      d["sa_id"],
                "seq":        d["seq"],
            })

    return {
        "sa_state":         {"sas": sa_state_arr},
        "packet_decisions": {"decisions": decisions},
        "replay_log":       {"entries": replay_log},
        "summary":          summary,
    }


def reference_outputs() -> dict[str, Any]:
    sas_doc    = load_json(SAS_PATH)
    events_doc = load_json(EVENTS_PATH)
    policy_doc = load_json(POLICY_PATH)
    return run_simulation(sas_doc["sas"], events_doc["events"], policy_doc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def expected_outputs() -> dict[str, Any]:
    return reference_outputs()


@pytest.fixture(scope="session")
def binary_run_outputs() -> dict[str, Any]:
    """Wipe /app/output, run the agent's binary with the canonical CLI,
    capture rc/stdout/stderr/start_time. Tests asserting against
    /app/output/*.json depend on this fixture so the agent's binary is the
    only thing that produces those files."""
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
# Build / CLI / freshness checks
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
    """Agent must install a runnable TypeScript launcher at BINARY_PATH."""
    assert BINARY_PATH.exists(), f"expected launcher at {BINARY_PATH}"
    assert BINARY_PATH.stat().st_mode & stat.S_IXUSR, (
        f"{BINARY_PATH} is not executable"
    )
    src_ts = list(Path("/app/src").rglob("*.ts"))
    assert src_ts, "expected agent-authored TypeScript under /app/src"







def test_binary_runs_cleanly_and_outputs_are_fresh(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The agent's binary must run with the canonical two-arg CLI on
    /app/data, exit 0, and produce all four outputs that are mtime-newer
    than the moment the verifier started the run."""
    rc = binary_run_outputs["returncode"]
    assert rc == 0, (
        f"/app/build/arwsim exited with rc={rc} when run with canonical "
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
    """The binary must enforce exactly two positional args. Calls with 0/1/3
    args must exit non-zero."""
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


# ---------------------------------------------------------------------------
# Reference equality
# ---------------------------------------------------------------------------


def test_sa_state_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """sa_state.json must equal the live-computed reference exactly.

    Stresses:
      - per-SA top, window_size, owner at trace end
      - hex-encoded bitmap (little-endian byte order)
      - per-SA lifetime counters (accepted, recv_total, replays, too_old, rekeys)
      - SAs sorted by id ASCII ascending
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(SA_STATE_PATH)
    assert actual == expected_outputs["sa_state"]


def test_packet_decisions_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """packet_decisions.json must equal the live-computed reference exactly.

    Stresses:
      - chronological order (no sorting beyond input seq)
      - exactly one row per recv event
      - decision string from the closed enum
      - diagnostic field correctly null/string per the docs table
      - passive_created flag set ONLY for accept_passive rows
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(PACKET_DECISIONS_PATH)
    assert actual == expected_outputs["packet_decisions"]


def test_replay_log_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """replay_log.json must equal the live-computed reference exactly.

    Stresses:
      - subset of packet_decisions whose decision is replay_*, too_old_*,
        or unknown_drop (NEVER accept or accept_passive)
      - chronological by seq
      - diagnostic is never null
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(REPLAY_LOG_PATH)
    assert actual == expected_outputs["replay_log"]


def test_summary_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """summary.json must equal the live-computed reference exactly.

    Stresses:
      - accepted_total = sum of per-SA "accepted" across every observed id
      - hot_sas sorted by (replays + too_old) DESC then id ASC
      - hot_sas filtered by min_hot_threshold AND > 0
      - policy_on_* fields echoed verbatim
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(SUMMARY_PATH)
    assert actual == expected_outputs["summary"]


# ---------------------------------------------------------------------------
# Structural / docs-driven invariants
# ---------------------------------------------------------------------------


def test_packet_decisions_seq_is_chronological(
    binary_run_outputs: dict[str, Any],
) -> None:
    """packet_decisions.decisions must be in non-decreasing seq order."""
    assert binary_run_outputs["returncode"] == 0
    pd = load_json(PACKET_DECISIONS_PATH)
    seqs = [r["seq"] for r in pd["decisions"]]
    assert seqs == sorted(seqs), (
        f"packet_decisions.decisions must be in non-decreasing seq order; "
        f"got {seqs}"
    )


def test_replay_log_subset_of_packet_decisions(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every replay_log entry must correspond to a packet_decisions row
    with the same (seq, sa_id, esp_seq, decision, diagnostic), AND the
    decision must NOT be accept or accept_passive."""
    assert binary_run_outputs["returncode"] == 0
    pd = {(r["seq"], r["sa_id"], r["esp_seq"]): r
          for r in load_json(PACKET_DECISIONS_PATH)["decisions"]}
    rl = load_json(REPLAY_LOG_PATH)["entries"]
    for r in rl:
        key = (r["seq"], r["sa_id"], r["esp_seq"])
        assert key in pd, (
            f"replay_log row {r} has no matching packet_decisions row"
        )
        assert pd[key]["decision"] == r["decision"], (
            f"replay_log decision {r['decision']} differs from "
            f"packet_decisions {pd[key]['decision']} for {key}"
        )
        assert pd[key]["diagnostic"] == r["diagnostic"], (
            f"replay_log diagnostic for {key} differs from packet_decisions"
        )
        assert r["decision"] in REPLAY_LOG_DECISIONS, (
            f"replay_log row {r} has illegal decision {r['decision']}"
        )


def test_decisions_use_only_legal_enum_values(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every decision string must come from the closed enum."""
    assert binary_run_outputs["returncode"] == 0
    pd = load_json(PACKET_DECISIONS_PATH)
    for r in pd["decisions"]:
        assert r["decision"] in VALID_DECISIONS, (
            f"unknown decision string {r['decision']!r} at seq={r['seq']}"
        )


def test_passive_created_flag_only_on_accept_passive(
    binary_run_outputs: dict[str, Any],
) -> None:
    """passive_created MUST be true iff decision == accept_passive."""
    assert binary_run_outputs["returncode"] == 0
    pd = load_json(PACKET_DECISIONS_PATH)
    for r in pd["decisions"]:
        if r["decision"] == "accept_passive":
            assert r["passive_created"] is True, (
                f"accept_passive at seq={r['seq']} has passive_created=false"
            )
            assert r["diagnostic"] == "N_PASSIVE_CREATED", (
                f"accept_passive at seq={r['seq']} has diagnostic="
                f"{r['diagnostic']!r}, expected 'N_PASSIVE_CREATED'"
            )
        else:
            assert r["passive_created"] is False, (
                f"non-passive decision at seq={r['seq']} has "
                f"passive_created=true (decision={r['decision']!r})"
            )


def test_diagnostic_field_matches_decision(
    binary_run_outputs: dict[str, Any],
) -> None:
    """diagnostic must follow the decision-to-diagnostic mapping in
    /app/docs/output_format.md exactly."""
    expected_map = {
        "accept":           None,
        "accept_passive":   "N_PASSIVE_CREATED",
        "replay_logged":    "W_REPLAY",
        "replay_dropped":   "W_REPLAY",
        "too_old_logged":   "W_TOO_OLD",
        "too_old_dropped":  "W_TOO_OLD",
        "unknown_drop":     "E_UNKNOWN_SA",
    }
    assert binary_run_outputs["returncode"] == 0
    pd = load_json(PACKET_DECISIONS_PATH)
    for r in pd["decisions"]:
        want = expected_map[r["decision"]]
        assert r["diagnostic"] == want, (
            f"seq={r['seq']} decision={r['decision']!r}: "
            f"diagnostic must be {want!r}; got {r['diagnostic']!r}"
        )


def test_sa_state_sorted_and_complete(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """sa_state.sas must be sorted by id ASCII ascending and contain exactly
    the live-at-end SAs."""
    assert binary_run_outputs["returncode"] == 0
    state = load_json(SA_STATE_PATH)
    ids = [s["id"] for s in state["sas"]]
    assert ids == sorted(ids), f"sa_state.sas not sorted by id: {ids}"
    expected_ids = [s["id"] for s in expected_outputs["sa_state"]["sas"]]
    assert ids == expected_ids, (
        f"sa_state ids {ids} differ from expected live-at-end set {expected_ids}"
    )


def test_summary_keys_match_documented_set(
    binary_run_outputs: dict[str, Any],
) -> None:
    """summary.json's top-level keys must exactly match the set documented in
    /app/docs/output_format.md."""
    import re
    text = DOCS_OUTPUT_FORMAT_PATH.read_text(encoding="utf-8")
    summary_match = re.search(
        r"##\s+`summary\.json`(.*?)(?:^###\s+|^##\s+|\Z)",
        text, flags=re.DOTALL | re.MULTILINE,
    )
    assert summary_match is not None, (
        "could not locate summary.json section in output_format.md"
    )
    block = summary_match.group(1)
    # Only consider top-level summary keys: lines that start with exactly
    # two spaces and a quoted JSON key (i.e. directly inside the outer
    # `{ ... }`). Keys nested in `hot_sas` (4-space indent) are excluded.
    keys = set(re.findall(r'^\s{2}"([a-z_]+)"\s*:', block, flags=re.MULTILINE))
    assert keys, "could not extract any summary keys from output_format.md"
    assert binary_run_outputs["returncode"] == 0
    summary = load_json(SUMMARY_PATH)
    actual = set(summary.keys())
    extra = actual - keys
    missing = keys - actual
    assert not extra, (
        f"summary.json has undocumented keys: {sorted(extra)}; "
        f"docs expect exactly {sorted(keys)}"
    )
    assert not missing, (
        f"summary.json missing documented keys: {sorted(missing)}"
    )


def test_dataset_invariants_have_diversity(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """Dataset-level sanity: the bundled trace must exercise enough branches
    that the simulator is actually stressed."""
    expected = expected_outputs
    pd = expected["packet_decisions"]["decisions"]
    seen_decisions = {r["decision"] for r in pd}
    # With one fixed policy triple, the maximum reachable decision values
    # in a single trace is 4 (accept, replay_X, too_old_X, plus either
    # accept_passive or unknown_drop). We require all four to be exercised.
    assert len(seen_decisions) >= 4, (
        f"expected at least 4 distinct decision values exercised; "
        f"got {sorted(seen_decisions)}"
    )
    assert expected["summary"]["replays_total"] >= 2, (
        "expected at least two replay events in the bundled trace"
    )
    assert expected["summary"]["too_old_total"] >= 1, (
        "expected at least one too-old event in the bundled trace"
    )
    assert expected["summary"]["passive_created_count"] >= 1, (
        "expected at least one passive-create event in the bundled trace"
    )
    assert expected["summary"]["rekey_successes"] >= 1, (
        "expected at least one successful rekey in the bundled trace"
    )
    assert expected["summary"]["rekey_failures"] >= 1, (
        "expected at least one failed rekey in the bundled trace"
    )
    assert expected["summary"]["add_sa_failures"] >= 1, (
        "expected at least one add_sa failure in the bundled trace"
    )
    assert len(expected["summary"]["hot_sas"]) >= 2, (
        "expected at least two hot SAs in the bundled trace"
    )


# ---------------------------------------------------------------------------
# Hidden-dataset behavioural tests
# ---------------------------------------------------------------------------


def _run_binary_on(tmp_path: Path,
                   sas_doc: dict, events_doc: dict, policy_doc: dict
                   ) -> dict[str, Any]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (in_dir / "sas.json").write_text(json.dumps(sas_doc), encoding="utf-8")
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
    for fname in ("sa_state.json", "packet_decisions.json",
                  "replay_log.json", "summary.json"):
        docs[fname] = json.loads((out_dir / fname).read_text(encoding="utf-8"))
    return docs


def _ref_for(sas_doc, events_doc, policy_doc):
    return run_simulation(sas_doc["sas"], events_doc["events"], policy_doc)


def _empty_event(seq: int, op: str, **fields):
    base = {"seq": seq, "op": op,
            "sa_id": None, "top": None, "window_size": None,
            "owner": None, "esp_seq": None}
    base.update(fields)
    return base


def test_hidden_dataset_window_shift_drops_old_bits(tmp_path: Path) -> None:
    """A shift larger than window_size must drop every previously-set bit
    inside the window AND set bit 0 to 1; the bitmap encoding must match."""
    sas = {"sas": [{"id": "x", "top": 10, "window_size": 8, "owner": "u"}]}
    events = {"events": [
        _empty_event(0, "recv", sa_id="x", esp_seq=10),  # head replay (top stays 10)
        _empty_event(1, "recv", sa_id="x", esp_seq=200),  # huge shift
    ]}
    policy = {"window_sizes_allowed": [8],
              "on_replay": "drop", "on_too_old": "drop",
              "on_unknown_sa": "drop", "min_hot_threshold": 0}
    actual = _run_binary_on(tmp_path, sas, events, policy)
    expected = _ref_for(sas, events, policy)
    assert actual["sa_state.json"] == expected["sa_state"]
    state = actual["sa_state.json"]["sas"][0]
    assert state["top"] == 200
    assert state["bitmap"] == "01", (
        f"after huge shift, only bit 0 should be set; got bitmap={state['bitmap']}"
    )


def test_hidden_dataset_within_window_accept_sets_bit(tmp_path: Path) -> None:  # noqa: D401
    """An esp_seq inside the window with bit clear must be accepted and the
    bit set, observable through the bitmap byte. Initial SAs from sas.json
    start with an all-zero bitmap (bit 0 is NOT pre-set for the loaded top).
    """
    sas = {"sas": [{"id": "y", "top": 10, "window_size": 8, "owner": "v"}]}
    events = {"events": [
        _empty_event(0, "recv", sa_id="y", esp_seq=10),  # replay of head (bitmap stays 0)
        _empty_event(1, "recv", sa_id="y", esp_seq=4),   # offset=6, bit 6 clear -> accept
    ]}
    policy = {"window_sizes_allowed": [8],
              "on_replay": "drop", "on_too_old": "drop",
              "on_unknown_sa": "drop", "min_hot_threshold": 0}
    actual = _run_binary_on(tmp_path, sas, events, policy)
    expected = _ref_for(sas, events, policy)
    assert actual["sa_state.json"] == expected["sa_state"]
    state = actual["sa_state.json"]["sas"][0]
    assert state["top"] == 10
    # only bit 6 (esp_seq=4) set: 0x40 (bit 0 was not set because the SA
    # was preloaded; replay of head leaves the bitmap unchanged)
    assert state["bitmap"] == "40", (
        f"expected only bit 6 set -> bitmap='40', got {state['bitmap']!r}"
    )


def test_hidden_dataset_replay_drop_does_not_count_as_accepted(tmp_path: Path) -> None:
    """Under on_replay='drop', a replay does NOT increment accepted; under
    on_replay='log_only' on the same trace, it DOES. This proves the policy
    axis affects per-SA counters."""
    sas = {"sas": [{"id": "r", "top": 5, "window_size": 8, "owner": "u"}]}
    events = {"events": [
        _empty_event(0, "recv", sa_id="r", esp_seq=5),  # replay of head
        _empty_event(1, "recv", sa_id="r", esp_seq=5),  # replay
        _empty_event(2, "recv", sa_id="r", esp_seq=5),  # replay
    ]}
    drop_policy = {"window_sizes_allowed": [8],
                   "on_replay": "drop", "on_too_old": "drop",
                   "on_unknown_sa": "drop", "min_hot_threshold": 0}
    log_policy = dict(drop_policy)
    log_policy["on_replay"] = "log_only"

    drop_actual = _run_binary_on(tmp_path / "drop", sas, events, drop_policy)
    log_actual = _run_binary_on(tmp_path / "log", sas, events, log_policy)
    drop_expected = _ref_for(sas, events, drop_policy)
    log_expected = _ref_for(sas, events, log_policy)

    # 1. Reference proves the trace separates the two axes
    assert drop_expected["sa_state"]["sas"][0]["accepted"] == 0
    assert log_expected["sa_state"]["sas"][0]["accepted"] == 3
    # 2. Binary outputs match reference at each axis value
    assert drop_actual["sa_state.json"] == drop_expected["sa_state"]
    assert log_actual["sa_state.json"] == log_expected["sa_state"]
    assert drop_actual["sa_state.json"]["sas"][0]["replays"] == 3, (
        "all three replays must still count toward the per-SA replays counter "
        "regardless of on_replay action"
    )
    assert log_actual["sa_state.json"]["sas"][0]["replays"] == 3


def test_hidden_dataset_too_old_drop_vs_log(tmp_path: Path) -> None:
    """on_too_old='drop' vs 'log_only' produce observably different
    accepted counters."""
    sas = {"sas": [{"id": "r", "top": 100, "window_size": 8, "owner": "u"}]}
    events = {"events": [
        _empty_event(0, "recv", sa_id="r", esp_seq=1),  # offset=99 >= 8: too_old
        _empty_event(1, "recv", sa_id="r", esp_seq=2),  # too_old
    ]}
    drop_policy = {"window_sizes_allowed": [8],
                   "on_replay": "drop", "on_too_old": "drop",
                   "on_unknown_sa": "drop", "min_hot_threshold": 0}
    log_policy = dict(drop_policy)
    log_policy["on_too_old"] = "log_only"

    drop_actual = _run_binary_on(tmp_path / "drop", sas, events, drop_policy)
    log_actual = _run_binary_on(tmp_path / "log", sas, events, log_policy)
    drop_expected = _ref_for(sas, events, drop_policy)
    log_expected = _ref_for(sas, events, log_policy)

    assert drop_expected["sa_state"]["sas"][0]["accepted"] == 0
    assert log_expected["sa_state"]["sas"][0]["accepted"] == 2
    assert drop_actual["sa_state.json"] == drop_expected["sa_state"]
    assert log_actual["sa_state.json"] == log_expected["sa_state"]
    assert drop_actual["sa_state.json"]["sas"][0]["too_old"] == 2
    assert log_actual["sa_state.json"]["sas"][0]["too_old"] == 2


def test_hidden_dataset_unknown_sa_drop_vs_create_passive(tmp_path: Path) -> None:
    """on_unknown_sa='drop' yields zero new SAs and one unknown_drop;
    'create_passive' creates a passive SA and accepts the packet."""
    sas = {"sas": []}
    events = {"events": [
        _empty_event(0, "recv", sa_id="newbie", esp_seq=42),
    ]}
    drop_policy = {"window_sizes_allowed": [8],
                   "on_replay": "drop", "on_too_old": "drop",
                   "on_unknown_sa": "drop", "min_hot_threshold": 0}
    pass_policy = dict(drop_policy)
    pass_policy["on_unknown_sa"] = "create_passive"

    drop_actual = _run_binary_on(tmp_path / "drop", sas, events, drop_policy)
    pass_actual = _run_binary_on(tmp_path / "pass", sas, events, pass_policy)
    drop_expected = _ref_for(sas, events, drop_policy)
    pass_expected = _ref_for(sas, events, pass_policy)

    assert drop_expected["summary"]["drop_unknown_sa"] == 1
    assert drop_expected["summary"]["passive_created_count"] == 0
    assert drop_expected["summary"]["active_sa_count"] == 0
    assert pass_expected["summary"]["drop_unknown_sa"] == 0
    assert pass_expected["summary"]["passive_created_count"] == 1
    assert pass_expected["summary"]["active_sa_count"] == 1

    assert drop_actual["summary.json"] == drop_expected["summary"]
    assert pass_actual["summary.json"] == pass_expected["summary"]

    drop_pd = drop_actual["packet_decisions.json"]["decisions"]
    pass_pd = pass_actual["packet_decisions.json"]["decisions"]
    assert drop_pd[0]["decision"] == "unknown_drop"
    assert drop_pd[0]["passive_created"] is False
    assert pass_pd[0]["decision"] == "accept_passive"
    assert pass_pd[0]["passive_created"] is True
    assert pass_pd[0]["diagnostic"] == "N_PASSIVE_CREATED"
    assert pass_actual["sa_state.json"]["sas"][0]["owner"] == "passive"


def test_hidden_dataset_rekey_resets_window_keeps_counters(tmp_path: Path) -> None:
    """rekey resets top to 0 and bitmap to all-zero, increments rekeys, but
    leaves recv_total/accepted/replays/too_old as-is."""
    sas = {"sas": [{"id": "r", "top": 100, "window_size": 8, "owner": "u"}]}
    events = {"events": [
        _empty_event(0, "recv", sa_id="r", esp_seq=100),  # replay of head -> replays=1
        _empty_event(1, "rekey", sa_id="r", window_size=16),
        _empty_event(2, "recv", sa_id="r", esp_seq=5),    # accept after rekey
    ]}
    policy = {"window_sizes_allowed": [8, 16],
              "on_replay": "drop", "on_too_old": "drop",
              "on_unknown_sa": "drop", "min_hot_threshold": 0}
    actual = _run_binary_on(tmp_path, sas, events, policy)
    expected = _ref_for(sas, events, policy)
    assert actual["sa_state.json"] == expected["sa_state"]
    state = actual["sa_state.json"]["sas"][0]
    assert state["top"] == 5
    assert state["window_size"] == 16
    assert state["rekeys"] == 1
    assert state["replays"] == 1, (
        "rekey must NOT reset the replays counter (lifetime per-SA counter)"
    )
    assert state["recv_total"] == 2, (
        "rekey must NOT reset the recv_total counter"
    )


def test_hidden_dataset_id_not_reusable_after_delete(tmp_path: Path) -> None:
    """An SA id that has been observed cannot be re-added even after
    delete_sa removes the live entry."""
    sas = {"sas": [{"id": "x", "top": 0, "window_size": 8, "owner": "u"}]}
    events = {"events": [
        _empty_event(0, "delete_sa", sa_id="x"),
        _empty_event(1, "add_sa", sa_id="x", top=0, window_size=8, owner="z"),
    ]}
    policy = {"window_sizes_allowed": [8],
              "on_replay": "drop", "on_too_old": "drop",
              "on_unknown_sa": "drop", "min_hot_threshold": 0}
    actual = _run_binary_on(tmp_path, sas, events, policy)
    expected = _ref_for(sas, events, policy)
    assert actual["summary.json"] == expected["summary"]
    assert actual["summary.json"]["add_sa_failures"] == 1, (
        "re-adding a deleted SA id must count as an add_sa failure"
    )
    assert actual["summary.json"]["active_sa_count"] == 0


def test_hidden_dataset_min_hot_threshold_filters_hot_sas(tmp_path: Path) -> None:
    """min_hot_threshold gates hot_sas: SAs with replays+too_old below
    the threshold are NOT listed."""
    sas = {"sas": [
        {"id": "a", "top": 5, "window_size": 8, "owner": "u"},
        {"id": "b", "top": 5, "window_size": 8, "owner": "u"},
    ]}
    events = {"events": [
        _empty_event(0, "recv", sa_id="a", esp_seq=5),
        _empty_event(1, "recv", sa_id="b", esp_seq=5),
        _empty_event(2, "recv", sa_id="b", esp_seq=5),
        _empty_event(3, "recv", sa_id="b", esp_seq=5),
    ]}
    low_policy = {"window_sizes_allowed": [8],
                  "on_replay": "drop", "on_too_old": "drop",
                  "on_unknown_sa": "drop", "min_hot_threshold": 1}
    high_policy = dict(low_policy)
    high_policy["min_hot_threshold"] = 3

    low_actual = _run_binary_on(tmp_path / "low", sas, events, low_policy)
    high_actual = _run_binary_on(tmp_path / "high", sas, events, high_policy)
    low_expected = _ref_for(sas, events, low_policy)
    high_expected = _ref_for(sas, events, high_policy)

    low_ids = [h["id"] for h in low_expected["summary"]["hot_sas"]]
    high_ids = [h["id"] for h in high_expected["summary"]["hot_sas"]]
    assert low_ids == ["b", "a"], f"low policy hot_sas ids: {low_ids}"
    assert high_ids == ["b"], f"high policy hot_sas ids: {high_ids}"

    assert low_actual["summary.json"] == low_expected["summary"]
    assert high_actual["summary.json"] == high_expected["summary"]


def test_hidden_dataset_determinism_two_runs_byte_identical(tmp_path: Path) -> None:
    """Two runs of the binary on the same /app/data inputs into different
    output directories must produce byte-identical files."""
    in_dir = tmp_path / "data"
    in_dir.mkdir()
    for src in (SAS_PATH, EVENTS_PATH, POLICY_PATH):
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
    for fname in ("sa_state.json", "packet_decisions.json",
                  "replay_log.json", "summary.json"):
        a = (out_a / fname).read_bytes()
        b = (out_b / fname).read_bytes()
        assert a == b, (
            f"{fname} differs between two runs on identical input; "
            "binary is non-deterministic"
        )


# ---------------------------------------------------------------------------
# Anti-tampering: /app/data must be untouched by the binary
# ---------------------------------------------------------------------------


def _snapshot_data_tree() -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for p in sorted(DATA_DIR.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(DATA_DIR))
            snapshot[rel] = sha256_of(p)
    return snapshot


def test_data_dir_tree_unchanged_after_run(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The full file tree under /app/data must be byte-identical before and
    after the binary runs."""
    assert binary_run_outputs["returncode"] == 0
    after = _snapshot_data_tree()
    expected_files = set(EXPECTED_INPUT_HASHES.keys())
    expected_rel = {str(p.relative_to(DATA_DIR)) for p in expected_files}
    extra = set(after.keys()) - expected_rel
    assert not extra, (
        f"binary created extra files under /app/data: {sorted(extra)}"
    )
    missing = expected_rel - set(after.keys())
    assert not missing, (
        f"binary removed files from /app/data: {sorted(missing)}"
    )
    for path, expected in EXPECTED_INPUT_HASHES.items():
        rel = str(path.relative_to(DATA_DIR))
        assert after[rel] == expected, (
            f"input file {path} was modified by the binary"
        )


def test_input_hashes_unchanged_after_run(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Re-hash inputs after the binary runs to catch transient mutations."""
    assert binary_run_outputs["returncode"] == 0
    for path, expected in EXPECTED_INPUT_HASHES.items():
        actual = sha256_of(path)
        assert actual == expected, (
            f"after-run sha256 of {path} is {actual}; expected {expected}"
        )


# ---------------------------------------------------------------------------
# Malformed-input tests (instruction.md mandates non-zero exit on these)
# ---------------------------------------------------------------------------


_VALID_POLICY_TEXT = json.dumps({
    "window_sizes_allowed": [8],
    "on_replay": "drop",
    "on_too_old": "drop",
    "on_unknown_sa": "drop",
    "min_hot_threshold": 0,
})

_VALID_SAS_TEXT = json.dumps({
    "sas": [{"id": "s0", "top": 0, "window_size": 8, "owner": "u"}],
})

_VALID_EVENTS_TEXT = json.dumps({"events": []})


def _malformed_run(tmp_path: Path,
                   sas_text: str | None,
                   events_text: str | None,
                   policy_text: str | None) -> subprocess.CompletedProcess[str]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    if sas_text is not None:
        (in_dir / "sas.json").write_text(sas_text, encoding="utf-8")
    if events_text is not None:
        (in_dir / "events.json").write_text(events_text, encoding="utf-8")
    if policy_text is not None:
        (in_dir / "policy.json").write_text(policy_text, encoding="utf-8")
    return subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=60,
    )


def _assert_no_valid_outputs(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    if not out_dir.exists():
        return
    expected_names = {"sa_state.json", "packet_decisions.json",
                      "replay_log.json", "summary.json"}
    present = {p.name for p in out_dir.iterdir() if p.is_file()}
    if expected_names.issubset(present):
        for name in expected_names:
            try:
                json.loads((out_dir / name).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return
        raise AssertionError(
            "binary produced a complete, JSON-parsable output set despite "
            f"malformed input; outputs={sorted(present)}"
        )


def test_binary_rejects_malformed_json_syntax(tmp_path: Path) -> None:
    proc = _malformed_run(
        tmp_path,
        sas_text="{not valid json,",
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_missing_required_fields(tmp_path: Path) -> None:
    bad_sas = json.dumps({
        "sas": [{"id": "s0", "owner": "u", "window_size": 8}],  # missing top
    })
    proc = _malformed_run(
        tmp_path,
        sas_text=bad_sas,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_wrong_value_types(tmp_path: Path) -> None:
    bad_sas = json.dumps({
        "sas": [{"id": "s0", "top": "not-an-integer",
                 "window_size": 8, "owner": "u"}],
    })
    proc = _malformed_run(
        tmp_path,
        sas_text=bad_sas,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_non_dense_seq(tmp_path: Path) -> None:
    bad_events = json.dumps({"events": [
        _empty_event(0, "delete_sa", sa_id="s0"),
        _empty_event(5, "delete_sa", sa_id="s0"),
    ]})
    proc = _malformed_run(
        tmp_path,
        sas_text=_VALID_SAS_TEXT,
        events_text=bad_events,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_zero_esp_seq(tmp_path: Path) -> None:
    bad_events = json.dumps({"events": [
        _empty_event(0, "recv", sa_id="s0", esp_seq=0),
    ]})
    proc = _malformed_run(
        tmp_path,
        sas_text=_VALID_SAS_TEXT,
        events_text=bad_events,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_negative_esp_seq(tmp_path: Path) -> None:
    """Instruction.md explicitly states `recv` with `esp_seq <= 0`
    (including negatives) is malformed."""
    bad_events = json.dumps({"events": [
        _empty_event(0, "recv", sa_id="s0", esp_seq=-7),
    ]})
    proc = _malformed_run(
        tmp_path,
        sas_text=_VALID_SAS_TEXT,
        events_text=bad_events,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_duplicate_initial_sa(tmp_path: Path) -> None:
    bad_sas = json.dumps({"sas": [
        {"id": "dup", "top": 0, "window_size": 8, "owner": "u"},
        {"id": "dup", "top": 0, "window_size": 8, "owner": "u"},
    ]})
    proc = _malformed_run(
        tmp_path,
        sas_text=bad_sas,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_initial_sa_with_disallowed_window(tmp_path: Path) -> None:
    """Initial sas.json must use only window_sizes from
    policy.window_sizes_allowed; otherwise the input is malformed."""
    bad_sas = json.dumps({"sas": [
        {"id": "s0", "top": 0, "window_size": 99, "owner": "u"},
    ]})
    proc = _malformed_run(
        tmp_path,
        sas_text=bad_sas,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_missing_input_files(tmp_path: Path) -> None:
    proc = _malformed_run(
        tmp_path,
        sas_text=_VALID_SAS_TEXT,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=None,
    )
    assert proc.returncode != 0
    _assert_no_valid_outputs(tmp_path)


# ---------------------------------------------------------------------------
# Property-based / randomized hidden datasets
# ---------------------------------------------------------------------------


def _gen_random_dataset(seed: int, *,
                        n_initial: int = 4,
                        n_events: int = 30,
                        on_replay: str = "log_only",
                        on_too_old: str = "log_only",
                        on_unknown_sa: str = "create_passive",
                        ) -> tuple[dict, dict, dict]:
    """Deterministic pseudo-random dataset generator. Returns valid
    (sas, events, policy) triple."""
    import random
    rng = random.Random(seed)
    allowed_ws = [8, 16, 32, 64]
    initial: list[dict] = []
    used_ids: set[str] = set()
    for i in range(n_initial):
        sid = f"sa{i}"
        used_ids.add(sid)
        initial.append({
            "id": sid,
            "top": rng.randint(0, 50),
            "window_size": rng.choice(allowed_ws),
            "owner": rng.choice(["u", "v", "w"]),
        })

    events: list[dict] = []
    next_id_n = n_initial
    for seq in range(n_events):
        op = rng.choice(["recv", "recv", "recv", "recv",
                         "add_sa", "delete_sa", "rekey"])
        ev = _empty_event(seq, op)
        if op == "recv":
            ev["sa_id"] = rng.choice(sorted(used_ids) + ["ghost"])
            ev["esp_seq"] = rng.randint(1, 200)
        elif op == "add_sa":
            sid = f"sa{next_id_n}"
            next_id_n += 1
            ev["sa_id"] = sid
            ev["top"] = rng.randint(0, 100)
            ev["window_size"] = rng.choice(allowed_ws)
            ev["owner"] = rng.choice(["x", "y"])
            used_ids.add(sid)
        elif op == "delete_sa":
            ev["sa_id"] = rng.choice(sorted(used_ids) + ["ghost"])
        elif op == "rekey":
            ev["sa_id"] = rng.choice(sorted(used_ids) + ["ghost"])
            ev["window_size"] = rng.choice(allowed_ws)
        events.append(ev)

    sas_doc = {"sas": initial}
    events_doc = {"events": events}
    policy_doc = {
        "window_sizes_allowed": allowed_ws,
        "on_replay":         on_replay,
        "on_too_old":        on_too_old,
        "on_unknown_sa":     on_unknown_sa,
        "min_hot_threshold": rng.randint(0, 2),
    }
    return sas_doc, events_doc, policy_doc


@pytest.mark.parametrize("seed", [101, 202, 303, 404, 505])
def test_randomized_property_dataset_against_reference(
    tmp_path: Path, seed: int,
) -> None:
    """Generate a fresh pseudo-random dataset at test time and assert the
    binary's outputs match the live reference."""
    sas, events, policy = _gen_random_dataset(seed)
    actual = _run_binary_on(tmp_path, sas, events, policy)
    expected = _ref_for(sas, events, policy)
    for name, key in (("sa_state.json", "sa_state"),
                      ("packet_decisions.json", "packet_decisions"),
                      ("replay_log.json", "replay_log"),
                      ("summary.json", "summary")):
        assert actual[name] == expected[key], (
            f"seed={seed}: binary {name} differs from reference"
        )


@pytest.mark.parametrize("seed", [11, 22, 33])
def test_randomized_property_dataset_with_drop_policies(
    tmp_path: Path, seed: int,
) -> None:
    """Same as above but pinned to drop policies for replay/too_old/unknown
    to specifically exercise the drop branches."""
    sas, events, policy = _gen_random_dataset(
        seed, on_replay="drop", on_too_old="drop", on_unknown_sa="drop")
    actual = _run_binary_on(tmp_path, sas, events, policy)
    expected = _ref_for(sas, events, policy)
    for name, key in (("sa_state.json", "sa_state"),
                      ("packet_decisions.json", "packet_decisions"),
                      ("summary.json", "summary")):
        assert actual[name] == expected[key], (
            f"seed={seed} drop: binary {name} differs from reference"
        )
