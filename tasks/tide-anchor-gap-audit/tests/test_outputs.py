# scaffold-status: oracle-pending
"""Verifier suite for tide-anchor-gap-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN20_DATA_DIR", "/app/lab_20"))
AUDIT_DIR = Path(os.environ.get("GEN20_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'e9b5dde4e3ba23a63917126d2a3d2bb5b4c163c9237f0b6dedd87b4143318342', 'anchors/b.json': '81da631a6314b8ca0ca4d8f01b5fb1581d6cc28a6b3669814d13800279ecfebb', 'ancillary/extra.json': 'd35d533efdf5a0234b6b881dfbf5694c7315588adb2adb7b84602e78cbb9a642', 'ancillary/meta.json': '76239411f54f13c8ccd28cbacdb391d1733f742554ffcb82207c6135965d8d37', 'ancillary/notes.json': '539a8be5f9d6adf0945c4d4e427b2d43bc96988a33f0b7d11823b657043d84e0', 'domain_layout.json': '21dd6bfe058527e986763a1425fc965ad6339de44da1c084d819db6006ebf7fa', 'incident_log.json': 'ce90e44b8328eac9e30c5c1b17aaffbef17645138e2ae86d32c579bdf19956d6', 'items/item_00.json': 'fb523394af0e003eb766eb32748479ed06f771e91e7b2d2f27a29e5b29494af9', 'items/item_01.json': '18ab4d19d09d935f6ca5a075ce18cd5cefefa6fd82766f49c6833e5649b63ab2', 'items/item_02.json': '1b294ec8f5ac8c6ef3a35d0f170e879160884b3e2cee1cdfc585ac3293d6abd5', 'items/item_03.json': 'b4bf8592c4b6ed72f0bd57963509903790715a60e8915973e4a1fed510370a1b', 'items/item_04.json': '2ac2e462db5880bc6bdcef7d0eae2ad50072697b3c3674a56316f20b4298946e', 'items/item_05.json': '85b80c81567ba69d1ab77e8bc07e7bed72ef536d86b19d065032546464047a25', 'items/item_06.json': 'f506721d90d26263ca0046f1ac5a7626274d7f19c7007029a55cdeee2aff7e20', 'items/item_07.json': 'e32428b560b719a6f47530b4f53f650a3aaf3b738ede5f71acac18bb33fbe2c6', 'items/item_08.json': '0d8c99143e75e9f251c39fb0343da49c05a865d8b478a3266cf9e2b7d6479711', 'items/item_09.json': 'efab1cbaa8ca4c11b4c1a741ebd6509a5006439a650d35243857ca1091806a97', 'items/item_10.json': 'fe0e4d0104e08fb471e253172941ecac92df8a9ef6c2fa3a65e311ca60daa503', 'items/item_11.json': '6ce1645f1fc4817e52450d5e753cafee2249b4265fdf93018e566f87e834f49e', 'items/item_12.json': 'b1f623284b208f7be8ee6f8977ca646ca8b706c955ab2ad647da210e9133cd12', 'policy.json': 'c0bcc4061d62cfe0d83e096ec8ff47d267bce42f964b23fe056f5514594952c3', 'pool_state.json': '77068f0d531d4a4181587f1560021558ce2558b1f1df55d5f47e8462e6b7dc28', 'SPEC.md': '29d9e1cbb4b98f56746befb206fb9998e547d959a6d3439b907fb37c7d9832a3'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '68a74e0071ac52de428cb88f380002e4ce7de84215d3b03d12700bfed757d48a'}
EXPECTED_FIELD_HASHES = {'totals.alternator': 'a48317286e0445e807090fe301da37ceb30a15c4df3aa6c06a8d9cde05c0fd83', 'meta.task_label': '08f3ddd45d510bd0f6849b4ac4e3c09a6dada373ec60deadb3efdae8be9779cf'}


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
    ssum = sum(int(row["alt"]) for row in items)
    assert int(totals["alternator"]) == ssum
