# scaffold-status: oracle-pending
"""Verifier suite for beam-hop-alias-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("BHA_DATA_DIR", "/app/beamalias"))
AUDIT_DIR = Path(os.environ.get("BHA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ('bin_states.json', 'alias_plan.json', 'band_votes.json', 'window_stats.json', 'summary.json')

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "dff903342b488f13e3a73594d7911eba3871c6e0c16e30b53ec1ad8a80c601c7",
    "anchors/b1.txt": "9a6546af6427dea52212109567147ec3718fa75173dcefac6fea021214b7d44e",
    "anchors/b2.txt": "9a6546af6427dea52212109567147ec3718fa75173dcefac6fea021214b7d44e",
    "ancillary/meta.json": "41791dbcf398a967e7035f6c1802b3fcb2d14afa327aa9466c8d65c5886cf3a1",
    "ancillary/notes.json": "c22e804ab288f4fad75efe8ed18c703792670420770e7ed5e5e21876375dd5a3",
    "bins/bn01.json": "5062ff4454f6a1a276d4cd49d25de0fad30292bd8610adf8c0eb9312759bc2ff",
    "bins/bn02.json": "b5ccf2b5053f68f230567a2d618f8672d3e543028c1b9a693647437a54676bc6",
    "bins/bn03.json": "11759ae9b84a24a9fe53cd5aaa2ecd8ae9f6bcac95f570f867f9b8ed3c7af753",
    "bins/bn04.json": "4900523d3657e0edb8ecae5b0db0334c69f7e3eff493c0064074483b36e78bfd",
    "bins/bn05.json": "810e5e13200fc3fed0a43913e806966edd066303c6504170c2c4c1e0a3c2cc25",
    "bins/bn06.json": "cb15dbabe81f48590d34e72d3fdc7b157c799b026be450f53809321b89811a71",
    "bins/bn07.json": "c7839a98bbc9b2eb1a24b152960b26fc0700174fec408aac0f67e6a67cd7d9ea",
    "bins/bn08.json": "c65401823796b3ca2ac43e3b8bc6ffdc240318a753fb6549631b1297ccd0ccc9",
    "bins/bn09.json": "8922151c3c37ab683488070589ef75a9b501455eb4cc7cb9879c205193e657e7",
    "bins/bn10.json": "b364d93e6be27fe1bb1be56a4dd05de8e8aec31dcd350483e3d27f7677384bdb",
    "bins/bn11.json": "07a1f8c5815b5a03705c5b185e417de3461ee469ffd4a7f6dd996e3f83b2d58e",
    "bins/bn12.json": "133ca6f3d32adce05e7f5379d0c2f323c53e7a3788ba3e4db9fb9aba161a845f",
    "epochs.json": "663c9b59a5d258b8738eba907edef52631a7e8ff136c4cbd8a16b1e39b53338d",
    "frames.json": "7cc13f09ef27227538c92bb85b4c8a9bff0f22945d5336e20f945a8141318bc6",
    "grid/dims.json": "c4bd9e11944666a7ad00a087eb276986e15a464341ed42b4a9a064d13fd0a18c",
    "locks.json": "2c0b20977b432c44c32e4cfc7bd533cccdb1148a90eaff9c5b8c6d6ba8b1eec1",
    "manifest.json": "1144c38cccdc59ee08585138556b36b12d74580471a8ab22115317ce197009c9",
    "meta/seq.json": "280482e1075f6cf41b67bfd05b627e03cea4c63daf6178e8fa7d2aa824fb7c86",
    "policy.json": "26311291786540875c4a6df0217d88497be3a4c49ae80b9fed86d5540ee387be",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "alias_plan.json": "f3ef11e1ffe55c70ee818b4ca41954801c7f743df60164c2bbd0cd2424478512",
    "band_votes.json": "254343c1ea906e5e567c5f0a907e01414e0ff42f08985091a4438b16989af2a6",
    "bin_states.json": "42e947fb62104e249e63919182594670d8afd31db71ef1fd9100b124d4b4d7f7",
    "summary.json": "a0975000172f03c8504534050117636018ce8fec66a3aec9e534fa73dd08b29c",
    "window_stats.json": "7109e27b117a2d7c8ebcdc7df67c1360d218dc21303c97fbfe7940a16d0ab7a6",
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "alias_plan.json": "c40819a27dcb658d95299d350458f3b1dd337e6e3f9c878b868fb5e188ed966a",
    "band_votes.json": "e9bd8be0908d12e8a2aeca10708c5b36c84f0050d037f42c8d98f468d83de579",
    "bin_states.json": "5663361012e9d3eadeac3448e93d1969564e917b41f43ad075c5c47e79be68af",
    "summary.json": "7034e13b66a92bd66c428b03c47dd595d9d5523b27b3f20df078f1404026feed",
    "window_stats.json": "75e99c2a79ffd72048ca592353b3cf6d4281b30777aa05433c2e5b32f7de26c9",
}

EXPECTED_FIELD_HASHES = {
    "alias_plan.entries": "2888b92d2c6447e64a814d76df15c5bb758722766ee80d6f88014feeb33e29a0",
    "summary.effective_nyquist_hz": "00c10b58d5c431fee46080cd1ce96bf2fd15a683255e9fc30ee0f672dad91424",
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

        assert _sha256_bytes(_canonical(outputs["alias_plan.json"]["entries"]).encode()) == EXPECTED_FIELD_HASHES["alias_plan.entries"]
        assert _sha256_bytes(_canonical(outputs["summary.json"]["effective_nyquist_hz"]).encode()) == EXPECTED_FIELD_HASHES["summary.effective_nyquist_hz"]


class TestAliasSemantics:
    """Semantic checks for Nyquist halving, locks, hop carry, and stale bins."""

    def test_effective_nyquist_halved(self, outputs: dict[str, object]) -> None:
        """Calibration-run tag mismatch must halve nyquist in summary."""
        assert outputs["summary.json"]["effective_nyquist_hz"] == 25.0

    def test_phase_lock_suppresses_alias(self, outputs: dict[str, object]) -> None:
        """Frequencies inside a lock band must not be marked aliased."""
        entries = outputs["alias_plan.json"]["entries"]
        locked = [e for e in entries if e["bin_id"] == "bn02" and e["frame"] == 1]
        assert locked and locked[0]["aliased"] is False
        assert locked[0]["report_freq_hz"] == 46.0

    def test_stale_bin_skips_alias_row(self, outputs: dict[str, object]) -> None:
        """Stale bins must not appear in alias_plan."""
        states = {r["bin_id"]: r for r in outputs["bin_states.json"]["bins"]}
        alias_ids = {e["bin_id"] for e in outputs["alias_plan.json"]["entries"]}
        assert states["bn12"]["stale"] is True
        assert "bn12" not in alias_ids

    def test_alias_fold_above_nyquist(self, outputs: dict[str, object]) -> None:
        """Frequencies above effective nyquist must fold and mark aliased."""
        entries = outputs["alias_plan.json"]["entries"]
        folded = [e for e in entries if e["bin_id"] == "bn05" and e["frame"] == 2]
        assert folded and folded[0]["aliased"] is True
        assert folded[0]["report_freq_hz"] == -10.0

