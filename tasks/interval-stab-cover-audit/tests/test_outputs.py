
"""Behavioral tests for interval-stab-cover-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("ISC_DATA_DIR", "/app/isc_lat"))
AUDIT_DIR = Path(os.environ.get("ISC_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["stab_pick.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "45103d6eaf5f148c14705089cf9aeca42c6154d9ad922049799c797882b4ffbe",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "4e136a9be1fa1022eec8dfc39794898852cd86895b9a5adad345179688da8132",
    "items/item_00.json": "78be09de8979a61985786824595cb236c0f9431f8cc17d70847fbd6f92afa60a",
    "items/item_01.json": "39702ea3b4b924d08b270f33327e01a1fa9c9393dccb7bfffe857d69040e249a",
    "items/item_02.json": "552132c764cc9fae4284dacdf4ada314174b0aea3b33732bc05431e2dd6994e7",
    "items/item_03.json": "a42756d8945f8c5a25baa3acac4a74d7aaaa7f3f362629b3acb17aa9d44b976d",
    "items/item_04.json": "3a6c1c1d13828bae64d0cf19588b8e683996b5a37b57dc610923ff9bde8d49db",
    "items/item_05.json": "62b54dec90d509af5cda4bc6bb1983f068769e61938541880a6d413b91511069",
    "items/item_06.json": "0ff02dc6c8f933c7641d8be0c7359d195970f91844b6a7c36d9831c7c2a482dc",
    "items/item_07.json": "220f36e34900bf71dea07b9d24c6afb7c9394d17b5e96ad8b5a51def639dd189",
    "items/item_08.json": "c783b40139ea58bd11141a2656bb7fed13433bedea2489e5b55623770544cd50",
    "items/item_09.json": "b238270e7d869894a60ca8a4bdea03c89453ba37317232c0d146976937f51bc3",
    "items/item_10.json": "a08270dd7fc690a7f8a20ceff741abbd036801faafd508a3d9ca399ad6a6d76d",
    "items/item_11.json": "a57a3afec63e1f81d3e19718d72d2eb1fcb4036e00dceae756ad4e740dbc0f7c",
    "items/item_12.json": "884b89dc884534001543913efb1786b3503193d8e5068ee8656dd80d6dd9f28e",
    "items/item_13.json": "7b3c17fabadf951099400daabc56bc6c0e00883b4c8cb61977e298c083c2661f",
    "items/item_14.json": "8819e5a38a05b7f3ea03bfe3d38bb5cc9d2a23de9785f7cb6f05da4b0e84fcd9",
    "items/item_15.json": "87cb03eb2ceb3a18d0c7285ca4aebb65a73567196ffb912b5a7f5791a9695566",
    "items/item_16.json": "bf08a35a8bce6ccb2f2f48446d8c672097de8d9ab0d312be779029e50c10d27e",
    "items/item_17.json": "cedef1074e2e4de2b3978bd01e6d6e1cf78e4ec9af2b645ec79234a88960b2f2",
    "policy.json": "85d387825b263fbb55c937bbed5e1ea41d799130e2da1d211b689b6322405e8f",
    "pool_state.json": "03cae7b3f804c4514d070620550d9561d3c8b5dc7d24c9f6905820140007abe0"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "stab_pick.json": "594b084013af6c3447371e8417619be82c011dafb0458d3c08a1cbf75dc4cca6",
    "summary.json": "3d568f5a3b934fc70306283e8f4e8073f776013523d219dfc3b221710e4e2f28"
}


EXPECTED_FIELD_HASHES = {
    "stab_pick.json.best_point": "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9",
    "stab_pick.json.cover_weight": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "stab_pick.json.intervals_touching": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.json.candidates": "4fc82b26aecb47d2868c4efbe3581732a3e7cbcc6c2efb32062c08170a05eeb8",
    "summary.json.current_day": "1a6562590ef19d1045d06c4055742d38288e9e6dcd71ccde5cee80f1d5a774eb"
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
