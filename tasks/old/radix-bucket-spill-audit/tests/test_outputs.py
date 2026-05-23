
"""Behavioral tests for radix-bucket-spill-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RBS_DATA_DIR", "/app/rbs_lat"))
AUDIT_DIR = Path(os.environ.get("RBS_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["bucket_fill.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "27cd1107b07d62e56029a80a5b16afb798dc8f5c6baeb29978e08d3951a078b6",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "cf999f95b83042a6e40f15e0150556227db1c27206eec5e04ac08b84c1ac5529",
    "items/item_00.json": "7eb6761115aa3745f451b0b3aceb14838223d3589c1c30dd2fec1381d01df790",
    "items/item_01.json": "aa9a4f2542eed2481e25e9e6d6ff4d078bb943449c213f09faf16436b0944816",
    "items/item_02.json": "1d24c0729e1baf43e178523881ee462f23c3303b4da1fb51b5cfed3a3aed30a1",
    "items/item_03.json": "e8daf312cb87de0ed1061b635ede1b554e218b7cbc03352f933758f6dc65d0bb",
    "items/item_04.json": "9a6ebe3395b708302bffc761ae9342ddef0ac168d59899045c1d87aa95521425",
    "items/item_05.json": "48560c999f6ec3a047beb80ef661952002145f21da163ef70e6926ab86fbdecd",
    "items/item_06.json": "50e0f3e673ea8432d9016a2229da406da764d10f4cb5ff121113173263e50bfb",
    "items/item_07.json": "10427e122378d31c9fe53c8800dc46cf9710d7511ac56e21af888b77765d46c6",
    "items/item_08.json": "b9239a834bea8ab8bec12c3e66ff9bb611aececd9a8fbe40913ff8492e1e8bda",
    "items/item_09.json": "d973383509a8ad1d952540d99f593dc8f6ea7c2e4a2f2301573396a950b4f5e2",
    "items/item_10.json": "8743e5c3128e918262e8403c70a157cbd04a79ce9c62236341cf20196c907dc9",
    "items/item_11.json": "0b6182c532db116b79ad86ff6cf1718a8d6076cf17e3f023aad74cc0e9e6f31d",
    "items/item_12.json": "cdadc222eed359e0c2b8c6661dd7f97f5c6340db71591d51864f639027fb9aa2",
    "items/item_13.json": "fc045f6ede8e36b9ac7e8bb2eeaeb4e4f98930d35d7b4115e0ca56e40e4db14a",
    "items/item_14.json": "9e9739e5ca94651ddc1678109f48406755fde016080f72f3b4ddfd3022b1b2cd",
    "items/item_15.json": "847e1faf758f30389880dcb49be08203a430cb1aab05a66f813ab16a8036af1f",
    "items/item_16.json": "9d99a752589a087d86274c4bb06aeed579c07b46a6e686a50acc5801866d4de1",
    "items/item_17.json": "504b96b7d9bc2bb3b620d8b959d1a88f48ecb179da936ddc7e846a5ec539206a",
    "policy.json": "56af52439973c9418310d8f8a0a2da9635d2a1c30a566dd101607e67b36c77ac",
    "pool_state.json": "77068f0d531d4a4181587f1560021558ce2558b1f1df55d5f47e8462e6b7dc28"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "bucket_fill.json": "af597d6311cb875e054479c54119f2251deb4aa23593ba2d3722593f5c86831e",
    "summary.json": "54ffe45732bf124c5f970cac201b3ec563c069e23610d72b127be63ce350c33e"
}


EXPECTED_FIELD_HASHES = {
    "bucket_fill.json.buckets": "834ea029900ff428226a8483b171ff351a19415d9a77652bcfab5564701e56f2",
    "bucket_fill.json.rows": "f5d1d441ed188edf5cd7bf38a1ecdcc45a8db3669bde632e382bc254ab932460",
    "bucket_fill.json.spill_total": "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9",
    "summary.json.buckets": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "summary.json.cap": "d59eced1ded07f84c145592f65bdf854358e009c5cd705f5215bf18697fed103",
    "summary.json.current_day": "6b51d431df5d7f141cbececcf79edf3dd861c3b4069f0b11661a3eefacbba918"
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
