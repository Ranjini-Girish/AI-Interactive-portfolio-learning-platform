# scaffold-status: oracle-pending
"""Behavioral tests for latch-echo-bin-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("LEB_DATA_DIR", "/app/leb_lab"))
AUDIT_DIR = Path(os.environ.get("LEB_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ['latch_bins.json', 'summary.json']


EXPECTED_INPUT_HASHES = {
    "anchors/east.json": "95a9cb71c8647837804a96549a71bcd5859d24182396cbefcdc9b2a93c97ba97",
    "anchors/west.json": "a4f6d3014b11f77ca64a1c89d914caf3335510f49fb36f6c85c6b23db62108d9",
    "ancillary/extra.json": "66e0b05e1b6ab764bae179cd10b2453c3ca980eb095f89401c38ff4f021f5dbc",
    "ancillary/meta.json": "8c183cc752b30a37abd323114a0ec6775a191c5b2d886e5aad85589a6d31ea81",
    "ancillary/notes.json": "35939c1e11de41c34c3ca02d0b877737dd0dd3fec8b669fb719b9c84de2a61cb",
    "domain_layout.json": "6c322304d0e092797682ec43070b1a8374ac38b05f01e4036a2b09dc966c7f39",
    "incident_log.json": "d91cb68778fd4deac977670dde84b594e4ffeb0332fc9d0345767aad3831df3f",
    "policy.json": "3044fbe2cc5dcd5517695c0da622d30fa1575a6c4961edf7ec4d0a7660f3f1a4",
    "pool_state.json": "9f22c46193ca7e2bec3bf0fdbe27e8f0fbd7b2a2f4e4fc6b74b151b668dc6f68",
    "samples/sample_00.json": "0ff0636c66eae057615dc4f498e13069a8917f640a2cb80b6a5b0f80997c74d8",
    "samples/sample_01.json": "09430c1192487b8479c972b7f8c6f54667b75ed86dc4cb73086aa3c14af68cc9",
    "samples/sample_02.json": "c0919ae596827bf5eb6f71df397db1dd3ae39f8d6883091205b6484e9b1844ab",
    "samples/sample_03.json": "fd118d7f13058576c550f831a2f4d3e549c0507e60aafcbf0d778828fe336af8",
    "samples/sample_04.json": "15e8a77b4da797ff86faeb053b88b526df87354a0d1fd0b9196476ab755c095e",
    "samples/sample_05.json": "87642c823a07cf8bfd175b274e470999e05dd42fa80af0a8416e9619c3b423ba",
    "samples/sample_06.json": "619b766173f05569046c9ceb3f4a105e5a59cfc3f8d13f84dda54972fd229733",
    "samples/sample_07.json": "2be02010b16071695869acb526673071f121b15c61b351542907f137af922f91",
    "samples/sample_08.json": "1d6095a4263873e77203fa9d2da6fb7a5c393651f3f09a4589016d5fb24973a4",
    "samples/sample_09.json": "dc8bef283a3cbf40f393691c82f635f11da342f07cdc04850531146689ab238f",
    "samples/sample_10.json": "f21b56ee91bfec483450f86e0ec4832cf5e44669b558f727f87db70029046ba3",
    "samples/sample_11.json": "40c1c4dde58a2c7c6c10fad9ffdbe3a9e85bae31b0dcbbcbb760579c29dd6f33",
    "SPEC.md": "66f3921e2cb07e9dbb97e0d849489d949cba10fd995c6a8ff5bf30ba311ff75c"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "latch_bins.json": "c4319255ee081ce263cbd07f8dcb5455b6b15ae3517b41bb31411e11df864454",
    "summary.json": "5e7505d05d31de2a5f465db95ccbdb86760040fc51541df2466855397866073b"
}


EXPECTED_FIELD_HASHES = {
    "latch_bins.json.samples": "50459402a2a3627cae65b8759ac3a8310580dee866e966f3bb46d15947918e15",
    "summary.json.tail_ledger_sha": "a6a5a1e79374954569a4284a769432f35bc2674e024b094fc7c593f0339169b7",
    "summary.json.total_assignments": "9f14025af0065b30e47e23ebb3b491d39ae8ed17d33739e5ff3827ffb3634953"
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

    def test_echo_max_enabled_in_summary(self, outputs: dict[str, object]) -> None:
        """Policy echo_max flag is true and summary records it."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("echo_max") is True

    def test_latch_echo_enabled_in_summary(self, outputs: dict[str, object]) -> None:
        """Policy latch_echo flag is true and summary records it."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("latch_echo") is True



class TestLatchBins:
    """Semantic checks on the primary histogram artifact."""

    def test_samples_object_covers_every_fixture_id(self, outputs: dict[str, object]) -> None:
        """Every sample_*.json id appears under samples."""
        main = outputs["latch_bins.json"]
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
        main = outputs["latch_bins.json"]
        assert isinstance(main, dict)
        samples = main.get("samples")
        assert isinstance(samples, dict)
        for sid, rows in samples.items():
            assert isinstance(rows, list)
            bins = [row["bin"] for row in rows if isinstance(row, dict)]
            assert bins == sorted(bins), f"unsorted bins for {sid}"
