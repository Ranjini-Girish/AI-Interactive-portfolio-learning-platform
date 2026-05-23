# scaffold-status: oracle-pending
"""Behavioral tests for slew pace floor audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SPA_DATA_DIR", "/app/pace_lab"))
AUDIT_DIR = Path(os.environ.get("SPA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["floor_bins.json", "summary.json"]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "ad7c124aa95ac50c6545378d12743e5d7ea804efb5e3f1f30661ef7e0ecce9e6",
    "anchors/north.json": "86213b1fedd4f2489954650db19e45563814477d51cd72fa6ee7aea10a9d882e",
    "anchors/south.json": "b535565aed051ecb2be962b0e574fa3809b6c8e416098c355c988959af9d4aef",
    "ancillary/extra.json": "427f9e4e009a2cbd1c101a9a2384161fd994edaaa9fbecc610a09c2f9a91941c",
    "ancillary/meta.json": "9c15c8ca66af89345acbe0e29621281a72a20f56768ff093f820f808e53a52e9",
    "ancillary/notes.json": "119a444a36d8ebe48fcbfcbba3e4efd3ebb824e1ae3b9c7252468b3e2c2b9303",
    "domain_layout.json": "16390ea8307d8e320246139dc0130d5bf1749991545dd9c5c4e0f56d6c53848d",
    "incident_log.json": "028f09f9218ebe6e156df8163ef3dcec23f95543f7b37ec8c1e4c7dd14a7061c",
    "policy.json": "8d080d5de1797ced94805ce9a3c9398f888b4977b776db121c486187eebbf5b1",
    "pool_state.json": "aca4a432e86374c9817cd6e5b0c37e605a1cc68bd6cb9932ad0ab730d5c2a962",
    "samples/sample_00.json": "e0fdebdd4bd9eb3ddc65356715a3703527844399a9b4414f1c676cbe6e4aa2f5",
    "samples/sample_01.json": "c2072007e285dab26f621248be739b97797d88febeeae9bb47bd3e5df0166a89",
    "samples/sample_02.json": "304bcc2ec1ca6124fd14d60486246afced327e8287582ddba4a9a539884d93b5",
    "samples/sample_03.json": "0238127605bd9e4c7fe5b124bbe3fd915d44fb26bb71c5c07a2aa6cf0c73892e",
    "samples/sample_04.json": "e343ec45750cb2fc9c0eff5eae83bb99234de9873db0342b985273c0904b37fd",
    "samples/sample_05.json": "edd9e5e890f970571032e3a08578293da16f5a60c47e432e68eeff69dec08a00",
    "samples/sample_06.json": "a6065dd39ad85d4a2532a964d40680e5cfca10eba8f05d11d3f69ed95fd269c6",
    "samples/sample_07.json": "dd1392048f5a21d133387472509b48442e60a809fc841c98cfb644bdeeb4a546",
    "samples/sample_08.json": "48ed8c492588b4b893db8ce9e108411016f858969772393fe75c10e378ddfd44",
    "samples/sample_09.json": "a859cc5ea32f92e3653bc79435afdb496f0f286216d49d84f6772ad1025cca33",
    "samples/sample_10.json": "5da73a4581e92f111d87e63978f666443e08a6b69fe50abfd6dfe448f8a528d4",
    "samples/sample_11.json": "a45120bc5e81e8a2fb9244832f3fabe57435c993084e8b82c66d55f264b4074f",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "floor_bins.json": "a6d7b8bee3ecaaaa9e80e077b2d9815e413243168e617fd4449679f8abdca74b",
    "summary.json": "74ccc3397c7e7b806a21ce20c37c8c2dffc86c34ffc1aab2a9257e37b299bcf5",
}

EXPECTED_FIELD_HASHES = {
    "floor_bins.json.samples": "89409db0e13eff0a731e7e2fa2931c14e20d8bc70363dfb31aeaf96957c561f2",
    "summary.json.tail_floor_sha": "b5f685d2d0c96d62658a9e8b64f53353a6967bb372602df7821c97d3f93f651c",
    "summary.json.total_values": "98010bd9270f9b100b6214a21754fd33bdc8d41b2bc9f9dd16ff54d3c34ffd71",
}


def _sha256_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize like the reference harness."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from ``path``."""
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load mandated audit JSON objects."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


class TestInputIntegrity:
    """Pinned fixture bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every input file under the lab matches its digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Hash-locked outputs."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file matches the canonical minified digest."""
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


class TestPolicyFlags:
    """Enum coverage for policy toggles."""

    def test_cap_spill_enabled_in_summary(self, outputs: dict[str, object]) -> None:
        """Policy cap_spill flag is true and summary records it."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("cap_spill") is True

    def test_pace_echo_enabled_in_summary(self, outputs: dict[str, object]) -> None:
        """Policy pace_echo flag is true and summary records it."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("pace_echo") is True


class TestPrimaryBins:
    """Semantic checks on the histogram artifact."""

    def test_samples_object_covers_every_fixture_id(self, outputs: dict[str, object]) -> None:
        """Every sample_*.json id appears under samples."""
        main = outputs["floor_bins.json"]
        assert isinstance(main, dict)
        samples = main.get("samples")
        assert isinstance(samples, dict)
        fixture_ids = []
        for path in sorted((DATA_DIR / "samples").glob("sample_*.json")):
            doc = _load_json(path)
            assert isinstance(doc, dict)
            fixture_ids.append(doc["sample_id"])
        for sid in fixture_ids:
            assert sid in samples, f"missing histogram for {sid}"

    def test_histogram_rows_sorted_by_bin(self, outputs: dict[str, object]) -> None:
        """Each histogram list is sorted ascending by bin."""
        main = outputs["floor_bins.json"]
        assert isinstance(main, dict)
        samples = main.get("samples")
        assert isinstance(samples, dict)
        for sid, rows in samples.items():
            assert isinstance(rows, list)
            bins = [row["bin"] for row in rows if isinstance(row, dict)]
            assert bins == sorted(bins), f"unsorted bins for {sid}"

    def test_summary_total_matches_fixture_lengths(self, outputs: dict[str, object]) -> None:
        """Summary total_values equals summed post-mask value counts."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        total = 0
        for path in sorted((DATA_DIR / "samples").glob("sample_*.json")):
            doc = _load_json(path)
            assert isinstance(doc, dict)
            total += len(doc["values"])
        assert summary.get("total_values") == total
