# scaffold-status: oracle-pending
"""Verifier suite for yarrow-skew-bind-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN25_DATA_DIR", "/app/lab_25"))
AUDIT_DIR = Path(os.environ.get("GEN25_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'd3d6b4951604f0948626a5f602f941919a10005c0ea240531a8f10d7f2ba8d94', 'anchors/b.json': 'ec149b7cb0758ed3276e42db7e3529be322533c20ff870aaf6bfc8fe06937374', 'ancillary/extra.json': 'e5e7c79ca8c5668654ab4f9d484b9a3723c566563dd14a587822458a1de49d72', 'ancillary/meta.json': '4827dca9f166df74878c848d5cba30c6cb65a6497595f3ebf9567898aad8484c', 'ancillary/notes.json': '4ce17a084a80cfd6b1d62e31f7e63f84d574beaa0d92aa576d289be2359533a4', 'domain_layout.json': 'b15e7b119a29eeeabdf260d894177d3882e7c14e3dbffc8bba845159c9a5c26e', 'incident_log.json': '0f8818315fffc12f7583abbd0078a6729ea31fd82e3c423de59c19b0ecd46fdf', 'items/item_00.json': 'd168f728b3177e4b65b266c885e23d6bdab51c4d26fddb733c699db8d0d97be9', 'items/item_01.json': 'd86bc80865ddc3caa21419dbe1fe7cea86c4bbc860bf91f442ce5c578f3dd2c0', 'items/item_02.json': 'b12e515037897812a1a5f441cca0600ca6ed408c4de4b24a945f67ee104083c9', 'items/item_03.json': '45dedb1724d2a5a28dc4be2f7d0805a3e29f0c5adc848778ee61a200e76ec4c6', 'items/item_04.json': 'd371ea9071e57647e4f6f79e8f0c6107ea52970784970054ea52620f1d1ce1ca', 'items/item_05.json': '2ecf778dc08590034a38d7344341ebe2191941161d6744637660ba20c689b571', 'items/item_06.json': '5692c0384db5e1debbf2381941febdcd42cd05ec4713a5edf5b013df5a0ec521', 'items/item_07.json': 'adc74b163630d31bf0cc51161f0f2846bd3e3d3da9c3ab2589536fc6ad568cef', 'items/item_08.json': '3348e851a934d7169c6b161307e75835a2842f834c19094d2a854385bdcf8168', 'items/item_09.json': '7f3f56b9e2590a6d55f3ae4991d5eb27138cda2152660697e545196bd8ad74c6', 'items/item_10.json': 'c3d6d59840f24ccff75b24c0e1c97ef16c2181fdc589ff607ea4a7327d4d4637', 'items/item_11.json': 'e8df499957ec20147f8488241f91d2fda0bf55e968f99ddea92c3035b8c66479', 'items/item_12.json': 'fca26663b2f40189f160722a1aebc5a487a497a41225afb89fc1a19a558a13fd', 'policy.json': '7e32889f96d871978ec6c8872a4b844631c1728a097861f9f9dfd716cc11c572', 'pool_state.json': '50dfe969d3789746c192b5066a7e1f99b250c5e2c9fca82c90c9db05d28f8842', 'SPEC.md': '80a4957d1d778ad4b673bdf28a90dd9f99029bd3e72ce9110b0bd2eb258bb944'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": 'bc040d9ed35f4eacee47670a078adfacb5e7ec93c011da96e2167bcaf344ed2b'}
EXPECTED_FIELD_HASHES = {'totals.mod_squares': '0f76754c69c2d97df14d973c2a396c0bbe7a720d4e8ff384e22cd93af4fc0a9a', 'meta.task_label': '9615416d5762e33179e061e3f12e298300812e18781b77796fea60dd11e72509'}


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
    ssum = sum(int(row["ms"]) for row in items)
    assert int(totals["mod_squares"]) == ssum
