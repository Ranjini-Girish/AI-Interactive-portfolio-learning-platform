# scaffold-status: oracle-pending
"""Verifier suite for xylem-tier-hold-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN24_DATA_DIR", "/app/lab_24"))
AUDIT_DIR = Path(os.environ.get("GEN24_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '1fbb2ceca4a5f03f5132ca439e2ca0e3d05c9eda6615cfd7e7e85123fe81c29a', 'anchors/b.json': '7c59473e91046f68a231f88267de606e4eef5f68eba2aa81cac33193493166f7', 'ancillary/extra.json': '64812a37174cbf1f972faf6df306b08b50418085e4260b81efb7d17c9b09c2a6', 'ancillary/meta.json': 'cdf130a536087a39b2dca00031d6e761bbff05f70ce38f714c58182838820ded', 'ancillary/notes.json': 'dd4a22377db84ec9ed81e6fb7e987d52f675ba3378c0194753490165b796813e', 'domain_layout.json': '60d0ad80d53a905015a80eb9e66b66c397e905fbffc39c78f7bfbc872d5327bf', 'incident_log.json': '3fad69a454cfe7895920234cfed7e9424dffb866f03de4062333669c122c1efe', 'items/item_00.json': '355863eb3a8769ed3073fa512f096d35e8b1867f3204ff994bda7027e6ab1825', 'items/item_01.json': '70fbee90f0243b2378514e7366b9692f7891297463f89124060272cf09f842e4', 'items/item_02.json': 'fe84ab27e7c4bc36ea7e4229757afff5654f5d4d4db92e83fd8a5177bd519093', 'items/item_03.json': 'dfcb9abed2a5cdb57125e1a77351d84c6d3f6336561a8abc45b83f3c794739e8', 'items/item_04.json': '73d11561c87bd3c3398430c0193783f5e98df7afa6438fce49e83967045d29a5', 'items/item_05.json': 'c04dfed8e184e70de7dea5975e876ec2b4c8209ab8da2ab7797be92e1fce64bf', 'items/item_06.json': '4c25c0a30a90f6f7872c722678f8cb57fe8c0c9e8cc81878b2fbbe75ecb21cb8', 'items/item_07.json': '86534cc1426f8c8c838f05ea6e154930f1b956c1afc79aa1b64d595a24881d59', 'items/item_08.json': '925608297e67ea07bc95336adfe536ac5c5852b0ae7dac5a8eeb83f17f640cc0', 'items/item_09.json': 'a06bd6e4c0e460746e22fc7596b218079b9cfd1eb23c43f8f87b47e51fc47962', 'items/item_10.json': '2cbf37956f39f7fe0ba991eb4c6805cdc8a448af5fcda2ab9029347f870a0f15', 'items/item_11.json': '14f6b6dfc8bf32d36ee4556f5ddbc0c6073e735f202019044215dd888517f88b', 'items/item_12.json': '2c07f362bf3e0c59bd90edb2e48638fba5db45126dbb2223df7c2e79aa5015d4', 'policy.json': '450de74bdbca28e16d11c581aa0ab6ba6b7c91f91d06a8a067ae05f25cd97f2f', 'pool_state.json': 'dcc69b8c2e0ecb289467ee145eeeb8a491a565789d123c134e0b0f9b29750902', 'SPEC.md': 'c8c35964bf5de4a9aa83f0676965b057a43f4476a9b4beb0f5b08aea48e047a5'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '0db3cabb56e84caa686018ea905a8c3b556545869bee4077c20a78ef974e90be'}
EXPECTED_FIELD_HASHES = {'totals.abs_dev': '59dac69c02fa356c6337a03ef91cf7f19b07554a95a3e53d0e3baac34ad6cbce', 'meta.task_label': '1892a7c8bd6c5168bd63a13825c127d555c5d43adbcc02aa6eb59ce12074f141'}


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
    ssum = sum(int(row["ad"]) for row in items)
    assert int(totals["abs_dev"]) == ssum
