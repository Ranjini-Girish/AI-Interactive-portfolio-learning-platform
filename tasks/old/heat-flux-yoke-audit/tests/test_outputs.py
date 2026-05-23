"""Behavioral tests for heat-flux-yoke-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("HFY_DATA_DIR", "/app/hfy_lab"))
AUDIT_DIR = Path(os.environ.get("HFY_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["summary.json", "yoke_table.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "33f81f30cdabb36c37f149b25e7bfa4fcd5f2652748e0588451635db979e9169",
    "anchors/a.json": "8870684a1cc73a3847d386f8a0ade5d0773555e9d87540ea7cdb7f08312bd6d3",
    "anchors/b.json": "fa146c426bd40efd56d7672fd0a0f8a742e591b3666ccc85bebf99065e13fcfb",
    "ancillary/x.json": "bb1cd8a5fce81331b87e2c1cd037d0b9d0f07c438207943b781475b5714c3cfb",
    "incident_log.json": "dc747af1a9f93a4cc83db7912c24abec1645775241bd82e5b16d151c61ed5716",
    "items/item_00.json": "c1c02bdddce81139fe216b8e33f7fae25e850504273c3a31792aa4b4bc4f675c",
    "items/item_01.json": "bb3c95985fc10a023b37765211960316ce20f391750b4251627837e995cca6a2",
    "items/item_02.json": "e2dccd55400dd76b33a9bcf33b13e5ba59ab312166498afdf4d182cc8096ca68",
    "items/item_03.json": "b1550002b5aad5a56be4aecbcd37a8b7da614bd8246ad7fade5f25f5e2023b1b",
    "items/item_04.json": "aa92fd85fb48b13d2dbc458b191ae3b4603973826ccea153fb7d89e4b7a05c20",
    "items/item_05.json": "421dd263394cf21970d93c493b1335fda50565305c323bb655d32320d7cb014e",
    "items/item_06.json": "baf762037535651861b90a39de952dd74201c8b84f745edd00f973e54ae429dd",
    "items/item_07.json": "c4604a9f6cb3110e7c397674948a1d86613293524aa78b17b1c3a07a311c2b2b",
    "items/item_08.json": "dfe8cacee64fb9e3eb44d22f0945557a492d71fe29379c5481070cb7523478e9",
    "items/item_09.json": "9f2040626f7e19a54fe6988c115b6b679fbc18a90de5ce77939e771aaaca18db",
    "items/item_10.json": "d8f93f02782f7bd00c34292f6daf0bcadee4e1e4f2831b15320d4055caa9b9b2",
    "items/item_11.json": "e76f1da27695611ba3cde17f020233be46444ac060c08ec3a2da606fab77896a",
    "items/item_12.json": "12aaf86bfaba885e66dfa0f0571edafedd096b51c4b799bc828825f3f4994dce",
    "items/item_13.json": "53b4309a7cb2c8187cff0e49e58ec082b1b48e0140c2967737d15ba3af9e4fe2",
    "items/item_14.json": "a69f8c8fa4423bde298512260f96e54442382a3b86ce75f0572a41ba041c0580",
    "items/item_15.json": "969d527fc9922a20eba47f898a3af5f671a38f2381c9ebef09994201076c8c51",
    "items/item_16.json": "7eb7c3c3f4e6b12b1fc805f7d9aac5da44dd8f2cb210c458f0c8aa989e5794d8",
    "items/item_17.json": "c29d20e6735a98b03c9b11e721760af94c0b0a7f9433afe5a3e583df8974230c",
    "policy.json": "176f864abcb9c54753c5811db89d399fd41aafc053a1a89975a5feca5027f203",
    "pool_state.json": "1475861ae996c1df18c40b1e0376e5a2b8690da362acdc10e38be3116a43ca47",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "summary.json": "230d2ef306d09f7d5e8b2b9c8a6bb3685342dcad38a72a512c0d88c033f3d669",
    "yoke_table.json": "f27ab85459e92fc342fb5d5e33e0ff36be519cac6bae0e70e16bb04040bcefb6",
}


EXPECTED_FIELD_HASHES = {
    "summary.json.ancillary_note": "6afa7cb3705737cb8e4c47a38402ef00c0dfda5b18c1d1f81ae50a73f37e5520",
    "summary.json.applied_events": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.json.current_day": "d29d53701d3c859e29e1b90028eec1ca8e2f29439198b6e036c60951fb458aa1",
    "summary.json.regions": "502f77d97f7a589e9564f802e6880ed9fe3833b34e06e24679d91ef42771165a",
    "yoke_table.json.yokes": "f8e20bff6594dc23fcd4406632a6ea2e360ccf8b16d1dbd72fe33fca32f05faa",
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


class TestSummarySemantics:
    """Independent checks derived from the published specification text."""

    def test_regions_keys_track_active_policy_labels(self) -> None:
        """Region totals include exactly the active region labels sorted."""
        policy = _load_json(DATA_DIR / "policy.json")
        active = sorted(str(x) for x in policy["active_regions"])
        summary = _load_json(AUDIT_DIR / "summary.json")
        assert isinstance(summary, dict)
        regions = summary["regions"]
        assert isinstance(regions, dict)
        assert sorted(regions.keys()) == active

    def test_yoke_rows_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """Yoke table stays lexicographically ordered by identifier."""
        ytab = outputs["yoke_table.json"]
        assert isinstance(ytab, dict)
        rows = ytab["yokes"]
        assert isinstance(rows, list)
        ids = [str(row["yoke_id"]) for row in rows]
        assert ids == sorted(ids)
