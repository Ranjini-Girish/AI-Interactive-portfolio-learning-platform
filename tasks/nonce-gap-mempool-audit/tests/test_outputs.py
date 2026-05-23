# scaffold-status: oracle-pending
"""Verifier suite for nonce-gap-mempool-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("NGM_DATA_DIR", "/app/mempoolgap"))
AUDIT_DIR = Path(os.environ.get("NGM_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "account_states.json",
    "mempool_violations.json",
    "summary.json",
    "tx_outcomes.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "a3ecc5436acfa39b7515b0c28623dd2f5edbb6e62142ca43bfb0b2e2d6fb1c5f",
    "accounts/acct_a.json": "845e335d738bf196443ea9a1ae382313be7f8761eccd66e2db87d296c886b61b",
    "accounts/acct_b.json": "984631a44fe2106c8e37557592b3ffd2c8d3f6b6a08c4dec224b0d5e7ec89ba7",
    "accounts/acct_c.json": "64141230831ca61700da34e7fe89e5b52085e1024d2af8083ea4a0a5a196ccdc",
    "accounts/acct_d.json": "afc18a7769ce9467af0d444993136139cd212d874e697de13b5a18f622abea59",
    "accounts/acct_e.json": "f7a70ddd037e6b278f32165aca812567b13ce989e19ed3aa6d4ba343812ef806",
    "accounts/acct_old.json": "67cf68a2fb5fefe119024c5f8430fa9d8b7eb0fbf7ba508ad26277ec7e79ddec",
    "accounts/acct_x.json": "8a177a8f9ccc813c4e9ee82ce9e059f476a2ec71554254314cddb0201107c110",
    "anchors/a1.txt": "c2227f14f1e30eefe5bfe7a98d97f05b7666f606b013ec9d298806c43dfb8161",
    "anchors/a2.txt": "c15e25508bfdeebbfabf8a49469508106ba03faf69e81010f78345f0e828ab90",
    "ancillary/channels.json": "8f306f4d60472bc2acb5733753b5df723a5e907e8818f4807f65a107c670eee1",
    "ancillary/limits.json": "ca59ef8c3c0f0742e2ba9b0709ee4acbeb80ec93322eff96193751334a0849bb",
    "ancillary/meta.json": "7f32381afd6fa866d19e320a17f40f701091b1f09d4b2d96c2ab88e590bed1f2",
    "ancillary/notes.json": "e0f5fcae30068156d37c73608f46020562e6e97bb4d89e3240ffd041cb2d6fcf",
    "epochs.json": "f77258e5ee5e9f42594288f57c25460e85eab5d18dddf770744c463362866644",
    "grid/dims.json": "473fe2a850b82d2d981070f8b927487e44c4b0e7d6fb13b96047f064273cd03f",
    "manifest.json": "b17496fb4389a6a81aa8c47daad3963294640b852d2cf496e9dd798868be2999",
    "meta/seq.json": "12458d61557f106a59d1fbf80c4af4da737946699c2f2e93e3422bf0c9015919",
    "policy.json": "44db97a5946a06a0525727a198ac7e1aa0dd29c2e572520b1f7a8ed64ab4112f",
    "txs.json": "9c57db6c9e899549c7fab5a61b1adeb5e62507a5510b4b4fa68d863832cf8858",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "account_states.json": "124f6a891cc54e1fd62ffe270c0a0b1db62198bf92b125d8fd6c6fc9aeb2ec9e",
    "mempool_violations.json": "886dbf24f8000c9c015dce841acf3cfd7fc3fdefa162744bc143282d21afc542",
    "summary.json": "111018832d4cc06fb8667481075d271e579581471fe0f06f5eb04773a4a15eb0",
    "tx_outcomes.json": "5e815700d83c4a0bb1274c843c40e35dc4539355606703ad4d6d5a7a1a8cc99f",
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "account_states.json": "265d6f120997a6ec356d8f0f43154715e3e5427ac317d04855ed25fa1532d2f5",
    "mempool_violations.json": "ae96972c837bc016eab1b0b482b40657db074a444880fb854d0db4a244ea7d8f",
    "summary.json": "3331e0912dba24da764d49761a85fe51268163fec0a708e2bc863d99605287a6",
    "tx_outcomes.json": "0b34373cff61eebb96236d17e03c8c1f489ecb748b06679b39a630bf40b63fbd",
}

EXPECTED_FIELD_HASHES = {
    "summary.effective_gap_limit": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
}
def _sha256_bytes(data: bytes) -> str:
    """Return hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Minified canonical JSON for hash comparison."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Load UTF-8 JSON from path."""
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted audit artifacts once per session."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


class TestInputIntegrity:
    """Verify the mounted workspace matches the frozen reference bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the data directory must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Verify emitted JSON files exist and hash-lock to the canonical contract."""

    def test_output_raw_byte_hashes(self) -> None:
        """Each audit file UTF-8 bytes must match normative layout."""
        for name, expected in EXPECTED_OUTPUT_RAW_HASHES.items():
            digest = _sha256_bytes((AUDIT_DIR / name).read_bytes())
            assert digest == expected, f"raw byte mismatch for {name}"

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_output_files_single_trailing_newline(self) -> None:
        """Root JSON objects must end with exactly one line feed after the closing brace."""
        for name in OUTPUT_FILES:
            raw = (AUDIT_DIR / name).read_text(encoding="utf-8")
            assert raw.endswith("}\n"), f"{name} must end with exactly one LF after root brace"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected summary fields must match pinned canonical digests."""
        for key, expected in EXPECTED_FIELD_HASHES.items():
            field = key.split(".", 1)[1]
            val = outputs["summary.json"][field]
            assert _sha256_bytes(_canonical(val).encode()) == expected

class TestMempoolSemantics:
    """Semantic checks for gap limits, replace boost, and stale accounts."""

    def test_channel_halving_gap_limit(self, outputs: dict[str, object]) -> None:
        """Mismatched channel tags must halve effective_gap_limit in summary."""
        assert outputs["summary.json"]["effective_gap_limit"] == 2

    def test_step5_gap_violation(self, outputs: dict[str, object]) -> None:
        """Submit nonce beyond expected plus gap limit must be gap_violation."""
        row = next(
            t for t in outputs["tx_outcomes.json"]["txs"]
            if t["step"] == 5 and t["account_id"] == "acct_a"
        )
        assert row["outcome"] == "gap_violation"

    def test_step3_replace_accepted(self, outputs: dict[str, object]) -> None:
        """Replace with sufficient fee boost must be replace_accepted."""
        row = next(
            t for t in outputs["tx_outcomes.json"]["txs"]
            if t["step"] == 3 and t["account_id"] == "acct_a"
        )
        assert row["outcome"] == "replace_accepted"

    def test_step7_replace_rejected(self, outputs: dict[str, object]) -> None:
        """Replace below replace_boost threshold must be replace_rejected."""
        row = next(
            t for t in outputs["tx_outcomes.json"]["txs"]
            if t["step"] == 7 and t["account_id"] == "acct_b"
        )
        assert row["outcome"] == "replace_rejected"

    def test_stale_skipped_outcome(self, outputs: dict[str, object]) -> None:
        """Stale account submit must be stale_skipped."""
        row = next(
            t for t in outputs["tx_outcomes.json"]["txs"]
            if t["account_id"] == "acct_old"
        )
        assert row["outcome"] == "stale_skipped"

    def test_unknown_account_outcome(self, outputs: dict[str, object]) -> None:
        """Unknown account id must be unknown_account."""
        row = next(
            t for t in outputs["tx_outcomes.json"]["txs"]
            if t["account_id"] == "acct_ghost"
        )
        assert row["outcome"] == "unknown_account"

    def test_warmup_skipped_present(self, outputs: dict[str, object]) -> None:
        """Warmup steps must emit warmup_skipped outcomes."""
        outcomes = {t["outcome"] for t in outputs["tx_outcomes.json"]["txs"]}
        assert "warmup_skipped" in outcomes
