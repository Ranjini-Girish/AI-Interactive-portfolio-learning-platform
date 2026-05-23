# scaffold-status: oracle-pending
"""Verifier suite for ulva-claim-band-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN21_DATA_DIR", "/app/lab_21"))
AUDIT_DIR = Path(os.environ.get("GEN21_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '57df6d1a9142e02482aff06a237b176e3aa551ff7494009ad40d29cf74b88b77', 'anchors/b.json': 'd714807da3282f561213e84e31a8c394800cb6e01c1f03d269ece4b43ce4bbf1', 'ancillary/extra.json': 'a3599d7fd62f1c95768e9015873d6d98e71d86a2cca04b74da1d0768b97fd5a0', 'ancillary/meta.json': '1f7b88cb4da8e586119992fdd6e06dfb4374dfbd98090bceb47f94341ab688ec', 'ancillary/notes.json': 'ef999719e19e6d2684a8dd94ab4ea9bd89b76299b873a1c6aedaebe3a2637eb2', 'domain_layout.json': 'b2d54766aedc942f71886c2c4a8b59c271db7fd4af756f22d6fc68c340eb1971', 'incident_log.json': 'ef0e851c1ca752738f23f307f1d15d7d3f06045cd6806cf39420efb9ea990929', 'items/item_00.json': '9b8860f881b8dd5811ef3c7f25e692b085ca4e9ff2c7b0bb6d8d61f15adcfbb6', 'items/item_01.json': '5609bf59ca2fc5ba2fb34abd3619f4da574e6be25ea356b48a45fb7f3ff3192b', 'items/item_02.json': '67cbffa83d6e63132f16f1d374cc34cec49956e7d3e25aef92f73d7a7dbd3972', 'items/item_03.json': '9ac0f35dea10591f3f0bb39b41a2014ce810f88f73d2f9cf41933753925738c2', 'items/item_04.json': 'f22258a94b9d52e566ce4cbc91720cc665c3d6015abf119511899e07ea3e011e', 'items/item_05.json': '3be42a2035f56b5d6ae86d102b78272db053ffd728e2e4ad58c1da64f03c4a52', 'items/item_06.json': '1d2364a943ca69b73946d0da58832c03d99a26e2cc5ead90f7d3efee84308851', 'items/item_07.json': 'bcfa10780b15e72dac2b2e2f9943648e751031562e27887f389971deda641a7a', 'items/item_08.json': '4c9374f611fd161c2a2fbc7a5d3ba7f3c443a79d15ce1712d57f5a0b111f6bb6', 'items/item_09.json': '564fd7bedf2abfbca8edc700b34cb837235c1038990cbd9c7609c829f57fd24d', 'items/item_10.json': 'a5666f42b44eb11086185ba914c556767924240ff318cb2b27f0636c92b211ee', 'items/item_11.json': 'd77c571048ec37619faff10d597fabcd069e71c9945b746ed239a3fa802d7016', 'items/item_12.json': '19c63eaabb12c5d1517d8380ac733d0003d8ad7a43ed07fab9d96d60eb19d0d2', 'policy.json': '10b0551438a37479420e72dba0463af38d99754d7ea890455c8377af97159c0e', 'pool_state.json': '77068f0d531d4a4181587f1560021558ce2558b1f1df55d5f47e8462e6b7dc28', 'SPEC.md': '5648e5c4b29171653a64d6a03695f619ac9f4777fdcb2647483f42ddf50c0437'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '32773f6e7666751b01e45517964257c370ab582210cee989629b5dc6abb9182f'}
EXPECTED_FIELD_HASHES = {'totals.clamped_drag': '6219b932485fb6275fcf5f657b9148dc67b9e1137bb7b6e9d9d2461dc4b50863', 'meta.task_label': 'ab3974dc0721c39a043cf92f1d2bc69544571c8e4ffd0f426151d22424aa7fb5'}


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
    ssum = sum(int(row["cd"]) for row in items)
    assert int(totals["clamped_drag"]) == ssum
