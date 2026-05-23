# scaffold-status: oracle-pending
"""Verifier suite for lumen-field-anchor-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN12_DATA_DIR", "/app/lab_12"))
AUDIT_DIR = Path(os.environ.get("GEN12_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'b3c79ce43aef4d332e8d9b13395b2fa7e1415b6560c10fd5bdafd63bc08003d7', 'anchors/b.json': '7c02956aa224ad3e63a29f41315f6e78e7cf505b3e4b444c0df6077b0e51b35a', 'ancillary/extra.json': 'e898635ec51e2b3cb46d8a4a945913f92791b6520b3df17f67ca42c3350266d6', 'ancillary/meta.json': '0b22c9c9b60e90cef235b223801b136d9bdf5ef84b5ae21a0ebd03d92ebb4806', 'ancillary/notes.json': '348e93fac55d23a88fb11948257083669be12cc84f3717a7aaf6d35318c3295f', 'domain_layout.json': 'dd1df034045feabe92489a0315b101637d8ec5e8ef7a93f777060701045ddfd4', 'incident_log.json': '629ff9f3f0351ec17006c9d711a6f25daaa543b2bd40333f1ee6ab58b2af3935', 'items/item_00.json': 'c84234846d969855175a230adb34a027537ad25b6c982a76792669339a227953', 'items/item_01.json': '6c70366e5bf5e0dad6b4b4595d84ef8b45522e41aca817fb36c5baf5c9e23078', 'items/item_02.json': '6a5e67b5ffa6835eea4f03fedadc3d43008ff6f59f3ef37979852364167e5f19', 'items/item_03.json': '6edf9682aecf323fa8cd897e7c980be28d97a116ee1432363050964751c7c395', 'items/item_04.json': 'a6c9ded12393b78eabea706937ea4277bb016466821c8cbd7041f2058c8b7d2d', 'items/item_05.json': '5871e3e1121e25ff34168069d9f6122a029b94734e15468786bc4d32dc7e3272', 'items/item_06.json': 'f83341bf11b5d114d09e1a12e67fa51aa16df2075f62aaadc46d0f2e44acf779', 'items/item_07.json': '264dfb959e75c699fdbaedf605d780dea2a91ab7f5953bfa0827b2bef3ee25fd', 'items/item_08.json': 'f44191398f24c46bedc619b37aac976063224df51c1b3d5587bf909d878e9b23', 'items/item_09.json': 'c67cdf5e0c6fd3ad6b9c4458d03b502c09cce075101fcd9cf681207b33ae766b', 'items/item_10.json': 'c0a41b3de426cc45bb9b0c0ac80503e0cce84e714eaa12ff6665e924dde70b76', 'items/item_11.json': '478402d6a14a3268b981d25c2c80ff228c3497ed14c830c9a486d3b5bbef1eda', 'items/item_12.json': '0f7935dbee93ca2425c7f157e503833745c2c516bf2e2daf450a84053174dd6d', 'policy.json': '79135a0d96e2524d31dfdedf795e3c149cefa0c9a7b19c3703e7f9bfd55d63e5', 'pool_state.json': '2f97ca208a1083fed51e34df0fac79b82dc8f7001bfc6d630cd1fe223ac2eec2', 'SPEC.md': '5a2682a4b996f5cf36ca2785dd42763e99a763157632b9298b829acd26b6ac57'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '65dfcf1c0617d986d7a6b01d4e7c2f2ce1ee6d7678ff5901b53094de403a5b27'}
EXPECTED_FIELD_HASHES = {'totals.sq_bias_sum': '896f2c7dfb8bb3cbeaef3731237e975e6454824b9e9a0f1dffb0f0451686d8eb', 'meta.task_label': '015a48b9d2206fa803461cbc49b7f559526606cfd486c0b2260d496f4cf33678'}


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
    ssum = sum(int(row["sr"]) for row in items)
    assert int(totals["sq_bias_sum"]) == ssum
