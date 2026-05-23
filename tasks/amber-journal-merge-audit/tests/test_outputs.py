# scaffold-status: oracle-pending
"""Verifier suite for amber-journal-merge-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN02_DATA_DIR", "/app/lab_02"))
AUDIT_DIR = Path(os.environ.get("GEN02_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '6283c4aef75dad23fd5ad088ce07a9651c7a80f3a2feba7ca71295141985533a', 'anchors/b.json': '54889c9db31294a44df97cea5af6e56b9ee003d50ab1841ce134ec7af442efd6', 'ancillary/extra.json': 'd95e4b0ba3c298768cf6e239ee253e1dc7e1dd91c11dfd36ade9aefcdfd550ef', 'ancillary/meta.json': '837a35156ad3d76ac7a3bbae37cf857e7c03d38a4d6986c3dfd8d08f8eb97c15', 'ancillary/notes.json': '5028266bde534e6018232109e24f51b6d7c2b27d76e97cde3f79077d7f78faa3', 'domain_layout.json': '0499ee649f15873637c8d07e69726db2f1c3a5b447c85e39329485ed28fb3f2d', 'incident_log.json': 'b567969d457016577496bca22f9d7a08fb20527db66e7a86fb6e45ee3b76bded', 'items/item_00.json': '019a304f77fa8460ca8d93c3a627b49d4d000c49a235f58d046b910f88069048', 'items/item_01.json': '200afe3424b267804e02ccecdc1833bc2185a7c668247f3297979e597a14682a', 'items/item_02.json': '6407e904a1c3ca6cb26d27d32d77bdc77464ca9593e6a74427da925da22e6820', 'items/item_03.json': '6a21bee9815f85a36e134a1ae641a66e824f5cc65555a6d40a71b483f4fdf7ca', 'items/item_04.json': '213c83bd2f004cbbe37cad2124e22643fd52ee7f16153213fdbfe5adcf441b94', 'items/item_05.json': 'cb759bbabd433b51c23aa6311a0e4df75e5153d979ec0e9fda2a731a78abefaa', 'items/item_06.json': '5b6997d53434a80c685b6ff1e8b0c1984af50a64f45daa89e75d096fc3f8d63f', 'items/item_07.json': 'e671be3c2774375f24e77c11b7a528bcf23470edce6f4d3157f5e84bf702f096', 'items/item_08.json': 'e3103d85ba04d9b90923aa49e897fbad6be1364ad104a4b48ab6e5130cc1b3c1', 'items/item_09.json': '133f83833242acecc907b3a2fd9e242e990a9bb4df390fbd1c671b2186e2309c', 'items/item_10.json': '7f6985cf7f1af0c78ece0d939a65d9c337a1122165560276762dd31c79b69574', 'items/item_11.json': 'da41f1aaaeb6c9b141578d40c322932de90bb4d26b4205e7f69f7b954e95194d', 'items/item_12.json': 'b65b8cdc6ef058ad9b23558d8825c781271f5d97e06292a2d58e6ba98fa0e11d', 'policy.json': '9898c31e83ff7b0257a23a0d770d980e5d0b03dbc88c6312e6fbbe1d411d675c', 'pool_state.json': 'a7c6e0d75ec31c191f5d8247db9bbeed76431320cfbd1c44035817c558a158ed', 'SPEC.md': '099d9dc1439240e1c9378a6836099180fb47e16475b1a31618ff34302050095b'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": 'ddf3b9853e87d31d6f3b22cc46f0f3ccfeca516f8bde69f44496119cb4975d33'}
EXPECTED_FIELD_HASHES = {'totals.mass_sum': 'ec3fdcd8136188e3b476270894351cdc05dc44a4df50d1c4ed727294fb89430f', 'meta.task_label': '3461980800c0bffb33f183be07c7771d1221e6d73eaa7fae26864ff0affb3a3a'}


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
    ssum = sum(int(row["mass"]) for row in items)
    assert int(totals["mass_sum"]) == ssum
