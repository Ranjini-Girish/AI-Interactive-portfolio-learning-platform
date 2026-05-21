
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
    "SPEC.md": "29aa8a6dcc20e1472e5527501eb3811ac1c82176e9722936df96efe4e43bd2cb",
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
    "items/item_12.json": "f8aeca68e19c0c425532ce1fa9e8782f9c7a394d8db9a265d181efe2cd700de0",
    "items/item_13.json": "de38da025bddfb6cf2de1092bcb6efb012000fc9616a04889af52ef688385ae8",
    "items/item_14.json": "0dee3c2c0c845951ed22ba5cebc2883f64576cb9642d274d9175c3b7e6c2c4b3",
    "items/item_15.json": "a438ec2a48cffe8d16bf9f809d4fa7d25032d55e7e608e8ae057b0a8ce2ec790",
    "items/item_16.json": "e3734576f10953066429cf33588a44738676aa882b5042d5fc55879043b563d9",
    "items/item_17.json": "a37f84354f5c36c954f6485b27f7f6f58cb956f2a63b6345145d7aab45a5bf52",
    "policy.json": "658899612d340ac2e1df076fc2115f74985f24527d681c27fd640a6fdce99a0b",
    "pool_state.json": "13688a5dfc2b4ec5ee0363f8afe189d2620ef1eb365d8b73d377d80bf5c80b7e"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "suffix_rank.json": "f75887364b4888640a60817d7599102021a5f51369b2300149a71131a27af019",
    "summary.json": "bda8fbdde5f695d6663a9817017452fca550c1d79f64f21e76093c5c6560f725"
}


EXPECTED_FIELD_HASHES = {
    "suffix_rank.json.best_id": "6295dfddbf3d76dd702ff7db9cc3763ab270d4e6d33478dce639950cdb92eec9",
    "suffix_rank.json.best_score": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "suffix_rank.json.edge_overlaps": "73f5049789cabedc740388f50674b2e09de4b745a31f038e40bded87ed0e28b2",
    "summary.json.current_day": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.json.strings": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a"
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
