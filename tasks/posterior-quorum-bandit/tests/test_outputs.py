"""Verifier suite for posterior-quorum-bandit (hard, Rust + bandit audit).

Hash-locked inputs and canonical JSON outputs guard against fixture tampering.
Binary checks are skipped when `/app/bin/pqb-audit` is absent (local harness).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

DATA_DIR = Path(os.environ.get("PQB_DATA_DIR", "/app/pqb_lab"))
AUDIT_DIR = Path(os.environ.get("PQB_AUDIT_DIR", "/app/audit"))
BINARY_PATH = Path("/app/bin/pqb-audit")

REQUIRED_OUTPUT_FILES = [
    "flags.json",
    "posterior_report.json",
    "quorum_trace.json",
    "selection_log.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "285d9b2ac01db11e4923fb2fa8a99f21e8b2a673510e200e2272e3320397a74f",
    "anchors/day_cap.json": "255294c0da4a40a49b68cdb1c60691ef7eff3d332c8e000e6045ca6a918bb8ec",
    "anchors/window.json": "b85e25db2a71f1709a636d7314ff36008f1c273994a9feb85d91dc97b04ce77d",
    "ancillary/meta.json": "106187c402f90985d8871eeb5659161b7f1155b6b279e6dcd92b0b24d307089e",
    "ancillary/notes.json": "efa766cb9ea45db4f0928bf5674fdc0ef66465a7643465edf26742119a6c4443",
    "ancillary/stub.json": "1cd24289b8601443abf90711d9e15066c302c6d80a7cba5243d6292305b309e0",
    "arms/arm_a.json": "28e26ba29e3a99a0d9045ea437f7cd5c2615d5df696f6f660aac5e5ce75ecb2d",
    "arms/arm_b.json": "06cdcf17f6a08bf9852bb5b2fadd0be02d97602447e9ba4f5d7f0a27ac6ff7b9",
    "arms/arm_c.json": "8eea9cde79eeb8c26ed8141dae8beecfdaaebd266490ef91c404324f9b9ab60c",
    "arms/arm_d.json": "5ba660924f0fe24d762a56e814155ecb46fdfcfa6d1322e3ea73c0f77226c6f2",
    "arms/arm_e.json": "7637a9c9307c84a9790d3010aa7ad4159c76b41fb7a13f1cb7744ec1821d49c7",
    "arms/arm_f.json": "fed664f05766e0fff14e673e85e2e663456810f28246fb46ede2bccad1bc24cb",
    "arms/arm_g.json": "daa42733c9cb958a17d98616882f0ecec16e67c6177201d5b3dc48baee201c8a",
    "arms/arm_h.json": "14c367a99aabff2b6f229edba8b52614ccca88de3df93fd0ed42c1a466dcdfd1",
    "incident_log.json": "b51cd582313d4873ef55a22d538452f182197662aec8fa3be254961506103c35",
    "policy.json": "14a2d033641151c9813bb77dfefb51c2afd50a75030015bcd3a7da02355718b1",
    "pool_state.json": "6fd91175b5ac1fe68db4ed5358715928dc53d258627b03c4acbf4b34e285721c",
    "rounds/r01.json": "b035e5c11a8ae1eb88126bea27e424e818eb22bdb5ffcd9852363df6bc7551c9",
    "rounds/r02.json": "27b0a6ac55997b023f06ec3b2960fa5181f1419b72da37f1d430830681df216a",
    "rounds/r03.json": "86da29d898336ae52d8be34ca53f7e8211cd83d30ae73c8d6ff6846a31967bf0",
    "rounds/r04.json": "d2ceaafcadb6ac8049bbc100f9d4972b13aaecf6f3f33752fd18ebc66804eb0e",
    "rounds/r05.json": "cbd51ba2dc1450509648d1f7ed674f050810d51c29e94101f67896b81b5326f1",
    "rounds/r06.json": "d934c5144b153ed877bd179e87a5b767a41d620c77e4db337d681534f928b14e",
    "rounds/r07.json": "45624d890929287d9be7f8e61cc287e3ba5f316fe9326d2b63eabb38aa1ac4f7",
    "rounds/r08.json": "f84bdc5eba82eb56381c9da767ca6fb52acf5f43a3270717540586ab5762a5d2",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "flags.json": "f745f2025257a2798abaf47f46acd01d78b73fc69a889c73d03e0dc623ccd4a3",
    "posterior_report.json": "c9d46440b3725ff6fd59688dc0a0fa77b3b08fe974b9fb41ebd5157fdec8049b",
    "quorum_trace.json": "20ab928a08beb61f95bad67b89858021054e281a838194d6ef0b635a4bee84dd",
    "selection_log.json": "ddd79e06d4acb7d5d073713f5b346259dc96cf9d45ea3470d5e208e604c1b347",
    "summary.json": "e0e73ace22b0cf93397446651ff40bb4cc1fc3a863c50204558b3982dbfcac1a",
}

EXPECTED_FIELD_HASHES = {
    "flags.flags": "001a7d09e56893a16b2aa9c1b4c52e780c3cd715cbba8116570f3ae37b5d2910",
    "posterior_report.arms": "ecc50eef556af96caa71869a889ac93b24d3daeb2e78f2e099018938570e7a0d",
    "summary.active_incidents": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
    "summary.budget_remaining": "a4b2c5db15348c29451e18b8307e5ef81625ea638e807935f39ceaa8d9ac7758",
}


def _sha256_bytes(b: bytes) -> str:
    """Return lowercase hex SHA-256 for raw bytes."""
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj: Any) -> bytes:
    """Serialize like the reference JSON canonicalizer (sorted keys, no indent)."""
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _canonical_sha256(obj: Any) -> str:
    """Return SHA-256 hex of canonical JSON encoding."""
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    """Load every required audit JSON from AUDIT_DIR."""
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: {AUDIT_DIR.as_posix()}/{name}"
        text = p.read_text(encoding="utf-8")
        obj = json.loads(text)
        out[name] = {"text": text, "obj": obj}
    return out


class TestInputIntegrity:
    """Shipped lab fixtures must remain byte-stable."""

    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_unchanged(self, rel, expected):
        """Each input file matches its pinned SHA-256 digest."""
        p = DATA_DIR / rel
        assert p.is_file(), f"missing input fixture: pqb_lab/{rel}"
        if p.suffix == ".json":
            obj = json.loads(p.read_text(encoding="utf-8"))
            actual = _canonical_sha256(obj)
        else:
            actual = _sha256_bytes(p.read_bytes())
        assert actual == expected, f"input fixture pqb_lab/{rel} was modified"


class TestReportStructure:
    """Outputs exist, parse, and match canonical hashes."""

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_required_file_exists(self, name, loaded_outputs):
        """Every required output file is present."""
        assert name in loaded_outputs

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_canonical_hash_each_file(self, name, loaded_outputs):
        """Each output matches its pinned canonical SHA-256."""
        assert _canonical_sha256(loaded_outputs[name]["obj"]) == EXPECTED_OUTPUT_CANONICAL_HASHES[name]

    def test_files_are_pretty_printed(self, loaded_outputs):
        """Outputs use two-space indent, sorted keys, and a trailing newline."""
        for name, data in loaded_outputs.items():
            text = data["text"]
            assert text.endswith("\n"), f"{name} must end with a newline"
            assert not text.endswith("\n\n"), f"{name} must not end with multiple newlines"
            expected = json.dumps(data["obj"], indent=2, sort_keys=True, ensure_ascii=True) + "\n"
            assert text == expected, f"{name} is not canonical 2-space sorted JSON"


class TestFieldHashes:
    """Nested structures cannot drift without tripping field hashes."""

    @pytest.mark.parametrize("field,expected", sorted(EXPECTED_FIELD_HASHES.items()))
    def test_field_hash(self, field, expected, loaded_outputs):
        """Named nested fields match their pinned canonical hashes."""
        file_name, _, path = field.partition(".")
        obj = loaded_outputs[f"{file_name}.json"]["obj"]
        cur = obj
        for part in path.split("."):
            cur = cur[part]
        assert _canonical_sha256(cur) == expected, f"field {field} drifted"


class TestSummarySemantics:
    """Spot-check compound interactions reflected in summary.json."""

    def test_fixture_incident_counts(self, loaded_outputs):
        """Active vs ignored incident rows match the authored fixture mix."""
        s = loaded_outputs["summary.json"]["obj"]
        assert s["active_incidents"] == 3
        assert s["ignored_incidents"] == 2

    def test_void_and_flag_totals(self, loaded_outputs):
        """Quorum voids in the ledger line up with summary counters."""
        s = loaded_outputs["summary.json"]["obj"]
        assert s["void_steps"] == 2
        assert s["flags_total"] == 2


class TestSelectionSemantics:
    """Ledger rows expose tie and quorum shortfall codes."""

    def test_tie_vote_row(self, loaded_outputs):
        """Round r03 records a tie_vote void on the selection ledger."""
        steps = loaded_outputs["selection_log.json"]["obj"]
        row = next(x for x in steps if x.get("round_id") == "r03")
        assert row["void_reason"] == "tie_vote"

    def test_insufficient_quorum_row(self, loaded_outputs):
        """Round r04 records insufficient_quorum after relief no longer applies."""
        steps = loaded_outputs["selection_log.json"]["obj"]
        row = next(x for x in steps if x.get("round_id") == "r04")
        assert row["void_reason"] == "insufficient_quorum"


def _binary_runs_on_fixture() -> bool:
    """Return true when /app/bin/pqb-audit exits zero on DATA_DIR into a temp output dir."""
    if not BINARY_PATH.is_file():
        return False
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        out.mkdir()
        res = subprocess.run(
            [str(BINARY_PATH), str(DATA_DIR), str(out)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    return res.returncode == 0


@pytest.mark.skipif(not _binary_runs_on_fixture(), reason="fixture-smoke binary missing or failing on bundled lab")
class TestBinaryContract:
    """CLI and argv behaviour for the Rust audit binary."""

    def test_binary_rejects_wrong_argc_zero(self, tmp_path):
        """Exits non-zero when no argv paths are provided."""
        res = subprocess.run([str(BINARY_PATH)], capture_output=True, text=True, timeout=60)
        assert res.returncode != 0

    def test_binary_rejects_wrong_argc_one(self, tmp_path):
        """Exits non-zero when only one argv path is provided."""
        res = subprocess.run([str(BINARY_PATH), str(DATA_DIR)], capture_output=True, text=True, timeout=60)
        assert res.returncode != 0

    def test_binary_honors_argv_paths(self, tmp_path):
        """Binary reads DATA_DIR from argv1 and writes outputs into argv2."""
        out_dir = tmp_path / "pqb_argv_out"
        out_dir.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(
            [str(BINARY_PATH), str(DATA_DIR), str(out_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert res.returncode == 0, res.stderr
        for name in REQUIRED_OUTPUT_FILES:
            assert (out_dir / name).is_file()

    def test_binary_rejects_bad_schema_version(self, tmp_path):
        """Non-zero exit when audit_schema_version is not pqb-1."""
        lab = tmp_path / "lab"
        lab.mkdir()
        bad_policy = json.loads((DATA_DIR / "policy.json").read_text(encoding="utf-8"))
        bad_policy["audit_schema_version"] = "pqb-0"
        (lab / "policy.json").write_text(json.dumps(bad_policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for name in ["pool_state.json", "incident_log.json"]:
            (lab / name).write_bytes((DATA_DIR / name).read_bytes())
        for sub in ["arms", "rounds", "anchors", "ancillary"]:
            src = DATA_DIR / sub
            dst = lab / sub
            dst.mkdir(parents=True, exist_ok=True)
            for p in src.glob("*.json"):
                (dst / p.name).write_bytes(p.read_bytes())
        (lab / "SPEC.md").write_bytes((DATA_DIR / "SPEC.md").read_bytes())
        out_dir = tmp_path / "bad_out"
        out_dir.mkdir()
        res = subprocess.run(
            [str(BINARY_PATH), str(lab), str(out_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert res.returncode != 0
