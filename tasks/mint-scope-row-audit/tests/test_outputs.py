# scaffold-status: oracle-pending
"""Verifier suite for mint-scope-row-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN13_DATA_DIR", "/app/lab_13"))
AUDIT_DIR = Path(os.environ.get("GEN13_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '542a47af07252706df5dd301686ad7a16a794668640dafa10e3c369e6d51b14a', 'anchors/b.json': '187e83b25587173145b751e68a0ca2385df0c3d96db15df560770f747f3feadc', 'ancillary/extra.json': '798e80897525d4f524fb804921f943a582e025ee24a10036dd386ce8bfdf3b35', 'ancillary/meta.json': '50e71b42b73285b86cc8c6370d874a2b46a58670da6f7c6df872293dc2af0d4d', 'ancillary/notes.json': '57adba58fbc349eb758d60ff16ec62e0132e86d53e941de1d7fdbb3f815ca252', 'domain_layout.json': '3f82f5bf070ceb24795bc3b9faa1380c2ab00110aabb4109f0bb8a6ae8f80993', 'incident_log.json': '71669f0a40dc6aa59b95c58ec5f5913401947935b557f1e068587a8a4a6aa273', 'items/item_00.json': '766a3f6e313337ed97a7472f6323c31aa2c98fb81cf5cbb52da073addabfeb78', 'items/item_01.json': '1f56a3d498ce0bb923dfe09d1e4f2832e906047cfa1c935c564d29f78ca329d7', 'items/item_02.json': '6367abffba9650fb4fae33f6f7b8baa75e1c6cfa4aef5fb3ee1871b1b571c5b7', 'items/item_03.json': '53a77c9b2e75016be263647fbb31f4b29fca230c8827f988aae6bbcb634d2b9e', 'items/item_04.json': '127ba403c82c7c326f3af1eeae50364bdb57d029e8617b6d07126765f3bbf905', 'items/item_05.json': 'f7508d4f43c07e7cd6a893a612089bb5868a269b8d53e95ab501a5796094fbfd', 'items/item_06.json': '53edee9e8e9daadfa9d00f1956f861dd5af400aab8adc7ff716dc7f0aa76aeb7', 'items/item_07.json': '27ca1e36248ed2b596b13d042a0e181595735483caf5ed45bfaca3a5ab7d2d36', 'items/item_08.json': 'd8f31b2c382de84116c3ae6b8a6db69d81336f9c373804ba53a41781749df6c0', 'items/item_09.json': '1d9b33f4e31dacea4e90a6cf4469a1f652cc093f2c56289d0acbc2f08577a89d', 'items/item_10.json': '50ee4ef3bf1f675706cb0325690238ff28ca989d512245d0587dd21f27bff041', 'items/item_11.json': '657ce25b7b0b079b6d03edf2a1b73189feecc4364af489f663ec3800bc8fc059', 'items/item_12.json': '81aad3f618ef9422bcd6f6e65e68a975ee3cb6d76f22e16240a3b5bb21894b7c', 'policy.json': '3f46791c61361495e3b2362a67b3028f143d1db8dd4c3bbd04e0abb0a2ec8705', 'pool_state.json': '50dfe969d3789746c192b5066a7e1f99b250c5e2c9fca82c90c9db05d28f8842', 'SPEC.md': 'f683529d89f2165334e27994b927e11e39b5ae193f845ba7505422da28aa778a'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '6057a5fdd3d11bb9de3516a6ad620537e553abcdcbeb5a3a9d5cb4af3f2d2f8e'}
EXPECTED_FIELD_HASHES = {'totals.poly_digest': '45f9e8827681bc409d8f31b017eb8fceb7a93da221b630e6f5e641cf9f86b761', 'meta.task_label': '59688fdf8f3f8cb6975090e7a06e89e74c529ad14e24cd9e327451b3eee22fb5'}


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
    ssum = sum(int(row["pd"]) for row in items)
    assert int(totals["poly_digest"]) == ssum
