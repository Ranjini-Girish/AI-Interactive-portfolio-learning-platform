# scaffold-status: oracle-pending
"""Verifier suite for grove-mask-span-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN07_DATA_DIR", "/app/lab_07"))
AUDIT_DIR = Path(os.environ.get("GEN07_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '3e2cc6a283e0128a5a07056d80fedadbdd30ed195f7380fdb258e0024b60fde3', 'anchors/b.json': 'd7c47139aeb93da4f0cd6f09dbd1da507597a32373200bc4be70e52b7374f254', 'ancillary/extra.json': '92c66e2d5e29968e5c4b70a50e1bb8e3b657f5c714029f838497a280eb18c4b4', 'ancillary/meta.json': '042fa7d22e770efda4d24692a4eb1e989e478359a56624c37905ec51949724f2', 'ancillary/notes.json': '43478dc1e76e454403e7f73ab53a43f27e265124e0241fb5e26d7badfc708249', 'domain_layout.json': '30dca545cda5d51e7c83f800a9bd8b8232aa793a7dfdec19b92fe59f487fbcbd', 'incident_log.json': 'cd66be2e26a9aa54e300719d6c92d47885b1026cb9078c44df73b794d0311414', 'items/item_00.json': '28a542eccc0de0675d2063a577c10949069e31658fe87967427c71c1e70c3143', 'items/item_01.json': '706857e47104a808e4a7697d6e61881a40af6943370a855b55202a73ec52b1a1', 'items/item_02.json': '9e8ac6d357a95eea80e0a3662892835b7dabed039504b96f3b3e20243b894ae3', 'items/item_03.json': 'd5d44305eeb842fb5374a01ae112db34d7743afc7bb7545e5c0a16ec956a8f9d', 'items/item_04.json': 'd7131d3a2a8978c44767cf0812718870fd4ba9da5087e9d9b10579c6120f7dea', 'items/item_05.json': '99ab16c1c599e190d80744882f8352457c555941417419597af67248fe82fcab', 'items/item_06.json': '6163c3d852a33003d22801dbae2c8bc670e85d4464e9791f6bb2e1b1f0317162', 'items/item_07.json': '94bf01e3bcc08161e8df7c5f63d56f49c8445219ac80876a233ac15c8938e7e1', 'items/item_08.json': 'c8983294b33bd0907dcffad0a69721448070fcc0762a6e24956665f82d836f77', 'items/item_09.json': '989c8fcaf1dd1057e1f85de8b1cf697ef6fb084f75aa3b7d95f10a1edbcedc1f', 'items/item_10.json': '99d8ff1f96515248bfc61aecfdee412cb24236393ab2bc2431595179250e176f', 'items/item_11.json': '9e01a31e95e8227fbd383b927f3075999e498a3cb58fc5fe2c978661040feb30', 'items/item_12.json': 'e69ff4a272d0168dc81ce608e8013b5689a57428c2a7802ad27299aad7d1c623', 'policy.json': '98b481427d59065a092a4e2f20ddc59fb39cb45afb91926e3fd5d19b6025c08e', 'pool_state.json': 'e693a6e7c45482e0d5ac0221b8007ae15195a5e34119259c2af54766244709bb', 'SPEC.md': '94d927519da6ae5104a82c85a12543a7fd5004ced3599ac8a8f374a9f5b508c8'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '1cc1c1f23fbe74f64d77307319d219c3955a6bbd83025d2345bdbc8f1a15124a'}
EXPECTED_FIELD_HASHES = {'totals.gate_total': 'd933c100248234cbc4841a00095c9aa3951793524676de13be35297295f1ba48', 'meta.task_label': '27d34fb72fce2c8f4ab6e01fd5ce3168c8d744368bc2701d3fbffbabb0f54e5b'}


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
    ssum = sum(int(row["gate"]) for row in items)
    assert int(totals["gate_total"]) == ssum
