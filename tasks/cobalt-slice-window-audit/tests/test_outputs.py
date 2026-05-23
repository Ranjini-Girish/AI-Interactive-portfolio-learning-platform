# scaffold-status: oracle-pending
"""Verifier suite for cobalt-slice-window-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN03_DATA_DIR", "/app/lab_03"))
AUDIT_DIR = Path(os.environ.get("GEN03_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '3e869cfbc45e2ce904382fba209b1e4df53ba0bc1409c9954c9ad06576893c4c', 'anchors/b.json': 'e2152dc11b8f353d69ff64ace7ff1dac6b31cc6506eed298504ced01cdc3d36b', 'ancillary/extra.json': 'fc367b9a564e5d88442f0713804ef249e712c772217c29a51586485631558b8c', 'ancillary/meta.json': '316df2eda3e7eb84ccb317bf3c8ff63a0c93a120cbe36ff0741ae3bf49aca138', 'ancillary/notes.json': '46782c722ba47aeb18c36983db50c49711e30978457f3b750b7ded21ef3b7345', 'domain_layout.json': '9e9a2d9cb7062a708e37972a72251372647d2aab94ee47578720ed22698de984', 'incident_log.json': '8e29f30f556eaca7b01a79f2f6514e73fb9705acc55fa49f731d378d512eac83', 'items/item_00.json': '8fcfb9183c41da2172b6616dc1010db048e08b726c7e965441ef81a67fd2d20f', 'items/item_01.json': 'cf6970c964ae5f8c50fa43737716f769dc4bcfb3e9ab0b4db186a913d432f57f', 'items/item_02.json': '7fbea79fa631db0bed0a000eba39ea41b4b0edb86d7c60146c5642af56ed1f02', 'items/item_03.json': 'a8fbf14e3fb772c59d07502bdedbe0f89edb2c7cda7629b6c9c58630f80281c1', 'items/item_04.json': 'a5b058db82aca53b721316a0a80dcd01228e72ffcfa77c12c8244230022e629d', 'items/item_05.json': 'a36e5004c268ce284ba798e75f419332f4251807ab72edce77f05966529bef1e', 'items/item_06.json': 'c30f6323f015fe75adceed1d6f5790c5d6651b5c88502c5ddbba20ea42d7470f', 'items/item_07.json': 'd184784786597a2b2393f2cd270abf3cd189fe7fed16cee951bce472a7d8234f', 'items/item_08.json': '08c672c5d491fa826e77657d7d481b865c20fe7afa1f68eddf5cfba9cee8cfc7', 'items/item_09.json': '06b6677f9211014b85f70cbcbdbcd271a62a5456508082d478faa0e435d2b3ca', 'items/item_10.json': 'f81fd1d95e67bcc40d1401d46651cf44f09f9b511b7cd5ebeb71cfe2cc29a53e', 'items/item_11.json': 'ae634c4dfc5f103e5a44e46d34c3e2fb59b26bcda17dad5a9fcf90cac62d2419', 'items/item_12.json': '5b347de06f01c7bb67b7172e6293b7015c84361b705bc2a7ce6b4e6adf87ad33', 'policy.json': 'b9712b7cedd10ed3fa7592dee8348f0761668ed28896eb3e1c6098f8a725b5a4', 'pool_state.json': '6dddc28c79aa4305250c512e680e901d162f5df30f17fcfffb633ca0fff0f731', 'SPEC.md': '32140695526dad3e2c78a1d7248ed6dc8a3ac93d7d711f51a593737080cb6eee'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": 'dc8c3d9075e65a43dbb2931f28e8a1299cb8db6c76f2a8abc56c39a2a2f0d7d4'}
EXPECTED_FIELD_HASHES = {'totals.square_drive': '052216fe50a8f7636cdb0ac1bb3c62f4f94261d5d914c706ea5566c20e341960', 'meta.task_label': '8ca55d1ced9fe7a4a2cc9851dd81f27abeea0e3ed30ae6f84fd89dfdf23f29ae'}


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
    ssum = sum(int(row["quad"]) for row in items)
    assert int(totals["square_drive"]) == ssum
