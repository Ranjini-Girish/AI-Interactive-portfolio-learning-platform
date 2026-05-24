"""Verifier suite for ridge-guard-merge-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RGMA_DATA_DIR", "/app/rgma_lab"))
AUDIT_DIR = Path(os.environ.get("RGMA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["ridge_report.json", "summary.json"]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "a46d3cb69d208bbed14e4a018f4c38fc805295e631977d8c3039760316735bab",
    "anchors/day_floor.json": "013442b75a3a3ddd1b1fc1d514ed3a812739b460a0334ed8aafa955a0cdada9f",
    "anchors/window.json": "e0e4369b966b519d90ba68ff507afd0cf2cd7a64bf0c27d3d9675f34be8390e7",
    "ancillary/meta.json": "f19870054ddf85adda603814338b79aa34283782b7a968bce2d4c9438d3495d8",
    "ancillary/notes.json": "754c4df8f98fd2672eb62a12fb77b047ad70c49b9637aadeedfc1e6e05e6c278",
    "domain_layout.json": "e04b2738c38a8c805f8fccd31b38de7cd4641cc8868230f6675a5af6eab779c9",
    "hosts/h00.json": "2d521d68d19f78c9d50538cdba02a278559691197f898de6a5db73e00692cf25",
    "hosts/h01.json": "cb2bccf2fb52be50cb69426acba6453441994246f2deb55746cfb66b82cd6925",
    "hosts/h02.json": "7674cef1e21e0a7abb955e201ff367c4796ae3bc9eac2de5f0078548fadf70e8",
    "hosts/h03.json": "036eba712e0d8aaefa5a56f60386b2478d94fc7806e93c08bfc084b1d90ec07a",
    "hosts/h04.json": "3302f2cdbaf44ec7b31e994b374c242d1a97bd765b2e12b2417d0a4710dff2bc",
    "hosts/h05.json": "f4fc0256fa7b8ec179d8cc5c478b01ba04d29b5815be5bfe4df387bf668805c6",
    "hosts/h06.json": "d4becaa8b8a3d8dc6647c72a24a77705bcc0f44f6122982571196d7e30fddf63",
    "hosts/h07.json": "6d33f002c7f360b9f21ee3f6bad4ef1cdde249d6a88d95c4fb585e54c8c68bad",
    "hosts/h08.json": "d1d92ef761449313b2620a2cae36cd24a047b855041e7bac65a0bab90f71e38e",
    "hosts/h09.json": "e34fdfd47a39b669d152a6c8d21f02ac72c787044fa69795bbccb6ea2b6a0c4b",
    "hosts/h10.json": "f6428f792c13e8da4e5e8387a5840d7da45bf8f2bff750282f67a542416a528c",
    "hosts/h11.json": "e8dd8d8a12cb312e1e946636e7c323e5aa78096d431b4439372eb1b643e4fb0c",
    "incident_log.json": "d95bc072716230e458a11f371f07d0ed179e1fedfe163ee31a38846811854ecc",
    "policy.json": "6a32eb3dfc316712fe7d719fa2d3bfd9d7949b3333ab6cc66cfd2cb1b1e58c13",
    "pool_state.json": "f15f7075b8f3c07263032cdd054017fb2032bf6a496f2edad4d33b5623f59c9b",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "ridge_report.json": "9167e717b9cfe782cd131aa36258b297b6a7bab0eaf84d9786c8821e75927d05",
    "summary.json": "ea63cb5bba6ebdf63a853d434d70801cedb0e5efef3c750bcbeaba2c21a9a30e",
}

EXPECTED_FIELD_HASHES = {
    "ridge_report.json.anchor_factor": "00fef940a6aaf1e03dc157bcb46b818823ad5b5928a9011d7006809f08931eb4",
    "ridge_report.json.entries": "6f4ddd774cc97c464c82ec7a7c1af807185be280478f1e881eb491f8e0db4c77",
    "ridge_report.json.schema_version": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.anchor_overlap_days": "e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683",
    "summary.json.entries_total": "6b51d431df5d7f141cbececcf79edf3dd861c3b4069f0b11661a3eefacbba918",
    "summary.json.frozen_total": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.lambda_cap_micro": "5826ecc4d11e82b52e711bc41978052483102366d2b36e1a61831880d8fe2c00",
    "summary.json.merged_groups": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.json.schema_version": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
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


@pytest.fixture(scope="session")
def entries_by_host(outputs: dict[str, object]) -> dict[str, dict[str, object]]:
    """Index ridge report entries by host id."""
    report = outputs["ridge_report.json"]
    assert isinstance(report, dict)
    raw_entries = report["entries"]
    assert isinstance(raw_entries, list)
    out: dict[str, dict[str, object]] = {}
    for ent in raw_entries:
        assert isinstance(ent, dict)
        hid = str(ent["host_id"])
        out[hid] = ent
    return out


class TestInputIntegrity:
    """Pinned fixture bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every input file under the domain directory matches its digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"

    def test_witness_pool_state_unchanged(self) -> None:
        """pool_state.json bytes match the pinned witness digest."""
        path = DATA_DIR / "pool_state.json"
        digest = _sha256_bytes(path.read_bytes())
        assert digest == EXPECTED_INPUT_HASHES["pool_state.json"]

    def test_witness_domain_layout_unchanged(self) -> None:
        """domain_layout.json bytes match the pinned witness digest."""
        path = DATA_DIR / "domain_layout.json"
        digest = _sha256_bytes(path.read_bytes())
        assert digest == EXPECTED_INPUT_HASHES["domain_layout.json"]


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


class TestBiasClasses:
    """Enum coverage for bias_class."""

    def test_dataset_has_high_bias_class(self, entries_by_host: dict[str, dict[str, object]]) -> None:
        """At least one host is classified as high bias under the bundled policy."""
        assert entries_by_host["h01"]["bias_class"] == "high"

    def test_dataset_has_low_bias_class(self, entries_by_host: dict[str, dict[str, object]]) -> None:
        """At least one host is classified as low bias under the bundled policy."""
        assert entries_by_host["h03"]["bias_class"] == "low"

    def test_dataset_has_mid_bias_class(self, entries_by_host: dict[str, dict[str, object]]) -> None:
        """At least one host is classified as mid bias under the bundled policy."""
        assert entries_by_host["h00"]["bias_class"] == "mid"

    def test_dataset_has_frozen_bias_class(self, entries_by_host: dict[str, dict[str, object]]) -> None:
        """Frozen hosts surface as frozen with null microlambda."""
        ent = entries_by_host["h02"]
        assert ent["bias_class"] == "frozen"
        assert ent["microlambda"] is None


class TestSummarySemantics:
    """Lightweight structural checks aligned with the bundled fixture."""

    def test_summary_anchor_overlap_matches_report_factor(self, outputs: dict[str, object]) -> None:
        """Overlap days align with the bundled anchor window and policy window."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary["anchor_overlap_days"] == 6
        report = outputs["ridge_report.json"]
        assert isinstance(report, dict)
        assert report["anchor_factor"] == 1.05

    def test_alias_merge_lifted_cap_on_gold_pair(self, entries_by_host: dict[str, dict[str, object]]) -> None:
        """Merged gold hosts share the capped microlambda after alias merge."""
        assert entries_by_host["h04"]["microlambda"] == 480000
        assert entries_by_host["h05"]["microlambda"] == 480000

    def test_alias_merge_spreads_max_for_silver_pair(self, entries_by_host: dict[str, dict[str, object]]) -> None:
        """Merged silver hosts share the max microlambda before cap interaction."""
        assert entries_by_host["h01"]["microlambda"] == entries_by_host["h03"]["microlambda"]
