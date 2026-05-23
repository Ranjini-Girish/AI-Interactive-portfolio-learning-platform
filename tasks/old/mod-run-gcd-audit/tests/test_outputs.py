"""Behavioral tests for mod-run-gcd-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("MRG_DATA_DIR", "/app/mrg_lab"))
AUDIT_DIR = Path(os.environ.get("MRG_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["lane_table.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "a346b760cfea426600b99d7651c98f0d4b59611a3d73ffbd247596c29c6b5235",
    "anchors/a.json": "2d26b09eff88d9108ffe1321582762b4fd3faea039d89f31ae0202e57b30dcf3",
    "anchors/b.json": "10c005cd0cf75c8f59e4fff84d5d8d433df3de8a3a29d46fc596ea7ebf88d0e5",
    "ancillary/w.json": "154bfec51f75e32f479372701974117abceef6006ba435597691d0b206f9112a",
    "ancillary/x.json": "b1774a55dcf114e4111cab63d74c464f868036dc05bf6b10a670476b2872b7c0",
    "ancillary/y.json": "0d6e98eaf0a78263855c2c5e2e93e50364b524646ac0dc97f9a92d768d2570b5",
    "ancillary/z.json": "1cf8f42717456d22f2731ef7453f299557c9f51e17ec9255f5470c29836bde57",
    "incident_log.json": "2e496ec8724eca76766ec28ea16834fb9b7af779541b47ad9de3ce3f0c2c4607",
    "items/item_00.json": "9afcabef93d07c0f2f226b3d2868ada1856b52ba3d536095b4bc782dc3c9b4e6",
    "items/item_01.json": "754937a8678a1dc087cde72920dea94bc4b039876b9c7add4a393db487668a4d",
    "items/item_02.json": "af05725f64653f800ea5fa812e14d7fc5c96b2da3e36dfb982cd4eb170780fcb",
    "items/item_03.json": "3eea79f5dd782bb7f4b25076dbc52b110f12f8b4b26d6a0f2bdb617b043454d5",
    "items/item_04.json": "ca8f2d46f69fa17258b0be74b13edd9d6a23e600f9a05302d4068d5f64179f98",
    "items/item_05.json": "52895a2e3643a9fa96d31d0d897209b7005085a2b4f86eff6dae0e83d917b6fe",
    "items/item_06.json": "abf2e16782589714827c5d1a75a642bcb5311dd7f157b9a5dd607e2da294859e",
    "items/item_07.json": "42d8baa87c27bc553e1ef3253705b490f054cada0e149705cc091ee7a5392c9e",
    "items/item_08.json": "ce2fb2699f46fa67a5ee72b6023bb39940704ca9e853011561e341998660bca7",
    "items/item_09.json": "a0b366c44df8da48f5a63dfa69ff32267d3227889096a52c675c55a8ed28f721",
    "items/item_10.json": "ecf7d0666ee82148d27d4e550aea9af7065327babb1e2486da7b5a319a0d38c7",
    "items/item_11.json": "6e309057c1730b465fcfd5eaf76b44c337e948255fbf6e219b530bf71bc1ae33",
    "policy.json": "a41dafdd52b79eb553a02fa5fc17e08434ecc708cd9e1e03142ccc58b1109e54",
    "pool_state.json": "a5378c055fce683b06d1c92dcd76785a752ceb9bedca79f629c35b1866203c72",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "lane_table.json": "7dcb8b5bbca9203d45168707c6cd9338def43f08c7a8470e3a53f81c31ae1c72",
    "summary.json": "ce50665c2d412773b1841edc15105d1efac94eb84a2d32a4499bb20789365e5b",
}


EXPECTED_FIELD_HASHES = {
    "lane_table.json.lanes": "564aea9e9b3000bef787e1ee29d7727a2dd7fce3721b7ee0932b77bfdbe30f3b",
    "summary.json.regions": "7cc1278a6514f8fd314f0b22d619420219b9cfe4d3cde30287fc5c7cbe4f036c",
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

    def test_current_day_echo_matches_pool(self) -> None:
        """Summary carries the pool clock used for bump arithmetic."""
        pool = _load_json(DATA_DIR / "pool_state.json")
        summary = _load_json(AUDIT_DIR / "summary.json")
        assert isinstance(summary, dict)
        assert int(summary["current_day"]) == int(pool["current_day"])

    def test_applied_events_counts_unknown_kind(self) -> None:
        """Unknown incident kinds still advance the applied counter."""
        summary = _load_json(AUDIT_DIR / "summary.json")
        assert isinstance(summary, dict)
        assert int(summary["applied_events"]) == 4
