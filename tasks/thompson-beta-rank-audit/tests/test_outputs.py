
"""Behavioral tests for thompson-beta-rank-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("TBR_DATA_DIR", "/app/tbr_lat"))
AUDIT_DIR = Path(os.environ.get("TBR_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["arm_rank.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "429e38282c4ae5d555f5a162a9327a61aba90b8643a51b4bd656cf1166c0d6b0",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "15f290eaeaedf30a7e01995cd823e7fbf892e4b34a0108fcd443f97e97242fb7",
    "items/item_00.json": "6d90442b07196ad13bed56b675d5ca836ab841cab405387cce840db9f3f6e8dd",
    "items/item_01.json": "58e588ad75befd1ebf4c0c23299aba0387a1cda1294b1f969224eb35dae98e50",
    "items/item_02.json": "83c31c5321c198599560f77ad28dea553aa1429b1f0623c8466ea2b6e18bc82f",
    "items/item_03.json": "e7b1a5851024ebd8406adbf60ca6d0b288799666f0c45bc092434902bc95f7b6",
    "items/item_04.json": "8e03c13ee4bbd5d278cea4b134678a1a6b05a7bf570cdf8d70d69ea2f7a6b846",
    "items/item_05.json": "647cd306e7a876196a07fb4e3c44f373fa75a1924c6adad2ab6f6eac2c6c9f34",
    "items/item_06.json": "66c090b590f5762aa9c73a2d5338a8c8d7010f1b5f5ea7dc2180a88a817bcf47",
    "items/item_07.json": "803c5931f3a99511964b244c21d6d2c28d7182cec3759dc059f9412f79e37e0d",
    "items/item_08.json": "d8f8cdc30192ff4f199be20a6aec074945fb81a77e3fb666dca6af80d065a447",
    "items/item_09.json": "711530d45c1504f8d7c89a30eb21a43cbcc7594be76763bf7a904c64ee9a070b",
    "items/item_10.json": "806768a4f0c5343a448dea10f197fecc38dc8ae5aa35be7676d071a768178d94",
    "items/item_11.json": "f14dcc013127b6a13ec6d74df9d8545ff330964f7ec19ef9a2258ffc25df1424",
    "items/item_12.json": "ef220b4a2e2598fc10167f59bdd49c991d7d2e5f8777b1865c3ffc283a0f4ccc",
    "items/item_13.json": "adf286614519e1cc8710a354ceac71710ecc567c5a2f449babf66a7b01f652ad",
    "items/item_14.json": "b8c0fec0e8d4df3edad07c26f5998f6f1843abd2adcf55278252027452a01330",
    "items/item_15.json": "2395293730413a3f81c020b89298bdfc7fd619d289983b6f80bddba677bd282d",
    "items/item_16.json": "d570c52fe262a11a10c27e47e24dbadf0272fa3fa665b9ca3eb46587ed68adce",
    "items/item_17.json": "4d5610598d51c80a8fe7b1b822f2ca853a3a7f3c0947d7e93af3462c4f556fda",
    "policy.json": "0e9bb0eff26ec87ba8d2503c144aba1d86d410c6e2b7ce93f121c033c71eebaa",
    "pool_state.json": "5efc4fb8db98c200e0118a0c38bd5b034ffe336a102c8a37c56f553c6f3c20cf"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "arm_rank.json": "0203cb3093d823d6182f1e2fe708db3f92cfeac49a2c39c9ad4e104c74a33f7e",
    "summary.json": "68f987452e2059facadfcd3079d87237c136fdd7c0843882692f1eb36a914518"
}


EXPECTED_FIELD_HASHES = {
    "arm_rank.json.order": "3ea8881b37521f04b03b9a61e18944b68bc885afa37a8bc3380f57069389453c",
    "arm_rank.json.ranked": "41dbb59a302a66a69729cdfeff15dbe80401f62082e71e901ff60a913de704aa",
    "summary.json.arms": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a",
    "summary.json.current_day": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35"
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
