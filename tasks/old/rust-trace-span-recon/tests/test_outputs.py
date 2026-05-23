"""Verifier suite for rust-trace-span-recon (hard)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

DATA = Path("/app/data")
OUTPUT = Path("/app/output")
BIN = Path("/app/target/release/spanrecon")

SUMMARY = OUTPUT / "summary.json"
DUPLICATES = OUTPUT / "duplicates.json"
TRACES = OUTPUT / "traces.json"

EXPECTED_BUNDLED_DATA_SHA256 = {
    "static_pad_01.txt": "8bbfa29cdab45f4dcfa016887427c33f9d5c7a91f144e266432a453f1d2880fd",
    "static_pad_02.txt": "01f55f1b84048144bc572ec2f5f1df2bcca25f9b7bbfb9b150cac3227d0c3f57",
    "SPEC.md": "bdaa95b1041eaabae412ae3a17af2e40a0906454770464aac0eeaa810be9d044",
    "shards/shard_00.json": "5b3799b0cbfdb9db62df77890e61c38cb9d8ab536157fc3ab038b28144123cfe",
    "shards/shard_01.json": "34af7ac5f6fb3ef9608d79bb794fdcea045cb8c7b5031d7691c85361b725be06",
    "shards/shard_02.json": "9841ee53352cfe9b3d69617ee8beacd81c92e0232740a633bca46158602dab82",
    "shards/shard_03.json": "bc2b5c4bf2805153feecc0c3f441e3e4d7f1d662a130ba5b84d879adbaba744b",
    "shards/shard_04.json": "ec96b408a32949db12552e576880d20f6f01090a43f08d6605a4a2d4393a5542",
    "shards/shard_05.json": "d90c9161a2089b13afb5ed178c5ecdda266a875125ba3d98ac668f5a4dd02e1a",
    "shards/shard_06.json": "5a7e30a3dbbe15537efc8d48da3970d657e8b2c169f9556cb53d98c28ed0e492",
    "shards/shard_07.json": "cbc44bbdb8ef2f1adb063569314462eef1deec4f1e56ddba57baed38235a09f4",
    "shards/shard_08.json": "4ecd7e1aafe62db41ce137fb3442c53a85b9a727a84d5583a39072696d41c16d",
    "shards/shard_09.json": "4c8061ce21eeadd3a8c518a00300817f5c3348b4e20e35024405b696b18c5a2a",
    "shards/shard_10.json": "b57a516250624069cef0f2603b07aed90ff1ddd88a50280b1a302cce710976aa",
    "shards/shard_11.json": "f937af0b79bd8ca0e144cf438816b0fcb0f07c10faf62a8c5ea11a76e701b7e8",
    "shards/shard_12.json": "1340f6b38bf4e86c34b2bd973a5fcc8e713337f6a2b7ecbbc295a61f4fc3d6e8",
    "shards/shard_13.json": "b3b77eb83995950ca660b0b694f53b22433451a4726d5f4ff15309f21c872a3f",
    "shards/shard_14.json": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
}


def sha256_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    """Load JSON from UTF-8 text."""
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def canon_json(obj: Any) -> str:
    """Serialize JSON using the same canonical layout required on disk."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def well_formed(obj: object) -> bool:
    """Return True when a shard row satisfies SPEC.md well-formed rules."""
    if not isinstance(obj, dict):
        return False
    tid = obj.get("trace_id")
    sid = obj.get("span_id")
    if not isinstance(tid, str) or tid == "":
        return False
    if not isinstance(sid, str) or sid == "":
        return False
    pid = obj.get("parent_id")
    if pid is not None and not isinstance(pid, str):
        return False
    sm = obj.get("start_ms")
    em = obj.get("end_ms")
    if isinstance(sm, bool) or isinstance(em, bool):
        return False
    if not isinstance(sm, int) or not isinstance(em, int):
        return False
    return True


def iter_shard_rows(base: Path):
    """Yield shard rows in deterministic filename order."""
    d = base / "shards"
    if not d.is_dir():
        return
    for path in sorted(d.glob("*.json"), key=lambda p: p.name):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw, list):
            continue
        for obj in raw:
            yield obj


def compute_reference(base: Path) -> Tuple[dict, dict, dict]:
    """Re-derive the three contract JSON structures from shards under base."""
    claimed_first_index: Dict[str, Dict[str, int]] = defaultdict(dict)
    duplicates: List[dict] = []
    invalid_time_events = 0
    ingested = 0
    canon: List[dict] = []

    g = 0
    for obj in iter_shard_rows(base):
        if not well_formed(obj):
            continue
        tid = obj["trace_id"]
        sid = obj["span_id"]
        em = obj["end_ms"]
        sm = obj["start_ms"]
        if em < sm:
            invalid_time_events += 1
        if sid in claimed_first_index[tid]:
            duplicates.append(
                {
                    "trace_id": tid,
                    "span_id": sid,
                    "first_index": claimed_first_index[tid][sid],
                    "later_index": g,
                }
            )
            g += 1
            ingested += 1
            continue
        claimed_first_index[tid][sid] = g
        canon.append({"trace_id": tid, "span_id": sid, "parent_id": obj["parent_id"]})
        g += 1
        ingested += 1

    traces_ids: set[str] = set()
    for obj in iter_shard_rows(base):
        if well_formed(obj):
            traces_ids.add(obj["trace_id"])

    by_trace: Dict[str, List[dict]] = defaultdict(list)
    for row in canon:
        by_trace[row["trace_id"]].append(row)

    self_parent: Dict[str, set[str]] = defaultdict(set)
    orphan: Dict[str, set[str]] = defaultdict(set)
    roots: Dict[str, set[str]] = defaultdict(set)
    children: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))

    claimed_ids = {t: set(d.keys()) for t, d in claimed_first_index.items()}

    for row in canon:
        tid = row["trace_id"]
        sid = row["span_id"]
        pid = row["parent_id"]
        if pid is None:
            roots[tid].add(sid)
            continue
        assert isinstance(pid, str)
        if pid == sid:
            self_parent[tid].add(sid)
            continue
        if pid not in claimed_ids[tid]:
            orphan[tid].add(sid)
            continue
        children[tid][pid].append(sid)

    for tid in children:
        for p in children[tid]:
            children[tid][p].sort()

    def max_depth_for_trace(tid: str) -> int:
        depths: Dict[str, int] = {}
        dq: deque[str] = deque()
        for r in sorted(roots[tid]):
            if r in self_parent[tid] or r in orphan[tid]:
                continue
            depths[r] = 0
            dq.append(r)
        while dq:
            p = dq.popleft()
            dp = depths[p]
            for ch in children[tid].get(p, []):
                if ch in self_parent[tid] or ch in orphan[tid]:
                    continue
                depths[ch] = dp + 1
                dq.append(ch)
        return max(depths.values()) if depths else 0

    dup_in_trace: Dict[str, int] = defaultdict(int)
    for e in duplicates:
        dup_in_trace[e["trace_id"]] += 1

    invalid_in_trace: Dict[str, int] = defaultdict(int)
    for obj in iter_shard_rows(base):
        if not well_formed(obj):
            continue
        if obj["end_ms"] < obj["start_ms"]:
            invalid_in_trace[obj["trace_id"]] += 1

    traces_out: List[dict] = []
    for tid in sorted(by_trace.keys()):
        traces_out.append(
            {
                "trace_id": tid,
                "canonical_span_count": len(by_trace[tid]),
                "duplicate_events_in_trace": dup_in_trace[tid],
                "invalid_time_events_in_trace": invalid_in_trace[tid],
                "max_depth": max_depth_for_trace(tid),
                "orphan_span_ids": sorted(orphan[tid]),
                "roots": sorted(roots[tid]),
                "self_parent_span_ids": sorted(self_parent[tid]),
            }
        )

    summary = {
        "duplicate_events": len(duplicates),
        "ingested_well_formed_rows": ingested,
        "invalid_time_events": invalid_time_events,
        "orphan_canonical_rows": sum(len(v) for v in orphan.values()),
        "self_parent_canonical_rows": sum(len(v) for v in self_parent.values()),
        "trace_count": len(traces_ids),
    }

    duplicates_sorted = sorted(
        duplicates,
        key=lambda e: (e["trace_id"], e["span_id"], e["later_index"], e["first_index"]),
    )

    return summary, {"events": duplicates_sorted}, {"traces": traces_out}


def test_bundled_data_unchanged():
    """Every bundled input path under /app/data must still match the shipped SHA-256."""
    for rel, expected in EXPECTED_BUNDLED_DATA_SHA256.items():
        path = DATA / rel
        assert path.is_file(), f"missing bundled input {rel}"
        assert sha256_file(path) == expected, f"hash mismatch for {rel}"


def test_output_directory_scope():
    """Only the three contract output filenames may exist as regular files under /app/output/."""
    assert OUTPUT.is_dir(), "missing /app/output directory"
    names = {p.name for p in OUTPUT.iterdir() if p.is_file()}
    assert names == {
        "duplicates.json",
        "summary.json",
        "traces.json",
    }, f"unexpected files in /app/output: {sorted(names)}"


def test_outputs_exist():
    """Required JSON artifacts must exist under /app/output/."""
    assert SUMMARY.is_file(), "missing /app/output/summary.json"
    assert DUPLICATES.is_file(), "missing /app/output/duplicates.json"
    assert TRACES.is_file(), "missing /app/output/traces.json"


def test_byte_identity():
    """Agent outputs must match the independent reference and canonical JSON bytes."""
    exp_summary, exp_dup, exp_traces = compute_reference(DATA)
    got_summary = load_json(SUMMARY)
    got_dup = load_json(DUPLICATES)
    got_traces = load_json(TRACES)
    assert got_summary == exp_summary
    assert got_dup == exp_dup
    assert got_traces == exp_traces
    assert SUMMARY.read_text(encoding="utf-8") == canon_json(exp_summary)
    assert DUPLICATES.read_text(encoding="utf-8") == canon_json(exp_dup)
    assert TRACES.read_text(encoding="utf-8") == canon_json(exp_traces)


def test_fixture_semantics():
    """Spot-check bundled shard semantics exercised by the reference bundle."""
    exp_summary, exp_dup, exp_traces = compute_reference(DATA)
    assert exp_summary["ingested_well_formed_rows"] == 14
    assert exp_summary["duplicate_events"] == 1
    assert exp_summary["invalid_time_events"] == 1
    assert exp_summary["orphan_canonical_rows"] == 1
    assert exp_summary["self_parent_canonical_rows"] == 1
    assert exp_summary["trace_count"] == 5
    assert exp_dup["events"][0]["span_id"] == "dup-a"
    by_id = {t["trace_id"]: t for t in exp_traces["traces"]}
    assert by_id["epsilon"]["max_depth"] == 2
    assert by_id["beta"]["orphan_span_ids"] == ["orph-b"]
    assert by_id["delta"]["invalid_time_events_in_trace"] == 1


def test_reference_empty_shards_dir(tmp_path: Path):
    """With no shards directory, the reference model emits empty structures and zero counters."""
    base = tmp_path / "data"
    (base / "shards").mkdir(parents=True)
    s, d, t = compute_reference(base)
    assert s == {
        "duplicate_events": 0,
        "ingested_well_formed_rows": 0,
        "invalid_time_events": 0,
        "orphan_canonical_rows": 0,
        "self_parent_canonical_rows": 0,
        "trace_count": 0,
    }
    assert d == {"events": []}
    assert t == {"traces": []}


def test_release_binary_is_repeatable():
    """When the release binary exists, clearing /app/output and re-running reproduces the same bytes."""
    if not BIN.is_file():
        pytest.skip("release binary not present")
    assert OUTPUT.is_dir()
    for child in OUTPUT.iterdir():
        if child.is_file():
            child.unlink()
    res = subprocess.run([str(BIN)], cwd="/app", capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    exp_summary, exp_dup, exp_traces = compute_reference(DATA)
    assert load_json(SUMMARY) == exp_summary
    assert load_json(DUPLICATES) == exp_dup
    assert load_json(TRACES) == exp_traces
