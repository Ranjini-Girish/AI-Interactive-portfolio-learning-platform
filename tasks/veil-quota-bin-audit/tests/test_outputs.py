# scaffold-status: oracle-pending
"""Behavioral tests for veil-quota-bin-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("VQB_DATA_DIR", "/app/vqb_lab"))
AUDIT_DIR = Path(os.environ.get("VQB_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ['veil_bins.json', 'summary.json']


EXPECTED_INPUT_HASHES = {
    "anchors/east.json": "95a9cb71c8647837804a96549a71bcd5859d24182396cbefcdc9b2a93c97ba97",
    "anchors/west.json": "a4f6d3014b11f77ca64a1c89d914caf3335510f49fb36f6c85c6b23db62108d9",
    "ancillary/extra.json": "66e0b05e1b6ab764bae179cd10b2453c3ca980eb095f89401c38ff4f021f5dbc",
    "ancillary/meta.json": "8c183cc752b30a37abd323114a0ec6775a191c5b2d886e5aad85589a6d31ea81",
    "ancillary/notes.json": "35939c1e11de41c34c3ca02d0b877737dd0dd3fec8b669fb719b9c84de2a61cb",
    "domain_layout.json": "6c322304d0e092797682ec43070b1a8374ac38b05f01e4036a2b09dc966c7f39",
    "incident_log.json": "d91cb68778fd4deac977670dde84b594e4ffeb0332fc9d0345767aad3831df3f",
    "policy.json": "60670b933863d34ba7abb988abd7f681feb7b9dc892f07e1ece893b8b82703d3",
    "pool_state.json": "9f22c46193ca7e2bec3bf0fdbe27e8f0fbd7b2a2f4e4fc6b74b151b668dc6f68",
    "samples/sample_00.json": "acaeac9806440d4ef60eda3a69b9a8c30abab4cf8df1ad8b8f97cc3fc953ff7c",
    "samples/sample_01.json": "1453db9412e87f64ab031bcdb86566ec9f6dda0afeb004e15f3180a98e927407",
    "samples/sample_02.json": "5bd773aae1bbc1504c11421a82e68785aca13339763f9832d3344581b4d1603f",
    "samples/sample_03.json": "dfd2e59e3c01fb9d647e6a7196ef4e33f8f6b883c933f98cce459da30972b5ca",
    "samples/sample_04.json": "92b5f7c47ca9cbbcc2bbd9d7a5d8d52f43cbbae0eb2d237b63569abc58031da6",
    "samples/sample_05.json": "2840e034fce3569e76b2884056633ab38c0e71c2f5ee525036bfb296f58785a4",
    "samples/sample_06.json": "abe4d4940fa455e94602ce7f9b7d820cfb173b1f6c21bac4ef98f42920ff34e7",
    "samples/sample_07.json": "136dbde979c0cba9d27cf6714886e5ccb58b90a1153f226ed158efcf3e18a93b",
    "samples/sample_08.json": "68dc971852e654a23138b1a03fbb05029b89135609400c363bf817e2628527da",
    "samples/sample_09.json": "b90ac90fe7823fa4058e2b7461025707f17bc839c56e35861e558997cfe00292",
    "samples/sample_10.json": "878e1466dc532a1c2aa1318ce596eff4602e7464f858678a30cb77493ae1e59f",
    "samples/sample_11.json": "66df51b94c4456f0be98b11428475a7541184bba6bca32fd83460ae77f0339fb",
    "SPEC.md": "fba29f077b921b0fc5f74a30be70053a1e346836f845dd844e30a84ced0c91eb"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "veil_bins.json": "8fc6fbb25a171ab4c4734f065ba607a0bd178578e2a4799498e93ea26c65f1f5",
    "summary.json": "d5e5baee0807bff5c6cc52990d7e1df91f802173905bacfa30c2c5934ef36d3c"
}


EXPECTED_FIELD_HASHES = {
    "veil_bins.json.samples": "2b6472854625544490df2ba9c37b106d3243431dca0a1174aa7ff0f051ecdd1a",
    "summary.json.tail_ledger_sha": "f14f68a8de76552f699e8af62e31edc6b83732e950a3485c9a6951b116eb2087",
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

    def test_veil_spill_enabled_in_summary(self, outputs: dict[str, object]) -> None:
        """Policy veil_spill flag is true and summary records it."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("veil_spill") is True

    def test_veil_cap_recorded(self, outputs: dict[str, object]) -> None:
        """Summary copies the configured veil_cap integer."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("veil_cap") == 9



class TestVeilBins:
    """Semantic checks on the primary histogram artifact."""

    def test_samples_object_covers_every_fixture_id(self, outputs: dict[str, object]) -> None:
        """Every sample_*.json id appears under samples."""
        main = outputs["veil_bins.json"]
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
        main = outputs["veil_bins.json"]
        assert isinstance(main, dict)
        samples = main.get("samples")
        assert isinstance(samples, dict)
        for sid, rows in samples.items():
            assert isinstance(rows, list)
            bins = [row["bin"] for row in rows if isinstance(row, dict)]
            assert bins == sorted(bins), f"unsorted bins for {sid}"
