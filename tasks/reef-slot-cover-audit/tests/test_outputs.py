# scaffold-status: oracle-pending
"""Verifier suite for reef-slot-cover-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN18_DATA_DIR", "/app/lab_18"))
AUDIT_DIR = Path(os.environ.get("GEN18_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '77212713501f984e55a7ccacf2e52427135479d9c80d5ae8ea99e6928f830551', 'anchors/b.json': 'fd37e541f73c824720928972fad289966f7d4a254ad275126e429e647713d2c6', 'ancillary/extra.json': '78bbef38bb5f1d90c9aaab367b68362f23c14c72d098fd6aeea4e0cab50116f8', 'ancillary/meta.json': '34ad05e12ac4466a7fdec04e9137a2a0815b2cce1dc0645c2208f092fcbd4aa5', 'ancillary/notes.json': '1d5fbe4f2e3567f9540530119d97829dc2e932feb2e69d48ff17fee59178f7f2', 'domain_layout.json': 'ffe0fe746eb0a06174cd345902f83531a0fcea36878af80bbd57eb82af08c6c0', 'incident_log.json': '1a3368ce49a0b3f5542495c21b5092da933ce75f3b5af8e888fd5d3d84fbeedb', 'items/item_00.json': 'b3ae50c779bcc5e19de306ef2d77555c0471b2b41c7a13ec6b01705dd1f58f04', 'items/item_01.json': '93d3c8303bd6a46338982991ab1c7da53bfcf22c34fb8f2102a98addd30edc4b', 'items/item_02.json': '1bf701d4af4781772a8e42e2f676ebad761903ed257b90d8ff88c74d71ef2b71', 'items/item_03.json': 'd920a9f8288da37009e6c2a4b8ae7bbb735383762378a30e265bb0a188b7f934', 'items/item_04.json': '0f04f2cfbc6fe3e0811d42f943d7f1bf7139129d7559bcae80248d521a37bb7d', 'items/item_05.json': 'acd38aa7b93c19e676c39827d2208aa95380629eea6e24fcf005291b4d1726f5', 'items/item_06.json': 'b5d9e60b54675ccec09e0567413cd46ede6376438107be5cb0784098947838e1', 'items/item_07.json': '28693c40fa4a0969fb4b4d8b9922b063e28d8a714d307576d4f2a85944a5c967', 'items/item_08.json': '7217f5411f658c184d0274174e7e56fb03c8373e0084fa50d8056dd63e82f508', 'items/item_09.json': '9b9feefcfae9a45c53ab5752b3c5f6f6bedd273fbe60eea7695e0d0c194bf471', 'items/item_10.json': '90f5927a864cc6d8c39ae2804ace8de8305415c0c52cb59520cb050ef2d39967', 'items/item_11.json': 'a98732d634125a842b39f3d2d01ac9713f49f2c302e443d5c9c694e834c6de51', 'items/item_12.json': '7ca8a85100c4f023cce66c3c8536a734e04c8e53e1b5d51084faa8e711000ea5', 'policy.json': 'af22396674b0406e1158e0b6ac4ba53ba22579d724ddec51d7e92a6282ab9cf1', 'pool_state.json': 'dcc69b8c2e0ecb289467ee145eeeb8a491a565789d123c134e0b0f9b29750902', 'SPEC.md': 'b8715f7d2c070fde5cd93e0ca5b74d48757337fdc773a3969d12ae69da4eaa8f'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '83263c59749005476039e300a87238c209199877dcc6dd752c12b12ba430db18'}
EXPECTED_FIELD_HASHES = {'totals.decay_mass': '74f8d4b5c1276fad9a43f96a6cd973179c5dbed5b965727f05021cb441e3c481', 'meta.task_label': '4aa4257b0697ace7c2e321992d0215eb48f83d1191fb45252746de57b5296b45'}


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
    ssum = sum(int(row["dt"]) for row in items)
    assert int(totals["decay_mass"]) == ssum
