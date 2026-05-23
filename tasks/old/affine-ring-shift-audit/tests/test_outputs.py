
"""Behavioral tests for affine-ring-shift-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("ARS_DATA_DIR", "/app/ars_lat"))
AUDIT_DIR = Path(os.environ.get("ARS_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["plain_ring.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "b3c38d310189deecbd127f2d0b46aea7fdf60fc9f6c8dd1cf6f3d78d2fe42416",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "04a2cb4c55df0d864a5939d4057dceff80a7b2af9e61f3c26839f1931a214d5d",
    "items/item_00.json": "0b9369efc793b09554190e74f3c2db270c89e39328270cdad6fc56e5b8ee8be5",
    "items/item_01.json": "265bc8c106012ee54153c2f9f12d087cfc182923b87eaa7617a4fcba838cd0ac",
    "items/item_02.json": "0fe0d9d47cf724c04da9414e55a87631d0acf204f15212e8d104459e5e9e609a",
    "items/item_03.json": "1d0affd31ecc42740637c672364091e67c4598b2c0ae26ce8e54698bfa6f3e9c",
    "items/item_04.json": "edcb9264ec1f6a5560852e00b78aef4a49a5c70a05ba84b7022d21c658cc5673",
    "items/item_05.json": "bd46f324d1e38575219ae3f7df4330d5c870098dc87c2d67a1aca96a3466288b",
    "items/item_06.json": "1f9fc5886ccb6f69df987a249886c8716fa1c4317eb8e263b34a4ce4de82ce61",
    "items/item_07.json": "faf1752a7a8a19e3241e135be18afd29b4668ee83ff505a6bb1c36534d1e2ba1",
    "items/item_08.json": "8a15fc83422a6f89e76167f474d97a0438722e99916e53ea195739e94c42fe49",
    "items/item_09.json": "1624a1ae95eff3a5c74227b694fedf0955f08c96bb49ef6647d184639682763d",
    "items/item_10.json": "044d642eb055706b2fe8040e30565c53dcfcbf9df4bc3a4514b01cba4fab5644",
    "items/item_11.json": "da3f292828204c1bef576eff2da2fa34ab987a9113eb3e53b07e560b7cc3934d",
    "items/item_12.json": "b4d326673361510f38a7a4d729af1890c5bc4332dd9e99b0ac69db3a89aa8dbb",
    "items/item_13.json": "4f01b2dfd79080eeb1faf2bc8c97d027222675f51bc62c2add201fa6e9555d1a",
    "items/item_14.json": "a6280788922bddd912dedea98901f9408d45ff4bafa317d1be79148e77f91093",
    "items/item_15.json": "a84445d082b8ce4dadcea253089ebf23a35fd26647a4b5c71ee799989b7a2aee",
    "items/item_16.json": "2c7d8ad368c8e7036685c92015f84c11b994c0dd8c7ed3f27bef498cae5a540f",
    "items/item_17.json": "c76821714f5fb36c2f7455623063d1d9a70799eedd4d33bea6943b5b7bde8754",
    "policy.json": "0b5cba4303422795ef6e4471e24c8b6a7095accd1d02b5e025129d01315f38d4",
    "pool_state.json": "552a959d901c48cf8c9d186b4c794f880f192cc978e446cf312461bc0f56e19c"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "plain_ring.json": "faff0f570259f597678c8dd9a4b6407291ed1d61480076f1117e6ef284be0e39",
    "summary.json": "63e63c243eb7bf18d12c2d18c6153b7b7e7dd3dff97666b044b79ccf936cb26a"
}


EXPECTED_FIELD_HASHES = {
    "plain_ring.json.items": "530ad213672233bad293d23ecaf58309d30c213634d77570f60ef60011205b9e",
    "summary.json.current_day": "624b60c58c9d8bfb6ff1886c2fd605d2adeb6ea4da576068201b6c6958ce93f4",
    "summary.json.effective_rot": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.json.items": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a"
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
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
