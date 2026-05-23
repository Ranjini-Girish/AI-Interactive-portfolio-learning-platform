# scaffold-status: oracle-pending
"""Verifier suite for knot-interval-fuse-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN11_DATA_DIR", "/app/lab_11"))
AUDIT_DIR = Path(os.environ.get("GEN11_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'f6e0e7c6127f991913e8c57aedd124ab614921c06c11ca603645a3c6d480092d', 'anchors/b.json': '107ee480b0b425a11abaeeb05e903404811a7af4416334b5c150306f8cbb387a', 'ancillary/extra.json': '2dc2e0b10c159c45334ff3bcfd7a6a5315318d449415fe9b9f0738c4867ad921', 'ancillary/meta.json': '4fa8391fba81a561ced369c2e0bd08f8b18085da25eacdc9fb6827ad4f960051', 'ancillary/notes.json': '87a72db74f451552be5e67d75f34986bbbac9b21668b735020b0638424584899', 'domain_layout.json': '080a217845bb91a7c74bafe7ca9da8dd8acafde60ce82768a9ce7954711449fb', 'incident_log.json': '70f74f32696df75adff275d6f7c3a5d1b32fc598936be0d03b02a2307431b04f', 'items/item_00.json': '0a4fdbdd1d42f685df4c084b0f8de8dc20a656217f3c1e08666674e9c0409e57', 'items/item_01.json': 'e10d34d9fda5b420e3e8ea0c6c881d83cfa10b1bf263f43e61b4e2fc19311159', 'items/item_02.json': 'ce46fbacc1a1fc2ac32d1fdd0af08976facafe77b2ae1bb16ff809b1378ff4b7', 'items/item_03.json': '459114d2215c102be976d2cfb3613047b924a41cebbb7fff00e4eeae163404fa', 'items/item_04.json': '4d444419900e35a867fba054d18adce6dddca9da9979c6d91151f8601d968709', 'items/item_05.json': '68ef7919c9103f7d454b67d9d2997b30615b3659b7c3c24a48f39ac3269171a7', 'items/item_06.json': '3f326d59602ec2ca7cc27e5eae544fb753a7c5b3d9e1e8e88a2d75f06b748cfb', 'items/item_07.json': 'e1fd573db8f622619b9f264a3157d49dd647e20a5fbcda9fe84b0e9f17ccd9b8', 'items/item_08.json': 'f73869f349b39f2de4aeb69b946f19c798958ea55d7b8ad0370f02aecf39dfa6', 'items/item_09.json': '34f108b2049d3a9e2eb9aef0d611f98c9ec0ea2fc32941fc0b93e44dd11d47c8', 'items/item_10.json': 'dcbe1beae4eab0f004cc8a38c864ca6899e3469b4563e84bb0e7a6be1df8a955', 'items/item_11.json': 'eff51687412da1c698f8d311c0fdaee4b5c91bfb5ebcbb699bc895ca696756e7', 'items/item_12.json': 'ef65563cac07c40dd9ac13a2d674a035b2953549599c706047fbdaa9e71dd778', 'policy.json': 'a740cc1b55526e40c82206ffeb25a3974bd08be8d208a11ba2ccfbd3856386e5', 'pool_state.json': '50dfe969d3789746c192b5066a7e1f99b250c5e2c9fca82c90c9db05d28f8842', 'SPEC.md': '7a2f938f590a90cbc4eb9451ca82c816d5c8c0c77fc4cf374c96dd4fe1442b45'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '5c6e588a5b3d86ed50af262a98dfe714897a7ce7efa910b5b36760c85a2b399f'}
EXPECTED_FIELD_HASHES = {'totals.bundle_gcd': '7a9b1b9dd2e433fc1fc962c38ad571bf1ebb49cb365bfdfb2c36d3f059d6fdd5', 'meta.task_label': '4da45ea50a8b87082bf682dfb54d370e7c80374705f05aea5f914f2ed5c7bd76'}


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
    ssum = sum(int(row["gb"]) for row in items)
    assert int(totals["bundle_gcd"]) == ssum
