
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
    "SPEC.md": "8a8bc731c012c9a6b5355a2892cc3251e03c0bee12c94d06a649e65f307e8738",
    "anchors/a.json": "783461f68c8cc21db049b0ca80f3e5454b9959dee69ed783df45335d51a4a472",
    "anchors/b.json": "2798a4f14e858fca63cca731b000d97c379af95afd341f87608db6e514b31d30",
    "ancillary/x.json": "ded77fafb756735e444e7180202e9f1bb3f2cb680a3e5fe99a21fec0e8efa2af",
    "incident_log.json": "1a46c0402c164e450fc729a327a7f36d64cf4e4425fc9fd7063a788623706f19",
    "items/item_00.json": "844b47ac7bf5057e7fd59bb0e4e2631dd01e55c5403a3cfc8d07216d8b7a8575",
    "items/item_01.json": "2fc01d34d1a7a73d37d6b4c70b528d685d9bb34dfcc17551e85ed0d57b6b1fd4",
    "items/item_02.json": "78b78312b222b035338026b4f0591ad3fed5eb45c503043880f92dbb40986740",
    "items/item_03.json": "a551f6fc9ac21dfaec36eea4786f0f7b0e6b2a8b1411fe227ad7b9b5739b4397",
    "items/item_04.json": "dd08f01992fb250c54146892764af4a4d9e3439b2384443dde4eefc2bc60af80",
    "items/item_05.json": "084f003cb6f730c3a1467198de2beec39a064576dc2155e0aced562986ae4687",
    "items/item_06.json": "58187f69464fe64fa1ac52a6ba263318583d01e96743bd73025b4fa7fa84ffda",
    "items/item_07.json": "f2e034853a36d143e9d1da3bae160e89e757006ce18b5140d2e4b5980901a749",
    "items/item_08.json": "f91427605c48659bbe4f70e8a06e658d4e6c6508de39ec867e362973fec74457",
    "items/item_09.json": "b27975cbbf8eb4dd19e4bb62def2bb5f779b8bc2a8515907985acc740182f442",
    "items/item_10.json": "1cb4caeab0f6b8186b2e60f5206a6e40b0a041fac03307ab5e80c16144931377",
    "items/item_11.json": "c829a8781e865c89efa6078aa9878abd4e6f2350d4e66080e68993e13877766a",
    "items/item_12.json": "be74b90da857ac0e7ee4b9ac1a55bc7644f6ccd7bb083303db4dfb69423de855",
    "items/item_13.json": "cb02a58e7935418a97e1ac49958c1537a17626d77473d9b572e2ca508e3df752",
    "items/item_14.json": "d9714ba28ad3088e296d86ef7a96851097230432421a946b2d094dcf37a1743e",
    "items/item_15.json": "230042085748bb93b621362916445c52aea341935a99a3d9759509d15713222d",
    "items/item_16.json": "04dabd0a62ab7bcf049a0823b870609e10f8937dee37ebfe50a03214f83a774c",
    "items/item_17.json": "3a804c1696a6501e7ad0b69bf2a4c52a0528101ab9dcdb2e9d8c12ae92cb8eb0",
    "policy.json": "1384bfd62f48dd74d35bd4129b2e3079a4096806e7ddc658b07ec75b05a5c9cf",
    "pool_state.json": "936f25ed626b7178dcf4f05fe40246af3ce715ea622c131c9c792582c741eaea",
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
