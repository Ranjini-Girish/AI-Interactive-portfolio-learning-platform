"""Behavioral tests for bitmask-anchor-fuse-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("BAF_DATA_DIR", "/app/baf_lat"))
AUDIT_DIR = Path(os.environ.get("BAF_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["fuse_ledger.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "9f0eec72477c150c7feb740899019c70111c3b94c8179aac0dc3c595a11dfd8a",
    "anchors/a.json": "40fb7a54852591e46ecd6277215e779ba13c64fb27d0306a44c54e71c6c7d72e",
    "anchors/b.json": "40fb7a54852591e46ecd6277215e779ba13c64fb27d0306a44c54e71c6c7d72e",
    "ancillary/meta.json": "a515956717967bf2ce4531f69c7c880aa4b2dc82626c02ec23d6d3e0acab174e",
    "ancillary/notes.json": "e46048bdda148176042803a18a63011fac0ff89139c7668ccba1b1ee0e7535e5",
    "domain_layout.json": "2f1cadf8e8de320f47ee73364a2d4eb2d348994573f09fbbaa402f0d3523686e",
    "incident_log.json": "3116a83f9af863f9866a0bd5c307ae040b8e01a5483c824754fe49d1ccb7a6da",
    "items/item_00.json": "aca187c581aaeb28cc01a8c54300138edb3d9d68feab274e7fc609475ead9323",
    "items/item_01.json": "e5fa01005363d7d7840701d71cfe933803ace093c6332e39d123831a04dbbe40",
    "items/item_02.json": "b79d6030b9fb7192e53a828127638bee5a55d8d4a4c2b29d2df75b505245ccf9",
    "items/item_03.json": "78aa01dc9460abf1545ecc3793e5c573b60f3b3d322f319ed46946146750735f",
    "items/item_04.json": "513eabe8234b77451b9634a0311153b67532fecb589856a41b6a5fe99415180f",
    "items/item_05.json": "a46fc1228f271b2eff764553b9c221ead3bb4541dc407a485c40a9bd0d073313",
    "items/item_06.json": "ac926b1ed4dc3a77ff479216276f9fabc6f81aa8c383b0ec09f85d2304521cac",
    "items/item_07.json": "71e754228db1c27097b0ad2de99b6934a2739dec9a5e5a2aea76a13e321318a7",
    "items/item_08.json": "98a6cfba1e26ab09dd38ef1d6606b690eb85ec58ad74e504a706917f3f93789e",
    "items/item_09.json": "f471e0a4a975eb10297c487f6a4fc925faa53101b134522f930a9d2d883c2af6",
    "items/item_10.json": "1cacac848a53623f48770b844275bc1c828f95fad59a78b651219764304559d9",
    "items/item_11.json": "80ea0d408374f8f833faee90357841005636264035e74f4e0323f38f5e6de764",
    "items/item_12.json": "66275d79c5d2316608ab5ad60184d5735c7a17935beda7375f82312ee79d073e",
    "items/item_13.json": "9f24b6634e5003074d56a93fa241b509c5d814e64e331e6d06f24d10f9906097",
    "items/item_14.json": "4a0e526af6f9d59c80c1b4087da6be3f66b60b1b7ba41ca643aebf602f81d8ad",
    "items/item_15.json": "bc29a56fc109dc374209951186173867748098b57a84e67ec1a548e29b86c251",
    "items/item_16.json": "8ec8020e831221ebb144d1f461187c136e67faeaa836c18071939d3f503cb94c",
    "items/item_17.json": "a5256b85a1d8cf7ad29892c0bb929be04a306ea3a5ed60fcd48a71e6be779c19",
    "policy.json": "66473d0fd68cc2f60ad7a3a12d813b2ee2feb3518c7f247d765eb3afc5540ae6",
    "pool_state.json": "f8cd87f30ef19b1f2a157febf9d6b46aa0f3fc26b43aea70b9ec98b69668b29d",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "fuse_ledger.json": "4ed7025e867dc66c1ea80d345bd2219539673b497bde6da4f9754f0dd86f444f",
    "summary.json": "e2cf9328b4516d48cc298761d15cc663f59f35c4f941ed7d4233c39fa18d798b",
}


EXPECTED_FIELD_HASHES = {
    "fuse_ledger.json.entries": "49fdd11b7690c9201ba36b4338df68f8758282890188e8e1d9bd8b131207b377",
    "summary.json.entries": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a",
    "summary.json.total_score": "4f87f18dfc9a1a00ff7d832b7ecd52d7df4fc6f9d86d68d29ba8893152005f96",
    "summary.json.xor_acc": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize using the verifier's canonical minified JSON."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from disk."""
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
