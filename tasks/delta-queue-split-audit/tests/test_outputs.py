# scaffold-status: oracle-pending
"""Verifier suite for delta-queue-split-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN04_DATA_DIR", "/app/lab_04"))
AUDIT_DIR = Path(os.environ.get("GEN04_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '29982c01a85896e97e0d71ab0ffbe24b483c1443f9f6a5f3f78d46f08f17436f', 'anchors/b.json': 'e69e7043b5902f938df1a6c84bb83983b8fd9812f65203e3b981e389c1bba04f', 'ancillary/extra.json': '96ddebd495cbfcd1c4acbc453c7f7ec4a05f66fa84ab57911b4b6a4f8de3a02d', 'ancillary/meta.json': '00d2773f205dd5c39c075149fc6eb0e20efe6683446b3e45b13e1ed0cb02ce3e', 'ancillary/notes.json': '749fbd76577c4a00faebd00be1f196777fd1b7d7e8f61b4c234976de5e15f819', 'domain_layout.json': 'bde97bf1fafefb917680859f6c3d20f6f33f51b8777b8cf47367d86906dbc2ca', 'incident_log.json': '2d2ff0fc920833291e46839cf05e217da4d50033e2a2d6ad924edac2f1135d15', 'items/item_00.json': 'a6c26053d9bb54ace71f2317037193b557726aac4d0b0790e06fa4a201ccbd74', 'items/item_01.json': '65ccccdc1a6f728dbb12bd19d03c586d266a9bf8afc736585a9fd6776d8111e0', 'items/item_02.json': 'ed357605bc1db87c37e2fc419046cef944ad9482664ecb59533906c27a8e07c8', 'items/item_03.json': '1a5416551e5bc1f4887eacdff9417428cd661ef3ad5b4138718e5c7b5abb49c2', 'items/item_04.json': '0d388e2c7e26636c05edc05ed2311313a6d733c3dfd68f60d82a1706bc5cc1f5', 'items/item_05.json': 'e3c87e325dbd59da2583d10a2c1e42a7856156324c92a3929f5e5a653d2e0b18', 'items/item_06.json': '81be1b8708eec3724192e43dbfcd0c266a9e3a8843afe7acb9929f1874e4e1b5', 'items/item_07.json': '322244dbeb9f0bbf268e33acbd33a581a0c03e2302f8bb467e758eaf02b747dd', 'items/item_08.json': 'a4483f3d3070bfe35e8a483332c379c6949707000e91d73fb48b572cc7367fd9', 'items/item_09.json': '92461d487d13b851fa1c7003fa2961fdce9997b60f4e8d71aa24d5f1f5c321f0', 'items/item_10.json': '6b6f21eab51f8fac1b621bc857ecc6431d3c4da16908e83f6c81a73b2001f206', 'items/item_11.json': 'd8c88450c6b019aa42fbc62e8a6d47088ef2acb81d9912041e27575d2f3d0023', 'items/item_12.json': '215102bfab3336a1d5fa62f893f1b05892321668b9f6023a692af53119d6dae6', 'policy.json': '4ad225026d895ce36a3cd2bfd4de818314f0ca96a6f1fff1a3cf18e749aef187', 'pool_state.json': '77068f0d531d4a4181587f1560021558ce2558b1f1df55d5f47e8462e6b7dc28', 'SPEC.md': '1147622864751f0fc371281bc8c57dc26db7b995d247e2a30e8d81a0eed4cbcf'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '93ac15517ff089476a83ba6d91a49239b360abbd4b4b42ce677b069ef0754a1b'}
EXPECTED_FIELD_HASHES = {'totals.masked_fold': '7978a5cc69504b7beabceac8a24309ceab2af3a211f7c635b7a8501ada39410b', 'meta.task_label': '7200f91f88571c0905dda993ee5a7dbcaf58d13d3bb3733a600ec5fdb5395d5e'}


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
    ssum = sum(int(row["bitfold"]) for row in items)
    assert int(totals["masked_fold"]) == ssum
