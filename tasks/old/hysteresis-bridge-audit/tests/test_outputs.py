"""Behavioral tests for hysteresis-bridge-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("HBA_DATA_DIR", "/app/hba_lab"))
AUDIT_DIR = Path(os.environ.get("HBA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["crossing_log.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "f69ed990fbe0bc9c1f2943670da4e94a4901cf546cc933658026ea97add62102",
    "anchors/cap.json": "d7dad774334156457fbe4376212ce5e8107fa8f512f00433480497194d9ecc69",
    "anchors/window.json": "96266b35c242456e35682320f478793bcc3ce56c828dcd18e7deda5d224b2fb5",
    "ancillary/meta.json": "71038e14392e5c47f309224bea3b7107b5158a6823445f209cf9397322b44119",
    "ancillary/notes.json": "ae1388ff05bbfedbad9d29b8bb3dd5cd27b85f6948d7c19965f937efc900e5ad",
    "ancillary/scale.json": "a97f5c4fe8e93824da40d6292c7a8824b183e4fd27b2e203a0fcb1ead79ee96c",
    "domain_layout.json": "c2f4191e2aafb2b28ddd80f3bb3e6ec37e22875e02c5ec4e20bd1f61010a0fb9",
    "incident_log.json": "41a301c01effa6a7ef60b304391940bc344f43aa471f771bdf78370bb3f69cbd",
    "lanes/l01.json": "bee968ff733dd9738efc8b01bcd11101f676a6fce80d0f6e682405d6f5658ea2",
    "lanes/l02.json": "6f225eed19e35faed5b0411065601e8549befdb85179f772a42376c8b50f1be9",
    "lanes/l03.json": "45feda49944eda6311f9879a03f6f6cb2fec59eb4b7884b3252566415e6049dc",
    "lanes/l04.json": "8cd96b92f82b9a5d2c05883adeb879a44992274f3ab9fb42a4fa99abd50ddc3c",
    "lanes/l05.json": "90d91bfa5705f563e5df378c4f51f68d3246b042c68bd808f2638c5be9f7ab67",
    "lanes/l06.json": "8d13bffbbf337660d3f5c147e1a4fc8e89d2d2ab9eeb29079ed90b5f88994621",
    "policy.json": "bbc4fd0a6752cdf1e5a608ca45f00a45af8f10814501fd27961f393bc0bc8d8e",
    "pool_state.json": "d6c5eb17c3aaeeedc42e3b96e72e62d7b59c683a57ab816fb02fa2b3fad7567c",
    "ticks/tick_00.json": "920a02d0a815e6fbb76bd31ca1e1533dd592b50964cbfd8a34a97fe54a954067",
    "ticks/tick_01.json": "1eba08cee5bc502031b9c349b3de71c0911d55800f2c536081cc64e1779f0b6f",
    "ticks/tick_02.json": "417d8b4730c7e7800ce62078b7e034f2533afed6b0421667a0ed1713d1ac375b",
    "ticks/tick_03.json": "8083445eefd87e5cd51274e9bb17695673468a8e31792593cf74711c166e5510",
    "ticks/tick_04.json": "3c9600a44dd131c70dd8f9dbb2fa978296b6062a8b0e4d0ac31fa3dc87ff3d5f",
    "ticks/tick_05.json": "94c834d50d9be50eee67eabc00c3fc7f10ce57c06712a9dfc9612727f037be51",
    "ticks/tick_06.json": "60707ac2f3b1e3477980464301380eeaf49c51fd60c173cde81f028d5afbd3f9",
    "ticks/tick_07.json": "9404da6fe90411b950bab1ba52c67f0583a2bd3fa78fb4eea9734656f81ec4d1",
    "ticks/tick_08.json": "4917e724abfac42df22250491664809f2c986ff2b04595d35138fb8b01cb9a73",
    "ticks/tick_09.json": "2cdcaabc3e702b7e90e219242ac94a96ce44a95093c0e55ae6a2317882c8d446",
    "ticks/tick_10.json": "c8d506518869b972b99fbf8bd06709141039826fad0a5f951a5f665e3013db8c",
    "ticks/tick_11.json": "bf1301595adf319568bad778a95d9e2439195299e06fe32636929b2b5fb18063",
    "ticks/tick_12.json": "bece1f647b71ee73d43070f29c16ffe7f83e4962f23c479cb0cd11cfc137730e",
    "ticks/tick_13.json": "6ced581036da69207a70f9543e012ad99cfd1bb3d3e6be8bc4d1c688afb2ae7a",
    "ticks/tick_14.json": "69c70fe1ef560522382d9b1381d60a94534553829e314201838c54843c0021a3",
    "ticks/tick_15.json": "96274a00153b2806d4b66c47b7cf8e25cfa57cbb5ff1e1eb38420aad5373d5dd",
    "ticks/tick_16.json": "c1eeafabb63b0019da241888c28367a7e851cef96ad2fa3868da8d8881f878aa",
    "ticks/tick_17.json": "9b086d21677780ddf3d1d9968d922760235674aec9d0ec947c9a7f981356633f",
    "ticks/tick_18.json": "c905295d3283481082d972902cef32df7f432e9c89242ca85f29ca5b642ce30d",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "crossing_log.json": "cfc09ec4103fbe386ee7978be0f27c726d73cf9ee7a7229ef2b1b3450c9f937e",
    "summary.json": "b515bb04c210d88a237a2c69686ed805689e6be0a964e315fa0cd6b4e43c0dc3",
}


EXPECTED_FIELD_HASHES = {
    "crossing_log.json.crossings": "004f4e78cbc165857e61ee788665de6d1e469c798bfa1c9d0f4cd408bfc34423",
    "crossing_log.json.final_state": "29da692a7b3d2cf2e02e8d84555a7a82ce9fa5bef7f00080bd20c0c383377b0c",
    "summary.json.crossing_events": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
    "summary.json.debounce_required": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.json.end_day": "f5ca38f748a1d6eaf726b8a42fb575c3c71f1864a8143301782de13da2d9202b",
    "summary.json.incidents_applied": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.lanes": "658d8a03b1fd617925c97f49d1a60acfac21e4bdefc65892ede3596cbf402f77",
    "summary.json.start_day": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.ticks_evaluated": "b17ef6d19c7a5b1ee83b907c595526dcb1eb06db8227d650d5dda0a9f4ce8cd9",
    "summary.json.ticks_seen": "9400f1b21cb527d7fa3d3eabba93557a18ebe7a2ca4e471cfe5e4c5b4ca7f767",
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize using the verifier's canonical minified JSON."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from disk."""
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


class TestDatasetSemantics:
    """Spot-checks that bundled fixtures exercise blind resets and unknown lanes."""

    def test_day_blind_reset_visible_in_alpha_crossings(self, outputs: dict[str, object]) -> None:
        """Alpha flips high then low on later days after a blind gap breaks streak carry."""
        log = outputs["crossing_log.json"]
        assert isinstance(log, dict)
        xs = log["crossings"]
        assert isinstance(xs, list)
        alpha_days = [int(c["day"]) for c in xs if str(c["lane_id"]) == "alpha"]
        assert alpha_days == [3, 7]

    def test_unknown_lane_tick_does_not_raise_lane_count(self, outputs: dict[str, object]) -> None:
        """Lane list excludes orphan ids while ticks_seen counts every tick file."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        lanes = summary["lanes"]
        assert isinstance(lanes, list)
        assert "orphan" not in lanes

    def test_rejected_incident_not_counted_as_applied(self, outputs: dict[str, object]) -> None:
        """Only accepted incidents increment incidents_applied."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert int(summary["incidents_applied"]) == 1

    def test_crossing_log_sorted_by_day_lane(self, outputs: dict[str, object]) -> None:
        """Crossings appear sorted by day then lane id ASCII."""
        log = outputs["crossing_log.json"]
        assert isinstance(log, dict)
        xs = log["crossings"]
        assert isinstance(xs, list)
        keys = [(int(c["day"]), str(c["lane_id"])) for c in xs]
        assert keys == sorted(keys)
