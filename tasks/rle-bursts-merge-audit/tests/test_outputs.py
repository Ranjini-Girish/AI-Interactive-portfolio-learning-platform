
"""Behavioral tests for rle-bursts-merge-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RBM_DATA_DIR", "/app/rbm_lat"))
AUDIT_DIR = Path(os.environ.get("RBM_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["rle_merge.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "3c19d3fac757f4aa01bdf8b6e742d07ba5702fa3501206c6ef9f2d0c6adeda1e",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "4e136a9be1fa1022eec8dfc39794898852cd86895b9a5adad345179688da8132",
    "items/item_00.json": "657bc8122f271c7ee60f3d3b50961623e19723f19c4c17d08c8d8569891d22e2",
    "items/item_01.json": "9c0daf8c8d5d1cc3330ff98cb2b21da4938730442684d1a2f7d86f7982c568f3",
    "items/item_02.json": "6ee23a3095350e526d3d13b9c8cdb788f6512b84cf31b907f4de249162b34b41",
    "items/item_03.json": "cc8ea49d7d2a22697b2b07471a71a75233ff41bd25f5c4a46ab798131310f1ac",
    "items/item_04.json": "d5b8db0148010048915cf4253387ed5c70a8a9c2918fa60df33249523b063424",
    "items/item_05.json": "34c41f8494b3ddc6337b88e91d463e577cd2c39597278586ebb51f91217a64cc",
    "items/item_06.json": "8f18bd7460b8b6ca5a1cc1eb9a10aca5552d7f2c71c61eb0bb77c4528c653833",
    "items/item_07.json": "c548ee062eddc1e77b7edc0e906e884357cabbf0c91e823e69d8b94a0087c130",
    "items/item_08.json": "ea62ba72b7d3667af6ed6043ffb875d43b12158f4260b7b6fcdf61a07eda0e44",
    "items/item_09.json": "93f143b0d1e8346908347157e496d37046a41997338233c14d816c3a34061fb5",
    "items/item_10.json": "fa8cbd99964fb19058233ad2501033aaf96d81c4f987d2514b7ed95b8a529a83",
    "items/item_11.json": "89654f59c30b36c435f76267812c24aae509033a3279b521950d977a30b4f2c5",
    "items/item_12.json": "b054a71747804bfd74a1cfecdb990a0d2dc6f339eb63103b4ee433f3c450153e",
    "items/item_13.json": "dd6466b14ddd031b1b876b4504be3cac5a1938dd3d3842bf09c2b8edb2f70d1d",
    "items/item_14.json": "3b20037d030bfb65bd5f6c1c03f1a9b8681bfd335d8b0da38fa00ae6b4667e64",
    "items/item_15.json": "8f98f528c4fd307690b218f364ccc4acc6030b2ed388b8d1fb5a44733801b282",
    "items/item_16.json": "4994bb7bd85f99ae638ba4601ffb2a23c258c589e920bb611407d03d8abe0dbf",
    "items/item_17.json": "df74381ba5ba46bb98e9539a2c20b4e1f10a11a24c8368d522ced2461458237f",
    "policy.json": "cc7f999ef43ebd3c8c0e41b375c6a61e437ba40eab675bae8f9ff0a6e5904cc8",
    "pool_state.json": "45b5e7e87cafa2f521d4565e6573484beeea1b2cb99443f96d191d2edc8927d8"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "rle_merge.json": "73e5d433eef61b5888196fa781dea980c9138cfa5317f7d610f8f22af6a1fa69",
    "summary.json": "e6466e2c07667c3106bd3bc27c45606d9a1b82fdbbb2212e730fdf65f5992067"
}


EXPECTED_FIELD_HASHES = {
    "rle_merge.json.runs": "0ce6d8944feaf90d78f06ac08ecddda93bb285074f6e71458d07edaca2266167",
    "summary.json.current_day": "71ee45a3c0db9a9865f7313dd3372cf60dca6479d46261f3542eb9346e4a04d6",
    "summary.json.runs_in": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a",
    "summary.json.runs_out": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a"
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
