# scaffold-status: oracle-pending
"""Verifier suite for jade-signal-quorum-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN10_DATA_DIR", "/app/lab_10"))
AUDIT_DIR = Path(os.environ.get("GEN10_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'bc212b27f04905689ba3ec58cf674fc08f608e4b1f44a3dc561ac77de165bf82', 'anchors/b.json': '5be166f289229662ec2f4b747a6f66e687e5df93784a4766d098af64af3cbde5', 'ancillary/extra.json': '859658a9e905085c3539fa88c882fc7b789953fb4027d576cb2a95128e5cdc66', 'ancillary/meta.json': '18f9a6303e39d1a89b284423690b1e73dfb409abe25f561b8097a121f9d39b63', 'ancillary/notes.json': 'de12bf95fd80af2f6f971d10dd413eae093b73bd4bc27f31008be317972bb6d3', 'domain_layout.json': '63cff3ff42c2e08f5b6d1f14061dc1b01665de0c0d4f8897832d127a764e29ff', 'incident_log.json': '822246fa8180df9363b5a4ad5473e8eaa4a9af1cc94fedc91a20804d6db9fd8a', 'items/item_00.json': 'a8723d8705b046288b26be25fd95b7cc6d88dc79c14ac3f72068764d3d9979d1', 'items/item_01.json': '82cb77fb31d8f277f20e708972eff71857092bda64a421a2ce812fe898c31b76', 'items/item_02.json': 'a1a871589a9f80d4d2f6af99bf752c3208982d58ceb2f7d5479611e9fdade608', 'items/item_03.json': '8e7cb95cfe312788675ac6cde3d2b835f84dd7483443d1bde7dff9ac8b071482', 'items/item_04.json': '17089c93c989dcdb5d8cef37074320933e1298ca65c9a9451d3b04785685a6c5', 'items/item_05.json': '8710a6ae841dfad204d7ac16ce80659320304629ab3a9392af89b91a3426a2b0', 'items/item_06.json': 'aa4df72a98b549e48af1e20670ebd7a80baefb3be664965c7af0951568ad35cf', 'items/item_07.json': 'f3f8287ceafc4eb9b4540834332ea30b280c838ecc9c0d1c6b567bbe40010d23', 'items/item_08.json': 'd298f8a77162224f3f9ffbd7a0c12f0d25c244eb58754a20e7bd8b4da5e011aa', 'items/item_09.json': '23907dd9a5d8225bcf3bd68156a56014122f8d97a61bedd4d9993c7f95bdb3c6', 'items/item_10.json': '4a437c60f929aec4fe173bbedc4d2e3590b3bcb696b2b64d83dd9e15a6cd4b4b', 'items/item_11.json': '3df883166962e140a39d385f5593957d242fc4a70099c4badfe8bbe2e5cdfb0c', 'items/item_12.json': '64fdb6f07ee86365e0e828f4bd87107ca5e9cf065575d9f2bede63c884762fc3', 'policy.json': '9af4981173b4d70589809ae0f131afa5f6c3ee0408e8135bef4253a994642acb', 'pool_state.json': '6dddc28c79aa4305250c512e680e901d162f5df30f17fcfffb633ca0fff0f731', 'SPEC.md': 'bf3d68e5a1fb5c736aca3eb417ea1a09b7bbd6767fde89edc39c5d07ef7483d6'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '0a0145b587340d50ebf0f64ee2ae22f7a7d29f0482e6c0764673f020ce31f339'}
EXPECTED_FIELD_HASHES = {'totals.parity_weight': 'fa4ddf29f41b575377ce14a7900d1e26b669163ca53b80ea3168c6801cf7e114', 'meta.task_label': '8b275eb80441f67f978c1b266b4499b35c4e38980e99a45f8364e1fe1a671419'}


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
    ssum = sum(int(row["pc"]) for row in items)
    assert int(totals["parity_weight"]) == ssum
