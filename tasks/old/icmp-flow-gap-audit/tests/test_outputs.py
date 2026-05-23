
"""Behavioral tests for icmp-flow-gap-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("IFG_DATA_DIR", "/app/ifg_lat"))
AUDIT_DIR = Path(os.environ.get("IFG_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["flow_gaps.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "4b9efac5c3bd526ebe664d77a5f38cb17baf7998cb24ff68084b8b4a57cb8a51",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "69c3a11bbf286b91342fc4a18ae32b74e3a2b2e193f0615ff074f158f640f59a",
    "items/item_00.json": "12fff1dcbed0b118178750ff38efd7f6041db92674a69ab4bc4219586700e536",
    "items/item_01.json": "04bea89aa7c20288680d59de92765eb309b19594e1a8ade7a985b1b483fb531d",
    "items/item_02.json": "95e804b111429de8977b1257d74e0182195e20fad4e0de240d4e812b2681258c",
    "items/item_03.json": "0d773b62201b99b817834a91477e96ca219a75cbed90d92642d8040fd771b3b8",
    "items/item_04.json": "cc455a55023099cb0603a4a7bd3f040f0605b3f436df4a79f16448b8ca8e0364",
    "items/item_05.json": "e9e8d771c12767e5b1bab173d9efc34b34be70274a6845834030a159d0024cdb",
    "items/item_06.json": "af7ee182f179fa5408ffca3cf14458e3c879403953592ca0849b78310af3705e",
    "items/item_07.json": "81257864d96f2aec6b13946d91b6298491526a314f158e95c4e45ee5687ec49a",
    "items/item_08.json": "a542f24ce8a707ea66484bb6945791737a5b04bebc7376e0821a8a413f64ed9b",
    "items/item_09.json": "3b8c1317ddfa875b4e89e65bbd945b8df9b30e733de0a928ec5f6f704ccbfba0",
    "items/item_10.json": "0c26e6cfceca7112a2d224427b3535d0a986ba9e483e563a3bfde9bb955cc101",
    "items/item_11.json": "4d31ab55013e3d6f96dd2b120cd0b5d00145a568f1a273ee24186e88f2a03017",
    "items/item_12.json": "be527ff32f05d0d32f12230523a5bb9b865df0b6ef520f65ebd0a002c8929ee7",
    "items/item_13.json": "ebe50b93da575ed6d6fd26d16b048913ea6e234b4ecb56aa3cc8887040aa686b",
    "items/item_14.json": "e3f2b304af92f95ea401b65ec88ec4d81122f68453a13efe12faea314f96ed68",
    "items/item_15.json": "7bb044838abb88b7add80f3a8c4703d7897838f6f6428b6b4bc9b5a55ad4eb74",
    "items/item_16.json": "8f2ef76ff843a8af3cbdda882b0f96a8e8edd7bb869fa6093a260b729cb16229",
    "items/item_17.json": "b01b008ada6d0669dc1e517f0b11cc8f8198c64c3b3c3b4040751b11156e2cda",
    "policy.json": "fb17b88c0d081fd58def129feff57a1d686960e00d49943c3efe01372887e47a",
    "pool_state.json": "e693a6e7c45482e0d5ac0221b8007ae15195a5e34119259c2af54766244709bb"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "flow_gaps.json": "a4fe0e15895cf2e2d20d6889946880ad3d93c7c5732c4ebd14ae98293a7a7b2a",
    "summary.json": "f752bfef61e9eba833b231bf168d8f149a24709358266b8631e2e3be5fd4e254"
}


EXPECTED_FIELD_HASHES = {
    "flow_gaps.json.flows": "40496506d48f698d9832a31db8c2a64840c657e3d7317dc2d9aef466f0c2eee7",
    "summary.json.current_day": "e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683",
    "summary.json.flows": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce"
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
