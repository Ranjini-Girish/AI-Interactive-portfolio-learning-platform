
"""Behavioral tests for cpm-float-chain-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CFC_DATA_DIR", "/app/cfc_lat"))
AUDIT_DIR = Path(os.environ.get("CFC_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["cpm_schedule.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "2fa5433a6fe19605eaec368c3c1f2918e7d8ea5052c85cd076114b05a22acbde",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "26f1beaef37664ccaa097ad6dd37fc62fc39cd3e3cb76e498f2d059ad13f13aa",
    "items/item_00.json": "89f70483c52b7738a1b3b1a48c1dabd20b0348ac99be54a9670a134e9b888b35",
    "items/item_01.json": "9b808c9774f2df578f3b90c7af3b8b4d1004a3ad6e6235cf13925dd6b5db93d7",
    "items/item_02.json": "af9a7c920a86c605981e11d08a0668a0586270f019b3ce2218130ad3bf8190aa",
    "items/item_03.json": "73e09c0b434a5eda74ab1a737f9f3affb6571e9f7d8ae106d443766fdbbe33b4",
    "items/item_04.json": "2a7460de99dfe679ec7add312029e7111e91b9f5c81b1d5f0f3f662db65689a5",
    "items/item_05.json": "7a29d4345580fcfcfcd2e295f589bfcca774a642580f3cdec1f394b13518d4a6",
    "items/item_06.json": "187a69eff88359350c0ebdc56550309435bde11afd3ce2f2253dfe46ffc75e10",
    "items/item_07.json": "5396741ef058f740da6a5219f5da77862592c6cd125e8b9f1cfc9efc4af47713",
    "items/item_08.json": "640a53d0efb03f0691b69615f13540aa71f905beb4d7882a30896b27b89c551a",
    "items/item_09.json": "53399cb5bbb19c068ae09b8c2610a308306ea1d9692454f36c5e85245200b05f",
    "items/item_10.json": "4198d6a5c4f9a58a17d8cbc40200ef02e682cf88c2cda22b6a4b276ccd890936",
    "items/item_11.json": "319cbd0cd46f5d71c7dbce73fd6c22a3fa3a8fd7d8dd22daa8024fee92ffd0b1",
    "items/item_12.json": "97fae9955d35ec0885b706904558b2a9bfb64a54a53a02d2990b7150715a04ff",
    "items/item_13.json": "5c96fb2f002e8e935febda58b4e24f63ef5ecff62ddc289f53550c9c4e75edf6",
    "items/item_14.json": "a2dcbece4518ad95125c1a57d41bf2fdba4d9e0ec092b737fc907465d3282aa1",
    "items/item_15.json": "5302ef7896887fc2568a738e177f7f7039e342246555744c00c11a29158cc296",
    "items/item_16.json": "918fa6cf7b1f731ca3bdced890e81ec361f2b669665f8a547de4f4b8d2b529be",
    "items/item_17.json": "a47303a6b00330987e25c55fdac292bea6db12fe0e3266a2fa146ccf09ee5c87",
    "policy.json": "4c103a011e5db942112a72511d5efc6a5f4353bdfd82fa9674d029a07f0c63ce",
    "pool_state.json": "98b34facad42f6651403f9a0d279962101775db88b22bdc5a77adb2341cb1a85"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "cpm_schedule.json": "e940a2bb403f465b4d0dd095e22167586024a3272e731b22c183a9c500ada4da",
    "summary.json": "b615f1c8e43c91e79ccd98e89fc16d9fa58f96c037775668595b913ab5837bd6"
}


EXPECTED_FIELD_HASHES = {
    "cpm_schedule.json.project_end": "aea92132c4cbeb263e6ac2bf6c183b5d81737f179f21efdc5863739672f0f470",
    "cpm_schedule.json.tasks": "3c1c33a2788a229bd87e965e80483966785dc4e9e6dce20ef892fd4316807d43",
    "summary.json.current_day": "27badc983df1780b60c2b3fa9d3a19a00e46aac798451f0febdca52920faaddf",
    "summary.json.tasks": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a"
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
