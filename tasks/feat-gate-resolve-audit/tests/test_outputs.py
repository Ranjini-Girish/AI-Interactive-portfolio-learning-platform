# scaffold-status: oracle-pending
"""Behavioral tests for feat-gate-resolve-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("FGR_DATA_DIR", "/app/featgate"))
AUDIT_DIR = Path(os.environ.get("FGR_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["package_states.json", "conflict_report.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "anchors/leaf.json": "5120ff645bb3bd88ac3e25bed20448c2a09ec8f6e13f41cb5874707ad7b9c238",
    "anchors/root.json": "97bed92c20c5820630a7fe5674e0d32a18f53067a7e5a21a12ca0e5ff53ae567",
    "ancillary/meta.json": "71e3d0fca8c894d1420ea2a559a008a08b2b831f96a595c51bb7c67d8dce2a14",
    "ancillary/notes.json": "2821e697e49a09b4426dadfa7546e1931baec39642c43784925f031ed414fd02",
    "domain_layout.json": "cf7fac7ff9f88d00ba149e306ce093de66d6db17798be4a261f1e12d0e6c63cd",
    "grid/dims.json": "570390b875276e013dd2350b2669bd1eab9b87b48ac27e343cd4900a510fc874",
    "manifest.json": "d2ebcb5d8075d013f8dca94a504cdd8b6043425741ddba1e6320f7afde9a31d1",
    "meta/seq.json": "5267f954e82e9ded0399236bc34803c1c4ecf4dd67594dca6fb786a607d6890b",
    "overrides.json": "21d5f69922a3525c5e738b96cb6ddd1c021c44548ecd7376432f6e4636e63b58",
    "packages/app.json": "eb1e2dcea09d6adb476a28c6a81b7a487b0cfdc4dbb883f407c2c36fd3ccb22d",
    "packages/cache.json": "cd53c3a7e6b11122bd54fa017b198e04c89f8913c7f0dff3d0dc32949fb0d0f0",
    "packages/ghost.json": "0e23203273a8b6c05993492d12b643cb7137759708bb81840a2b2b4e5dc00b32",
    "packages/legacy.json": "036dbf7c04c1e26b781618cca0c75282d84a52a391a85aa4d02ff0d53bd2f258",
    "packages/net.json": "e1ce9a68d5a94cf35c00df51dfba69195b0802b6e18c65ccf2acf8eb7e851b93",
    "packages/util.json": "40eeb571a13fbb9eeaf5ba2e9e99d2cd89c5edffa075fc041c0fa0cd804238fe",
    "policy.json": "c29b3dd8228cac4934e47bdf4d99aeec8149f256d8e62ac35b32b99c55c6ed08",
    "samples/probe_00.json": "ac41c12a74a119841047b472ae11b14b9dff213d7f3dd17da5f25892967546d8",
    "samples/probe_01.json": "fa706b7d0f1ab8c2198b29a0a95e2fa028498ece4f998ccc2ed4b9061518a318",
    "samples/probe_02.json": "d5d8a59df93f4803e5de8891ed3fe1f85715fa037f7bcee4c2368892497f84af",
    "samples/probe_03.json": "6cea1e62cd557193fc3f74aec45fbbb809008a6b205688faa83cd8f9fea457d0",
    "samples/probe_04.json": "a9d59428c71c5f4587f68e1a4b9839ab3e143a5f40cd73d928abeeb7d1bb5fe9",
    "samples/probe_05.json": "6cd3a59d0f18425a0c49ff0c6ea240e81e13730c2741613e55a7d2cedc12665f",
    "samples/probe_06.json": "559ca2de07d9542ac167747cbf6a9ab56fe1fde235e961b0064e978a61596d9d",
    "samples/probe_07.json": "1a43266b344d5b312d990d9c3758cb1e8945f3d6b7244ecbd8d8912e58c0a532",
    "SPEC.md": "9365cdb2024d4a2f99a9695f1a8ec99a14138461ce4f7e0e7f0e0a1d95af151d",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "conflict_report.json": "2fe36c896c658f8979a9d388b92ea66a93cfad7374c5001f7dc48339ffa8a784",
    "package_states.json": "2e552e239498f26c370c66ac1e167656dbef9542e1b1654c284f024d17e61e8e",
    "summary.json": "59f636f59f50258615e406648f9cba0cd5311ea54bbc6b2049924f834e2fc5f2",
}


EXPECTED_FIELD_HASHES = {
    "package_states.json.packages": "96d9e7254f2304fc6173718f2a3463a2952bd72d7f985e1c4842724bba8d173d",
    "summary.json.conflict_drop_total": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.forced_off_total": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
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


class TestDropReasonEnums:
    """Enum coverage for conflict_report reasons."""

    def test_conflict_drop_present(self, outputs: dict[str, object]) -> None:
        """Conflict demotion emits at least one conflict row."""
        reasons = {row["reason"] for row in outputs["conflict_report.json"]["drops"]}
        assert "conflict" in reasons

    def test_forced_off_drop_present(self, outputs: dict[str, object]) -> None:
        """Patch force-off emits at least one forced_off row."""
        reasons = {row["reason"] for row in outputs["conflict_report.json"]["drops"]}
        assert "forced_off" in reasons

    def test_optional_blocked_drop_present(self, outputs: dict[str, object]) -> None:
        """Optional dependency epoch failure emits optional_blocked."""
        reasons = {row["reason"] for row in outputs["conflict_report.json"]["drops"]}
        assert "optional_blocked" in reasons


class TestPackageStates:
    """Resolved package rows."""

    def test_active_package_present(self, outputs: dict[str, object]) -> None:
        """At least one reached package remains active with enabled features."""
        rows = outputs["package_states.json"]["packages"]
        assert any(row["status"] == "active" for row in rows)

    def test_net_plain_wins_conflict(self, outputs: dict[str, object]) -> None:
        """After conflict demotion the net package keeps net-plain enabled."""
        by_name = {row["name"]: row for row in outputs["package_states.json"]["packages"]}
        assert "net-plain" in by_name["net"]["enabled_features"]
        assert "net-tls" not in by_name["net"]["enabled_features"]
