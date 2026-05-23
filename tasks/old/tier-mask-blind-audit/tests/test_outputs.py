
"""Behavioral tests for tier-mask-blind-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("TMB_DATA_DIR", "/app/tmb_lat"))
AUDIT_DIR = Path(os.environ.get("TMB_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["mask_rows.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "e310c0eba1ad317ad47199c2b89f1e1a7578d4ccfbd7b63c725263a5f845960b",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "90d2f500b2c59c8e48eb1943ceaed47782a7b354502468fd6b70edd1d61041f5",
    "items/item_00.json": "3ee0f80d6b3f4ec1efd7cff47af76215d559a5c2f09cf9a5b80c30da4dafa3a4",
    "items/item_01.json": "f9c3dc8165bf91ad787cdde857b2c0038431d6f0606265a4a55f74cd2fac2a65",
    "items/item_02.json": "83875769b9f7200fbc89001b389aac6cb22cc7a0352ca6aa495189a497dc12ad",
    "items/item_03.json": "2bfd77d9c4dad2c50c8c53cb554b3a7b591bd0be82cf0b97f321fe48cbc2d725",
    "items/item_04.json": "ba2d81621669ec0d55fb1ba3808afdfa62ad89f51250fd7a16de2619cfe58ff2",
    "items/item_05.json": "aa7cb85b8bad5c15871e5f3f100d380af7df9b19086bfdc5c4e4461607f19cb2",
    "items/item_06.json": "3b9d0f96164c4247cda19d4e2b648a22bc29f9d0519914fc5092790a51c1c8ba",
    "items/item_07.json": "9bd0dea12018aae399fa0915d1962ba64f283043b1ded64f8b3d94066d21be0b",
    "items/item_08.json": "2cb44ab12b0989603f569444aec0c8882133ff06e2890b12c904af620c07867f",
    "items/item_09.json": "53285bcf6409480525339072f08eb927b6fe431cca3b7127d5396738d068e07e",
    "items/item_10.json": "2b7dbf445698bc104401c371eabdc8f8055ce34928c68bf9dcb1edced944e4e3",
    "items/item_11.json": "3775a6bdbcc544399826b2b6c987e47ce04174435932ba9cdf2fd7c1f4a040f5",
    "items/item_12.json": "0cac7db849bad1629fe348857f57f5047e4551f9dfb54638fa21eed9cc9de8c6",
    "items/item_13.json": "1be26d87fff095ec8edd38ecc9bc9ad2b72d81c4a434b14ed5da288ced8bf8ba",
    "items/item_14.json": "6552cfebc360302c5781e67e4e7925c310cf4083bc1c9a6e862a438366ef03a0",
    "items/item_15.json": "b4c15053fc4a5118b6b9739bf8433e4c3a00cfa2c00519f4d1646e1b4f05d02e",
    "items/item_16.json": "a0ae08ace08013b9ee8b294f169d91450bc5c375a66c76b438347d49d763ea50",
    "items/item_17.json": "2e05097f4d9e1bd8bee6e09d7b7fcdeea301ad38a6ec574b1a34f321536a7cf9",
    "policy.json": "652e2fa2b17ff70cc8b70c80014cb0edcad944b7d4e16d8c84120af3ec1c936a",
    "pool_state.json": "9a7f2a9ad8bd7950b14170e0d288df2442005dc5f156a84d1b033bb8140f6cb8"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "mask_rows.json": "15d0cc352b6fde4df8e113ad5b484a6e2debbea931a6071159389532f25f784a",
    "summary.json": "a6573b3110c192612e225246983c24e1c54226f69d2b0d4ab9a2456b286d7be3"
}


EXPECTED_FIELD_HASHES = {
    "mask_rows.json.scopes": "893cb11e5f8502ad8052794e41b175a67fcd0c39645f94b972f93a619d798d6e",
    "summary.json.current_day": "d59eced1ded07f84c145592f65bdf854358e009c5cd705f5215bf18697fed103",
    "summary.json.disabled_bits": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.json.popcount_sum": "9400f1b21cb527d7fa3d3eabba93557a18ebe7a2ca4e471cfe5e4c5b4ca7f767",
    "summary.json.scopes": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a"
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
