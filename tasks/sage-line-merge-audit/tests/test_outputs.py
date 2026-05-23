# scaffold-status: oracle-pending
"""Verifier suite for sage-line-merge-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN19_DATA_DIR", "/app/lab_19"))
AUDIT_DIR = Path(os.environ.get("GEN19_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'a07863a2181d1c07c78907fe2565b08eb4b88142d3057786fac1ec0f05105010', 'anchors/b.json': '9722aca24b8f245bda9ed8cb12729e8e6e0e2f5246e0a6dbb37b4dbe93dfcecc', 'ancillary/extra.json': '67f4ce1e3207ed1e660109ae7844ae58bade0120e82ed80697639f1f8e1ac8e0', 'ancillary/meta.json': 'a023cd78b43c1fdbdb4f71ba2c99e7e508aa9a3aac54d2e7a9a2904c9e831c6b', 'ancillary/notes.json': 'fdb61fcd3f266a4e19f06836c905f8fb0afceb4b14bdef250c6479c6e2b47b9c', 'domain_layout.json': '41923a54f06f6095e65685f66675cda2f4df3d0eba395138ac5de84df182f569', 'incident_log.json': '958022d0757488a75322ae7caaff1eda4c7b77ed1ff3ca14a1fa3b64e303c034', 'items/item_00.json': '5ea628d32efe0894a8d19ed8462c079d5cef9072092529b629b3f1a1d257a11a', 'items/item_01.json': '27463545babcf1cf11288588152ebe886506064cc5366003df44d04a2a61781f', 'items/item_02.json': '0cbdc2db3b711127cb567740d1671c0abd06301b5af3485a34326f409942280b', 'items/item_03.json': 'a8130c668ac01af06deda4c67d145fd981e22e6711f795a475403c88b1c25622', 'items/item_04.json': 'd563c796a002a3d7d4ece7de81a81d2d12e328237162f6d3b0d4e5600dd6f685', 'items/item_05.json': 'f5b413649a09f3601b5a06d8ce65299f9896d7c7358ba4c7d72b7ebdf1c9f31e', 'items/item_06.json': '830a0517237b363fa32550ed991de41bcb55f739f770ca9e3efefd3cb9ba6a19', 'items/item_07.json': '04b617208f1797179be77f8230331f0928481c09d817bc7c051d7fc401f5ce92', 'items/item_08.json': '0c14135d51c4df4200388984c728f30d44f9eaf7646927bb764b49e86920b688', 'items/item_09.json': '5ea0f2277add3e183d8ca424a29dd26a84258cd2b0e61497f6b658a0d6d6b125', 'items/item_10.json': 'da1fb024afd7957b494f4142e07581fe2b7d9fc06d5133c63b5304949db8c1ad', 'items/item_11.json': '04da56a648bed143f095d63cb39ed1fbc053f9d65425bcd35e84e15a88c823e5', 'items/item_12.json': '3af2363bb9cf45f86c4689bd7326e0daa1410c3d4246e3a1a11ba030d9add68d', 'policy.json': '7688c969a0c9708e701fbd3da2b84541c4f4512bb314e292aab5b8d1f1c6e904', 'pool_state.json': 'a7c6e0d75ec31c191f5d8247db9bbeed76431320cfbd1c44035817c558a158ed', 'SPEC.md': '721be2f9b6e15738b85d20a0fde3695b17776cc147f092075938b4c38304a773'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '070dd4558ea785cb623f42e582742ebc1ea592a55683e5fe52207a2375a514bf'}
EXPECTED_FIELD_HASHES = {'totals.suffix_trace': '71eebf8f5760b70c2eb19230bef73d7cc009bbf06695182f42782114b0d53ab7', 'meta.task_label': '8e3bb02f97310339eef45eee2ece49c76ce4a6fe5de04278caeaba47091f5ae2'}


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
    ssum = sum(int(row["st"]) for row in items)
    assert int(totals["suffix_trace"]) == ssum
