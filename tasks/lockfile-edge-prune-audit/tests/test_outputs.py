
"""Behavioral tests for lockfile-edge-prune-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("LEP_DATA_DIR", "/app/lep_lat"))
AUDIT_DIR = Path(os.environ.get("LEP_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["lock_edges.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "091f68af397190246da91c71e49e4b9580a5eef62e286a16e5ada7f4f8b97607",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "efe16f41c87c78bc07f5461faad8da951f4355723807d7e26cc16e622fc5eb67",
    "items/item_00.json": "d238d8b6e6526e57e9b8fb5c41c3c1fe558e88c379ac06594187a7012aabf398",
    "items/item_01.json": "24109269a7c46da2a3ba9f119f765dc8265993c84a6dabaefc57f5fdac73a755",
    "items/item_02.json": "20e804d483cd89ee1ff45c2b6c029facc2b8047f62b778539dc9334e409301e3",
    "items/item_03.json": "cf473b4151f4097fe8a4bf4e081a056a6f4fe669850adea26aa792430896c5e9",
    "items/item_04.json": "718fae6e6d06bf910b4cbc5f9b655bb3f6d8905bd572e041374f59a6bcc8bfc8",
    "items/item_05.json": "cab002a0c60822b69f769ee7aa10af3a3495dd77747fc1c7ddb58834ee23e049",
    "items/item_06.json": "2c0916a6e833d226beb00df9c2a33cf243f00629b067e53a0fa7207b91b34dbf",
    "items/item_07.json": "1c4fb123d3ecdb999600be3c43f8563145efdda57f1d4fa629ed19b1efebc45f",
    "items/item_08.json": "a1eabc370ecb20637466b9cfc69185e4b44d81aee472a472399cb62d5567d7a3",
    "items/item_09.json": "c1219008161165f72f83e89f87815d8de6f20d7246c9140ec24f82ff124e731f",
    "items/item_10.json": "57c1b8ff86f738e689f8395674bd525ae1715679de82a47a02755d8f86a6e9a7",
    "items/item_11.json": "aa98b1d963f7ad658428b51231aaca60ef51d362133f97b289c134b5f5fefb2e",
    "items/item_12.json": "119f0fb599d8d7bc53a900816bab5eca8e18a714dd51e37593b43c1fd4fb55f9",
    "items/item_13.json": "6fb0a8029c429d8e3b8bb82f994799611dca292d603604f67800f98a68401f75",
    "items/item_14.json": "f4065796bb3fc7dc13c0194c925232a121676aba742a2dbdf180666a090a386a",
    "items/item_15.json": "20870443f4551dfff7450227db8ba979c994023fa38cc647a6ebb87b2e2a1331",
    "items/item_16.json": "5d586cf71d20fcf82dcef91641daaea43b8d9ee1e04c5cd4c007284f4f8105bd",
    "items/item_17.json": "28a1b08fbb90b3998d586d2f69f4020f5b2fd375927619d011c4180216e8f14e",
    "policy.json": "8d0e7d20d312873f831a25a7cca60da0bc756f6f421de0d6bb4295a2712e56df",
    "pool_state.json": "d9f9aa815dd131e8e124a32ff7e6acaf7bf5eaa6936dc5871485969641dd0dc7"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "lock_edges.json": "fa60f90e9245faaa1f8b4d6851710136321a75f7469fac6a536644a5da18fa9f",
    "summary.json": "18f9b0322369933b6865b208b4357500946615f36f30b6a9b23ddc8860979a91"
}


EXPECTED_FIELD_HASHES = {
    "lock_edges.json.edges": "8ed8362a641d21e90419650027cfb69c87f40f2412149ad3f97087a6990e2a19",
    "summary.json.current_day": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.edges_kept": "e629fa6598d732768f7c726b4b621285f9c3b85303900aa912017db7617d8bdb"
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
