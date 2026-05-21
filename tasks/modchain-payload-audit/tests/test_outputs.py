"""Verifier suite for modchain-payload-audit (hard, Rust)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pytest

DATA_DIR = Path(os.environ.get("MODCHAIN_DATA_DIR", "/app/mod_chain_lab"))
AUDIT_DIR = Path(os.environ.get("MODCHAIN_AUDIT_DIR", "/app/audit"))
REPORT = AUDIT_DIR / "mod_digest.json"
BIN = Path("/app/target/release/modchain")

EXPECTED_INPUT_HASHES: Dict[str, str] = {
    "SPEC.md": "3306830d6d8680b913bb2b47ee7654fe48c4356b4a5d9f143ee4d76112a03bc6",
    "catalog.json": "d02232b4fd8f64f80384b890e8c9c2d5eab4e1c949be68a4322505125841ce6a",
    "frames/f00.json": "1da06225afc14909494c6fe623d0aff00f552b1ce543303eb2ef7475fa3e5e81",
    "frames/f01.json": "5ce74732baf3b0c6e358570b1caa1f2dde61c05fffca168c2fe21db2edfbceae",
    "frames/f02.json": "f8087d4154d870a74dc87079b168b0c965093144685845141a674c541877c0d5",
    "frames/f03.json": "e1b70fc36722a3091a2c6599afb6bbe45aecd70cc8a099970c0d04b6a355245a",
    "frames/f04.json": "bf1c16d6290c8de129b8f777bac3b38818a6b313dfafc0b62e8d1cbb71acf3fb",
    "frames/f05.json": "dbeef8ae229ee853a32eefea1cf50831d54c818710848e665bcb120537dcf782",
    "frames/f06.json": "fd8a4d6a4430c7d92b47ff06153631ee25ae966727641799fef9e88230ee4298",
    "frames/f07.json": "584e555d144b637a2d8a4a3eccdda5a99783891d0058142ff0a50786e39915eb",
    "frames/f08.json": "bf385132b0cfbd78f73e0af85d76c7f9fc290c52a1ba59b978efc25d9c499a60",
    "frames/f09.json": "ce2f00a0da38905493f21fb47f4bfc8b7bf267ffa28c9e6c868ddee25560407b",
    "frames/f10.json": "e0db60d041b3d2bb745c3ead6b5afdbf25cfdd19f5e1fceb117bed1a8ab3234b",
    "frames/f11.json": "23ece6aa807abe64398942bf848854c7c78f62017ec22faa00f4a7c44b58054f",
    "frames/f12.json": "37f33e2ce4297cecbe62356073206b399802665a8e732e35df839f73fd70f07e",
    "incidents.json": "835818f1dae456565db86887093a94358898a1ec27e214b98f5061f178e2b707",
    "noise/n1.json": "78444e48e439faabc99a0c390629c40fb73b0ebb0c95ecc5d1f4d00cd1ee52ae",
    "noise/n2.json": "78444e48e439faabc99a0c390629c40fb73b0ebb0c95ecc5d1f4d00cd1ee52ae",
    "noise/n3.json": "78444e48e439faabc99a0c390629c40fb73b0ebb0c95ecc5d1f4d00cd1ee52ae",
    "noise/n4.json": "78444e48e439faabc99a0c390629c40fb73b0ebb0c95ecc5d1f4d00cd1ee52ae",
    "noise/n5.json": "78444e48e439faabc99a0c390629c40fb73b0ebb0c95ecc5d1f4d00cd1ee52ae",
    "policy.json": "971b89ea72d70a5c8e3d79fb64cc11459813832ce299f1075be656436f19b4e8",
    "pool_state.json": "08db25c3c930ea4aaaa042a92bdfcb6f096ce8f441fd9750f3a67e4dea594754",
}


def _sha256_file(path: Path) -> str:
    """Return lowercase hex SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canon_json(obj: Any) -> str:
    """Canonical JSON matching SPEC on-disk layout."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _parse_hex(payload: str) -> Tuple[List[int], bool]:
    """Decode lowercase hex payload; invalid returns ([], False)."""
    if len(payload) % 2 != 0:
        return [], False
    out: List[int] = []
    for i in range(0, len(payload), 2):
        pair = payload[i : i + 2]
        for ch in pair:
            if ch not in "0123456789abcdef":
                return [], False
        out.append(int(pair, 16))
    return out, True


def _load_frame(path: Path) -> Dict[str, Any]:
    """Load a single frame JSON object."""
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw)


def compute_reference(base: Path) -> Dict[str, Any]:
    """Re-derive mod_digest.json from fixtures under base."""
    policy = json.loads((base / "policy.json").read_text(encoding="utf-8"))
    catalog = json.loads((base / "catalog.json").read_text(encoding="utf-8"))
    incidents = json.loads((base / "incidents.json").read_text(encoding="utf-8"))
    pool = json.loads((base / "pool_state.json").read_text(encoding="utf-8"))

    m = int(policy["modulus"])
    b = int(policy["base"]) % m
    h0 = int(policy["init"]) % m
    tier_bias = {str(k): int(v) for k, v in policy["tier_bias"].items()}
    dday = int(policy["current_day"])

    cap_raw = pool.get("terminal_sum_cap")
    cap: int | None
    if cap_raw is None:
        cap = None
    else:
        cap = int(cap_raw)

    suppressed: Set[str] = set()
    bias_addends: Dict[str, int] = {}
    compromised_streams: Set[str] = set()
    for ev in incidents.get("events", []):
        kind = str(ev.get("kind", ""))
        if kind == "suppress_frame":
            sd = int(ev["start_day"])
            ed = int(ev["end_day"])
            if sd <= dday <= ed:
                suppressed.add(str(ev["frame_id"]))
        elif kind == "bias_window":
            sd = int(ev["start_day"])
            ed = int(ev["end_day"])
            if sd <= dday <= ed:
                sid = str(ev["stream_id"])
                bias_addends[sid] = bias_addends.get(sid, 0) + int(ev["addend"])
        elif kind == "compromise_stream":
            if bool(ev.get("accepted", False)) and dday >= int(ev["day"]):
                compromised_streams.add(str(ev["stream_id"]))

    stream_rollups: List[Dict[str, Any]] = []
    raw_by_stream: Dict[str, int] = {}

    total_cataloged = 0
    total_after_suppress = 0

    for stream in catalog["streams"]:
        sid = str(stream["stream_id"])
        paths = [str(p) for p in stream["frame_paths"]]
        total_cataloged += len(paths)

        frames: List[Dict[str, Any]] = []
        for rel in paths:
            frames.append(_load_frame(base / rel))

        kept: List[Dict[str, Any]] = []
        for fr in frames:
            if str(fr.get("frame_id", "")) in suppressed:
                continue
            kept.append(fr)
        total_after_suppress += len(kept)

        diags: Set[str] = set()
        if sid in compromised_streams:
            diags.add("stream_compromised")
            stream_rollups.append(
                {
                    "diagnostics": sorted(diags),
                    "frames_considered": len(kept),
                    "mix_steps": 0,
                    "status": "quarantined",
                    "stream_id": sid,
                    "terminal_residue": 0,
                }
            )
            raw_by_stream[sid] = 0
            continue

        kept.sort(
            key=lambda o: (int(o.get("seq", 0) or 0), str(o.get("frame_id", "")))
        )

        h = h0
        add = bias_addends.get(sid, 0) % m
        for fr in kept:
            payload = str(fr.get("payload_hex", ""))
            seq = int(fr.get("seq", 0) or 0)
            tier = str(fr.get("tier", ""))
            q = ((seq % m) + m) % m

            bs, ok = _parse_hex(payload)
            if not ok:
                diags.add("bad_hex")
            ssum = sum(bs)
            ln = len(bs)

            if tier in tier_bias:
                tb = tier_bias[tier]
            else:
                tb = 0
                diags.add("unknown_tier")

            dig = (ssum + ln + q + tb) % m
            dig = (dig + add) % m
            h = (h * b + dig) % m

        stream_rollups.append(
            {
                "diagnostics": sorted(diags),
                "frames_considered": len(kept),
                "mix_steps": len(kept),
                "status": "ok",
                "stream_id": sid,
                "terminal_residue": int(h),
            }
        )
        raw_by_stream[sid] = int(h)

    stream_rollups.sort(key=lambda o: str(o["stream_id"]))

    n_quarantine = sum(1 for r in stream_rollups if r["status"] == "quarantined")

    nonq_raw_sum = sum(raw for sid, raw in raw_by_stream.items() if sid not in compromised_streams)
    cap_applied = cap is not None and nonq_raw_sum > cap

    scaled_sum: int | None
    if not cap_applied:
        scaled_sum = None
        for r in stream_rollups:
            if r["status"] == "ok":
                r["terminal_residue"] = raw_by_stream[str(r["stream_id"])]
    else:
        assert cap is not None
        c = int(cap)
        scaled_sum = 0
        for r in stream_rollups:
            sid = str(r["stream_id"])
            raw = raw_by_stream[sid]
            if r["status"] == "quarantined":
                tr = 0
            else:
                tr = (raw * c) // nonq_raw_sum if nonq_raw_sum > 0 else 0
                r["terminal_residue"] = int(tr)
            scaled_sum += int(r["terminal_residue"])

    meta = {
        "base": int(policy["base"]),
        "catalog_sha256": _sha256_file(base / "catalog.json"),
        "current_day": int(policy["current_day"]),
        "init": int(policy["init"]),
        "incidents_sha256": _sha256_file(base / "incidents.json"),
        "modulus": int(policy["modulus"]),
        "policy_sha256": _sha256_file(base / "policy.json"),
        "pool_sha256": _sha256_file(base / "pool_state.json"),
    }

    summary = {
        "cap_applied": bool(cap_applied),
        "quarantined_streams": int(n_quarantine),
        "scaled_sum": scaled_sum,
        "streams": int(len(stream_rollups)),
        "total_frames_after_suppress": int(total_after_suppress),
        "total_frames_cataloged": int(total_cataloged),
    }

    return {"meta": meta, "stream_rollups": stream_rollups, "summary": summary}


@pytest.fixture(scope="session")
def expected_report() -> Dict[str, Any]:
    """Reference digest rebuilt from bundled fixtures."""
    return compute_reference(DATA_DIR)


@pytest.fixture(scope="session")
def actual_report() -> Dict[str, Any]:
    """Parsed agent-produced mod_digest.json."""
    assert REPORT.is_file(), "missing /app/audit/mod_digest.json"
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_bundled_data_unchanged() -> None:
    """Bundled inputs under the lab directory must match pinned SHA-256 values."""
    for rel, expected in EXPECTED_INPUT_HASHES.items():
        path = DATA_DIR / rel
        assert path.is_file(), f"missing bundled input {rel}"
        assert _sha256_file(path) == expected, f"hash mismatch for {rel}"


def test_report_exists() -> None:
    """mod_digest.json must exist under the audit directory."""
    assert AUDIT_DIR.is_dir(), "missing /app/audit directory"
    assert REPORT.is_file(), "missing /app/audit/mod_digest.json"


def test_top_level_keys(actual_report: Dict[str, Any]) -> None:
    """Top-level JSON must contain exactly meta, stream_rollups, summary."""
    assert set(actual_report.keys()) == {"meta", "stream_rollups", "summary"}


def test_canonical_bytes(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """On-disk bytes must match canonical reference serialization."""
    assert actual_report == expected_report
    assert REPORT.read_text(encoding="utf-8") == _canon_json(expected_report)


def test_meta_hashes(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """meta must pin every policy input file and echo numeric knobs."""
    assert actual_report["meta"] == expected_report["meta"]


def test_stream_rollups_sorted_and_fields(
    actual_report: Dict[str, Any], expected_report: Dict[str, Any]
) -> None:
    """stream_rollups must be sorted and carry the contract fields."""
    assert actual_report["stream_rollups"] == expected_report["stream_rollups"]
    ids = [str(r["stream_id"]) for r in actual_report["stream_rollups"]]
    assert ids == sorted(ids)
    for r in actual_report["stream_rollups"]:
        assert set(r.keys()) == {
            "diagnostics",
            "frames_considered",
            "mix_steps",
            "status",
            "stream_id",
            "terminal_residue",
        }
        assert r["diagnostics"] == sorted(set(r["diagnostics"]))


def test_summary_counters(actual_report: Dict[str, Any], expected_report: Dict[str, Any]) -> None:
    """summary block must match the reference counters and scaling flag."""
    assert actual_report["summary"] == expected_report["summary"]


def test_gamma_stream_quarantined(actual_report: Dict[str, Any]) -> None:
    """gamma must be quarantined with the compromise diagnostic."""
    row = next(r for r in actual_report["stream_rollups"] if r["stream_id"] == "gamma")
    assert row["status"] == "quarantined"
    assert row["mix_steps"] == 0
    assert row["terminal_residue"] == 0
    assert row["diagnostics"] == ["stream_compromised"]


def test_alpha_includes_bad_hex_and_unknown_tier(
    actual_report: Dict[str, Any],
) -> None:
    """alpha must record both bad_hex and unknown_tier diagnostics."""
    row = next(r for r in actual_report["stream_rollups"] if r["stream_id"] == "alpha")
    assert "bad_hex" in row["diagnostics"]
    assert "unknown_tier" in row["diagnostics"]


def test_beta_bias_window_applied(actual_report: Dict[str, Any]) -> None:
    """beta must remain ok with two mixed frames."""
    row = next(r for r in actual_report["stream_rollups"] if r["stream_id"] == "beta")
    assert row["status"] == "ok"
    assert row["mix_steps"] == 2


def test_cap_applied_when_sum_exceeds_pool(actual_report: Dict[str, Any]) -> None:
    """When raw terminals exceed the cap, summary.cap_applied is true."""
    assert actual_report["summary"]["cap_applied"] is True
    assert isinstance(actual_report["summary"]["scaled_sum"], int)


def test_release_binary_is_repeatable() -> None:
    """Re-running the release binary on a clean audit dir reproduces the report."""
    if not BIN.is_file():
        pytest.skip("release binary not present")
    assert AUDIT_DIR.is_dir()
    for child in AUDIT_DIR.iterdir():
        if child.is_file():
            child.unlink()
    res = subprocess.run([str(BIN)], cwd="/app", capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    assert REPORT.is_file()
    assert json.loads(REPORT.read_text(encoding="utf-8")) == compute_reference(DATA_DIR)
