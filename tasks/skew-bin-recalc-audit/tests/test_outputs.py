# scaffold-status: oracle-pending
"""Behavioral tests for skew-bin-recalc-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SBR_DATA_DIR", "/app/sbr_lab"))
AUDIT_DIR = Path(os.environ.get("SBR_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["skew_bins.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "ee0411e849ba1df53bcb0f56b718f782a374363e0e86fc8198bbfcb7c98269b9",
    "anchors/east.json": "95a9cb71c8647837804a96549a71bcd5859d24182396cbefcdc9b2a93c97ba97",
    "anchors/west.json": "a4f6d3014b11f77ca64a1c89d914caf3335510f49fb36f6c85c6b23db62108d9",
    "ancillary/extra.json": "66e0b05e1b6ab764bae179cd10b2453c3ca980eb095f89401c38ff4f021f5dbc",
    "ancillary/meta.json": "8c183cc752b30a37abd323114a0ec6775a191c5b2d886e5aad85589a6d31ea81",
    "ancillary/notes.json": "35939c1e11de41c34c3ca02d0b877737dd0dd3fec8b669fb719b9c84de2a61cb",
    "domain_layout.json": "6c322304d0e092797682ec43070b1a8374ac38b05f01e4036a2b09dc966c7f39",
    "incident_log.json": "d91cb68778fd4deac977670dde84b594e4ffeb0332fc9d0345767aad3831df3f",
    "policy.json": "41f0d872bd382fb521d193d0d7311533fed7f915c6f35da30fb897e10e978b7f",
    "pool_state.json": "9f22c46193ca7e2bec3bf0fdbe27e8f0fbd7b2a2f4e4fc6b74b151b668dc6f68",
    "samples/sample_00.json": "807def418674e558e0c87970bfb2673ce03554c6525458938d1bff4e5bde4e0a",
    "samples/sample_01.json": "73af7fda8af3af9d44bd79e24f39c2bab01fd75c692cf205a882a02c4dca137e",
    "samples/sample_02.json": "4c9d855418b9f4cdd8b9b812da900174e10082d5271829bc02c1a9837fdfa0da",
    "samples/sample_03.json": "01e4b2aff4a18161d7e5635418c3af847b536c2b6666530221863a38a2808cdb",
    "samples/sample_04.json": "06fecb73062a4f051742df3a5fd31310121b5bc18079609f7cbeaece65749e57",
    "samples/sample_05.json": "90400c1f11c08ba84b71ed571d1ef300b4352f750bd1ee17b2a903854de457a9",
    "samples/sample_06.json": "ea4781842184567e8a260cdf57cfa253b07c3b376806bc6d220af36d76e7dee4",
    "samples/sample_07.json": "ab11e3121cc13736f33369f30cb9d914d4b86badecdb6c522845887aec98bdd5",
    "samples/sample_08.json": "9e194411fbab6a16e32e34a17576c53dbb86b1404d4a9057612334a4ded78975",
    "samples/sample_09.json": "30b541004ea397e87900bcb272ccc17a9b383975237f1708a2f2c885d03544b8",
    "samples/sample_10.json": "f97b1710381bdb95ed98cf8657972fc4ac27cdcc57fc036d0439ede475301a7f",
    "samples/sample_11.json": "41d6bce97f8e800a2b93c2018e8c9a483c8fbbdbb521212dfda0547cbe83da51",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "skew_bins.json": "91e2eb36419fa2559e8694545f079a2ab90d3806171a11e605ce08122b1ca3e8",
    "summary.json": "913199aae0777c56556fea1a973e3b15257607642e79a6c211aea33df23ea23b",
}


EXPECTED_FIELD_HASHES = {
    "skew_bins.json.samples": "1b70b785a8bd54c23acd88019a02241edfdc1d227083715accd00361c7d7d634",
    "summary.json.tail_ledger_sha": "83699e8cbbeb0cc036a2a6b03208b52eeedff1f43b9d65d56232ba3e480dbf0a",
    "summary.json.total_assignments": "9f14025af0065b30e47e23ebb3b491d39ae8ed17d33739e5ff3827ffb3634953",
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hexadecimal SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize ``value`` like the reference harness (sorted keys, compact separators)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from ``path``."""
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load every mandated audit JSON object from ``AUDIT_DIR``."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


class TestInputIntegrity:
    """Pinned fixture bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every input file under the domain directory matches its digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Hash-locked outputs."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file matches the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Nested summaries remain stable."""
        for field, expected in EXPECTED_FIELD_HASHES.items():
            head, sep, rest = field.partition(".json.")
            assert sep, f"bad field hash key: {field}"
            fname = head + ".json"
            key = rest.lstrip(".")
            obj = outputs[fname]
            assert isinstance(obj, dict)
            fragment = obj[key]
            digest = _sha256_bytes(_canonical(fragment).encode("utf-8"))
            assert digest == expected, f"field mismatch for {field}"
