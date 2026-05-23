"""Behavioral tests for slo-burn-window-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SBW_DATA_DIR", "/app/sloburn"))
AUDIT_DIR = Path(os.environ.get("SBW_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["host_states.json", "window_burns.json", "fleet_summary.json"]


EXPECTED_INPUT_HASHES = {
    "anchors/east.json": "617bde82cf4814cbf4015f74c1d35cd8a3c245e4ba607645dced03803e7ea808",
    "anchors/west.json": "9dade45d819b92c0e7d8a2deb7ae8d9eed4eda57c004d9153071eefd4df19ab3",
    "ancillary/meta.json": "a07763b6f68c3b6811e555596464dfd9744d969e8fbf82ff9cb02a5fbdb38261",
    "ancillary/notes.json": "2821e697e49a09b4426dadfa7546e1931baec39642c43784925f031ed414fd02",
    "blackout.json": "2ee8e419e1f4f1f9bc48b14b8f4175fb75d05bb779ce9f8e5434a525012c7058",
    "domain_layout.json": "f5ac6a97de2838d24aaf041d6450a83de9b789c7787113c42b86a3c22989ef7f",
    "grid/dims.json": "6dfc05286939c4657697ed2d6a304c679787ebb1eca82e25fa02410d88069654",
    "hosts/h01.json": "a190e39eff002e099d33bd2263fff2395ceb325138fe2762117fa044e744c609",
    "hosts/h02.json": "b202af5bf37fcddd21f35fdf1185e070c9904c425f01f699af944b901dc07e59",
    "hosts/h03.json": "3781a91a9226e6a2ce0bb79dc124105285ca1236c739c3daa5de38f3f3abd0ab",
    "hosts/h04.json": "1d37d2b853f4ab04803d8ed7650c1624aa39c757fb88c44075f66e4ab70f728b",
    "hosts/h05.json": "14affc96edadf20b26a98721c88229fbcca442dea6b9a3a3e7459c0908d2e522",
    "hosts/h06.json": "a34b4c04fa1134de8de4f8f71510fc8043a7435c007ee436af15679075388d6b",
    "hosts/h07.json": "d29e3484f2f3cb8c99bcdf8bc11df91638b15408e7e03636de00d5a43d656b5b",
    "hosts/h08.json": "753777bf6d686f91b85f1e8a73e6a30e5b2dd20d6a3b2a76b662995de4b23075",
    "hosts/h09.json": "d2cad58017a219a5a3ce72baa4b189d736a79adc93ac62d8ddbd9e2515d681cd",
    "hosts/h10.json": "130a10d4ab6d7d3e4419c9d60f35db95a92e39e6a7c4c237ec7a805fe7c01dfe",
    "hosts/h11.json": "f9d753de2525855fc8a80277c1f2d31601a60456784b68658987544bbfc7a441",
    "hosts/h12.json": "fccba9eb0953e83a8dab9f6c337b99850f3d6b61466127040ce973e92cde374b",
    "incidents.json": "bbf487f70919238d11c86e628e292359251d3ec8eeac7b91489815fbb51d0dd6",
    "meta/seq.json": "d6368387f3124e30a94678e6175f39918e00a004039d76ed02a070a1433162d6",
    "policy.json": "97b5c90261edbc3a553ffbc9ca8c06cf48a274f6f0dd9e526955e86d8050e61f",
    "SPEC.md": "6157f2b87d4f5f5a004264469ea6a7b1118005975adb7d0f8a14dd3d5702d0b7",
    "view.json": "af5014ecc09004dcd9e2b0fb043fe76399e3918e3ab7371580bb060d474b8569",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "fleet_summary.json": "6922a250e80189d6bb1fa2911a0d7d1acd86c3813ea9973e0324c0503943a72e",
    "host_states.json": "138bcfcab8ff91620651b04c1923c0b4af648abf06ed054dba95dac4e5d99eef",
    "window_burns.json": "cdeffa1c213b0e92c6f9f5016bee5c2f9a748f482090790c0c2e497b28538732",
}


EXPECTED_FIELD_HASHES = {
    "fleet_summary.json.breach_total": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "fleet_summary.json.fleet_burn_ppm": "e3ed30f247130675fd7a683f09a08ff711a4048c00b2a9a542dbce66af359660",
    "fleet_summary.json.frozen_total": "19581e27de7ced00ff1ce50b2047e7a567c76b1cbaebabe5ef03f7c3017bb5b7",
    "host_states.json.hosts": "372fd20ef84df34b84d64b5a2355df64a1b9b18163e2d1b198f90aca1cca4932",
}


def _sha256_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize like the reference harness."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from ``path``."""
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load mandated audit JSON objects."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


class TestInputIntegrity:
    """Pinned fixture bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every input file under the lab matches its digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Hash-locked outputs."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file matches the canonical minified digest."""
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


class TestHostStatusEnums:
    """Enum coverage for per-host status values."""

    def test_active_host_present(self, outputs: dict[str, object]) -> None:
        """At least one host remains active when freeze tags align."""
        hosts = outputs["host_states.json"]["hosts"]
        assert any(row["status"] == "active" for row in hosts)

    def test_frozen_host_present(self, outputs: dict[str, object]) -> None:
        """At least one host is frozen on freeze-tag mismatch."""
        hosts = outputs["host_states.json"]["hosts"]
        assert any(row["status"] == "frozen" for row in hosts)

    def test_breach_host_present(self, outputs: dict[str, object]) -> None:
        """At least one host breaches the burn threshold."""
        hosts = outputs["host_states.json"]["hosts"]
        assert any(row["status"] == "breach" for row in hosts)

    def test_critical_host_breach_overrides_freeze(self, outputs: dict[str, object]) -> None:
        """Critical hosts breach even when freeze tags differ from the incident tag."""
        by_id = {row["host_id"]: row for row in outputs["host_states.json"]["hosts"]}
        assert by_id["h03"]["status"] == "breach"
        assert by_id["h09"]["status"] == "breach"


class TestFleetSummary:
    """Fleet-level counters."""

    def test_effective_warmup_matches_view_penalty(self, outputs: dict[str, object]) -> None:
        """Ops-tag mismatch adds one warmup slot beyond policy.warmup_slots."""
        summary = outputs["fleet_summary.json"]
        host_doc = outputs["host_states.json"]
        assert summary["effective_warmup"] == host_doc["effective_warmup"] == 3

    def test_blackout_zeroed_errors_positive(self, outputs: dict[str, object]) -> None:
        """Blackout windows zero at least one sample error in the bundled fleet."""
        assert outputs["fleet_summary.json"]["blackout_zeroed_errors"] >= 1
