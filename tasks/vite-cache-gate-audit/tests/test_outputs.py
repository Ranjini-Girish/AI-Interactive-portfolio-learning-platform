# scaffold-status: oracle-pending
"""Verifier suite for vite-cache-gate-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN22_DATA_DIR", "/app/lab_22"))
AUDIT_DIR = Path(os.environ.get("GEN22_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'aa668ab296601008c0a7362bc652a5871df5dd9e0cb53fb0fa1d66aafb1afade', 'anchors/b.json': '271ba5914971189a62e9cb3614fc3edde735bac45d8591a95da73ee725ba9172', 'ancillary/extra.json': 'c21585be940ac0fefaefc4ab99783b12254e9a423d1cf4e44bac01795d705254', 'ancillary/meta.json': '7ecbf39eb5fced1717b59f9d89dbcb9bb8173a21f625dbc9a905f6541c3fbc17', 'ancillary/notes.json': '429ed7192486e54710b4e61b1d8c8c097df1c708d3f79d6a473420c2809bbbec', 'domain_layout.json': 'a4f4a725fe0ec2ca122ad65506bfe07ef76c1f3fb1d7744a24f644ecded964e9', 'incident_log.json': '7a1da1dc23b617dce8d0b8d5a41ae36807a750e14d74611903d314087dc5c1f1', 'items/item_00.json': 'b8bb46047a94510c72bc158a057fd9d33ba8d1cc247208f2baa23e60229193c1', 'items/item_01.json': 'a5c4eebcf316d479ad29a4cc235ce333918de950f92820d313afd9b476bb93a1', 'items/item_02.json': '95d420314b247aeb0270d3ad8d8154dd2fea872f507e6efb1e7e01b72569819c', 'items/item_03.json': 'd1c7b4c890dbe1a79eb2755cd53a41aa469867c8321d36a201741d74d9b5af99', 'items/item_04.json': '172e876a18bb8f78d8498d372a8589640d72a2236db9ee4327269d1caff98ac3', 'items/item_05.json': '8ac823dd37d01e93295f7320001308b05e12666ec85c647bb8b8218e59f974fe', 'items/item_06.json': '4f59ccb67cdcf32a3d9d6f5eabf7f8951469ab21bf5a717adbdc5e6ec0cd1c12', 'items/item_07.json': 'b439ddadb8271666657c2a3f495fc86787d1250758409d019fd71d8307c6495f', 'items/item_08.json': '2b61a687311566f9dbb1bb8eb0b388f6f00678c86b5ecca65d599e8f9befd8df', 'items/item_09.json': '2e62570c8800c48f1827e49bd7a1860dae7420d658f1ce8daebfa1f6be1e650c', 'items/item_10.json': '867bd6779088473fb339c7de974eebfddc96402d19568fac589ab1ed93940f2b', 'items/item_11.json': 'b15f97a068ce721580e5750241761443e09e4bd409a42f1777ef44f694655618', 'items/item_12.json': '29e8c102d55984e0b0f061b060b721d0c8fefc28943aa70afa9c65ab071fc30c', 'policy.json': 'f5805f4ddb1820032d38f959643d649deb13a110bfe64a3343ed7b09d99a50e6', 'pool_state.json': '571f98eea35ec3eba8252f3c7351d686f1a13bc627c4581d895ff3721963d872', 'SPEC.md': 'd26ab10b7cebb611df4dbe00f7b5bb7a9a5d41d006de932aae8959c77e2e9bfa'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '032414c28864e5474da71a0b3a07d775b8434acdae2d06e4ba9c2c0ed9d556cf'}
EXPECTED_FIELD_HASHES = {'totals.stencil_and': 'fe4f4f270df95e1b05dc0f682ec6f10ec55644cd1d6cfe07ade1807347020057', 'meta.task_label': 'dd23c2c3d3a86281128990177195eb289f8cd3fa1866a341100f781dab8b6bda'}


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
    ssum = sum(int(row["sa"]) for row in items)
    assert int(totals["stencil_and"]) == ssum
