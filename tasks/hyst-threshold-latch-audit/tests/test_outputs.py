"""Verifier suite for hyst-threshold-latch-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("HTL_DATA_DIR", "/app/htl_lab"))
AUDIT_DIR = Path(os.environ.get("HTL_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["latch_trace.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "3ed0de72263e5b6c237c483b5fa5e7c81435ece660ae0cf0606df723c140ab59",
    "policy.json": "0c5bd58fab0fb2bf0fedf1b0761d5aeec951d316ccc9bd9b96207dec0b0a9c69",
    "pool_state.json": "81a16fbf469a2d231eadca61f7ecf0292d65e58a57bad588dc3b4f8ae568b9f7",
    "incident_log.json": "88bf66d1d4bf2e11001a2713a7483945ab9e20f972bb98e995c7267cf3e659d0",
    "domain_layout.json": "d534a06440fc89a2da7451a13df5036a56b78c90c0a517dc6c4fc5b6d8182185",
    "anchors/hi.json": "1f2230b3755e2d0beb0943e4b2c9258a2a118c7b810a20978e3baea17831bbb0",
    "anchors/lo.json": "4ed53d62ec33e3a0f7a8c5d54714e4770c97973f777fecde53beccce78689265",
    "ancillary/a.json": "bfdade9354b6eaf7854b6130c94d772be9a3371b57867f432b11d4dd5ec53d37",
    "ancillary/b.json": "d6bba350a411e9ab0aa4f942dc85e817f4e67852415cd1e3c19cd9a16d043a37",
    "ancillary/c.json": "5827127f4278e34ea63e095fc8d58cd8ab73acc5aad3a0a9366bce16ba314019",
    "points/point_00.json": "6f65e0e95f6fbfb17619902ce086956dffa81710f9094a3c6923bca0d1ab961c",
    "points/point_01.json": "9cd4672bace4cfe68ac414f8f90651ab611d08f0774e2d31400c9af66798bce6",
    "points/point_02.json": "4975b7cd3ce53b99d326d1b89441eb17f3db11aab5509843ef1b99ff8e25ed0b",
    "points/point_03.json": "97770a8b977dfa092e63ea529a6dc60fb28f932a8bd1f0fd1f5feb36d8a5deb5",
    "points/point_04.json": "63cc61c578e1da269bdaaa8bde48b7001e41916d928c923ff0a6c86bf1fe0afd",
    "points/point_05.json": "18bd571e3719287b511475e88f0ccaf36ba0b709f3649e7dc732bc29c0d09688",
    "points/point_06.json": "1415f628b0210a48ab837be331a078019ed8e406bac8ea83e3ac977106b86c6b",
    "points/point_07.json": "719a34fef4f97a823eab8af234bcf47df37e7dbd3aac46515215edad6e9b8564",
    "points/point_08.json": "11ce04a55c60b9329acdf3aa6d335ede9d3cb513ca3e76dc7d06d8bee022366c",
    "points/point_09.json": "afffc9ade51b04cd04920e527f5130494e60b73ab7b7cab7766904dae66dca57",
    "points/point_10.json": "76cf87ea34bab08d862aff54700040b445c721bca2e165ce18c97365d4d9367e",
    "points/point_11.json": "2221e4f6650cfe595fb85e678fa17f034a8c1f306e48fb0c6f0077fedb539f92",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "latch_trace.json": "b5adb5eac0a5967fdd227e7ed7ee0f668572b88c1c5f8ebbafecc0f1022740d6",
    "summary.json": "b22ead83ff8d0fc8ba0d43351591b1a0fc281b35192a08e934fba214aa9fb41f",
}


EXPECTED_FIELD_HASHES = {
    "latch_trace.json.states": "b83ed830de25c231b00129b46f34cc31500e38a98f389cc3ffad49460a2fce50",
    "summary.json.flips": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.json.high_steps": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.json.points": "6b51d431df5d7f141cbececcf79edf3dd861c3b4069f0b11661a3eefacbba918",
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize using the verifier's canonical minified form."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Load JSON from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted audit JSON objects."""
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
