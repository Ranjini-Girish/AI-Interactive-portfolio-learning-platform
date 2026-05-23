# scaffold-status: oracle-pending
"""Verifier suite for quartz-ring-flip-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN17_DATA_DIR", "/app/lab_17"))
AUDIT_DIR = Path(os.environ.get("GEN17_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '9afe70f5f8282b71439f3a547902b246eefaf54f3bfdc0b8bf8501cc4819e0f4', 'anchors/b.json': 'a78cdc3b59e3cd4f4d58d65b6508159522b0cc4a63b28bce5774e104ba7f38b3', 'ancillary/extra.json': '03686e5768213bbebf722131c41b6202c7410835a63f75c3c80fc1c7e742c262', 'ancillary/meta.json': '50860dba09b6fcd133314dcc9ddc8671c867a48b9004d6817ffc14cd81a7568b', 'ancillary/notes.json': '386f1e1517d618a88de039ae413b177895b18ecbe876bd87f134b71289508bf7', 'domain_layout.json': '03e5671a152b3b12af08e41153dc8616871af747e5a4a8a3d208184a46234484', 'incident_log.json': '4be45150f9bf24c2c769e5b4db18f8a5674a8225321a5a01e56d80352397adfc', 'items/item_00.json': 'c0ee7121383e5672eecef71639a8a5dec976468c124c181f8a0558acdbd3e347', 'items/item_01.json': 'd744f79a3f7d752123c90e556eecf98b5c1df77c4a60bb57a5f945e6b514464f', 'items/item_02.json': 'a1b34be1fdd5352604d7af86e14ff01996b985176888c8fdc9d5462a2daccd3a', 'items/item_03.json': 'e8254454f89a695ca426f79862144cbcbdc79466f11fa289f6d9a25551aaa345', 'items/item_04.json': 'f98ae9eec02166464195726ee5e740a67965072b0f030b66a9e9c4b7f805500c', 'items/item_05.json': '79c967eb3d5c3af3ce86a43db1d9d13ed3fbd51793f1f34cf0bb0902d5661795', 'items/item_06.json': '072d0674e092f3b6cb5f80a9729d4991cd92c0f29bf8887dd5e00735c2b8fbee', 'items/item_07.json': '354becd245c45845c7337cea88b23e931066f31f0a009d7c2f1d331bcdad62ed', 'items/item_08.json': '33054e1fade615c83bdc2deecd49e96024bdcd1f8b59603e8bcc18e1d244937c', 'items/item_09.json': '8ac823b4f54711c5421b835c92198b10076aa97ad40d8109bd1ce0344ec1f6f1', 'items/item_10.json': 'e2e86d056e198f98006b027282b2146c269875085d1aa32e90bb56792de781ac', 'items/item_11.json': '0a6ca0c8d43e0ab163b79c0b72f12d57dcb191060fae0dfc4bfa7daaf2550b11', 'items/item_12.json': 'a784508a6fa567a76b3a2b088b90896cca998b26a51988869d89b7ab4848105b', 'policy.json': 'f1b67bcef2ad4b643971cc0afb5ef0b86afd88002ca2034c0b95d38bce329f12', 'pool_state.json': '6dddc28c79aa4305250c512e680e901d162f5df30f17fcfffb633ca0fff0f731', 'SPEC.md': '0af1aa230d1bec558d091e8c6c0a22e0fcafff6c19bc6c48ff8f207bcce272fe'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": 'c20499f54f4af18c8f9c31fb8c8a4fb56e2130f0e2f6d7f8ebf776ed6fc5a6d5'}
EXPECTED_FIELD_HASHES = {'totals.rotate_sum': '94f237831755112ed6597937ea6457d45f8ddffd0f538fd761dff18d0343f3fa', 'meta.task_label': '5dd04d5775fb7abe86ab5149a2997304524ce0b2e08f7b818cd1e546ef727de7'}


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
    ssum = sum(int(row["rs"]) for row in items)
    assert int(totals["rotate_sum"]) == ssum
