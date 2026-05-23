# scaffold-status: oracle-pending
"""Verifier suite for the MHz guard coalesce audit task.

Hash locks pin the frozen fixture bytes and exact on-disk JSON bytes for each
audit artifact, while a small set of semantic checks guards incident ordering
and the staging merge that disappears if strip or gap tightening is skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SGA_DATA_DIR", "/app/sga_data"))
AUDIT_DIR = Path(os.environ.get("SGA_AUDIT_DIR", "/app/sga_audit"))

OUTPUT_FILES = (
    "segments.json",
    "incident_trail.json",
    "tier_rollup.json",
    "summary.json",
)

BINARY_PATH = Path("/app/sga_tool/sgaudit")


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "a90005f40b2b19e08d550a42a27897a789259bec9bf1c79bb43640155d1b6176",
    "anchors/cal_note.json": "7a5d60ed429094ba1b41f874b1e8ab1d36d9510cc0077d63531c587815741e35",
    "anchors/window.json": "51240a9d7bd5ad1536326bcf4434a84f1f629721d73662e8b1f27222b85d1473",
    "ancillary/extra.json": "395b1715329edb6a75e3ad0889409a36922a16c9100f2ee0eee6ab236042bb40",
    "ancillary/notes.json": "21d5184b60859984d170890c3618747ce5ff9b5e29a7ca2982d957697039e660",
    "ancillary/tags.json": "03bcd0c0d4f400afed627195fc9af85a7cc49dc0d6b15a954c7d2b372d119a2b",
    "bins/b01.json": "1101fb1e6a123556686aadf18eea68dc88e36c8d5a8c6f8c27037697ce3e88d5",
    "bins/b02.json": "1cc5592e9404c3d3299d5032a2fd13a270e419595cbad80504d8665789707710",
    "bins/b03.json": "f613b412d2331a8500a696310cab865daa69380ab979f441848b25975cdbfa88",
    "bins/b04.json": "5ea673a48beff37662e89b5e542290c128645b2a8fd473a37e28d362ee4b864e",
    "bins/b05.json": "f948628c9368e1dababa149156a2edc091fa2b8a2a34d1cb404cbc35cd6b4259",
    "bins/b06.json": "e95796d9ff8bdc3ba72d04661be5731649dccf97e85b80938a9e44ba4970eb59",
    "bins/b07.json": "2a349ad4a27a8091089baef271b0018d6ad3d5e3e2ed92ab4d16400de2d8dbe3",
    "bins/b08.json": "e6262d48335153be453017ad1d3e76632395c473773fc16d1cc8653b562efec5",
    "bins/b09.json": "55a46905563fb53b6dd61556021eee4fffbb388875346bd19fd64fc898165dce",
    "bins/b10.json": "9f5f5f4636e4b17c7ed5a72d684c5e8c51c29887dc1b01fe040521c945e1880e",
    "domain_layout.json": "efbc816df7631d27f2b690e21a5348f581718cc56a1e9d647b0b9480b6a01746",
    "incident_log.json": "e00b7f10ca9660b207046694a1e8bb925d5652346632f672ccd8530b7d76c2d8",
    "policy.json": "bc34ff444830f9882bd4e95a3f155b7ee980bc6850c54f0894dbfb56caad1523",
    "pool_state.json": "aadd89dd51545bdd36d958677c7960a4cd77a00fa0896292d0306a2ba178d528",
    "waves/w1.json": "1623f1b29d45c7eb60a2e0e62de25324c68559e157df824489316f72be062d27",
    "waves/w2.json": "8a6b2c6cfea2509de5671d14e3722bf80de60e4f759aed730b7041a5144ee2a5",
}


EXPECTED_RAW_OUTPUT_HASHES = {
    "incident_trail.json": "9adacfd1376f71248279b447f9076be7e7caaae5b3622efa25327d5429415a6f",
    "segments.json": "bab82c615bfd3c24f6d705042cb9650484a870628da28f131fa0176782712b18",
    "summary.json": "4a1eb02197604179f5111a3baeac29d63d390992b0bb1003da7e157d23b6f9e4",
    "tier_rollup.json": "f2a1974bb31c4f5b4f2402e45b83e81625e7d9b6f239571de8cd8b94ea53631d",
}


EXPECTED_FIELD_HASHES = {
    "incident_trail.applied": "d5be190f5679b17244a435cf9f240db25484e688ee1a16e96c395f47190df6c3",
    "segments.segments": "6b471d68daa3ac8d4f075c17bffe0e6cd414f51e3866173ca345be7666efb2fe",
    "tier_rollup.tiers": "2b4090acc9f60c6040ab05124637a0e7e0c23f1b0244be42dd1168e2d8db45dd",
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
    """Verify the mounted workspace matches the frozen reference bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the data directory must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Verify emitted JSON files exist and hash-lock to the on-disk byte contract."""

    def test_output_raw_byte_hashes(self) -> None:
        """Each audit file's raw bytes must match the pinned digest (canonical JSON + single newline)."""
        for name, expected in EXPECTED_RAW_OUTPUT_HASHES.items():
            path = AUDIT_DIR / name
            assert path.is_file(), f"missing emitted artifact: {name}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"raw output bytes mismatch for {name}"

    def test_nested_field_hashes(self, outputs: dict[str, object]) -> None:
        """Nested collections remain stable under canonical serialisation."""
        seg = outputs["segments.json"]
        assert isinstance(seg, dict)
        body = _canonical(seg["segments"])
        assert (
            _sha256_bytes(body.encode("utf-8")) == EXPECTED_FIELD_HASHES["segments.segments"]
        )

        tr = outputs["incident_trail.json"]
        assert isinstance(tr, dict)
        applied = _canonical(tr["applied"])
        assert (
            _sha256_bytes(applied.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_trail.applied"]
        )

        roll = outputs["tier_rollup.json"]
        assert isinstance(roll, dict)
        tiers = _canonical(roll["tiers"])
        assert (
            _sha256_bytes(tiers.encode("utf-8")) == EXPECTED_FIELD_HASHES["tier_rollup.tiers"]
        )


class TestIncidentReplay:
    """Incident ordering and ignore accounting."""

    def test_applied_incidents_sorted(self, outputs: dict[str, object]) -> None:
        """Applied incidents follow ascending day then event_id order."""
        applied = outputs["incident_trail.json"]["applied"]
        assert isinstance(applied, list)
        keys = [(int(e["day"]), str(e["event_id"])) for e in applied]
        assert keys == sorted(keys)

    def test_ignored_and_applied_counts(self, outputs: dict[str, object]) -> None:
        """Three incidents are ignored while three eligible incidents mutate state."""
        tr = outputs["incident_trail.json"]
        sm = outputs["summary.json"]
        assert isinstance(tr, dict) and isinstance(sm, dict)
        assert tr["ignored"] == 3
        assert sm["ignored_incidents"] == 3
        assert sm["applied_incidents"] == 3


class TestCoalescingSemantics:
    """Behavioural spot checks on merged spans."""

    def test_staging_bins_merge_after_gap_tighten(self, outputs: dict[str, object]) -> None:
        """Staging neighbours within the tightened gap merge into one span carrying both ids."""
        segments = outputs["segments.json"]["segments"]
        assert isinstance(segments, list)
        merged = next(
            s
            for s in segments
            if isinstance(s, dict) and s.get("tier") == "staging" and s.get("lo_mhz") == 200
        )
        assert merged["hi_mhz"] == 210
        assert merged["bin_ids"] == ["s1", "s2"]

    def test_production_bins_stay_split_after_middle_strip(self, outputs: dict[str, object]) -> None:
        """Stripping the middle production bin prevents the outer pair from coalescing."""
        segments = outputs["segments.json"]["segments"]
        assert isinstance(segments, list)
        lows = [s["lo_mhz"] for s in segments if s["tier"] == "production"]
        assert 100 in lows and 118 in lows and 130 in lows


class TestSummaryRollup:
    """Summary counters stay consistent with emitted segments."""

    def test_summary_counts_align_with_segments(self, outputs: dict[str, object]) -> None:
        """Segment totals in summary match the emitted segment list and bin membership."""
        segs = outputs["segments.json"]["segments"]
        sm = outputs["summary.json"]
        assert isinstance(segs, list) and isinstance(sm, dict)
        assert sm["segments"] == len(segs)
        bins = 0
        for seg in segs:
            bins += len(seg["bin_ids"])
        assert sm["total_active_bins"] == bins


class TestBinaryPresent:
    """Anti-cheat: the reference entrypoint exists in the agent image layout."""

    def test_release_binary_exists(self) -> None:
        """The compiled audit binary must be present for containerised runs."""
        assert BINARY_PATH.is_file(), (
            "sgaudit Go binary must exist at /app/sga_tool/sgaudit"
        )
