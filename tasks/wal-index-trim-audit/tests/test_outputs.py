# scaffold-status: oracle-pending
"""Verifier suite for wal-index-trim-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("WIT_DATA_DIR", "/app/waltrim"))
AUDIT_DIR = Path(os.environ.get("WIT_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ('segment_states.json', 'trim_plan.json', 'role_votes.json', 'index_stats.json', 'summary.json')

EXPECTED_INPUT_HASHES = {
    "anchors/a1.txt": "eda1e7f014d71e973056539606f40f628146839a1237ecfdf64b45dfafa8cb10",
    "anchors/a2.txt": "160d7aac92c1fe0952a6a66be79b4e24b6f42a1363331475735877a1fcef5722",
    "ancillary/meta.json": "6f2053d6c290f8b4bb85d1ada8c41eab035b815b54c2a039a6341076359d0761",
    "ancillary/notes.json": "e0f5fcae30068156d37c73608f46020562e6e97bb4d89e3240ffd041cb2d6fcf",
    "epochs.json": "74d0df6b2da068335c9f47cea7a106bda059a331139ac65ba0f0f6873fad0aa0",
    "grid/dims.json": "6dfc05286939c4657697ed2d6a304c679787ebb1eca82e25fa02410d88069654",
    "indexes.json": "2f542edc302c6e9b44e84151839a5f44bd28bae8e7a54eb4c2655f9d9fd5e167",
    "links.json": "b735c2041de3415e49c22d171d2e0963872570ed71dce82b70c7c36b4bbfe576",
    "manifest.json": "6e2d964a5aa47ab3889d7e98e975e909e6ca975483f6e2ddcca7aae5163d91c8",
    "meta/seq.json": "113ae8c4b2d22a73be65a82c62b00f278d0ed84640ed2ff955f091c39618c579",
    "policy.json": "3f15471d7c834a792e7de89a718dbfa9e7edbb268438820802e2c3f1233a4089",
    "segments/sg01.json": "1764b9c19e33f9847fe75ec85c5e00cea63c119ed4738fdc6ed84be369e74da3",
    "segments/sg02.json": "11a08540677218b824052859c1358b097430e3e409434199bd1281372a5d32f5",
    "segments/sg03.json": "8a746da85c602684bbdb91635d95e2bb331df6174bdee588078695c7e01bab02",
    "segments/sg04.json": "87133ce721a50e134def2e76dfcd4a0d152d291fdb293e5beef74c026dcdfefb",
    "segments/sg05.json": "e76ea65e378f5ff942a048cd1f98ca0154228cc47dc638f1858d3d683edba53f",
    "segments/sg06.json": "d96f240fdbac29161628494ab81c9edbc60d626b202ef2f0042d9874458b7e1f",
    "segments/sg07.json": "a05b7bbb720941c00344d18c1f59b04393f0953571d4325c28dfc1b0c26c058c",
    "segments/sg08.json": "c9bdc691bd5bae7981cb3d9d6f2f68eb0aa19fe3f8091d9ba7e946f4df0f098d",
    "segments/sg09.json": "302c62585a6a25c8bc32e9eef263c402ef672060b81d121be51a0434dfc350e3",
    "segments/sg10.json": "d2616403483a647d956fc96315ce4c31bf575051f22961fd9727316f018083bb",
    "segments/sg11.json": "26e9b0ca806fc6c5d79f2cf9e4ddf1e8fc5037087a2fca8bde0d31356926ce41",
    "segments/sg12.json": "0c59f58c8e513ef057b9327825b7dcc12ddf7c225b74ae8ca7ccf7243d70ac46",
    "SPEC.md": "85f633bed607e7a808c5f12a77d7b21f3b75c6c93c6716010ae5c26945a73938"
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "segment_states.json": "146a8efecce02f2e5f6b2daaa489c1c28227cf74d7c9aee72bbe626b225a5e85",
    "trim_plan.json": "ef50c41ee78afb4e09976fd5b04df3ccd60c917bbdbb8453ec59e2659c178a52",
    "role_votes.json": "a166efd85b98c51f261a466e918ebdd2326c252f1c5c5e41641c5bfa557035ee",
    "index_stats.json": "8c9560eef0d0b32535e3e8541e2d563f0c727f2fa464b705894544fe40111b7c",
    "summary.json": "b86072a8d5509d9be41e4e605f177f3721961bbaecb5fef28fb5d75db001eec6"
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "segment_states.json": "2ea9502343358d3c04176f453a69553eece0ecc8d9daa0edb073a7e89c59b90d",
    "trim_plan.json": "00f4ce8ad731a5bf9eb78f1635dc9354191dfabcb37618ad6aa6cddd9fa8c86a",
    "role_votes.json": "8f51d919355565f0c6ff2902fbfa40ad3798585f0503a10318d7747fb1a57ec7",
    "index_stats.json": "56299efbd4fd9d314f5380a14903015e45d05f1aff4349908fa84670f0d0deb4",
    "summary.json": "d01da740d81b653570d2c79407adc26799294fdf43d979dd845001a828af1b4e"
}

EXPECTED_FIELD_HASHES = {
    "trim_plan.entries": "9307825edebfd6463037de3a7a874ec5833f3d62eb336002bd184974009feb38",
    "summary.effective_trim_threshold": "f97a13577367c1d604d37c4d2b6242d7193c7ba04aa4d1a64c322b23b2f9bd2a"
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
    for fname in OUTPUT_FILES:
        path = AUDIT_DIR / fname
        assert path.is_file(), f"missing emitted artifact: {fname}"
        payload[fname] = _load_json(path)
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
        for fname, expected in EXPECTED_OUTPUT_RAW_HASHES.items():
            digest = _sha256_bytes((AUDIT_DIR / fname).read_bytes())
            assert digest == expected, f"raw byte mismatch for {fname}"

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for fname, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[fname])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {fname}"

    def test_output_files_single_trailing_newline(self) -> None:
        """Root JSON objects must end with exactly one line feed after the closing brace."""
        for fname in OUTPUT_FILES:
            raw = (AUDIT_DIR / fname).read_text(encoding="utf-8")
            assert raw.endswith("}\n"), f"{fname} must end with exactly one LF after root brace"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match pinned canonical digests."""
        assert _sha256_bytes(_canonical(outputs["trim_plan.json"]["entries"]).encode()) == EXPECTED_FIELD_HASHES["trim_plan.entries"]
        assert _sha256_bytes(_canonical(outputs["summary.json"]["effective_trim_threshold"]).encode()) == EXPECTED_FIELD_HASHES["summary.effective_trim_threshold"]


class TestSemantics:
    """Semantic checks for compound audit rules."""

    def test_effective_trim_threshold_halved(self, outputs: dict[str, object]) -> None:
        """Snapshot-live tag mismatch must halve the trim threshold in summary."""
        assert outputs["summary.json"]["effective_trim_threshold"] == 50.0

    def test_warmup_index_not_trimmed(self, outputs: dict[str, object]) -> None:
        """Indexes inside warmup must keep trim_factor at zero."""
        entries = outputs["trim_plan.json"]["entries"]
        warm = [e for e in entries if e["index"] <= 2]
        assert warm and all(e["trim_factor"] == 0.0 for e in warm)

    def test_stale_segment_skips_trim_row(self, outputs: dict[str, object]) -> None:
        """Stale segments must not appear in trim_plan."""
        states = {r["segment_id"]: r for r in outputs["segment_states.json"]["segments"]}
        trim_ids = {e["segment_id"] for e in outputs["trim_plan.json"]["entries"]}
        assert states["sg12"]["stale"] is True
        assert "sg12" not in trim_ids

    def test_transitive_pin_blocks_trim(self, outputs: dict[str, object]) -> None:
        """Transitively pinned segments must never trim even above threshold."""
        entries = outputs["trim_plan.json"]["entries"]
        sg07 = [e for e in entries if e["segment_id"] == "sg07"]
        assert not sg07 or all(e["trim_factor"] == 0.0 for e in sg07)

    def test_replica_role_vote_rejected_on_hot_index(self, outputs: dict[str, object]) -> None:
        """A lone replica role on a contested index must fail role acceptance."""
        votes = [v for v in outputs["role_votes.json"]["votes"] if v["index"] == 3 and v["role"] == "replica"]
        assert votes and not any(v["accepted"] for v in votes)
