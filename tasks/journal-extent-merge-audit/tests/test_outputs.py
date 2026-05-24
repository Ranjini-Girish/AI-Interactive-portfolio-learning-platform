"""Behavioral tests for journal-extent-merge-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("JEM_DATA_DIR", "/app/jem_lab"))
AUDIT_DIR = Path(os.environ.get("JEM_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["merged_extents.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "c74159193784dddf3bc4008bfabdbda74db6f67640284479edfd90ca2bf68094",
    "anchors/guard.json": "9fc76de2cc0d33775293e8d798f573c984b12da9f2fe52232fc599c3a83e5677",
    "ancillary/notes.json": "7fe5c212ce6eb3e48377d2363895c544be1b459763856b4b7817f3510110c6c7",
    "extents/ext_00.json": "ab0b9a4ea126544e4d3b0052c3e4f06241484e3e4d5b0692c9b5242920e04043",
    "extents/ext_01.json": "28df81aae68d85ee6764aa5f9e272f2cb81399aa86be8f52b6f41bed2328f777",
    "extents/ext_02.json": "afade83c988770439da4c502705ecc6f431dde1b1610ba839ae7f53d21284d36",
    "extents/ext_03.json": "fe73b0eccbe6d61decf31a11bf06594d1c6a066fb9a8423619eca709fe9d96b5",
    "extents/ext_04.json": "cf4e984adda03a222c602095c8776950a0be87a204fe16d56242be21aaa3bd5a",
    "extents/ext_05.json": "bd1caeed3c68786b95e78d31121663eaa1cceef89877f3e070855f91c1f83eaf",
    "extents/ext_06.json": "484396e7272bc0caf20932d0ab99941c30f3397722f5d776f306e99700d053fc",
    "extents/ext_07.json": "15991eb4efbf8528d61903fbd663d7997cbe6a29020e5eb9d725279ef9e2d92b",
    "extents/ext_08.json": "2bfb13d117c1b47c9ac70bc2b1a0d5b8a28a2db59d01c3cf09555519e82b4d8a",
    "extents/ext_09.json": "17aeab8537c1a9de4b0691995c268ae634053c399a0b49a3ae7b87c3b849d416",
    "extents/ext_10.json": "ee4f202b3b6903b5722a8a5d5375f9f2f886263a75e51c480a64e0ba95097f63",
    "extents/ext_11.json": "28fa2b1ae25e16b1ff8fa95b6285bb755e8230200afb5f383374090bcb741f00",
    "extents/ext_12.json": "8ed56a347ba32dbd873d3c1ce354601103e54ce453f6a04ff56ec7df5fec4158",
    "extents/ext_13.json": "62ef320243fe64a346be2e9b119409682795f3412886a14bfd6bd129e6aaf9e5",
    "extents/ext_14.json": "6a05a2fe887614a4b1824e465f62e33fbde52df19f6c1a635afc673a63db939b",
    "extents/ext_15.json": "e21db2b31d27cf801d5337dffd5d8c4c0a12528c12148371ded7f3d2e81fab82",
    "extents/ext_16.json": "55fe25ff7b26588b610aa4b3bffd2cd082ab83214f0bc9de0a8a3cec11138850",
    "extents/ext_17.json": "f182605ff27d7bf174613cc330df7a2ad12243ced0138e8e8fdac046909a3ff9",
    "incident_log.json": "3fed0dfd1f7e1f58b4927fcdbd15521e5b55d205331183a97ed4d90df3fed674",
    "policy.json": "3bc313b5d5fd40c5a360f2c41b838626996b652722db07e0a09a861ad5d47007",
    "pool_state.json": "f81b5f8d542ab8b4ca1b420a0e461eaa70e43526abd0424462847fb6d12de1ad",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "merged_extents.json": "059c0e4c07a2f04f67620e3d60162189cd7a629535d460dbdb8a8021af730d40",
    "summary.json": "f48bec87fcc6aed617bdb15edc40d747dd0b0acfa4f28e56cd6cef2d78fdfbe5",
}


EXPECTED_FIELD_HASHES = {
    "merged_extents.json.volumes": "7c1b545b87ea6643042b080c4612148535f66e408b38ae0d5039e191589864fb",
    "summary.json.applied_events": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.json.journal_seq": "e7e30e46ea2c1381c9fffb2c3489050054d35ad938e958be43a29313efb3b268",
    "summary.json.merged_extent_count": "8527a891e224136950ff32ca212b45bc93f69fbb801c3b1ebedac52775f99e61",
    "summary.json.tag": "82e13dde70346cb1918cd8af84f217d52c9afd26b99991ce83491fe561251c82",
    "summary.json.watch_hits": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


class TestInputIntegrity:
    """Pinned fixture bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every input file under the domain directory matches its digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Hash-locked outputs."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file matches the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Nested summaries remain stable."""
        for field, expected in EXPECTED_FIELD_HASHES.items():
            head, sep, rest = field.partition(".json.")
            assert sep, f"bad field hash key: {field}"
            fname = head + ".json"
            key = rest.lstrip(".")
            obj = outputs[fname]
            assert isinstance(obj, dict)
            fragment = obj[key]
            digest = _sha256_bytes(_canonical(fragment).encode("utf-8"))
            assert digest == expected, f"field mismatch for {field}"


class TestMergedExtentsSemantics:
    """Independent structural checks."""

    def test_volume_keys_match_active_policy(self) -> None:
        """Merged bundle lists the same volume identifiers as the active list."""
        policy = _load_json(DATA_DIR / "policy.json")
        active = sorted(str(x) for x in policy["active_volumes"])
        merged = _load_json(AUDIT_DIR / "merged_extents.json")
        assert isinstance(merged, dict)
        vols = merged["volumes"]
        assert isinstance(vols, dict)
        assert sorted(vols.keys()) == active

    def test_merged_extent_count_matches_rows(self, outputs: dict[str, object]) -> None:
        """Summary counter equals the number of merged extents emitted."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        merged = outputs["merged_extents.json"]
        assert isinstance(merged, dict)
        vols = merged["volumes"]
        assert isinstance(vols, dict)
        total = 0
        for rows in vols.values():
            assert isinstance(rows, list)
            total += len(rows)
        assert int(summary["merged_extent_count"]) == total
