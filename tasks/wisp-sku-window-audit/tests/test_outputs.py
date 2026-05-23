# scaffold-status: oracle-pending
"""Verifier suite for wisp-sku-window-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN23_DATA_DIR", "/app/lab_23"))
AUDIT_DIR = Path(os.environ.get("GEN23_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'e625f0edd4c79eaa253732c7407b50c21806c1969a1d2a7f86276fa0dd52efc3', 'anchors/b.json': '8f418defe3898c836602431bf2273d940003c7ca3d86b91ebfa1669e82ef2d86', 'ancillary/extra.json': '2277cd4a661fea807c500c2f5eabbcb34c17bcf74587f8ca4a134f5e92b7198a', 'ancillary/meta.json': '409c4d5ffd4a6378c166edad2fcb46c438e8f5ad5aaf66515901c0d488cca475', 'ancillary/notes.json': 'daf3f8a57964d90853f27842598c80a6d6eeee5d99ff5583ed01d6d8d1547b34', 'domain_layout.json': '8d6637f7d02fb1a69bfb9795741310c209317ebf38a98f5af627cda7b7fefe20', 'incident_log.json': 'eaad867dec57f7a78a390a90ed94e793b3628e26d43e3466e04d18ee97e6029f', 'items/item_00.json': 'ad4d80b0b30ebe6ce09904dc816ccd45598d9b68efc9b51df869206ba4c0f34d', 'items/item_01.json': 'da8ad91be44742fcd0f72fa5077600f51aced84187a5c9578f3751a26fea6a66', 'items/item_02.json': '5b8f3a5525383a6750f68e070570a8da65d1ea1218d469c9c8001c00e6e4acfa', 'items/item_03.json': '8ad30cab20c44d4e44ead452082f4f46b0ca0b9b481d18cdc2b1f0004470df59', 'items/item_04.json': '3af13a6280dbf48a44e62edf478e1e0066fdcf88e578cd23458be6daea007ae0', 'items/item_05.json': 'ce49b98b13aa12296e6189826ee3d2f6756196b9b108b65ac9aa2485e76815d0', 'items/item_06.json': 'f0af54f5f868c6734dd52869ad7df5c5d143af8ab9e0998f30573d22fb05b555', 'items/item_07.json': 'd1f12f151b9b7835afad690e90e476b1cc972fb168a4b2faf5b539a2aa224f0c', 'items/item_08.json': '800bec98485b9c2127947d98fdb5530dc64542cbdd32ac7029047b335e417c69', 'items/item_09.json': '735a82d0c210874184e81a853d024898416492a51e2a3c1fff28e3e76127e7f0', 'items/item_10.json': '7e6a55258a7f813e80b98ffd588563bf1e3bfc74c6e0f675905ed5f0be5e7fa4', 'items/item_11.json': '70a6ff8f5cbebfcf3b34da0133aa9b61c4c1cc3ce6327c4f9f02ee20074a6802', 'items/item_12.json': 'b1898821a833b9337f14f4feebc775602ceecaf40b599ebec05c19fb15d42ea8', 'policy.json': 'c2b0079fefb79fa5ae607bc574273d6a48e0d91e4bcd3d6d20b4af8726eb44c4', 'pool_state.json': '2f97ca208a1083fed51e34df0fac79b82dc8f7001bfc6d630cd1fe223ac2eec2', 'SPEC.md': '7ce131d8ba84ca01373bc091d6242f8fa92bf627b1d276e029244b1798e47373'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": 'e3f5fe39d727684d88bdaa2af3e77e8c8e3b0027c98d5db9eda04f9c8d8110bb'}
EXPECTED_FIELD_HASHES = {'totals.fold_product': '7bf3c227f531b4cd730604d5b5317698aff98d84c250406dbc621c2fc29dd8ec', 'meta.task_label': '350a606a025e95ab2286c140f591f5a5c9d18af97b877ebf1c9ac7e33e25e3cf'}


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
    ssum = sum(int(row["fp"]) for row in items)
    assert int(totals["fold_product"]) == ssum
