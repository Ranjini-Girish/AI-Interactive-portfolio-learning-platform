# scaffold-status: oracle-pending
"""Verifier suite for helm-offset-chain-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN08_DATA_DIR", "/app/lab_08"))
AUDIT_DIR = Path(os.environ.get("GEN08_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '2dda4e01734d1410e0c5a64c6602c3b0d59bd4bb4f76dbb81e63913f11a5aac5', 'anchors/b.json': '07f3379f294c33f069582796ec351069d146bd4ee914944ccce7cddec58c3d2c', 'ancillary/extra.json': '997872fc71dcbad33c51e63536257057a9bec3dea06405a30e7c058d7c848186', 'ancillary/meta.json': '2993179c44fe62d4941d76778fd5d95af97b1bc2e07fc0c435cfdfbc0cfbfb10', 'ancillary/notes.json': 'c191c2a1d83f34465a06fc64aa11daac4c31f3d6e6db9f1f8b92dbf5c1bb07bd', 'domain_layout.json': '4d49a8d713ba8fe8dea8c07fa1bf7a3a237e40e41404989e1dc5ce3a2f233fd5', 'incident_log.json': '60e7e6872df381fc829a27ae2d1b3ac6554b03e89268f201f92f2870d3754178', 'items/item_00.json': 'ce4130b88359f21cbd5b88d4e806394961d1af260902987b2275085759c51fcd', 'items/item_01.json': '7e34b638c08439cc477396e855c12e42374abab3da1abb70b735038155facad6', 'items/item_02.json': '297bb5772313c64cb755d8278d92a286ded899ab4588825755135cb84cb0744f', 'items/item_03.json': 'b173046201a87605932cf7c60e152add83c0d9bc0c8217cae8af6b487e1da2fa', 'items/item_04.json': '567f9c789e43235ce7abc4f3be4e8fedc66386524a300fda6345a65b4533f107', 'items/item_05.json': '833308e483336ac31b953f36416ec26400c944f042e61b0b8abf15c1b70341c8', 'items/item_06.json': 'e53aa5eafc0717a3b56e7a62db899d67c53c0713d490a49919ca6f7ebcc3f738', 'items/item_07.json': '7d9a30f7f6a1657eb87866babba29ed95a23fa58bc2d93cd7c69e13d3968c380', 'items/item_08.json': '367cc88a5400298500350ed33883102dfed11d5f87736316a63d354482c60a51', 'items/item_09.json': '192d3b21a43180a974720bd93d1f20ccd1a651d2fbe656385e679a5f3f021953', 'items/item_10.json': 'fd4ac311281ecf0a71573cceb59af59d8d5f9e535744df85c4c85767a1e9e506', 'items/item_11.json': '1b5fd9ea2e062fd64cf12c3504c7722ecd0645f50e10c3b3ddc510337c74c1b3', 'items/item_12.json': '0ed047a8c1b26b255784916b89ef23ded257d18a2fca5730c9d2f2625ede7b0f', 'policy.json': '971a5ba890d92b6b7a320b3cb7cb316af0d07912604c9fa7c8a90bf603b6b139', 'pool_state.json': 'e693a6e7c45482e0d5ac0221b8007ae15195a5e34119259c2af54766244709bb', 'SPEC.md': '8b6556accd6b5f609924c6593807ead7cf06bec6b3c81d899bf76b1532dd01b0'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '70abf739a6779f583539863c5f652ed92a30e95dbaea5df033fb74743f6a1732'}
EXPECTED_FIELD_HASHES = {'totals.zigzag_sum': '59933d776452c8a5a00db247871079d8ae1e273192afd2075cb917cb5bbe402f', 'meta.task_label': 'b9925f96b6437a4ffb324485db7a0d4ac20dabf3d200186ac65db076e8894085'}


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
    ssum = sum(int(row["zig"]) for row in items)
    assert int(totals["zigzag_sum"]) == ssum
