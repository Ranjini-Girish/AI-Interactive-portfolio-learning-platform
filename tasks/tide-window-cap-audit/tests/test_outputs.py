"""Behavioral tests for tide-window-cap-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("TWC_DATA_DIR", "/app/twc_lab"))
AUDIT_DIR = Path(os.environ.get("TWC_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["lane_table.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "6665cdb3cc6b74260dbed6471a10472739e0b8720ed4f60e3df5af916f223d41",
    "anchors/a.json": "c0e5d644d44382b27d9349b18f059a6de238a2ab0cc014b9904f8cca6ebd00e8",
    "anchors/b.json": "48867377f6801fe7e8bf332cbd3847953748a0cd2eca64726ccfb90d595b8425",
    "ancillary/w.json": "154bfec51f75e32f479372701974117abceef6006ba435597691d0b206f9112a",
    "ancillary/x.json": "f0460e2c9b2ab5799069cb21088e826cc6cee3d590dfc60a16ad94de79ced302",
    "ancillary/y.json": "0d6e98eaf0a78263855c2c5e2e93e50364b524646ac0dc97f9a92d768d2570b5",
    "ancillary/z.json": "1cf8f42717456d22f2731ef7453f299557c9f51e17ec9255f5470c29836bde57",
    "incident_log.json": "6c064d24d7b5cf39f51e975ee38572d4a11e8e047a2d0f52818b0c493db4b7a3",
    "items/item_00.json": "fafd400ba1908c23615283def1dbc5b396ef5bb50af3b5699cb2553479a49ec1",
    "items/item_01.json": "5ea55d9e49c269d8462d07a3388d738a7bf51ab406fe705cdce95a0cf5111d06",
    "items/item_02.json": "20c83d2a362020639bc3a70453a5a7f9f262643b22f6e9ddb5c05f9130dd3a9a",
    "items/item_03.json": "5f5cf4d267244a2e54d0e9dbc222328597a524d5bfa1b98a71d533f1da8981a9",
    "items/item_04.json": "c216836c54691348a6f0921d83d1c3ce4c4d20012218533b790c6e4cce642ddb",
    "items/item_05.json": "dfeef7c1425c2f2d0d6fb7854e993e3ac05c75c64030b473b0af161ebfe5838b",
    "items/item_06.json": "e6daa7c4d8f4ef29cd0ce9012fd956f2548764e9b69b1a541acbf7d40c58afc4",
    "items/item_07.json": "3754423378c43613bdd0f6893e4ee8ad2494f6f3bb079320bd3d8c86bd931bc5",
    "items/item_08.json": "e64b54f30f2be3eb3d3873af3e8891965dc744e8f8e2ff04e398bb1d4bdeabca",
    "items/item_09.json": "8fc7358b0be70c54a7768f539eca18ccfc935dadf77976c05f7458471d07f5b1",
    "items/item_10.json": "81e05f147fbb2ca7bf83c747f132f0779a7bb7d2a0d44642681741b600135ee5",
    "items/item_11.json": "c7a603c5336a411d3892b60cf4dea45f4378dc4098f168779391a83b6c974233",
    "policy.json": "e39e162d43991d2ea25b098a505baa8fecb6acd21fe683e46b437bac54c30a57",
    "pool_state.json": "45b5e7e87cafa2f521d4565e6573484beeea1b2cb99443f96d191d2edc8927d8",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "lane_table.json": "4347ca0ec9c56cfed4b59317979411082c6aef8602dd7c7ba549afdb71d47098",
    "summary.json": "701719635f047561f75f336b95b4294378aa8313677dc59464e61aa559f9ffae",
}


EXPECTED_FIELD_HASHES = {
    "lane_table.json.lanes": "e161a5a4f85f2b1b0bd3e9498e6e682a4ee2aa4bbac180a714972177da989a6f",
    "summary.json.regions": "d36f2edfcf6b26f59a54fd21e08e542dbdb7eab90db6d666cebac3ecd271c4e4",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted audit artifacts once per session."""
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
        """Nested collections remain stable under canonical serialisation."""
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


class TestSummarySemantics:
    """Behavioural checks aligned with the bundled scenario."""

    def test_regions_keys_track_active_policy_labels(self) -> None:
        """Region totals include exactly the active region labels sorted."""
        policy = _load_json(DATA_DIR / "policy.json")
        active = sorted(str(x) for x in policy["active_regions"])
        summary = _load_json(AUDIT_DIR / "summary.json")
        assert isinstance(summary, dict)
        regions = summary["regions"]
        assert isinstance(regions, dict)
        assert sorted(regions.keys()) == active

    def test_lane_rows_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """Lane table stays lexicographically ordered by identifier."""
        lt = outputs["lane_table.json"]
        assert isinstance(lt, dict)
        rows = lt["lanes"]
        assert isinstance(rows, list)
        ids = [str(row["lane_id"]) for row in rows]
        assert ids == sorted(ids)

    def test_lookback_echo_matches_policy(self) -> None:
        """Summary carries the lookback width from policy."""
        policy = _load_json(DATA_DIR / "policy.json")
        summary = _load_json(AUDIT_DIR / "summary.json")
        assert isinstance(summary, dict)
        assert int(summary["lookback_days"]) == int(policy["lookback_days"])

    def test_applied_events_counts_unknown_kind(self) -> None:
        """Unknown incident kinds still advance the applied counter."""
        summary = _load_json(AUDIT_DIR / "summary.json")
        assert isinstance(summary, dict)
        assert int(summary["applied_events"]) == 4
