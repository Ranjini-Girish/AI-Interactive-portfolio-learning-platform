
"""Behavioral tests for cred-leak-floor-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CLF_DATA_DIR", "/app/clf_lat"))
AUDIT_DIR = Path(os.environ.get("CLF_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["cred_ledger.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "e7b9c1a39120b63b2a38581898aef3ec87a6e022e07645e6172870ff1df674ac",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "5d8cec58de0f80ad11163fbccf8876ff213b881ec9bef26c0150e8215f0c8174",
    "items/item_00.json": "ca2912c3c0023fe1bde047debaa0a91353c13d3aeda0af7a5a30d31e0d9a2068",
    "items/item_01.json": "f433d536be784b6537a91801a8ffae43485f9480be37747b705fb8063625697b",
    "items/item_02.json": "c29602731686d2fc354e0a705037fe28c8a3e6d2f6f632bd73cd2e8e85888d53",
    "items/item_03.json": "47947bc15050add2852773f30fdfc28888d43c81d7583d005b18dc3b0b70f491",
    "items/item_04.json": "1e8a7785fcab912e0d98a68cce88d1c3f54b0c406e718a70670c7e2ca0fb468b",
    "items/item_05.json": "3e060269e144254cd7cac96b5a53ee26df06b87fa51c24b55958463645e3ed7b",
    "items/item_06.json": "51490fc3df755075894f9248bd928076f983d7ab13ebaa324f585a32521cb71e",
    "items/item_07.json": "5f2a29d21f9284ed84e8e3e0a520e224b59a7bf268381b22bfe5ffac8a2dc942",
    "items/item_08.json": "2aa52f5dc3dc1bccaa571d5a95cbe520a1a6a85b571df2ae4bac261a370117c9",
    "items/item_09.json": "a79280dcfafa5156b69ac96127b7acc0a1fef8d720fc19ed6d865a3db3204e2d",
    "items/item_10.json": "be0ed0a4bee0852a42951a5cb788ec4e11263de2ff0abb91acc0be6434daf21b",
    "items/item_11.json": "bd32505cc24f27db435cdb40e0e7411ca89b3d03cee77ee881b71e63fc3e08a7",
    "items/item_12.json": "0efba12e2e7e04be9510ebf474d432ee31875c1ac9b8b3e5487eb514ee6c777e",
    "items/item_13.json": "6fa8b552910b517e452fd37e15b4055621c954737719bdf6fae3a19ad0d68924",
    "items/item_14.json": "ca93e903c24af24cf2047244328c4d9f10bb131ff8a761937ac3636ce725833a",
    "items/item_15.json": "1a38c181e452dc998965a8f4281a8839259d5384441e05f39ebdc47972ef2ccd",
    "items/item_16.json": "7440c1159dc9bd9caf6ea02f1d49e6ed307627528a8d88f03f8703820febf823",
    "items/item_17.json": "3c4a86a77af3ae92eca7e56bcf93e1cd6cf1e621e21fd16c18d61e2ba9f81b90",
    "policy.json": "c022becb7955e1577740d85915e95ff9a8ed433d05e5f9ad9c1c26d579fc5511",
    "pool_state.json": "552a959d901c48cf8c9d186b4c794f880f192cc978e446cf312461bc0f56e19c"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "cred_ledger.json": "abacf2d07b4bee6010398c036994afa9d468e631cc33f02e313981e508dbc8b6",
    "summary.json": "d1d8de512099c75bc14f045166bd72ae234c2816f26026c23f740828d85c4cdf"
}


EXPECTED_FIELD_HASHES = {
    "cred_ledger.json.users": "6419a02624868745dcc3dbce54ae4888fadef25c032023a2867e613729cb298a",
    "summary.json.current_day": "624b60c58c9d8bfb6ff1886c2fd605d2adeb6ea4da576068201b6c6958ce93f4",
    "summary.json.users": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a"
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
