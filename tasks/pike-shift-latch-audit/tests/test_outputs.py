# scaffold-status: oracle-pending
"""Verifier suite for pike-shift-latch-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN16_DATA_DIR", "/app/lab_16"))
AUDIT_DIR = Path(os.environ.get("GEN16_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'cc20a5a9c4ec500ce85c51f3587ab3692441ae1ed9a3dfa20b1a34cb5d3d28a4', 'anchors/b.json': '749294f2ca4eca68324d42f17067a1ae4e6ddd2bf5af2823ecdc42e090d3ce5a', 'ancillary/extra.json': 'de70a6bb60219066ecdd2611ee90e0305af6d6030a462202bea617238151741d', 'ancillary/meta.json': 'a39386ec6da549fbc96c434cf843a7e8b2ad3014e41d4d023730e65a92a2ae19', 'ancillary/notes.json': '6a7857fc75135958c6f5de6e92c56cbd61c8ee5df8c2f00f01bb5f3afb118007', 'domain_layout.json': '8000d5ca8b94134600306f07030f724a5cf590886caef346ce1268f5b2ec1ba4', 'incident_log.json': '298d39b5a49d285b108d5f7f9c2383749d987517aa20bb20da31c09eff1a5698', 'items/item_00.json': '0843825dc6d0ec462463dc29ab014e91b76f87391a6debdc59b8cdabd126bc42', 'items/item_01.json': 'f2129e8a664cd744638c254bb9fa490e1bacd28099ac462d1fd6dffdee61e8a4', 'items/item_02.json': '76647041420b7c281eb0a9faef42ba22fc4715a8e1d20e15eb8c9468a15c636a', 'items/item_03.json': '727adf8277242c1c3e41aa07a44b7bed06f3709784fe92aed90b3c9f3220e2dc', 'items/item_04.json': 'dffd8b8032e98c84a21e392737355918333179276b315334b964d7662a3319a9', 'items/item_05.json': 'f903464d7fa533e69cbbeafd11773660032dedc56a64bc770ba90ece27bfdcc1', 'items/item_06.json': '83bb2fd3267a0f48c8680463c99cc8df0f6a221d2432718933065728dc79b54d', 'items/item_07.json': 'f21d001236b7d50a3519e20a8a3d16590bf61b411fed6988bd0ddd4b6862479d', 'items/item_08.json': 'b2e2f4093e55bf4e0309979ee428ad1e2e8c680e08c1b00a372f31f1bfb31a67', 'items/item_09.json': '445c11281609e199fc5388cf7c87cecf99e5242287a372109aec18771ff45cfc', 'items/item_10.json': 'b5000289597b908854fa1bfda33806ef9e974fb8d98e5ad4a983be7b260fc8be', 'items/item_11.json': 'a23856a9d7c27f8b5d806592212be23b55b1e0d5362949dd781869c4884d462f', 'items/item_12.json': 'd32b516d73bdefb2f5e18a8d2946179475930298f5d68302e741c0eedbc6450a', 'policy.json': '583edfe3791403d9cb1ce7138c1939642c8802955204b20d5de68629cedb9cbe', 'pool_state.json': 'dcc69b8c2e0ecb289467ee145eeeb8a491a565789d123c134e0b0f9b29750902', 'SPEC.md': '5e0ac3b3d450ea4075614ab22cbc3dc4e57c8ddf5c4e48ed5b2a86ad0aec7ce0'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '9282364d51b32b4fef9133a17c24f24ce677e3b78b753f9ba48b78ed10202d9d'}
EXPECTED_FIELD_HASHES = {'totals.hamming_drive': '46e67c525617663b392a53c0e94ba79e62db62a851fb175ae87756d4e73c9718', 'meta.task_label': '3fe396f711dcd8ce8b4c7fda7e51e86f425094785bd3ecc5f03962463f088852'}


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
    ssum = sum(int(row["hx"]) for row in items)
    assert int(totals["hamming_drive"]) == ssum
