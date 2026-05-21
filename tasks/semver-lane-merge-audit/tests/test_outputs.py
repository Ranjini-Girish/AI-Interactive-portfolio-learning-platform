
"""Behavioral tests for semver-lane-merge-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SLM_DATA_DIR", "/app/slm_lat"))
AUDIT_DIR = Path(os.environ.get("SLM_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["lane_merge.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "44e04dc0119374399e3d6d36e9a5320e4a9b9ecbc8ca5c846324d23d74f9b5d5",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "9ec9aab8a5650a08d7ecd65b642b3dcec6c1a3f964cee873b417f7df8c4abd79",
    "items/item_00.json": "52ab75b5dae7250bc82b7a5eadc3347d8d15ccb84e085d06602295aa2b938600",
    "items/item_01.json": "87d1a35244ffdca920e60b53bf90bb912a83b2304300119d86662714d91fc8ac",
    "items/item_02.json": "fd6a5ad0fd7e8b26ba638a406452c79309e8c567282af3eb12b5eaf30f6dc939",
    "items/item_03.json": "7bec74ae8cc3beea093e23993d6b7332d035d708d50db44730d9762d2cd8a924",
    "items/item_04.json": "dbe54ffee5bd50c781542d9b9294850a8b8d1826f39e4673bdfc90d22aa7ec37",
    "items/item_05.json": "ccafe9ccb8269418bcbcf0b1f5113f07e79e3659acf40082534be1b698380477",
    "items/item_06.json": "3a329dff22c1974cd6d64790a693902e77c176f1d6baffcb1c8e10d36a27055d",
    "items/item_07.json": "048a56f654f99d3e5e20380fbfd244a383e7460a3dad61d6c6dadfcdf753851f",
    "items/item_08.json": "b76dd0043e2c03cb9ef581e0a54f21e06fb9c24fb45ea5577b56f21160a778d0",
    "items/item_09.json": "fd60a97907fd61020ac1de3d0b7a3c1ad255f3f154e7cf1c14fd06ad52870800",
    "items/item_10.json": "306788ef593c24ce0a37a0d79a6775732b2e2839503c062f8ed9721c7e7d2b20",
    "items/item_11.json": "3fed81790e430376f1831a1da8edf91ea080d8c312f94aca80b4b78b8a561306",
    "items/item_12.json": "6bbf822195f2589d700d3896f015c387cf686ceede37d5125982913b5c77c04e",
    "items/item_13.json": "f86062bcd7c76541b0df3441973e127a848a182cb08d96b4203ef66b2338c020",
    "items/item_14.json": "dfdc430d309697228ffb02a2e6e0d31d7746803f7d1cd1cdf775a267d522cc44",
    "items/item_15.json": "aedb459fb82603c840d7946e7e26487a687732b7b0d8c71e4c473a1ace753db2",
    "items/item_16.json": "5839abb98a240119736ef12318c91bd73c3a7ece4b5930f2c25823e8be8e8669",
    "items/item_17.json": "c48bd6d9197bee8d5c042bc2f45cf03d80e3b4dda0ffe327546ca9b83ad243a8",
    "policy.json": "77035e6f61226925b4a7ffb3ff44385845236f07cb436bba425f103c224844fa",
    "pool_state.json": "7cab8f750f657f8da2e5379d4cb0882dc7b9451868236205d39110240a5bcb73"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "lane_merge.json": "f11b72b48bbd43f068af9111d29796bac505e466e05ffc054a281b2127cf4ee7",
    "summary.json": "eddb951b6c6ab261e478ea0e74f65d127ce85a3255a7733b66c5d9d86a4df611"
}


EXPECTED_FIELD_HASHES = {
    "lane_merge.json.lanes": "9f7d3024f8ff539e7276f6c38fb12ba3f6f2f287b14d540bcec54830c3f99e0b",
    "summary.json.current_day": "02d20bbd7e394ad5999a4cebabac9619732c343a4cac99470c03e23ba2bdc2bc",
    "summary.json.frozen_lanes": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.lanes_total": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce"
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
