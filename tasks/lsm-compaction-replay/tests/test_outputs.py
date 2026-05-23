"""Verifier suite for Replay (java)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import os
from pathlib import Path
from typing import Any

import pytest



def _java_cmd(data_dir: Path, out_dir: Path) -> list[str]:
    """Build argv for the Java entry class."""
    return [
        "java",
        "-cp",
        f"{BUILD_DIR}:{GSON_CP}",
        JAVA_CLASS,
        str(data_dir),
        str(out_dir),
    ]




SOURCE_SUFFIXES = (".java",)
BUILD_SCRIPT_SUFFIXES = (".mk", ".cmake", ".sh", ".bash")
BUILD_SCRIPT_NAMES = {"Makefile", "GNUmakefile", "makefile",
                      "CMakeLists.txt", "build.ninja"}


def _src_files() -> list[Path]:
    out: list[Path] = []
    for root in (Path("/app/src"),):
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in SOURCE_SUFFIXES:
                    out.append(p)
    return out


def _all_app_source_files() -> list[Path]:
    out: list[Path] = []
    skip_roots = (Path("/app/build"), Path("/app/output"))
    for p in Path("/app").rglob("*"):
        if not p.is_file() or p.suffix not in SOURCE_SUFFIXES:
            continue
        if any(str(p).startswith(str(r) + os.sep) for r in skip_roots):
            continue
        out.append(p)
    return out


def _all_app_build_inputs() -> list[Path]:
    out: list[Path] = []
    skip_roots = (Path("/app/build"), Path("/app/output"))
    for p in Path("/app").rglob("*"):
        if not p.is_file():
            continue
        if any(str(p).startswith(str(r) + os.sep) for r in skip_roots):
            continue
        if p.suffix in SOURCE_SUFFIXES + BUILD_SCRIPT_SUFFIXES:
            out.append(p)
        elif p.name in BUILD_SCRIPT_NAMES:
            out.append(p)
    return out

def _java_class_ready() -> bool:
    """Return True when the compiled entry class exists."""
    return (BUILD_DIR / f"{JAVA_CLASS}.class").is_file()


DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
BUILD_DIR = Path("/app/build")
JAVA_CLASS = "Replay"
GSON_CP = "/opt/gson.jar"

EV_PATH = DATA_DIR / "events.json"
CONFIG_PATH = DATA_DIR / "config.json"

SEG_STATES_PATH = OUT_DIR / "segment_states.json"
DECISIONS_PATH = OUT_DIR / "compact_decisions.json"
EVENT_AUDIT_PATH = OUT_DIR / "event_audit.json"
VIOLATIONS_PATH = OUT_DIR / "violations.json"
SUMMARY_PATH = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    SEG_STATES_PATH,
    DECISIONS_PATH,
    EVENT_AUDIT_PATH,
    VIOLATIONS_PATH,
    SUMMARY_PATH,
)
ALL_OUT_NAMES = tuple(p.name for p in ALL_OUT_PATHS)

ALL_INPUT_PATHS = (EV_PATH, CONFIG_PATH)

VALID_TYPES = {"flush_memtable", "compact"}
VALID_STATUSES = {"live", "merged"}
VALID_REASON_IGNORED = {
    "none", "duplicate_seg_id", "level_out_of_range",
    "top_level_compaction", "level_below_threshold",
}
PAYLOAD_KEYS = {
    "flush_memtable": {"seg_id", "size_bytes"},
    "compact": {"level"},
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def is_strictly_formatted(path: Path) -> tuple[bool, str]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        return False, f"{path} missing trailing newline"
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"{path} not utf-8: {exc}"
    payload = json.loads(decoded)
    canonical = dump_canonical(payload)
    if decoded != canonical:
        return False, f"{path} not in canonical 2-space sorted-keys form"
    return True, ""


# ---------------------------------------------------------------------------
# Reference simulator (mirrors /app/docs/state_machine.md).
# ---------------------------------------------------------------------------


def simulate(events_doc: dict, config: dict) -> dict:
    events = list(events_doc["events"])
    max_level = int(config["max_level"])
    min_segs = int(config["compaction_min_segments"])

    state: dict[str, dict] = {}
    audit: list[dict] = []
    decisions: list[dict] = []

    for ev in events:
        eid = ev["event_id"]
        ts = int(ev["ts_unix_ms"])
        t = ev["type"]
        p = ev["payload"]
        row = {
            "event_id": eid,
            "ts_unix_ms": ts,
            "type": t,
            "payload": dict(p),
            "accepted": False,
            "reason_ignored": "none",
        }
        if t == "flush_memtable":
            sid = p["seg_id"]
            if sid in state:
                row["reason_ignored"] = "duplicate_seg_id"
            else:
                state[sid] = {
                    "seg_id": sid,
                    "level": 0,
                    "size_bytes": int(p["size_bytes"]),
                    "created_at_unix_ms": ts,
                    "status": "live",
                    "merged_at_unix_ms": None,
                    "merged_into_event_id": None,
                }
                row["accepted"] = True
        elif t == "compact":
            level = int(p["level"])
            if level > max_level:
                row["reason_ignored"] = "level_out_of_range"
            elif level == max_level:
                row["reason_ignored"] = "top_level_compaction"
            else:
                live = sorted(
                    (s for s in state.values()
                     if s["status"] == "live" and s["level"] == level),
                    key=lambda s: s["seg_id"],
                )
                if len(live) < min_segs:
                    row["reason_ignored"] = "level_below_threshold"
                else:
                    ids = [s["seg_id"] for s in live]
                    total = sum(s["size_bytes"] for s in live)
                    for s in live:
                        s["status"] = "merged"
                        s["merged_at_unix_ms"] = ts
                        s["merged_into_event_id"] = eid
                    new_id = "merged_" + eid
                    state[new_id] = {
                        "seg_id": new_id,
                        "level": level + 1,
                        "size_bytes": total,
                        "created_at_unix_ms": ts,
                        "status": "live",
                        "merged_at_unix_ms": None,
                        "merged_into_event_id": None,
                    }
                    decisions.append({
                        "event_id": eid,
                        "ts_unix_ms": ts,
                        "level": level,
                        "input_seg_ids": ids,
                        "output_seg_id": new_id,
                        "output_level": level + 1,
                        "total_bytes": total,
                    })
                    row["accepted"] = True
        audit.append(row)

    segs_sorted = sorted(state.values(), key=lambda s: s["seg_id"])
    audit_sorted = sorted(audit, key=lambda r: r["event_id"])
    violations_sorted = [dict(r) for r in audit_sorted if not r["accepted"]]

    accepted = sum(1 for r in audit if r["accepted"])
    rejected = len(audit) - accepted
    flushes_acc = sum(
        1 for r in audit if r["accepted"] and r["type"] == "flush_memtable"
    )
    comps_acc = sum(1 for r in audit if r["accepted"] and r["type"] == "compact")
    live = sum(1 for s in state.values() if s["status"] == "live")
    merged = sum(1 for s in state.values() if s["status"] == "merged")

    per_level: dict[str, int] = {str(L): 0 for L in range(max_level + 1)}
    for s in state.values():
        if s["status"] == "live":
            per_level[str(s["level"])] = per_level.get(str(s["level"]), 0) + 1

    summary = {
        "total_events": len(events),
        "total_flushes_accepted": flushes_acc,
        "total_compactions_accepted": comps_acc,
        "total_segments_ever": len(state),
        "live_segment_count": live,
        "merged_segment_count": merged,
        "events_accepted": accepted,
        "events_rejected": rejected,
        "per_level_live_counts": per_level,
    }

    return {
        "segment_states": {"segments": segs_sorted},
        "compact_decisions": {"decisions": decisions},
        "event_audit": {"events": audit_sorted},
        "violations": {"violations": violations_sorted},
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def input_data() -> dict[str, Any]:
    return {
        "events": load_json(EV_PATH),
        "config": load_json(CONFIG_PATH),
    }


@pytest.fixture(scope="session")
def expected_outputs(input_data) -> dict[str, Any]:
    return simulate(input_data["events"], input_data["config"])


@pytest.fixture(scope="session")
def precomputed_input_hashes() -> dict[Path, str]:
    return {p: sha256_of(p) for p in ALL_INPUT_PATHS}


@pytest.fixture(scope="session")
def binary_run_outputs(precomputed_input_hashes) -> dict[Path, Any]:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert _java_class_ready(), f"agent binary missing at {(BUILD_DIR / f"{JAVA_CLASS}.class")}"
    assert (BUILD_DIR / f"{JAVA_CLASS}.class").stat().st_mode & True  # Java class, "binary not executable"
    res = subprocess.run(
        [*_java_cmd(DATA_DIR, OUT_DIR)],
        capture_output=True, text=True, timeout=180,
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
# Positive tests
# ---------------------------------------------------------------------------


def test_inputs_unchanged(precomputed_input_hashes):
    for p, h in precomputed_input_hashes.items():
        assert sha256_of(p) == h, f"{p} content mutated"



def test_java_entry_class_exists():
    """Compiled Java entry class exists under /app/build after the agent build."""
    assert _java_class_ready()




def test_sources_present_and_class_newer():
    """Java sources under /app/src are no older than the compiled entry class."""
    required_sources = _src_files()
    assert required_sources, "no .java under /app/src"
    inputs = _all_app_build_inputs()
    class_path = BUILD_DIR / f"{JAVA_CLASS}.class"
    bin_mtime = int(class_path.stat().st_mtime)
    for s in inputs:
        src_mtime = int(s.stat().st_mtime)
        assert bin_mtime >= src_mtime, (
            f"class mtime {bin_mtime} older than build input {s} mtime {src_mtime}"
        )



def test_binary_runs_cleanly_and_outputs_are_fresh(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        assert p in binary_run_outputs


def test_binary_rejects_wrong_arg_counts(tmp_path):
    res = subprocess.run([*_java_cmd(DATA_DIR, OUT_DIR)], capture_output=True, text=True, timeout=30)
    assert res.returncode != 0
    res = subprocess.run([*_java_cmd(DATA_DIR, OUT_DIR)], capture_output=True, text=True, timeout=30)
    assert res.returncode != 0
    probe_out = tmp_path / "probe_out"
    probe_out.mkdir()
    res = subprocess.run(
        [*_java_cmd(DATA_DIR, OUT_DIR)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0
    leftovers = sorted(probe_out.rglob("*"))
    assert leftovers == [], f"wrong-arg-count invocation wrote artifacts: {leftovers}"


def test_binary_uses_argv2_paths_not_hardcoded(tmp_path):
    tmp_out = tmp_path / "altout"
    tmp_out.mkdir()
    res = subprocess.run(
        [*_java_cmd(DATA_DIR, tmp_out)],
        capture_output=True, text=True, timeout=180,
    )
    assert res.returncode == 0, f"binary failed under alt out_dir: {res.stderr}"
    for name in ALL_OUT_NAMES:
        p = tmp_out / name
        assert p.exists(), f"binary did not write {name} to argv[2]"
        assert p.is_file(), f"{name} under alt out_dir is not a regular file"
        assert not p.is_symlink(), f"{name} under alt out_dir is a symlink"
    entries = sorted(p.name for p in tmp_out.iterdir())
    assert entries == sorted(ALL_OUT_NAMES), (
        f"alt out_dir contains unexpected artifacts: {entries}"
    )


def test_binary_reads_input_from_argv1_not_hardcoded(tmp_path, input_data, expected_outputs):
    tmp_data = tmp_path / "altdata"
    tmp_data.mkdir()
    tmp_out = tmp_path / "altout"
    tmp_out.mkdir()
    variant_evs = {"events": input_data["events"]["events"][:-1]}
    (tmp_data / "events.json").write_text(dump_canonical(variant_evs))
    (tmp_data / "config.json").write_text(dump_canonical(input_data["config"]))
    res = subprocess.run(
        [*_java_cmd(tmp_data, tmp_out)],
        capture_output=True, text=True, timeout=180,
    )
    assert res.returncode == 0, f"binary failed under variant data_dir: {res.stderr}"
    variant_expected = simulate(variant_evs, input_data["config"])
    name_map = {
        "segment_states.json": "segment_states",
        "compact_decisions.json": "compact_decisions",
        "event_audit.json": "event_audit",
        "violations.json": "violations",
        "summary.json": "summary",
    }
    for name, key in name_map.items():
        actual = json.loads((tmp_out / name).read_text(encoding="utf-8"))
        assert actual == variant_expected[key], (
            f"binary's {name} from argv[1]={tmp_data} did not track the variant data"
        )
    assert variant_expected["event_audit"] != expected_outputs["event_audit"], (
        "variant dataset did not produce a different event audit; test is degenerate"
    )


def test_outputs_strict_json_formatting(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(p)
        assert ok, msg


def test_outputs_are_ascii_at_every_depth(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        text = p.read_text(encoding="utf-8")
        text.encode("ascii")


def _walk_object_keys_in_emitted_order(text: str) -> list[list[str]]:
    obj = json.loads(text, object_pairs_hook=lambda items: items)
    out: list[list[str]] = []

    def walk(node):
        if isinstance(node, list):
            if (node and isinstance(node[0], tuple) and len(node[0]) == 2
                    and isinstance(node[0][0], str)):
                keys = [k for k, _ in node]
                out.append(keys)
                for _, v in node:
                    walk(v)
            else:
                for v in node:
                    walk(v)

    walk(obj)
    return out


def test_outputs_keys_sorted_at_every_depth(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        text = p.read_text(encoding="utf-8")
        for keys in _walk_object_keys_in_emitted_order(text):
            assert keys == sorted(keys), f"{p}: object keys not sorted: {keys}"


def test_output_directory_contains_exactly_five_files(binary_run_outputs):
    entries = list(OUT_DIR.iterdir())
    names = sorted(p.name for p in entries)
    assert names == sorted(ALL_OUT_NAMES), f"unexpected output files: {names}"
    for p in entries:
        assert p.is_file(), f"{p} is not a regular file"
        assert not p.is_symlink(), f"{p} must not be a symlink"


def test_segment_states_match_reference(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[SEG_STATES_PATH] == expected_outputs["segment_states"]


def test_compact_decisions_match_reference(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[DECISIONS_PATH] == expected_outputs["compact_decisions"]


def test_event_audit_match_reference(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[EVENT_AUDIT_PATH] == expected_outputs["event_audit"]


def test_violations_match_reference(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[VIOLATIONS_PATH] == expected_outputs["violations"]


def test_summary_match_reference(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[SUMMARY_PATH] == expected_outputs["summary"]


def test_segment_states_use_closed_sets(binary_run_outputs):
    for s in binary_run_outputs[SEG_STATES_PATH]["segments"]:
        assert s["status"] in VALID_STATUSES, s
        if s["status"] == "live":
            assert s["merged_at_unix_ms"] is None
            assert s["merged_into_event_id"] is None
        else:
            assert isinstance(s["merged_at_unix_ms"], int)
            assert isinstance(s["merged_into_event_id"], str)


def test_event_audit_uses_closed_sets(binary_run_outputs):
    for r in binary_run_outputs[EVENT_AUDIT_PATH]["events"]:
        assert r["type"] in VALID_TYPES
        assert r["reason_ignored"] in VALID_REASON_IGNORED
        assert isinstance(r["accepted"], bool)
        if r["accepted"]:
            assert r["reason_ignored"] == "none", r
        else:
            assert r["reason_ignored"] != "none", r
        assert set(r["payload"].keys()) == PAYLOAD_KEYS[r["type"]], r


def test_segment_states_sorted_by_seg_id(binary_run_outputs):
    ids = [s["seg_id"] for s in binary_run_outputs[SEG_STATES_PATH]["segments"]]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))


def test_event_audit_sorted_by_event_id(binary_run_outputs):
    ids = [r["event_id"] for r in binary_run_outputs[EVENT_AUDIT_PATH]["events"]]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))


def test_violations_sorted_by_event_id(binary_run_outputs):
    ids = [v["event_id"] for v in binary_run_outputs[VIOLATIONS_PATH]["violations"]]
    assert ids == sorted(ids)


def test_violations_match_event_audit_rejections(binary_run_outputs):
    rejected = [r for r in binary_run_outputs[EVENT_AUDIT_PATH]["events"] if not r["accepted"]]
    violations = binary_run_outputs[VIOLATIONS_PATH]["violations"]
    assert sorted(rejected, key=lambda r: r["event_id"]) == sorted(violations, key=lambda r: r["event_id"])


def test_compact_decisions_one_per_accepted_compact_in_input_order(binary_run_outputs, input_data):
    accepted_compacts = set()
    for r in binary_run_outputs[EVENT_AUDIT_PATH]["events"]:
        if r["accepted"] and r["type"] == "compact":
            accepted_compacts.add(r["event_id"])
    expected_eids = [
        ev["event_id"] for ev in input_data["events"]["events"]
        if ev["type"] == "compact" and ev["event_id"] in accepted_compacts
    ]
    actual_eids = [d["event_id"] for d in binary_run_outputs[DECISIONS_PATH]["decisions"]]
    assert actual_eids == expected_eids


def test_compact_decisions_input_ids_sorted_and_total_matches(binary_run_outputs):
    seg_size_by_id = {
        s["seg_id"]: s["size_bytes"]
        for s in binary_run_outputs[SEG_STATES_PATH]["segments"]
    }
    for d in binary_run_outputs[DECISIONS_PATH]["decisions"]:
        ids = d["input_seg_ids"]
        assert ids == sorted(ids)
        assert len(ids) == len(set(ids))
        assert d["total_bytes"] == sum(seg_size_by_id[s] for s in ids)
        assert d["output_level"] == d["level"] + 1
        assert d["output_seg_id"] == "merged_" + d["event_id"]


def test_merged_segments_consistent_with_decisions(binary_run_outputs):
    by_id = {s["seg_id"]: s for s in binary_run_outputs[SEG_STATES_PATH]["segments"]}
    for d in binary_run_outputs[DECISIONS_PATH]["decisions"]:
        for sid in d["input_seg_ids"]:
            seg = by_id[sid]
            assert seg["status"] == "merged"
            assert seg["merged_into_event_id"] == d["event_id"]
            assert seg["merged_at_unix_ms"] == d["ts_unix_ms"]
        out = by_id[d["output_seg_id"]]
        # output may itself be later merged by a higher-level compaction;
        # only its creation-time facts are guaranteed to be the decision's
        assert out["level"] == d["output_level"]
        assert out["size_bytes"] == d["total_bytes"]
        assert out["created_at_unix_ms"] == d["ts_unix_ms"]


def test_summary_consistent_with_states(binary_run_outputs):
    s = binary_run_outputs[SUMMARY_PATH]
    states = binary_run_outputs[SEG_STATES_PATH]["segments"]
    live = sum(1 for seg in states if seg["status"] == "live")
    merged = sum(1 for seg in states if seg["status"] == "merged")
    assert s["total_segments_ever"] == len(states)
    assert s["live_segment_count"] == live
    assert s["merged_segment_count"] == merged


def test_summary_per_level_counts_consistent(binary_run_outputs, input_data):
    s = binary_run_outputs[SUMMARY_PATH]
    states = binary_run_outputs[SEG_STATES_PATH]["segments"]
    max_level = int(input_data["config"]["max_level"])
    actual = {str(L): 0 for L in range(max_level + 1)}
    for seg in states:
        if seg["status"] == "live":
            actual[str(seg["level"])] = actual.get(str(seg["level"]), 0) + 1
    assert s["per_level_live_counts"] == actual


def test_summary_event_counts_consistent(binary_run_outputs):
    s = binary_run_outputs[SUMMARY_PATH]
    events = binary_run_outputs[EVENT_AUDIT_PATH]["events"]
    acc = sum(1 for r in events if r["accepted"])
    rej = sum(1 for r in events if not r["accepted"])
    assert s["total_events"] == len(events)
    assert s["events_accepted"] == acc
    assert s["events_rejected"] == rej
    flushes = sum(1 for r in events if r["accepted"] and r["type"] == "flush_memtable")
    comps = sum(1 for r in events if r["accepted"] and r["type"] == "compact")
    assert s["total_flushes_accepted"] == flushes
    assert s["total_compactions_accepted"] == comps


def test_dataset_exercises_every_branch(expected_outputs):
    s = expected_outputs["summary"]
    audit = expected_outputs["event_audit"]["events"]
    seen_reasons = {r["reason_ignored"] for r in audit if not r["accepted"]}
    states = expected_outputs["segment_states"]["segments"]
    statuses = {seg["status"] for seg in states}
    assert s["total_flushes_accepted"] > 0
    assert s["total_compactions_accepted"] >= 2, (
        "fixture should exercise cascading compactions across at least two levels"
    )
    required = {
        "duplicate_seg_id", "level_out_of_range",
        "top_level_compaction", "level_below_threshold",
    }
    missing = required - seen_reasons
    assert not missing, f"fixture does not exercise rejection reasons: {missing}"
    assert {"live", "merged"} <= statuses
    levels_with_output = {d["output_level"] for d in expected_outputs["compact_decisions"]["decisions"]}
    assert len(levels_with_output) >= 2, (
        "fixture should produce merged segments at more than one level"
    )


def test_now_unix_ms_does_not_leak_into_outputs(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        text = p.read_text(encoding="utf-8")
        assert '"now_unix_ms"' not in text, f"{p} contains a now_unix_ms key"

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k != "now_unix_ms"
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for _, doc in binary_run_outputs.items():
        walk(doc)


def test_now_unix_ms_value_change_does_not_affect_outputs(tmp_path, input_data):
    in_a = tmp_path / "now_a"
    in_a.mkdir()
    in_b = tmp_path / "now_b"
    in_b.mkdir()
    out_a = tmp_path / "out_a"
    out_a.mkdir()
    out_b = tmp_path / "out_b"
    out_b.mkdir()
    cfg_a = dict(input_data["config"])
    cfg_b = dict(input_data["config"])
    cfg_b["now_unix_ms"] = int(cfg_a["now_unix_ms"]) + 9_999_999
    _write_inputs(in_a, base=input_data, config=cfg_a)
    _write_inputs(in_b, base=input_data, config=cfg_b)
    for in_dir, out_dir in [(in_a, out_a), (in_b, out_b)]:
        res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                             capture_output=True, text=True, timeout=120)
        assert res.returncode == 0, f"binary failed: {res.stderr}"
    for name in ALL_OUT_NAMES:
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes(), (
            f"now_unix_ms changed {name}; must be informational only"
        )


def test_events_processed_in_input_order_not_ts_order(tmp_path, input_data):
    in_dir = tmp_path / "shuf_in"
    in_dir.mkdir()
    out_dir = tmp_path / "shuf_out"
    out_dir.mkdir()
    events = [dict(e) for e in input_data["events"]["events"]]
    base_ts = max(int(e["ts_unix_ms"]) for e in events) + 10
    for i, ev in enumerate(events):
        ev["ts_unix_ms"] = base_ts - i
    shuffled = {"events": events}
    _write_inputs(in_dir, base=input_data, events=shuffled)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, f"binary failed: {res.stderr}"
    expected = simulate(shuffled, input_data["config"])
    actual = json.loads((out_dir / "event_audit.json").read_text())
    assert actual == expected["event_audit"], (
        "binary appears to sort events by ts_unix_ms instead of processing in input order"
    )


def test_determinism_two_runs_byte_identical(tmp_path):
    out_a = tmp_path / "outA"
    out_a.mkdir()
    out_b = tmp_path / "outB"
    out_b.mkdir()
    for out in (out_a, out_b):
        res = subprocess.run(
            [*_java_cmd(DATA_DIR, out)],
            capture_output=True, text=True, timeout=180,
        )
        assert res.returncode == 0
    for name in ALL_OUT_NAMES:
        a = (out_a / name).read_bytes()
        b = (out_b / name).read_bytes()
        assert a == b, f"non-deterministic output for {name}"


def test_data_dir_unchanged_after_run(precomputed_input_hashes, binary_run_outputs):
    for p, h in precomputed_input_hashes.items():
        assert sha256_of(p) == h, f"{p} mutated by binary run"


def test_binary_can_be_rebuilt_from_visible_sources(tmp_path, expected_outputs):
    src_root = Path("/app/src")
    inc_root = Path("/app/include")
    sources = sorted(p for p in src_root.rglob("*.cpp") if p.is_file()) if src_root.exists() else []
    assert sources, "no .cpp sources under /app/src/"
    binbuilt = tmp_path / "lsmcompact_rebuilt"
    cmd = ["javac", "-std=c++17", "-O2", "-Wall"]
    if inc_root.exists():
        cmd.extend(["-I", str(inc_root)])
    cmd.extend(str(s) for s in sources)
    cmd.extend(["-o", str(binbuilt)])
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, f"rebuild failed:\n{res.stderr}"
    out = tmp_path / "out_rebuilt"
    out.mkdir()
    res = subprocess.run([str(binbuilt), str(DATA_DIR), str(out)],
                         capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, f"rebuilt binary failed:\n{res.stderr}"
    name_map = {
        "segment_states.json": "segment_states",
        "compact_decisions.json": "compact_decisions",
        "event_audit.json": "event_audit",
        "violations.json": "violations",
        "summary.json": "summary",
    }
    for name, key in name_map.items():
        actual = json.loads((out / name).read_text(encoding="utf-8"))
        assert actual == expected_outputs[key], f"rebuilt binary produced {name} != reference"


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------


_OMIT = object()


def _write_inputs(directory: Path, *, base, events=None, config=None):
    spec = {
        "events.json": events if events is not None else base["events"],
        "config.json": config if config is not None else base["config"],
    }
    for name, payload in spec.items():
        if payload is _OMIT:
            continue
        path = directory / name
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(dump_canonical(payload), encoding="utf-8")


def _run_binary(in_dir: Path, out_dir: Path):
    out_dir.mkdir(exist_ok=True)
    return subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )


def _assert_rejected_no_output(out_dir: Path, res):
    assert res.returncode != 0, (
        f"expected non-zero exit, got 0\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    if out_dir.exists():
        extras = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*"))
        assert extras == [], (
            f"binary wrote artifacts under argv[2]={out_dir} despite malformed input: {extras}"
        )


def test_binary_rejects_missing_all_inputs(tmp_path):
    in_dir = tmp_path / "empty_in"
    in_dir.mkdir()
    out_dir = tmp_path / "empty_out"
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


@pytest.mark.parametrize("drop", ["events.json", "config.json"])
def test_binary_rejects_missing_each_input(tmp_path, input_data, drop):
    in_dir = tmp_path / f"drop_{drop}"
    in_dir.mkdir()
    out_dir = tmp_path / f"drop_{drop}_out"
    overrides = {
        "events": _OMIT if drop == "events.json" else None,
        "config": _OMIT if drop == "config.json" else None,
    }
    _write_inputs(in_dir, base=input_data, **overrides)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


@pytest.mark.parametrize("bad_file", ["events.json", "config.json"])
def test_binary_rejects_invalid_json(tmp_path, input_data, bad_file):
    in_dir = tmp_path / f"bad_{bad_file}"
    in_dir.mkdir()
    out_dir = tmp_path / f"bad_{bad_file}_out"
    overrides = {
        "events": "{ not json" if bad_file == "events.json" else None,
        "config": "{ not json" if bad_file == "config.json" else None,
    }
    _write_inputs(in_dir, base=input_data, **overrides)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_events_top_level_not_object(tmp_path, input_data):
    in_dir = tmp_path / "arr_top"
    in_dir.mkdir()
    out_dir = tmp_path / "arr_top_out"
    _write_inputs(in_dir, base=input_data, events=[])
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_events_extra_top_level_key(tmp_path, input_data):
    evs = dict(input_data["events"])
    evs["bonus"] = "x"
    in_dir = tmp_path / "ev_extra_top"
    in_dir.mkdir()
    out_dir = tmp_path / "ev_extra_top_out"
    _write_inputs(in_dir, base=input_data, events=evs)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_event_bad_type(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "explode", "payload": {}}]}
    in_dir = tmp_path / "bad_type"
    in_dir.mkdir()
    out_dir = tmp_path / "bad_type_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_event_record_extra_key(tmp_path, input_data):
    bad = {"events": [{
        "event_id": "e1", "ts_unix_ms": 1, "type": "compact",
        "payload": {"level": 0}, "bonus": "x",
    }]}
    in_dir = tmp_path / "ev_extra_rec"
    in_dir.mkdir()
    out_dir = tmp_path / "ev_extra_rec_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_event_missing_payload(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "compact"}]}
    in_dir = tmp_path / "no_payload"
    in_dir.mkdir()
    out_dir = tmp_path / "no_payload_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_flush_payload_extra_key(tmp_path, input_data):
    bad = {"events": [{
        "event_id": "e1", "ts_unix_ms": 1, "type": "flush_memtable",
        "payload": {"seg_id": "s1", "size_bytes": 100, "bonus": "x"},
    }]}
    in_dir = tmp_path / "flush_extra"
    in_dir.mkdir()
    out_dir = tmp_path / "flush_extra_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_flush_payload_missing(tmp_path, input_data):
    bad = {"events": [{
        "event_id": "e1", "ts_unix_ms": 1, "type": "flush_memtable",
        "payload": {"seg_id": "s1"},
    }]}
    in_dir = tmp_path / "flush_missing"
    in_dir.mkdir()
    out_dir = tmp_path / "flush_missing_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_compact_payload_extra(tmp_path, input_data):
    bad = {"events": [{
        "event_id": "e1", "ts_unix_ms": 1, "type": "compact",
        "payload": {"level": 0, "bonus": "x"},
    }]}
    in_dir = tmp_path / "compact_extra"
    in_dir.mkdir()
    out_dir = tmp_path / "compact_extra_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_compact_payload_missing(tmp_path, input_data):
    bad = {"events": [{
        "event_id": "e1", "ts_unix_ms": 1, "type": "compact", "payload": {},
    }]}
    in_dir = tmp_path / "compact_missing"
    in_dir.mkdir()
    out_dir = tmp_path / "compact_missing_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_event_duplicate_id(tmp_path, input_data):
    bad = {"events": [
        {"event_id": "dup", "ts_unix_ms": 1, "type": "flush_memtable",
         "payload": {"seg_id": "a", "size_bytes": 1}},
        {"event_id": "dup", "ts_unix_ms": 2, "type": "flush_memtable",
         "payload": {"seg_id": "b", "size_bytes": 2}},
    ]}
    in_dir = tmp_path / "dup_eid"
    in_dir.mkdir()
    out_dir = tmp_path / "dup_eid_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_event_negative_ts(tmp_path, input_data):
    bad = {"events": [{
        "event_id": "e1", "ts_unix_ms": -1, "type": "compact",
        "payload": {"level": 0},
    }]}
    in_dir = tmp_path / "neg_ts"
    in_dir.mkdir()
    out_dir = tmp_path / "neg_ts_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_negative_size_bytes(tmp_path, input_data):
    bad = {"events": [{
        "event_id": "e1", "ts_unix_ms": 1, "type": "flush_memtable",
        "payload": {"seg_id": "s1", "size_bytes": -1},
    }]}
    in_dir = tmp_path / "neg_size"
    in_dir.mkdir()
    out_dir = tmp_path / "neg_size_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_negative_level(tmp_path, input_data):
    bad = {"events": [{
        "event_id": "e1", "ts_unix_ms": 1, "type": "compact",
        "payload": {"level": -1},
    }]}
    in_dir = tmp_path / "neg_level"
    in_dir.mkdir()
    out_dir = tmp_path / "neg_level_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_empty_seg_id(tmp_path, input_data):
    bad = {"events": [{
        "event_id": "e1", "ts_unix_ms": 1, "type": "flush_memtable",
        "payload": {"seg_id": "", "size_bytes": 1},
    }]}
    in_dir = tmp_path / "empty_seg"
    in_dir.mkdir()
    out_dir = tmp_path / "empty_seg_out"
    _write_inputs(in_dir, base=input_data, events=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_config_extra_key(tmp_path, input_data):
    cfg = dict(input_data["config"])
    cfg["bonus"] = "x"
    in_dir = tmp_path / "cfg_extra"
    in_dir.mkdir()
    out_dir = tmp_path / "cfg_extra_out"
    _write_inputs(in_dir, base=input_data, config=cfg)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_config_missing_max_level(tmp_path, input_data):
    cfg = dict(input_data["config"])
    cfg.pop("max_level", None)
    in_dir = tmp_path / "no_max"
    in_dir.mkdir()
    out_dir = tmp_path / "no_max_out"
    _write_inputs(in_dir, base=input_data, config=cfg)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_config_negative_max_level(tmp_path, input_data):
    cfg = dict(input_data["config"])
    cfg["max_level"] = -1
    in_dir = tmp_path / "neg_max"
    in_dir.mkdir()
    out_dir = tmp_path / "neg_max_out"
    _write_inputs(in_dir, base=input_data, config=cfg)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_config_zero_min_segments(tmp_path, input_data):
    cfg = dict(input_data["config"])
    cfg["compaction_min_segments"] = 0
    in_dir = tmp_path / "zero_min"
    in_dir.mkdir()
    out_dir = tmp_path / "zero_min_out"
    _write_inputs(in_dir, base=input_data, config=cfg)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_config_negative_min_segments(tmp_path, input_data):
    cfg = dict(input_data["config"])
    cfg["compaction_min_segments"] = -1
    in_dir = tmp_path / "neg_min"
    in_dir.mkdir()
    out_dir = tmp_path / "neg_min_out"
    _write_inputs(in_dir, base=input_data, config=cfg)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_config_negative_now(tmp_path, input_data):
    cfg = dict(input_data["config"])
    cfg["now_unix_ms"] = -1
    in_dir = tmp_path / "neg_now"
    in_dir.mkdir()
    out_dir = tmp_path / "neg_now_out"
    _write_inputs(in_dir, base=input_data, config=cfg)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


@pytest.mark.parametrize("swap_to_dir", ["events.json", "config.json"])
def test_binary_rejects_input_path_is_directory(tmp_path, input_data, swap_to_dir):
    in_dir = tmp_path / f"swap_{swap_to_dir}"
    in_dir.mkdir()
    out_dir = tmp_path / f"swap_{swap_to_dir}_out"
    _write_inputs(in_dir, base=input_data)
    target = in_dir / swap_to_dir
    target.unlink()
    target.mkdir()
    (target / "decoy.json").write_text("{}\n")
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_when_input_dir_does_not_exist(tmp_path):
    out_dir = tmp_path / "no_in_out"
    res = subprocess.run(
        [*_java_cmd(tmp_path / "absent_dir", out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_when_output_dir_does_not_exist(tmp_path, input_data):
    in_dir = tmp_path / "good_in_no_out_dir"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    missing_out = tmp_path / "absent_out_dir"
    res = subprocess.run(
        [*_java_cmd(in_dir, missing_out)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0, (
        f"binary unexpectedly succeeded with missing out_dir\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    assert not missing_out.exists() or list(missing_out.iterdir()) == [], (
        "binary must not auto-create or write into a missing argv[2]"
    )


def test_binary_rejects_when_output_dir_is_a_regular_file(tmp_path, input_data):
    in_dir = tmp_path / "good_in_out_is_file"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    file_out = tmp_path / "out_is_file"
    file_out.write_text("not a directory\n")
    original_bytes = file_out.read_bytes()
    res = subprocess.run(
        [*_java_cmd(in_dir, file_out)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0
    assert file_out.is_file()
    assert file_out.read_bytes() == original_bytes


@pytest.mark.parametrize("blocker_name", list(ALL_OUT_NAMES))
def test_binary_atomic_writes_when_target_blocked_by_directory(tmp_path, input_data, blocker_name):
    in_dir = tmp_path / f"good_in_{blocker_name}"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / f"blocked_{blocker_name}"
    out_dir.mkdir()
    blocker = out_dir / blocker_name
    blocker.mkdir()
    (blocker / "decoy").write_text("not your file")
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0, (
        f"binary unexpectedly succeeded with blocker at {blocker}\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [blocker_name]
    assert blocker.is_dir()
    assert (blocker / "decoy").read_text() == "not your file"


@pytest.mark.parametrize("sentinel_name", list(ALL_OUT_NAMES))
def test_binary_atomic_rejects_when_output_name_preexists_as_regular_file(
    tmp_path, input_data, sentinel_name
):
    in_dir = tmp_path / f"good_in_preexisting_{sentinel_name}"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / f"preexisting_out_{sentinel_name}"
    out_dir.mkdir()
    sentinel = out_dir / sentinel_name
    sentinel.write_text("pre-existing sentinel payload, do not touch\n")
    original_bytes = sentinel.read_bytes()
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [sentinel_name]
    assert sentinel.read_bytes() == original_bytes


@pytest.mark.parametrize("sentinel_name", list(ALL_OUT_NAMES))
def test_binary_atomic_rejects_when_partial_path_preexists(tmp_path, input_data, sentinel_name):
    in_dir = tmp_path / f"good_in_partial_{sentinel_name}"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / f"partial_out_{sentinel_name}"
    out_dir.mkdir()
    partial_name = sentinel_name + ".partial"
    stale = out_dir / partial_name
    stale.write_text("stale partial payload\n")
    original_bytes = stale.read_bytes()
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [partial_name]
    assert stale.read_bytes() == original_bytes


def test_binary_atomic_cleanup_propagates_to_already_committed_siblings(tmp_path, input_data):
    in_dir = tmp_path / "good_in_late"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / "late_blocker_out"
    out_dir.mkdir()
    blocker_name = "violations.json"
    blocker = out_dir / blocker_name
    blocker.mkdir()
    (blocker / "decoy").write_text("keep me")
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [blocker_name]
    assert blocker.is_dir()
    assert (blocker / "decoy").read_text() == "keep me"


@pytest.mark.parametrize("sentinel_name", list(ALL_OUT_NAMES))
def test_binary_atomic_rejects_when_output_name_preexists_as_symlink(
    tmp_path, input_data, sentinel_name
):
    in_dir = tmp_path / f"good_in_symlink_{sentinel_name}"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / f"symlink_out_{sentinel_name}"
    out_dir.mkdir()
    sentinel = out_dir / sentinel_name
    target = tmp_path / f"absent_target_{sentinel_name}"
    sentinel.symlink_to(target)
    assert sentinel.is_symlink()
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0, (
        f"binary unexpectedly succeeded with pre-existing symlink at {sentinel}\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [sentinel_name]
    assert sentinel.is_symlink()
    assert not target.exists()


@pytest.mark.parametrize("sentinel_name", list(ALL_OUT_NAMES))
def test_binary_atomic_rejects_when_partial_path_preexists_as_symlink(
    tmp_path, input_data, sentinel_name
):
    in_dir = tmp_path / f"good_in_partial_symlink_{sentinel_name}"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / f"partial_symlink_out_{sentinel_name}"
    out_dir.mkdir()
    partial_name = sentinel_name + ".partial"
    stale = out_dir / partial_name
    target = tmp_path / f"absent_partial_target_{sentinel_name}"
    stale.symlink_to(target)
    assert stale.is_symlink()
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0, (
        f"binary unexpectedly succeeded with pre-existing .partial symlink at {stale}\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [partial_name]
    assert stale.is_symlink()


def test_binary_rejects_when_output_dir_is_a_symlink_to_file(tmp_path, input_data):
    in_dir = tmp_path / "good_in_out_link"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    real_file = tmp_path / "real_file"
    real_file.write_text("not a directory\n")
    link_out = tmp_path / "out_link"
    link_out.symlink_to(real_file)
    res = subprocess.run(
        [*_java_cmd(in_dir, link_out)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0
    assert link_out.is_symlink()
    assert real_file.is_file()
    assert real_file.read_text() == "not a directory\n"


def test_binary_leaves_no_stray_temporary_files_on_success(tmp_path, input_data):
    in_dir = tmp_path / "good_in_clean"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / "clean_out"
    out_dir.mkdir()
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, f"binary failed: {res.stderr}"
    entries = {p.name for p in out_dir.iterdir()}
    assert entries == set(ALL_OUT_NAMES)
    for n in entries:
        assert not n.endswith(".partial")
