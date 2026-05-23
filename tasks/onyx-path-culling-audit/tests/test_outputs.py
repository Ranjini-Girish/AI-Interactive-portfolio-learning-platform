# scaffold-status: oracle-pending
"""Verifier suite for onyx-path-culling-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN15_DATA_DIR", "/app/lab_15"))
AUDIT_DIR = Path(os.environ.get("GEN15_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '4ae657582130ff779278387c0a8d993ac7a0a8068e3d81b6a01e8e87c6c60a07', 'anchors/b.json': '8c0b4c77a2ee609de0420bc1ee108d687f690a596d330c0cfdc291129c41419a', 'ancillary/extra.json': '4f1e7d0b343899fe6756a34f7ddc7fa42494455166de687ce4e8d9abdc3605a4', 'ancillary/meta.json': '1d0dc8ee3ceef849ae18fb855be95e6871da695976d73fb9b553869a5a75edad', 'ancillary/notes.json': 'b0fa803c46d199aaf8e404c01a7dc53ec743913f3fc04d2b5caeb4eeb31b0124', 'domain_layout.json': '6a242a69caf59d9046ef435d1dd2480b8e52eb79b8e1600269d4023de4667564', 'incident_log.json': '2730fb380f5be2864df801b2ca333de7ae3d63dff88b17d2f0c12c3278c1f305', 'items/item_00.json': '7162e5ddfa58f0556d7b9e1e2e85403dd70232471de13968395d880c2cda6a76', 'items/item_01.json': 'b6c555dc8f949290b0eeae9b0d328bfb52b9cfb3b0f857f05aa2a57f78537709', 'items/item_02.json': 'b22e3b465095e08749781ce5b3ab7442beef893c7d1d8073fc01f41e6cfde190', 'items/item_03.json': '95c0d72747d4b653490df94b686b75f727e1eb5d0f23590b665133bab725d29c', 'items/item_04.json': 'cca09c0c042bc28229a85dbe3f506e7a6434abe813f62bc9fa74bf62906feec2', 'items/item_05.json': 'f268dcbfbf9945afc00a54bb483eff79208bd9517266826ffff4e70b5f2f3362', 'items/item_06.json': 'f4acdbadef2f0a395aee9d04aa07ed6e15e60ea2ea07cbe13f2be80f8d595793', 'items/item_07.json': '105885e4741d40b9af7361f8a8714f524111ea3adb6048349f4acd1244b3a6a2', 'items/item_08.json': 'f09ee0f5618fc503b023b4e4646ff4b21ad818cfed42cd29560a4a7c42e5a16c', 'items/item_09.json': '5ef6fa39f47dc289e2ad5fc9c74ec9e4cf5b7443441657ea757b37d63424a1c9', 'items/item_10.json': '130903fe533dfcfdcb142388b76535038f938bdbae1115ac64871eee96eff54b', 'items/item_11.json': '2c83d272bdd6607b6dacaaa50dce55499bf0f5ca776754fc536f44040c48690c', 'items/item_12.json': '6f3efbb4b67d229f69714c18a44530b304b0930b5f60bec2ecdc52c2b1479970', 'policy.json': '2f2d238bbdabc41a394bc5ae1c8cb72f4e6695b8f38aa762c4aef74a26ac3da1', 'pool_state.json': '6dddc28c79aa4305250c512e680e901d162f5df30f17fcfffb633ca0fff0f731', 'SPEC.md': 'ceedec1507ec8ebff6e3729025dcf5c0ff15e06bb9d41891ede8e58575405359'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '53010d5e44054bf7ba1a47696462a480c3ea38d8c0773c804414bc38a01504b6'}
EXPECTED_FIELD_HASHES = {'totals.squeeze_total': 'ccb9ca95ca75b3c3e244327f58efc3b58a2115517a5703dc8fb74092f589521d', 'meta.task_label': 'baf32f735c1881d7c2bb1a35f85dfceb5ba69a121ce8705a7b51f79ef0411623'}


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
    ssum = sum(int(row["sp"]) for row in items)
    assert int(totals["squeeze_total"]) == ssum
