"""Verifier suite for  (typescript)."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
BUILD_DIR = Path("/app/build")
BINARY_PATH = BUILD_DIR / "bfreplay"

KEYS_PATH = DATA_DIR / "keys.json"
EVENTS_PATH = DATA_DIR / "events.json"
POLICY_PATH = DATA_DIR / "policy.json"

FILTER_STATE_PATH = OUT_DIR / "filter_state.json"
QUERY_LOG_PATH = OUT_DIR / "query_log.json"
EVENT_LOG_PATH = OUT_DIR / "event_log.json"
STATS_DUMPS_PATH = OUT_DIR / "stats_dumps.json"
SUMMARY_PATH = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    FILTER_STATE_PATH,
    QUERY_LOG_PATH,
    EVENT_LOG_PATH,
    STATS_DUMPS_PATH,
    SUMMARY_PATH,
)


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


FNV1A_A_OFFSET = 0xCBF29CE484222325
FNV1A_B_OFFSET = 0x84222325CBF29CE4
FNV1A_PRIME = 0x100000001B3
U64_MASK = (1 << 64) - 1


def _fnv1a_64(seed: int, key: str) -> int:
    h = seed
    for b in key.encode("utf-8"):
        h ^= b
        h = (h * FNV1A_PRIME) & U64_MASK
    return h


def positions(key: str, m: int, k: int) -> list[int]:
    h_a = _fnv1a_64(FNV1A_A_OFFSET, key)
    h_b = _fnv1a_64(FNV1A_B_OFFSET, key)
    return [(h_a + i * h_b) % m for i in range(k)]


def simulate(keys: list[str], events: list[dict], policy: dict) -> dict[str, Any]:
    m = policy["m"]
    k = policy["k"]
    counter_bits = policy["counter_bits"]
    saturation_action = policy["saturation_action"]
    remove_below_zero_action = policy["remove_below_zero_action"]

    counters = [0] * m
    multiset_count: dict[str, int] = {key: 0 for key in keys}

    stats = {
        "clamped_remove": 0,
        "clears": 0,
        "rejected_negative": 0,
        "rejected_saturate": 0,
        "resizes": 0,
        "successful_adds": 0,
        "successful_queries": 0,
        "successful_removes": 0,
    }

    queries: list[dict] = []
    event_log: list[dict] = []
    dumps: list[dict] = []
    fn_count = fp_count = tn_count = tp_count = 0
    queries_per_key: dict[str, int] = {}

    def saturate_max() -> int:
        return (1 << counter_bits) - 1

    def do_add(key: str) -> str:
        nonlocal counters
        positions_for_key = positions(key, m, k)
        max_v = saturate_max()
        if saturation_action == "reject":
            if any(counters[p] == max_v for p in positions_for_key):
                stats["rejected_saturate"] += 1
                return "D_REJECTED_SATURATE"
            for p in positions_for_key:
                counters[p] += 1
            multiset_count[key] = multiset_count.get(key, 0) + 1
            stats["successful_adds"] += 1
            return "D_OK_ADD"
        else:
            for p in positions_for_key:
                if counters[p] < max_v:
                    counters[p] += 1
            multiset_count[key] = multiset_count.get(key, 0) + 1
            stats["successful_adds"] += 1
            return "D_OK_ADD"

    def do_remove(key: str) -> str:
        nonlocal counters
        positions_for_key = positions(key, m, k)
        if remove_below_zero_action == "reject":
            if any(counters[p] == 0 for p in positions_for_key):
                stats["rejected_negative"] += 1
                return "D_REJECTED_NEGATIVE"
            for p in positions_for_key:
                counters[p] -= 1
            if multiset_count.get(key, 0) > 0:
                multiset_count[key] -= 1
            stats["successful_removes"] += 1
            return "D_OK_REMOVE"
        else:
            any_clamp = any(counters[p] == 0 for p in positions_for_key)
            for p in positions_for_key:
                if counters[p] > 0:
                    counters[p] -= 1
            if multiset_count.get(key, 0) > 0:
                multiset_count[key] -= 1
            if any_clamp:
                stats["clamped_remove"] += 1
                return "D_CLAMPED_REMOVE"
            stats["successful_removes"] += 1
            return "D_OK_REMOVE"

    def do_query(seq: int, key: str) -> None:
        nonlocal fn_count, fp_count, tn_count, tp_count
        positions_for_key = positions(key, m, k)
        predicted = all(counters[p] > 0 for p in positions_for_key)
        actual = multiset_count.get(key, 0) > 0
        if predicted and actual:
            outcome = "tp"
            tp_count += 1
        elif predicted and not actual:
            outcome = "fp"
            fp_count += 1
        elif not predicted and not actual:
            outcome = "tn"
            tn_count += 1
        else:
            outcome = "fn"
            fn_count += 1
        queries.append({
            "actual": actual,
            "key": key,
            "outcome": outcome,
            "predicted": predicted,
            "seq": seq,
        })
        stats["successful_queries"] += 1
        queries_per_key[key] = queries_per_key.get(key, 0) + 1

    def do_clear() -> None:
        nonlocal counters
        counters = [0] * m
        for kk in list(multiset_count.keys()):
            multiset_count[kk] = 0
        stats["clears"] += 1

    def do_resize(new_m: int, new_k: int) -> None:
        nonlocal counters, m, k
        old_multiset = dict(multiset_count)
        m = new_m
        k = new_k
        counters = [0] * m
        for kk in list(multiset_count.keys()):
            multiset_count[kk] = 0
        for key in keys:
            n = old_multiset.get(key, 0)
            for _ in range(n):
                do_add(key)
        stats["resizes"] += 1

    def do_dump_stats(seq: int) -> None:
        max_v = saturate_max()
        non_zero = sum(1 for c in counters if c > 0)
        sat = sum(1 for c in counters if c == max_v)
        total = sum(counters)
        dumps.append({
            "counter_bits": counter_bits,
            "k": k,
            "m": m,
            "non_zero_slots": non_zero,
            "saturated_slots": sat,
            "seq": seq,
            "stats": dict(stats),
            "total_count": total,
        })

    for ev in events:
        seq = ev["seq"]
        op = ev["op"]
        if op == "add":
            key = keys[ev["key_idx"]]
            code = do_add(key)
            event_log.append({"code": code, "key": key, "op": op, "seq": seq})
        elif op == "remove":
            key = keys[ev["key_idx"]]
            code = do_remove(key)
            event_log.append({"code": code, "key": key, "op": op, "seq": seq})
        elif op == "query":
            key = keys[ev["key_idx"]]
            do_query(seq, key)
            event_log.append({"code": "D_OK_QUERY", "key": key, "op": op, "seq": seq})
        elif op == "clear":
            do_clear()
            event_log.append({"code": "D_OK_CLEAR", "key": None, "op": op, "seq": seq})
        elif op == "resize":
            do_resize(ev["new_m"], ev["new_k"])
            event_log.append({"code": "D_OK_RESIZE", "key": None, "op": op, "seq": seq})
        elif op == "dump_stats":
            do_dump_stats(seq)
            event_log.append({"code": "D_OK_DUMP", "key": None, "op": op, "seq": seq})
        else:
            raise ValueError(f"unknown op: {op}")

    filter_state = {
        "counter_bits": counter_bits,
        "counters": counters,
        "k": k,
        "m": m,
        "stats": dict(stats),
    }
    query_log = {"queries": queries}
    event_log_obj = {"events": event_log}
    stats_dumps = {"dumps": dumps}

    hot_keys = sorted(
        ({"key": kk, "queries": v} for kk, v in queries_per_key.items()),
        key=lambda d: (-d["queries"], d["key"]),
    )

    summary = {
        "clamped_remove": stats["clamped_remove"],
        "clears": stats["clears"],
        "dumps_total": len(dumps),
        "events_total": len(events),
        "fn_count": fn_count,
        "fp_count": fp_count,
        "hot_keys": hot_keys,
        "queries_total": len(queries),
        "rejected_negative": stats["rejected_negative"],
        "rejected_saturate": stats["rejected_saturate"],
        "resizes": stats["resizes"],
        "successful_adds": stats["successful_adds"],
        "successful_queries": stats["successful_queries"],
        "successful_removes": stats["successful_removes"],
        "tn_count": tn_count,
        "tp_count": tp_count,
    }

    return {
        "filter_state": filter_state,
        "query_log": query_log,
        "event_log": event_log_obj,
        "stats_dumps": stats_dumps,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def input_data() -> dict[str, Any]:
    return {
        "keys": load_json(KEYS_PATH)["keys"],
        "events": load_json(EVENTS_PATH)["events"],
        "policy": load_json(POLICY_PATH),
    }


@pytest.fixture(scope="session")
def expected_outputs(input_data) -> dict[str, Any]:
    return simulate(
        input_data["keys"],
        input_data["events"],
        input_data["policy"],
    )


@pytest.fixture(scope="session")
def precomputed_input_hashes() -> dict[Path, str]:
    return {p: sha256_of(p) for p in (KEYS_PATH, EVENTS_PATH, POLICY_PATH)}


@pytest.fixture(scope="session")
def binary_run_outputs(precomputed_input_hashes) -> dict[Path, Any]:
    """Wipes /app/output and runs the agent binary fresh against
    /app/data, then loads each output document. Subsequent tests use the
    loaded documents."""
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert BINARY_PATH.exists(), f"agent binary missing at {BINARY_PATH}"
    assert BINARY_PATH.stat().st_mode & stat.S_IXUSR, "binary not executable"
    res = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode == 0, (
        f"binary failed: rc={res.returncode}\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    out: dict[Path, Any] = {}
    for p in ALL_OUT_PATHS:
        assert p.exists(), f"missing output: {p}"
        out[p] = load_json(p)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inputs_unchanged(precomputed_input_hashes):
    """All three /app/data/*.json files have the same SHA-256 they did at
    fixture time, proving the binary did not mutate inputs."""
    for p, h in precomputed_input_hashes.items():
        assert sha256_of(p) == h, f"{p} content mutated"


def test_binary_built_and_executable():
    """The agent's compiled binary lives at /app/build/bfreplay and is
    marked executable."""
    assert BINARY_PATH.exists(), f"missing {BINARY_PATH}"
    assert BINARY_PATH.stat().st_mode & stat.S_IXUSR, "binary not executable"






def test_binary_runs_cleanly_and_outputs_are_fresh(binary_run_outputs):
    """A fresh run of the binary against /app/data writes all five outputs."""
    for p in ALL_OUT_PATHS:
        assert p in binary_run_outputs


def test_binary_rejects_wrong_arg_counts():
    """The CLI accepts exactly two positional args; zero, one, and three
    args are all hard rejects."""
    res = subprocess.run([str(BINARY_PATH)], capture_output=True, text=True, timeout=30)
    assert res.returncode != 0
    res = subprocess.run([str(BINARY_PATH), str(DATA_DIR)], capture_output=True, text=True, timeout=30)
    assert res.returncode != 0
    res = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR), "extra"],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_binary_uses_argv_paths_not_hardcoded(tmp_path, input_data):
    """Run the binary with a custom out_dir to prove it doesn't write to a
    hardcoded /app/output. We pass /app/data as input and a temp dir as
    output, then check the temp dir got populated."""
    tmp_out = tmp_path / "altout"
    tmp_out.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(tmp_out)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode == 0, f"binary failed under alt out_dir: {res.stderr}"
    for name in (
        "filter_state.json", "query_log.json", "event_log.json",
        "stats_dumps.json", "summary.json",
    ):
        assert (tmp_out / name).exists(), f"binary did not write {name} to argv[2]"


def test_outputs_strict_json_formatting(binary_run_outputs):
    """Each output is canonical 2-space-indent ASCII JSON with sorted keys
    at every depth and a single trailing newline."""
    for p in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(p)
        assert ok, msg


def test_outputs_are_ascii_at_every_depth(binary_run_outputs):
    """Every output file is ASCII-only after UTF-8 decode."""
    for p in ALL_OUT_PATHS:
        text = p.read_text(encoding="utf-8")
        text.encode("ascii")  # raises if any non-ascii


def test_filter_state_match_reference(binary_run_outputs, expected_outputs):
    """The agent's filter_state.json matches the reference simulator
    document exactly."""
    actual = binary_run_outputs[FILTER_STATE_PATH]
    assert actual == expected_outputs["filter_state"]


def test_query_log_match_reference(binary_run_outputs, expected_outputs):
    """The agent's query_log.json matches the reference simulator output."""
    actual = binary_run_outputs[QUERY_LOG_PATH]
    assert actual == expected_outputs["query_log"]


def test_event_log_match_reference(binary_run_outputs, expected_outputs):
    """The agent's event_log.json matches the reference simulator output."""
    actual = binary_run_outputs[EVENT_LOG_PATH]
    assert actual == expected_outputs["event_log"]


def test_stats_dumps_match_reference(binary_run_outputs, expected_outputs):
    """The agent's stats_dumps.json matches the reference simulator output."""
    actual = binary_run_outputs[STATS_DUMPS_PATH]
    assert actual == expected_outputs["stats_dumps"]


def test_summary_match_reference(binary_run_outputs, expected_outputs):
    """The agent's summary.json matches the reference simulator output."""
    actual = binary_run_outputs[SUMMARY_PATH]
    assert actual == expected_outputs["summary"]


def test_event_log_codes_are_legal(binary_run_outputs):
    """Every event_log entry has a code from the closed catalogue and the
    code is consistent with the op."""
    legal = {
        "D_OK_ADD", "D_REJECTED_SATURATE",
        "D_OK_REMOVE", "D_CLAMPED_REMOVE", "D_REJECTED_NEGATIVE",
        "D_OK_QUERY", "D_OK_CLEAR", "D_OK_RESIZE", "D_OK_DUMP",
    }
    legal_per_op = {
        "add": {"D_OK_ADD", "D_REJECTED_SATURATE"},
        "remove": {"D_OK_REMOVE", "D_CLAMPED_REMOVE", "D_REJECTED_NEGATIVE"},
        "query": {"D_OK_QUERY"},
        "clear": {"D_OK_CLEAR"},
        "resize": {"D_OK_RESIZE"},
        "dump_stats": {"D_OK_DUMP"},
    }
    for e in binary_run_outputs[EVENT_LOG_PATH]["events"]:
        assert e["code"] in legal, e
        assert e["code"] in legal_per_op[e["op"]], e


def test_event_log_seqs_are_dense_and_match_input(binary_run_outputs, input_data):
    """event_log has one entry per input event in seq order. The input
    seqs themselves are strictly ascending and dense starting at 1, and
    event_log must mirror that ordering exactly."""
    log_seqs = [e["seq"] for e in binary_run_outputs[EVENT_LOG_PATH]["events"]]
    in_seqs = [e["seq"] for e in input_data["events"]]
    assert log_seqs == in_seqs
    assert in_seqs == list(range(1, len(in_seqs) + 1)), (
        "input events.json must have a strictly ascending dense seq starting at 1"
    )


def test_query_log_seqs_subset_of_query_events(binary_run_outputs, input_data):
    """query_log carries exactly the seqs of the input `query` events."""
    log_seqs = [q["seq"] for q in binary_run_outputs[QUERY_LOG_PATH]["queries"]]
    in_query_seqs = [e["seq"] for e in input_data["events"] if e["op"] == "query"]
    assert log_seqs == in_query_seqs


def test_query_outcomes_are_consistent(binary_run_outputs):
    """Each query entry's outcome matches the boolean cross-product of
    predicted x actual."""
    table = {
        (True, True): "tp",
        (True, False): "fp",
        (False, False): "tn",
        (False, True): "fn",
    }
    for q in binary_run_outputs[QUERY_LOG_PATH]["queries"]:
        assert table[(q["predicted"], q["actual"])] == q["outcome"], q


def test_filter_state_counters_are_within_bounds(binary_run_outputs):
    """Every counter is in [0, 2^counter_bits - 1] and there are exactly m
    of them."""
    fs = binary_run_outputs[FILTER_STATE_PATH]
    max_v = (1 << fs["counter_bits"]) - 1
    assert len(fs["counters"]) == fs["m"]
    for c in fs["counters"]:
        assert 0 <= c <= max_v, c


def test_summary_consistency_with_other_outputs(binary_run_outputs):
    """summary aggregates agree with the other four outputs."""
    fs = binary_run_outputs[FILTER_STATE_PATH]
    ql = binary_run_outputs[QUERY_LOG_PATH]
    el = binary_run_outputs[EVENT_LOG_PATH]
    sd = binary_run_outputs[STATS_DUMPS_PATH]
    sm = binary_run_outputs[SUMMARY_PATH]
    assert sm["events_total"] == len(el["events"])
    assert sm["queries_total"] == len(ql["queries"])
    assert sm["dumps_total"] == len(sd["dumps"])
    assert sm["successful_adds"] == fs["stats"]["successful_adds"]
    assert sm["successful_removes"] == fs["stats"]["successful_removes"]
    assert sm["successful_queries"] == fs["stats"]["successful_queries"]
    assert sm["rejected_saturate"] == fs["stats"]["rejected_saturate"]
    assert sm["rejected_negative"] == fs["stats"]["rejected_negative"]
    assert sm["clamped_remove"] == fs["stats"]["clamped_remove"]
    assert sm["clears"] == fs["stats"]["clears"]
    assert sm["resizes"] == fs["stats"]["resizes"]
    counts = (
        sum(1 for q in ql["queries"] if q["outcome"] == "tp"),
        sum(1 for q in ql["queries"] if q["outcome"] == "fp"),
        sum(1 for q in ql["queries"] if q["outcome"] == "tn"),
        sum(1 for q in ql["queries"] if q["outcome"] == "fn"),
    )
    assert (sm["tp_count"], sm["fp_count"], sm["tn_count"], sm["fn_count"]) == counts


def test_summary_hot_keys_sorted_correctly(binary_run_outputs):
    """hot_keys is sorted by descending queries, then ascending key."""
    hot = binary_run_outputs[SUMMARY_PATH]["hot_keys"]
    expected = sorted(hot, key=lambda d: (-d["queries"], d["key"]))
    assert hot == expected
    for entry in hot:
        assert entry["queries"] >= 1


def test_dataset_invariants_exercise_branches(input_data, expected_outputs):
    """Sanity check that the visible dataset exercises the interesting
    branches: at least one rejected_saturate or clamped_remove or
    rejected_negative, at least one tp, at least one fp, at least one
    tn, and at least one resize and one clear and one dump."""
    sm = expected_outputs["summary"]
    diagnostics_fired = (
        sm["rejected_saturate"]
        + sm["rejected_negative"]
        + sm["clamped_remove"]
    )
    assert diagnostics_fired > 0, (
        "dataset never exercises the saturate / clamp / reject branches"
    )
    assert sm["tp_count"] > 0
    assert sm["fp_count"] > 0
    assert sm["tn_count"] > 0
    assert sm["resizes"] > 0
    assert sm["clears"] > 0
    assert sm["dumps_total"] > 0


def test_data_dir_tree_unchanged_after_run(precomputed_input_hashes, binary_run_outputs):
    """Re-checks input hashes after the binary has run, catching any
    write to /app/data the binary may have done."""
    for p, h in precomputed_input_hashes.items():
        assert sha256_of(p) == h, f"{p} mutated by binary run"


def test_binary_rejects_missing_input_files(tmp_path):
    """Running against a directory with no JSON files exits non-zero."""
    bad_data = tmp_path / "nodata"
    bad_data.mkdir()
    bad_out = tmp_path / "noout"
    bad_out.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(bad_data), str(bad_out)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_binary_rejects_malformed_json(tmp_path, input_data):
    """Pass a data dir whose policy.json is not valid JSON; the binary
    must exit non-zero rather than producing outputs."""
    bad_data = tmp_path / "baddata"
    bad_data.mkdir()
    (bad_data / "keys.json").write_text(json.dumps({"keys": input_data["keys"]}))
    (bad_data / "events.json").write_text(json.dumps({"events": input_data["events"]}))
    (bad_data / "policy.json").write_text("{not valid json")
    bad_out = tmp_path / "badout"
    bad_out.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(bad_data), str(bad_out)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def _make_data_dir(tmp_path: Path, name: str, keys: list, events: list, policy: dict) -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "keys.json").write_text(json.dumps({"keys": keys}))
    (d / "events.json").write_text(json.dumps({"events": events}))
    (d / "policy.json").write_text(json.dumps(policy))
    return d


def test_binary_rejects_invalid_counter_bits(tmp_path, input_data):
    """A policy with counter_bits outside {2,3,4,8} is malformed input;
    the binary must exit non-zero rather than producing outputs."""
    bad_policy = dict(input_data["policy"])
    bad_policy["counter_bits"] = 5
    data_dir = _make_data_dir(
        tmp_path, "data", input_data["keys"], input_data["events"], bad_policy,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(data_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_binary_rejects_unknown_hash_family(tmp_path, input_data):
    """A policy whose hash_family is not the literal
    'fnv1a_double_hashing' is malformed input; reject."""
    bad_policy = dict(input_data["policy"])
    bad_policy["hash_family"] = "murmur3_double_hashing"
    data_dir = _make_data_dir(
        tmp_path, "data", input_data["keys"], input_data["events"], bad_policy,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(data_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_binary_rejects_unknown_op(tmp_path, input_data):
    """An events.json with an op outside the closed catalogue is
    malformed input; reject without writing outputs."""
    bad_events = [{"seq": 1, "op": "frobnicate", "key_idx": 0}]
    data_dir = _make_data_dir(
        tmp_path, "data", input_data["keys"], bad_events, input_data["policy"],
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(data_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_binary_rejects_out_of_range_key_idx(tmp_path, input_data):
    """A key_idx outside [0, len(keys)) is malformed input; reject."""
    bad_events = [{"seq": 1, "op": "add", "key_idx": 999999}]
    data_dir = _make_data_dir(
        tmp_path, "data", input_data["keys"], bad_events, input_data["policy"],
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(data_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_binary_rejects_invalid_saturation_action(tmp_path, input_data):
    """saturation_action is a closed enum {"reject","saturate"}; any other
    value is malformed input and the binary must exit non-zero."""
    bad_policy = dict(input_data["policy"])
    bad_policy["saturation_action"] = "wrap"
    data_dir = _make_data_dir(
        tmp_path, "data", input_data["keys"], input_data["events"], bad_policy,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(data_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_binary_rejects_invalid_remove_below_zero_action(tmp_path, input_data):
    """remove_below_zero_action is a closed enum {"reject","clamp"}; any
    other value is malformed input and the binary must exit non-zero."""
    bad_policy = dict(input_data["policy"])
    bad_policy["remove_below_zero_action"] = "negate"
    data_dir = _make_data_dir(
        tmp_path, "data", input_data["keys"], input_data["events"], bad_policy,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(data_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


@pytest.mark.parametrize("bad_field,bad_value", [("m", 0), ("m", -1), ("k", 0), ("k", -3)])
def test_binary_rejects_non_positive_m_or_k(tmp_path, input_data, bad_field, bad_value):
    """The instruction says `m` and `k` are positive integers; non-positive
    values are malformed input and must be rejected before any output is
    written."""
    bad_policy = dict(input_data["policy"])
    bad_policy[bad_field] = bad_value
    data_dir = _make_data_dir(
        tmp_path, "data", input_data["keys"], input_data["events"], bad_policy,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(data_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


@pytest.mark.parametrize("missing_field", ["new_m", "new_k"])
def test_binary_rejects_resize_missing_new_m_or_new_k(tmp_path, input_data, missing_field):
    """A `resize` event must carry both `new_m` and `new_k`; dropping
    either makes the event malformed and the binary must exit non-zero."""
    ev = {"seq": 1, "op": "resize", "new_m": 32, "new_k": 3}
    del ev[missing_field]
    bad_events = [ev]
    data_dir = _make_data_dir(
        tmp_path, "data", input_data["keys"], bad_events, input_data["policy"],
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(data_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


@pytest.mark.parametrize(
    "bad_field,bad_value",
    [("new_m", 0), ("new_m", -1), ("new_k", 0), ("new_k", -3)],
)
def test_binary_rejects_resize_non_positive_new_m_or_new_k(
    tmp_path, input_data, bad_field, bad_value,
):
    """events.md says resize `new_m` and `new_k` are positive integers;
    non-positive values are malformed input and the binary must exit
    non-zero before writing any output."""
    ev = {"seq": 1, "op": "resize", "new_m": 32, "new_k": 3}
    ev[bad_field] = bad_value
    bad_events = [ev]
    data_dir = _make_data_dir(
        tmp_path, "data", input_data["keys"], bad_events, input_data["policy"],
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(data_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_output_dir_contains_only_the_five_documented_files(binary_run_outputs):
    """The instruction names exactly five output files. After the
    canonical run, /app/output must contain those five files and no
    extras (no scratch/temp files, no subdirectories)."""
    expected = {
        "filter_state.json", "query_log.json", "event_log.json",
        "stats_dumps.json", "summary.json",
    }
    actual = {p.name for p in OUT_DIR.iterdir()}
    assert actual == expected, (
        f"output dir has unexpected files. expected={expected}, actual={actual}"
    )


@pytest.mark.parametrize(
    "bad_seqs",
    [
        [2, 3, 4],          # does not start at 1
        [1, 1, 2],          # not strictly ascending (duplicate)
        [1, 3, 4],          # gap (not dense)
        [1, 2, 5],          # gap later
        [3, 2, 1],          # reversed
    ],
)
def test_binary_rejects_malformed_event_seq(tmp_path, input_data, bad_seqs):
    """The instruction says event seqs are strictly ascending and dense
    starting at 1. Inputs whose seq sequence violates that invariant are
    malformed and the binary must exit non-zero."""
    bad_events = [{"seq": s, "op": "query", "key_idx": 0} for s in bad_seqs]
    data_dir = _make_data_dir(
        tmp_path, "data", input_data["keys"], bad_events, input_data["policy"],
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = subprocess.run(
        [str(BINARY_PATH), str(data_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


SCHEMA_DIR = Path("/app/schemas")
_SCHEMA_FOR_OUTPUT = {
    FILTER_STATE_PATH: SCHEMA_DIR / "filter_state.schema.json",
    QUERY_LOG_PATH: SCHEMA_DIR / "query_log.schema.json",
    EVENT_LOG_PATH: SCHEMA_DIR / "event_log.schema.json",
    STATS_DUMPS_PATH: SCHEMA_DIR / "stats_dumps.schema.json",
    SUMMARY_PATH: SCHEMA_DIR / "summary.schema.json",
}


def _check_against_schema(value: Any, schema: dict, path: str = "$") -> list[str]:
    """Lightweight JSON-Schema subset checker: handles `type`, `required`,
    `properties`, `additionalProperties`, `items`, `enum`, `minimum`. We
    avoid pulling in `jsonschema` so that the verifier image doesn't need
    extra Python deps; the schemas /app/schemas/ ship use only this
    subset, which is enough to enforce the documented output shapes."""
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object, got {type(value).__name__}"]
        required = schema.get("required", [])
        for k in required:
            if k not in value:
                errors.append(f"{path}: missing required key '{k}'")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for k in value.keys():
                if k not in props:
                    errors.append(f"{path}: unexpected extra key '{k}'")
        for k, v in value.items():
            if k in props:
                errors.extend(_check_against_schema(v, props[k], f"{path}.{k}"))
    elif expected_type == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array, got {type(value).__name__}"]
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                errors.extend(_check_against_schema(item, item_schema, f"{path}[{i}]"))
    elif expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{path}: expected integer, got {type(value).__name__}")
        else:
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{path}: value {value} < minimum {schema['minimum']}")
            if "enum" in schema and value not in schema["enum"]:
                errors.append(f"{path}: value {value} not in enum {schema['enum']}")
    elif expected_type == "string":
        if not isinstance(value, str):
            errors.append(f"{path}: expected string, got {type(value).__name__}")
        elif "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: value '{value}' not in enum {schema['enum']}")
    elif expected_type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean, got {type(value).__name__}")
    return errors


@pytest.mark.parametrize(
    "out_path",
    list(_SCHEMA_FOR_OUTPUT.keys()),
    ids=lambda p: p.name,
)
def test_outputs_conform_to_published_schemas(binary_run_outputs, out_path):
    """Each agent-produced output validates against the published JSON
    Schema in /app/schemas/. The instruction declares those schemas
    normative for the output shape."""
    schema_path = _SCHEMA_FOR_OUTPUT[out_path]
    assert schema_path.exists(), f"schema missing: {schema_path}"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = _check_against_schema(binary_run_outputs[out_path], schema)
    assert not errors, f"schema violations for {out_path.name}:\n  " + "\n  ".join(errors)


def test_input_event_seqs_are_strictly_monotonic(input_data):
    """The instruction guarantees the input event log is strictly
    ascending (and dense from 1). This is a property of the visible
    dataset itself: assert it directly so that, if the dataset ever drifts
    away from the documented invariant, the verifier flags it."""
    seqs = [e["seq"] for e in input_data["events"]]
    assert all(b > a for a, b in zip(seqs, seqs[1:])), (
        "input events.json seqs are not strictly increasing"
    )
    assert seqs == list(range(1, len(seqs) + 1)), (
        "input events.json seqs are not dense starting at 1"
    )


def test_event_log_codes_in_documented_catalogue(binary_run_outputs, input_data):
    """Every code produced lies in the documented closed catalogue. We
    don't require all nine codes to appear (the canonical dataset's
    policy enums (`saturation_action`, `remove_below_zero_action`) gate
    which subset is reachable), only that produced codes are documented
    and that, given the chosen policy enums, each catalogue subset is
    consistent with the per-op legal mapping."""
    documented = {
        "D_OK_ADD", "D_REJECTED_SATURATE",
        "D_OK_REMOVE", "D_CLAMPED_REMOVE", "D_REJECTED_NEGATIVE",
        "D_OK_QUERY", "D_OK_CLEAR", "D_OK_RESIZE", "D_OK_DUMP",
    }
    seen = {e["code"] for e in binary_run_outputs[EVENT_LOG_PATH]["events"]}
    assert seen.issubset(documented), f"undocumented codes produced: {seen - documented}"
    sat_action = input_data["policy"]["saturation_action"]
    rm_action = input_data["policy"]["remove_below_zero_action"]
    if sat_action == "saturate":
        assert "D_REJECTED_SATURATE" not in seen, (
            "policy says saturate yet the binary produced D_REJECTED_SATURATE"
        )
    if rm_action == "clamp":
        assert "D_REJECTED_NEGATIVE" not in seen, (
            "policy says clamp yet the binary produced D_REJECTED_NEGATIVE"
        )
    if rm_action == "reject":
        assert "D_CLAMPED_REMOVE" not in seen, (
            "policy says reject yet the binary produced D_CLAMPED_REMOVE"
        )


def test_determinism_two_runs_byte_identical(tmp_path):
    """Run the binary twice into two different out-dirs and check the
    five output files are byte-identical."""
    out_a = tmp_path / "a"
    out_a.mkdir()
    out_b = tmp_path / "b"
    out_b.mkdir()
    for out in (out_a, out_b):
        res = subprocess.run(
            [str(BINARY_PATH), str(DATA_DIR), str(out)],
            capture_output=True, text=True, timeout=60,
        )
        assert res.returncode == 0
    for name in (
        "filter_state.json", "query_log.json", "event_log.json",
        "stats_dumps.json", "summary.json",
    ):
        a = (out_a / name).read_bytes()
        b = (out_b / name).read_bytes()
        assert a == b, f"{name} differs between two runs"


