# scaffold-status: oracle-pending
"""Verifier suite for nova-pool-spill-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN14_DATA_DIR", "/app/lab_14"))
AUDIT_DIR = Path(os.environ.get("GEN14_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'baa0826809654c13ce972ec3888aceaf88a4d54432542f462c4ca2e842270797', 'anchors/b.json': 'df7cc9b21771c027143ac8f5688b196cf27b53add77cc3bb47be2ee8b997002c', 'ancillary/extra.json': '0fb646a07bbf7f927b827edbf52814297db738e42d23740e7c8336331814d749', 'ancillary/meta.json': '2caed2620ba890a112269ca77f4792339f8129fac1e6523027bc448fa841a998', 'ancillary/notes.json': 'b8af6dcb27ce94f176293dcfec8ba1388a6cd8867431257b81c285ad9a3478f9', 'domain_layout.json': 'ed910cb2ee336a40e470f46bb8701bedafc9669ce74fa358505b3d7f610675b6', 'incident_log.json': 'c39f595d8885e0c7c4075752360a993884e2559e18921098ce06e8f7938233d5', 'items/item_00.json': 'cecba699b1e1289a5d7ed748a56f9b8509aa5150c66d6235b78a867498ed238f', 'items/item_01.json': '82f3825cf6955ffcb86b7b5eb5bc8a0c78e70c380b305b1b97957af37f53cf3b', 'items/item_02.json': 'd93f37b6ec33d4fff73f65c5c58e37d7510814df419bb9e4ae36fd6b5da9e133', 'items/item_03.json': '5698fb0ee7bf7c2dbf15bdb048a6c12599b7e0f2d44f53f938d6236649ee88dd', 'items/item_04.json': '7782933aa27fc260998df8a649c1647f795bd58068596bac1b8a778f3311af14', 'items/item_05.json': '600f18cf487164df8ddadca2eb5ce08605beaff41d5355b2ba30dfd6cff409b8', 'items/item_06.json': '0bd94952f6350fab083d720b5f53896806f9da24eedb36d7a3d19b08605ce9ec', 'items/item_07.json': '537569976b5d56a33d145d83740733835eacef80909077bef906af4a5f3f3cdd', 'items/item_08.json': '868f75b60ddf865bc127c82143d1fc612e9971a6db823aff14644943d7a188e7', 'items/item_09.json': 'bc92c1953ff5c85ef4450a23795d99573267376e4fb94356f141a8c0f7f5862f', 'items/item_10.json': 'd570160c011571f4325f8b5df813f2f5d46fc386c89c324846b058615e67c472', 'items/item_11.json': 'e2c44b0d6a4152e49e8c533dceeab33aa06fc3622dcb1563fd1b777bcec08964', 'items/item_12.json': '0c6ff37f3d56fb8733012adf8e31ee9d79f6b157f285716c025ae685fd7ea130', 'policy.json': '7b0c787ef95ba01dcbf16ff37811b3dec38462b4c1710c14d7bb161b86582908', 'pool_state.json': '2f97ca208a1083fed51e34df0fac79b82dc8f7001bfc6d630cd1fe223ac2eec2', 'SPEC.md': 'f356506912f46290cb13a254b128b2c96838c028bc16e9a120dce0d72749ae81'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": 'e9b919f76a7b937f02ec07379618304c409c0029ec2a6ceaf09538adff7dfa30'}
EXPECTED_FIELD_HASHES = {'totals.trace_len_mass': '81a64dc2d4d67de6f6b30552ee4dc37b9e637ff147b7b9895555c17d3618523a', 'meta.task_label': '86567c0c69985235e8e3573bbc63486d1a41dc4558d61ad54acb34972a9bf5fd'}


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
    ssum = sum(int(row["lr"]) for row in items)
    assert int(totals["trace_len_mass"]) == ssum
