# scaffold-status: oracle-pending

"""Behavioral tests for suffix-overlap-rank-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SOR_DATA_DIR", "/app/sor_lat"))
AUDIT_DIR = Path(os.environ.get("SOR_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["suffix_rank.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "b8df0759a1c75433f8b33d9171f5de1d379b34b780673a660e5b8bf87bc130c5",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "4e136a9be1fa1022eec8dfc39794898852cd86895b9a5adad345179688da8132",
    "items/item_00.json": "a4a12377666009f405c6bcbea4b4217063176fd2b5be392cbf1690bdd26dd880",
    "items/item_01.json": "10f9f75ce32a71514cc8acdf159d45fae9c0d8e30db18492933331a528d2a688",
    "items/item_02.json": "ab8046b3c2d0fffa42a7bd306c7274cba06ef249816bf43e3d27ff04b355936c",
    "items/item_03.json": "be2eb3dcb61dde8135adf99b82ae6cf187a8aa174c5bf6593c1ded4dee725a77",
    "items/item_04.json": "f6caf531069a5408ce6ee93b900fab3a8a945f5375de23fc319df891ae8c650e",
    "items/item_05.json": "067ae4c2949cf768e7a37a672e08ac08da5c30d413b574f0d19c196e066512c4",
    "items/item_06.json": "719fa42add34485b4a6cd4be7f19910e874f6623cda24261b1886450a69615e9",
    "items/item_07.json": "e3df63bcccaf81ccdca75025736c17e4ba9555fc0598f86998522aa3a2f17437",
    "items/item_08.json": "9ac7df8d679293eddb78a0186519c06e8e11ea4600b48fd91287c359f7e31b61",
    "items/item_09.json": "cfc45b27bed702e3e1ca3e8f9824a773ef7b8df0f792abea9d9345cce252a83a",
    "items/item_10.json": "f9cf6766feb6757dc523266d696ad4a0da0c840b0db5be82d13a1589326e2012",
    "items/item_11.json": "c0a8912a182202425807a4da1711ce9327be8e9b184a4a135864eb7bd0611dbd",
    "items/item_12.json": "a9e66c3f567474858de544523521b4510be2d7b15c9415275c754bed8960fde8",
    "items/item_13.json": "ed8e83a02bb3cfda82e51f2f86ab002e4c5e758015315837019248a019eb2660",
    "items/item_14.json": "57e519dbbdb8b449a4ee5ec655de4f24d37d161d3f3c908bf9fd55e6fe51cf7e",
    "items/item_15.json": "270f2974c8ad45f3abf41817ad32e339a64a6a26557f51e15bb5bfb3441d0236",
    "items/item_16.json": "bddac8cef6e84f186a7480a26f79bdc3374c131b225bd613d9ce7832cfcf4ad8",
    "items/item_17.json": "34fe30ba32bb841948f10fbfc30b403c98b579b6f42b1a7fe1cd8bee21d05964",
    "policy.json": "658899612d340ac2e1df076fc2115f74985f24527d681c27fd640a6fdce99a0b",
    "pool_state.json": "13688a5dfc2b4ec5ee0363f8afe189d2620ef1eb365d8b73d377d80bf5c80b7e"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "suffix_rank.json": "7eef7ce57398253a2f41061b09f4f4c00d7f59df98218ee54bc67b68571c22fb",
    "summary.json": "bda8fbdde5f695d6663a9817017452fca550c1d79f64f21e76093c5c6560f725"
}


EXPECTED_FIELD_HASHES = {
    "suffix_rank.json.best_id": "2de774d8eac5a7246cadb770e187ec48b06ef6127f3de0ec5c374f4099c195ad",
    "suffix_rank.json.best_score": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "suffix_rank.json.edge_overlaps": "0da7b77ce8c58f8ffa3c4d464cfee9bb1f509fec1cffb412c0dff4d4cc61a728",
    "summary.json.current_day": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.json.strings": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a"
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hexadecimal SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize ``value`` like the reference harness (sorted keys, compact separators)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from ``path``."""
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load every mandated audit JSON object from ``AUDIT_DIR``."""
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
