
"""Behavioral tests for beam-split-phaser-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("BSP_DATA_DIR", "/app/bsp_lat"))
AUDIT_DIR = Path(os.environ.get("BSP_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["beam_combine.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "50a6437039fbdb2aca3077c874973403eca7e3070c2336055bd1df36561a32b6",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "73efe4e5a4c4187eb4d2b393652280ef7a16b5f04a9cd60e0ad797d4a664c3f3",
    "items/item_00.json": "6dc526c0dd3848d6db5e87a2411d0b29df2ad1c0f34e72489b03b4ee10e50fd0",
    "items/item_01.json": "c245b0c11a15f30cc8b8920edb52ef60530e947f6c4f4fe4ad33c40c8973711e",
    "items/item_02.json": "9c6d42909d0cd9692fd5a2ba7aee61b0606fc6b01d11ab14912e2c93b6378898",
    "items/item_03.json": "cabe0e4a28c9dcdb8a6be8d042076fd46a92c4556ebd6246f29cd048f5042378",
    "items/item_04.json": "a43882fd89ab59e6dc6af5ee83faa6127af686c2dac68ffa218224d12ab5c510",
    "items/item_05.json": "43673a665c12e3590e5480d45ca82e918d19a9af1d17c17a28097fb0e803c94d",
    "items/item_06.json": "9c472145dbe78eafa97d689fb3b6f0ac85597b1bb40d2fb17cd784ed8f54ce0e",
    "items/item_07.json": "c014fb882a68b595186de810c5b70e6510cea5bbe7982634ec4c6d59103141c1",
    "items/item_08.json": "7575b763405a7371c732ce0731aa2ce94d672f36e3a241c9a3d1455a3ac96166",
    "items/item_09.json": "9ba4652ad14230708068732f9a1fae42e14f01c1c189d8dbd3003f5edf60f7fa",
    "items/item_10.json": "c68d266d6761d6283b72432a1b56e78636f3cbec9e7509fab921856a888e636c",
    "items/item_11.json": "caaeb7a22b4da634bcd6e92a2eddb2d6b28830be5ec51dd163a9ed15950be959",
    "items/item_12.json": "b2614f34477dc6ba03a4f5bc123aba332bd0e3eb88b07d106f944bbd0518ec49",
    "items/item_13.json": "c683133eb643d802fa21063bc9152b6f1aa34816f5158d0d9454a24585ff4a80",
    "items/item_14.json": "ff78aee4b7e33f90af09578cb9c270bbf4fd6b28b2153e7ff802fffdf2fc244e",
    "items/item_15.json": "fa018192d815cf22c127a7cc6c10dd977c2493a11e3c637763ed16582d5cf33d",
    "items/item_16.json": "71e4eea25a6777802388998feb080c42755360f06d53689dc656f4388b7d714a",
    "items/item_17.json": "c087ba99d637bbc46e3a90d3f6e2be940b64f0efdde32d7ccbb0cfa7f69de3cb",
    "policy.json": "ec937924e0c9e6bacf9d5e45a7c17cba592e3296850f201248a4646afb3a05fb",
    "pool_state.json": "a7c6e0d75ec31c191f5d8247db9bbeed76431320cfbd1c44035817c558a158ed"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "beam_combine.json": "2552912ce6511786529cbfbc5dac98d79ef474d34b644a4f936923385df487f6",
    "summary.json": "bc0710995a7618f81aadc762dd567196ad707cd13af10b8549331ad14aea1946"
}


EXPECTED_FIELD_HASHES = {
    "beam_combine.json.beams": "14ac191b8f82501f8d4e5f2f0c46d189bad18a81463933f5214e18880da41535",
    "beam_combine.json.combined_phase": "d6d824abba4afde81129c71dea75b8100e96338da5f416d2f69088f1960cb091",
    "summary.json.beams": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a",
    "summary.json.current_day": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d"
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
