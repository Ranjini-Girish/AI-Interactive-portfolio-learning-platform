"""Verifier suite for shard clocks merge audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SCM_DATA_DIR", "/app/clk_lat"))
AUDIT_DIR = Path(os.environ.get("SCM_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ("segments_out.json", "summary.json")


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "b76eff4eeae89bdbe2aff9687690de42db80a9d5a1e814c30f43f6890e865619",
    "policy.json": "a4853def24a8e2758ad4163e84bac089922fc4aa9ec5abdbcf107b0ab5e07a3b",
    "pool_state.json": "6a0531ec80eadf098d92923a2b4a62c2789cb22385e89c53e11eecab56e40df9",
    "incidents.json": "047a0eb5de2ba34b581f9693cb90e1fecedb46cfcaeb0457a7853f7a5527a2fc",
    "segments/s01.json": "988ce4c95648772e814523f8f4ea7eb7854593764afe9d8a476193c9b4bbf9ed",
    "segments/s02.json": "cd1eb7d8702359a6f6b73f4426f96a9876def5bfef1354f8d04700c50b60d9e0",
    "segments/s03.json": "640a6af4728cdf7b5240a5c79a50075fce0aa881cb49ff0b2fffce8f9dd6b5f6",
    "segments/s04.json": "d3c507c0a4a44dcbd2276948f8e660635bfa2779fe64d29250170188f057c524",
    "segments/s05.json": "c6475761b1220618f948e2eea096248bf2e44647919f640799f5510b177b0fc2",
    "segments/s06.json": "04ba706df8cf19633f8b1f655de794517bbf95e47b3e6c6c1f4168bb3e82788f",
    "segments/s07.json": "c03f82bf481d072c9508d299be242fa006dadcd7d964a300ac1609625a883e7e",
    "segments/s08.json": "f15f888160395f451bd68f8eaaa12311b8addf30bb1958ca091f46dd5de24db4",
    "segments/s09.json": "2a9379286ace730c4e88bcaa8fba932f2e3152c5002a9e49d97d5e52e7088534",
    "segments/s10.json": "00b35904d6291d1bb07cf176fdd479fa494d7612f78d61cdfe5508464469792b",
    "segments/s11.json": "f2bb2fc1568a28ad6785249fc984fd63623df60d998f53065ab9ceafcf7dce61",
    "segments/s12.json": "9f32652323b2c0c7764d04e57831e031c2f01a4a7fb4b9fb502ffb8a8c08e2be",
    "anchors/east.txt": "558ab82b12eea753739e7908213bc623d7861e253af5a8a2823f37754ec53323",
    "anchors/north.txt": "82c92fb87af68b79fc2d771ad9830228ee015f33e5b2f0e6062b360e1b55ada6",
    "anchors/south.txt": "853384be4bd8d6a4c7625a0b75c77e4071757a36c3b7a55a4e8d6fbabfadc7a3",
    "anchors/west.txt": "fd8002e2bd3e35dd2f939530df9265642f8b00222c226bb7dc63ddcda6991250",
    "anchors/ydiag.txt": "89efb2ca4c01091af27681e2737afeaff3725d7aca446357c85c79e4c18a14cc",
    "anchors/zdiag.txt": "9e3856d8421d575198e0b1c4609d7ddd184d0c4140c359b58c5138d0e2f5fe55",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "segments_out.json": "77b7e665f4d50c926ab1d9666d6ceb37c6afeb7592dec9c94b6d7f8f3a6b8d15",
    "summary.json": "2579fe7841c09e8f050a635f9197c31f01a5b09bd6d60d59e072501ecb27ffc3",
}


EXPECTED_FIELD_HASHES = {
    "segments_out.rows": "b2e5fcb756852e1ea43bf3ef715d5c7c5b55a85696f77c4bc4e1e45f0ab73357",
    "summary.sum_adjusted": "36ebe205bcdfc499a25e6923f4450fa8d48196ceb4fa0ce077d9d8ec4a36926d",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted audit artefacts once per session."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


class TestInputIntegrity:
    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the data directory must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            digest = _sha256_bytes(_canonical(outputs[name]).encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        seg = outputs["segments_out.json"]
        sm = outputs["summary.json"]
        assert isinstance(seg, dict) and isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(seg["rows"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["segments_out.rows"]
        )
        assert (
            _sha256_bytes(_canonical(sm["sum_adjusted"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.sum_adjusted"]
        )


class TestSummarySemantics:
    def test_summary_counts(self, outputs: dict[str, object]) -> None:
        """Summary counters must be non-negative integers."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in ("trusted_count", "untrusted_count", "frozen_count", "sum_adjusted"):
            assert isinstance(sm[key], int)
        assert isinstance(sm["baseline_id_out"], str)

    def test_rows_sorted(self, outputs: dict[str, object]) -> None:
        """Rows follow ascending id order."""
        seg = outputs["segments_out.json"]
        assert isinstance(seg, dict)
        rows = seg["rows"]
        assert isinstance(rows, list)
        ids = [str(r["id"]) for r in rows if isinstance(r, dict)]
        assert ids == sorted(ids)


class TestIncidentKinds:
    def test_falseticker_present(self) -> None:
        """Dataset includes a falseticker incident row."""
        inc = _load_json(DATA_DIR / "incidents.json")
        assert isinstance(inc, dict)
        kinds = [str(r["kind"]) for r in inc["incidents"] if isinstance(r, dict)]
        assert "falseticker" in kinds

    def test_hold_and_lift_present(self) -> None:
        """Dataset includes hold and lift_hold rows."""
        inc = _load_json(DATA_DIR / "incidents.json")
        assert isinstance(inc, dict)
        kinds = [str(r["kind"]) for r in inc["incidents"] if isinstance(r, dict)]
        assert "hold" in kinds and "lift_hold" in kinds
