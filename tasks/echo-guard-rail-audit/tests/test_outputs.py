# scaffold-status: oracle-pending
"""Verifier suite for echo-guard-rail-audit: frozen input digests, canonical report.json hash, field checks."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GEN05_DATA_DIR", "/app/lab_05"))
AUDIT_DIR = Path(os.environ.get("GEN05_AUDIT_DIR", "/app/audit"))
REPORT_PATH = AUDIT_DIR / "report.json"

EXPECTED_INPUT_HASHES = {'anchors/a.json': '795d1cca391ddad683cbc653910530103b3f0cdbc47d5f5725f0a12ac8199b23', 'anchors/b.json': '9ea7c6a50330a2d5c197003de6ad19082a028c0fc32af94ca4918c35172218ac', 'ancillary/extra.json': 'f58749569ec24be0557540bce724f70e1b78643ae9bb4a9e0c0227d0d8cd1a6e', 'ancillary/meta.json': 'd64a88eddac1ad584d2413eee1eb12cd4b1067d345d60a166856ee1253ed5e8f', 'ancillary/notes.json': '3a5fbc7fbf0b3f709f2589412c0e0355e8737c08c13f4c255e7636d80de38e5f', 'domain_layout.json': 'c3ba6872beae6e6df67b5bad5bd2647aa2d1cb29a1bf7cfe5be1d037e565e1e5', 'incident_log.json': '50a7a5c3db9918b3ff83fd1120edc06e5a38221c08dd09819c0a5e7e968e770b', 'items/item_00.json': '96dce645271ad3da2cfbbefcaf217e48d30848de67f35ada6fe5c90c425d17ae', 'items/item_01.json': '538dab9f526ce155198d4f0d488aacac621745b768a4d2995d96c71d80ba9437', 'items/item_02.json': '62d19a77e275a363e61241d5391474315dddcd2281ce2a604814adc348d704d5', 'items/item_03.json': '45b0b25f13d0c77040851e040bc11f937f8305fe9756ab567f0c5941bc935e68', 'items/item_04.json': '008d38d086467df3589c5a4097490a6cdca244a07120a11c3f85f88b2d5a4039', 'items/item_05.json': '0b5eae2bb0b0febcd32cffbedb4c3eb5e9af4aaa865e0226d83cc30830d9eac6', 'items/item_06.json': 'bbe3ad6f3df8804803fb3fe8c50d888497fccdac791349177bf9c116c0d11791', 'items/item_07.json': 'cdc53265d4b15b8e1ab25f0943c52ef54c0a18cafb0f1a6bb90a54ceb5236db3', 'items/item_08.json': '55b5a8a39fb1657fa9540cd5c9b591baf64a5a89f6e0d5171ee6684f3d930669', 'items/item_09.json': 'cd68f76c7bf8c80d4e8f1947fc623339dd29ac2f22fa9ece16bc8a760d3e7ed5', 'items/item_10.json': '6388035727ff57df0abfb1c75b6e8ce9b2dfc228730bf77d1bb04f3e44825f76', 'items/item_11.json': '29f2aea897a0d037269a51c433417fda2e630c11b1326c5a6fc949a59ed38504', 'items/item_12.json': '3c7fb7a247d8d0171d4a926243afdd78f01bd7181c95d93880bc5b65af1c7aea', 'policy.json': '73e240af431db65a6f5028488085d10aef31ab6e48d70e65e99facba22df66d9', 'pool_state.json': '50dfe969d3789746c192b5066a7e1f99b250c5e2c9fca82c90c9db05d28f8842', 'SPEC.md': '5cad01079cc554e66d1688a34c27fe237ca7c40ba7b30328a5a9940af6d13c6b'}
EXPECTED_OUTPUT_CANONICAL_HASHES = {"report.json": 'c31d41fdbb70dec3d2959d0dd18bbe34cf21361bd37ff1eee225e7ddf1a43810'}
EXPECTED_FIELD_HASHES = {'totals.xor_chain': 'cdcaf888b551e74fe7c4c6909b2216058d03a773f60aa31c5632eeba2dce71c2', 'meta.task_label': '534debe0845df4a8718d20d2011d7f7dbaa59dd01093699350c69efdbfe58883'}


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
    ssum = sum(int(row["cascade"]) for row in items)
    assert int(totals["xor_chain"]) == ssum
