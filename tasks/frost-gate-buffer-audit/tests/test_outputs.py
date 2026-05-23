# scaffold-status: oracle-pending
"""Verifier suite for frost-gate-buffer-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN01_DATA_DIR", "/app/lab_01"))
AUDIT_DIR = Path(os.environ.get("GEN01_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'ffbddaa64f7601d28c00fbe2d15fdad08aeaadc95a89fd349be213287fff795a', 'anchors/b.json': 'a0994049c49732120dbecfcf81717192d99e21cf4c1cdc751cacdd49d2f44d36', 'ancillary/extra.json': 'd9834670148431eed706bbf7949665f345dafa60fc9de5449b81f13ec9ff6871', 'ancillary/meta.json': 'b3ad2673be1ecc09db2ee1415f511e33e23bb9b2900acb712ccc4b429a9f868d', 'ancillary/notes.json': '05c1943baa5f53fd03311754cbe6fbdfcf161b11488ba19a9353717e36103f51', 'domain_layout.json': '3b87958bb268fc527b82508a7b5c5d10120b335f59942058fcdbceb997794f47', 'incident_log.json': '1e20e715a55e5ddb2fcb3fe19cba206034caa082fd1afc0896bc3bedf11d9433', 'items/item_00.json': 'c72829e3fd913c329bf8ace253cc6e4f571ebdc462b6000aba6a5797bc2d38fc', 'items/item_01.json': 'c2cf8c6b0e9e2dc86d551ab4b54077955943754fb19ffe01e11d5067a0afcbff', 'items/item_02.json': 'c2ff8677ee55de89a67f81ac8a00277720afd2d49ecb6cf26f4a3df0ac7052d8', 'items/item_03.json': '6f93f0181ebe10cd64e6622bf955a088013aad07f4997585922417ca47e94628', 'items/item_04.json': 'e9f33eb2a9be31b1dd3799fe9a6e2cb57da0b5d3b05a3577c805f7ab34dc78ae', 'items/item_05.json': 'e037a80e1003ce18cf0e10d9ea740c9e916cb3518af60bdd0559ff056f701f0c', 'items/item_06.json': '8252b5eb64465078a6eececa8d01ea2ec4859540e90b3a3dce35d969c9ee313b', 'items/item_07.json': '9485f84c2acf6973542f46cb0e87b914ea739e4d04bba0038c7f7564f707be6a', 'items/item_08.json': '7fbd5f9deb85083a9a5de1cd69aaf2ba53f9c824ae7bba8e72e64c8cac8448e9', 'items/item_09.json': '637430602b06b898b5255a115b74c949210dfc961f3dedd30f00925cfc9a7586', 'items/item_10.json': '74b6a7a1b323a190229804c646ce10c4041470dfefd50d61b7b0ee0e6cbc1dd7', 'items/item_11.json': 'fe7ae6fc2e9e8dc494ca9e678459bb0a6c21420c0f5e49e977222521489d95fb', 'items/item_12.json': '5114052dcdd2ff628aa944b9223d89cece861dbf3854cb252df82ab5b8847fe4', 'policy.json': '3be50da4371257174a327809f4d6f5b9e3edc57bf335cffeaad7856c520a63b7', 'pool_state.json': 'dcc69b8c2e0ecb289467ee145eeeb8a491a565789d123c134e0b0f9b29750902', 'SPEC.md': '593ea21ee0544827479e897e2b121eb6d9541bb9d25b36ffa93e9cf7660f2a01'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '9dbeddf1d0d561cff17f05a4a5614f1765d0ad843c13ca0c018f54038123a673'}
EXPECTED_FIELD_HASHES = {'totals.weighted_sum': '0c38972c44d623312ef30267d7ab2769ea74513d8a3a31eb77d8eda8860402d0', 'meta.task_label': 'f8b503fbad803372754cb189b686eba9b5019703b5138f8fa313a2929f641d36'}


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
    ssum = sum(int(row["score"]) for row in items)
    assert int(totals["weighted_sum"]) == ssum
