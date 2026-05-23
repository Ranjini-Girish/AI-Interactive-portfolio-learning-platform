# scaffold-status: oracle-pending
"""Verifier suite for index-lag-bridge-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN09_DATA_DIR", "/app/lab_09"))
AUDIT_DIR = Path(os.environ.get("GEN09_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '2866a54003cc7cf9acc22d06cb9c364161ad1c45ddd22faa2535f8f6f2340017', 'anchors/b.json': '528fd11a78d4ce4ba46bec74f5e4466dc1f2fc4e82abe93aeeefd89d214ff505', 'ancillary/extra.json': 'b957903c3dc3958349fbca3ff390f02346ffd5df920c6ff820e90a9e8d72b963', 'ancillary/meta.json': '5940f15939dee19aac7bb210e1ad47b8da48597f32bc7464df235ea0d30ab4d3', 'ancillary/notes.json': '376775404a2f03579bb22f5a3096e88cdee3cfd65badcf5263e9db31ce59a33e', 'domain_layout.json': 'ba02a14dc21e2cf2f0bb1cb1284b14b22b48fdef351dbde38e034577dd94b8a1', 'incident_log.json': '6a01efa74656bdb3160223dd8d0e76739820fe8a093ee98068bff66cc9a06ac6', 'items/item_00.json': '50f5b2c2d88702092da2329af403be8d196b8a7cee87be9656f9fe9f48244679', 'items/item_01.json': 'b722da776ca63375fd7008bead49c36b09db9a9d74b808e3ac98a91c445c471b', 'items/item_02.json': '965db1be8f9bca4f33a5137fba475b92b28335c3c352c276b5ebe870376569a4', 'items/item_03.json': '70a4c91d036241435c93e49b076855696c084e29612721706e255b8b4f01c1c2', 'items/item_04.json': 'c776cf227199719d957a438b1e0dfd897987571e86691a42d04181348afd0cd1', 'items/item_05.json': '20dad1c1800ac3864fadf5077e4fd02a650e2eb92aa499d22d91bda86785015d', 'items/item_06.json': '53efdd8e9b0d6d54a004bea5b2675ed9e11c9f2ee43a94e30cfa38411ec60e45', 'items/item_07.json': '01d81fd5ac5d392aaa03b074ca7473001457ab2a7314082b17a5add08f95007d', 'items/item_08.json': '0050c091442ee27c29bb97eda000581c5fd6ff9f8afa1433cf45be4513f87799', 'items/item_09.json': 'cd36890d1c4a3e823c8284e91d0b252e639a195e65d0605a276f2629e84a21e7', 'items/item_10.json': 'ef3feb2de06327fbee43cc52cbab370a82c08d2d8e37290c49630c958b483c0e', 'items/item_11.json': '0c1f4087aad8e211b5953919a8cd2aecd004a5948cb7ba6d586bf749db682ddf', 'items/item_12.json': 'bc860b63e8b4041349304a477554ae452b6b67dee21049a2ec96221742ed7071', 'policy.json': '25923f493ec40d1bda8efe7c3dae4423f3480821069d16cb239708f822756cd5', 'pool_state.json': '77068f0d531d4a4181587f1560021558ce2558b1f1df55d5f47e8462e6b7dc28', 'SPEC.md': '7090058a67bedae0c166f41783fc3b8095ea85356fa54bd97bb8d210af547ece'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": 'ffff86b896c634e8ce692e3199e3a012ba563601d75944fcd9cbeffc659ebac2'}
EXPECTED_FIELD_HASHES = {'totals.deviation_energy': '4c7f587018203c5f346122b22301a8587c9c270087a95622b10b4400dd0b4c01', 'meta.task_label': '1c7a1128509f318d52fba51940b32676077e48f9b5ce1fd394d57abb9a59d276'}


def _sha256_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 for the given bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical_file(path: Path) -> str:
    """Return SHA-256 of the file bytes for the canonical report layout."""
    return _sha256_bytes(path.read_bytes())


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from path."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_input_hashes_unchanged() -> None:
    """Every bundled JSON and SPEC digest matches the pinned baseline."""
    for rel, expected in EXPECTED_INPUT_HASHES.items():
        digest = _sha256_bytes((DATA_DIR / rel).read_bytes())
        assert digest == expected, rel


def test_report_canonical_hash() -> None:
    """report.json matches pinned canonical SHA-256."""
    assert _canonical_file(REPORT_PATH) == EXPECTED_OUTPUT_CANONICAL_HASHES["report.json"]


@pytest.mark.parametrize("field_key", sorted(EXPECTED_FIELD_HASHES))
def test_field_hashes(field_key: str) -> None:
    """Selected JSON fields match independent digests."""
    doc = _load_json(REPORT_PATH)
    assert isinstance(doc, dict)
    parts = field_key.split(".")
    cur: object = doc
    for p in parts:
        assert isinstance(cur, dict)
        cur = cur[p]
    text = json.dumps(cur, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert digest == EXPECTED_FIELD_HASHES[field_key]


def test_items_sorted_by_id() -> None:
    """Item rows appear in ascending lexicographic item_id order."""
    doc = _load_json(REPORT_PATH)
    assert isinstance(doc, dict)
    items = doc["items"]
    assert isinstance(items, list)
    ids = [str(row["item_id"]) for row in items]
    assert ids == sorted(ids)


def test_totals_match_row_metric() -> None:
    """Declared totals key matches the sum of per-row metric values."""
    doc = _load_json(REPORT_PATH)
    items = doc["items"]
    totals = doc["totals"]
    assert isinstance(items, list) and isinstance(totals, dict)
    ssum = sum(int(row["pull"]) for row in items)
    assert int(totals["deviation_energy"]) == ssum
