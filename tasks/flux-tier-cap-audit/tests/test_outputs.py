# scaffold-status: oracle-pending
"""Verifier suite for flux-tier-cap-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN06_DATA_DIR", "/app/lab_06"))
AUDIT_DIR = Path(os.environ.get("GEN06_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': 'd8960be542b818b964e741d80815a905cebb3e3cabe3b42b3da43b160fe36dbe', 'anchors/b.json': '61546384550d6b14aba12c02d1ba0e827788d557c7a7fb2a92605ff6a4bc6489', 'ancillary/extra.json': '785ff51fb885fae9184800b985db82b22685c80ed712ff228f03f8719d38e631', 'ancillary/meta.json': '1c70a4635954d76bf554d867516b36d94219688e3db48ee3b4e4a7cf113ed787', 'ancillary/notes.json': '9a3c4f67ba7ebaea57487686b5666f1142c892a9cc3535d9c6fd9d6afe9adcdd', 'domain_layout.json': '2c8ec58ddf9f6003f51698eb6fd595ff81b6f257877d3fddd5085d156eaf7764', 'incident_log.json': '3a3aef3eea57e3555126ebb9d409622019f3b4aceeca6822a8dc33729fa8f6cc', 'items/item_00.json': '4324d2bbe1ac894d349caac25c345d8ca4854df56beecd41511843e3014c524f', 'items/item_01.json': '1df133bda67319f7331a6782904a59118ead8a7bfff6a0dfc4d1af33a73d2eb4', 'items/item_02.json': '65569a8b6d51318280da4db0f93491c4768ac17e866d8347bfa510d411bdf163', 'items/item_03.json': '2f1ef01f67056de90a92bbacd420820abc4f2cf6000ae46bd2506becadb18cee', 'items/item_04.json': '9cd239a878b332ee0a84b2003cec1f177d9cba8ab7683c7383a4ea3a416acc1e', 'items/item_05.json': '031b567b9e5cb342301a061568348826ef4b485181cd106562f811c02119c8ad', 'items/item_06.json': 'b34dce5924b01c4d1605efde92a80aafab5055bdf2799cec2033084e5c37b5a2', 'items/item_07.json': '7886492edd6783cc1d171a55d74dfc8f34302f2b1507c5b9add6bcd52f013de4', 'items/item_08.json': 'bebd474167feb59f4ed2dde9d57b23e280b3dc00d67c1c50cf490e6faf125997', 'items/item_09.json': '24c7753f4d531bd0bc2c816443a6404e0cba72bd157a9c645b4747b2f409e590', 'items/item_10.json': 'd0a757d442b3f5b776de7d951d2469bf53429890ef4f8b2660a1043e071d6423', 'items/item_11.json': 'fbc23c102a193005ac2b106bb4332c5c4f2f72cda0ebe5ce6264203aed124c2f', 'items/item_12.json': '5aadeee784cef5f52556e66e9888f153bc9b469d3e967bbe056607d9eef9cb34', 'policy.json': '32a01ee49ec9dff1b1b368f39af438234f19fd89fa084c33e9a1d1de40b035ed', 'pool_state.json': 'e693a6e7c45482e0d5ac0221b8007ae15195a5e34119259c2af54766244709bb', 'SPEC.md': 'ef41a29c3807fc0cc88476b786cbe395e1ed5f041612e5c57eebcefc37104d48'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": '09282109d16e111e52e0ecb717d7d829b402e42343cd52ae8a01125b0d66b5ad'}
EXPECTED_FIELD_HASHES = {'totals.range_spike': 'dcda112812f66db6dfaa0339956934817937d116b7b4a31aa3adaaaf9d98e634', 'meta.task_label': '602518bb425a0c596b54555023f920955deaa792933d169600d756b88d0dc2b1'}


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
    ssum = sum(int(row["edge"]) for row in items)
    assert int(totals["range_spike"]) == ssum
