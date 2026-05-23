# scaffold-status: oracle-pending
"""Verifier suite for grad-clip-window-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GCW_DATA_DIR", "/app/gradclip"))
AUDIT_DIR = Path(os.environ.get("GCW_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ('shard_states.json', 'clip_plan.json', 'quorum_votes.json', 'window_stats.json', 'summary.json')

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "0a6991a0b5843b0c634372b9c068e1c6273cb9366213e2e3e90cbed19c8c7d55",
    "anchors/a1.txt": "0aa4aeeb41f19b7af1cda74ffcb32486b9f786c31bd99e07486c2d40a16e1ffd",
    "anchors/a2.txt": "0aa4aeeb41f19b7af1cda74ffcb32486b9f786c31bd99e07486c2d40a16e1ffd",
    "ancillary/meta.json": "c699534e6a46a51414e1208102aed30704a4d10c79d8814a76a5a86b3a9430c1",
    "ancillary/notes.json": "2821e697e49a09b4426dadfa7546e1931baec39642c43784925f031ed414fd02",
    "epochs.json": "74d0df6b2da068335c9f47cea7a106bda059a331139ac65ba0f0f6873fad0aa0",
    "grid/dims.json": "570390b875276e013dd2350b2669bd1eab9b87b48ac27e343cd4900a510fc874",
    "manifest.json": "293cde39c105ea4414b441555db01b2a5bb0f26115ca731e50254fdac0d766c4",
    "meta/seq.json": "f2400d6b4eb85f378444b5285581e1fb39c71aefddfcf92bf7cd5adf6239f4fe",
    "policy.json": "9e5379059ac1d08fb637549cfb8ff1b661e30f2139668a171c61d945e456d32a",
    "shards/sh01.json": "4c75abd3f057015b055e2a966eb7066243c6ce2c70d6688d570f9054646e672c",
    "shards/sh02.json": "80ed9c819ff5ee050cf9523d7d14f101812262e008a5748d9789573fb0e76d6e",
    "shards/sh03.json": "15d96f443de70b9e36d00785c66050bfc2005a8627dc4bb345434ae1a9cffac8",
    "shards/sh04.json": "4697ef0af9d09acb67f941139bd20038bd5cdfd4176afbd21d4d42cff0c5c3f8",
    "shards/sh05.json": "dce4a5debe6be8d238bf7da0f9ee1d48cec260a586a68ccd71abcff75435b2f6",
    "shards/sh06.json": "b62200fdbfcd7fac07a9e0a0c91acf1336d4266387d564a314b547e3ba3c3621",
    "shards/sh07.json": "54ac772754729053789f2f2536fd39f2a44bf8953267648326568eb7c6aef8e1",
    "shards/sh08.json": "bf235edcee17f8f8cd254b26b54c0f3ecf20cf28502bb6fc9173c490c57f0105",
    "shards/sh09.json": "49d2fc1752dfa9ee3ac34a19e525a19646542c1c6af42a4174beb803bddcadea",
    "shards/sh10.json": "e213d16da975a0607e29a045254a2b165fea44c674f1b9985f667aab6b6deb7e",
    "shards/sh11.json": "c94ff3e299b1801039129d6a8034f340e65add51feeb96d17357b4177f54257c",
    "shards/sh12.json": "55517b2d6c7fad1cee82a772a8d9e3492afe0be993a35d2081c840f4d924f7e4",
    "steps.json": "c76cbcec9facce8174754a5eec67e0f28a4910b1ec97ed157b7393ee078e9baa",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "clip_plan.json": "02b64cb3f445656672d8839f50e006689d9be91e43ed332f43f05f74101deb31",
    "quorum_votes.json": "429fbf070ad66e41ecd45ffe67d1e9b4300784eae3a7a0174a52da1339016205",
    "shard_states.json": "2079eeca1d99ee25941e395c5705b591386affcdbf5e2d1534170118e96ef388",
    "summary.json": "d6b9e8b912dc79dd95724a8ef09e30ed01e42bda9ad223a2e350762932a2ed64",
    "window_stats.json": "69286cbfd96e2d60d7d7fe2b7dbdbc9707bcee930679ee4225ae7b49d826f6ee",
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "clip_plan.json": "74af131bb4a37e6d423b16a225ef370d99e2bdeb28a0463f54e03ac1b9ea6169",
    "quorum_votes.json": "7616ca9bcdcb4ab709cb615997531c2ab5c74a0fa434414a6a00ba3cbd8fe4e1",
    "shard_states.json": "196cf5c08c0411e368f23ca45b960960221065fe880e4b16c2c3344492cd53ec",
    "summary.json": "73e887bf6e4c8d6ae374e687edb99652b7f2d6127e0f877667af022d59d5d4b6",
    "window_stats.json": "152fcf52481bf8833cec865b236448ba03e4373760f5dae3f6935f2b0b41c7f1",
}

EXPECTED_FIELD_HASHES = {
    "clip_plan.entries": "6b62b935067cb7bcb8c6c3511b6b91d467f1f350afdef77b78b4ec9fe6a73ba1",
    "summary.effective_clip_cap": "a19a1584344c1f3783bff51524a5a4b86f2cc09356c9dbfb6af9cd236e314362",
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
        """Selected nested fields must match pinned canonical digests."""
        assert _sha256_bytes(_canonical(outputs["clip_plan.json"]["entries"]).encode()) == EXPECTED_FIELD_HASHES["clip_plan.entries"]
        assert _sha256_bytes(_canonical(outputs["summary.json"]["effective_clip_cap"]).encode()) == EXPECTED_FIELD_HASHES["summary.effective_clip_cap"]



class TestClipSemantics:
    """Semantic checks for warmup, halving, stale shards, and quorum."""

    def test_effective_cap_halved(self, outputs: dict[str, object]) -> None:
        """Monitor-run tag mismatch must halve the clip cap in summary."""
        assert outputs["summary.json"]["effective_clip_cap"] == 5.0

    def test_warmup_step_not_clipped(self, outputs: dict[str, object]) -> None:
        """Steps inside warmup must keep clip_factor 1.0."""
        entries = outputs["clip_plan.json"]["entries"]
        warm = [e for e in entries if e["step"] <= 2]
        assert warm and all(e["clip_factor"] == 1.0 for e in warm)

    def test_stale_shard_skips_clip_row(self, outputs: dict[str, object]) -> None:
        """Stale shards must not appear in clip_plan."""
        states = {r["shard_id"]: r for r in outputs["shard_states.json"]["shards"]}
        clip_ids = {e["shard_id"] for e in outputs["clip_plan.json"]["entries"]}
        assert states["sh12"]["stale"] is True
        assert "sh12" not in clip_ids

    def test_neg_sign_quorum_rejected(self, outputs: dict[str, object]) -> None:
        """A lone negative sign on a hot step must fail quorum acceptance."""
        votes = [v for v in outputs["quorum_votes.json"]["votes"] if v["step"] == 3 and v["sign"] == "neg"]
        assert votes and not any(v["accepted"] for v in votes)
