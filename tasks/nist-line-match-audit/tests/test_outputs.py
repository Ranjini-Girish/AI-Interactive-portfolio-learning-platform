"""Behavioral tests for the optical line matching audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("NLMA_DATA_DIR", "/app/nist_lines"))
AUDIT_DIR = Path(os.environ.get("NLMA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "run_matches.json",
    "line_utilization.json",
    "instrument_bias_state.json",
    "suppressed_catalog.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "8b30b7b58fa62c9c36611ea8df21e379b6a5168262e7a932c2f4a7dafa8a1b04",
    "catalog/ca.json": "6fecffb39a6d3b60a0024ff6d16fade1d09b29535b61b2c5e073d425da17f88c",
    "catalog/fe.json": "04974d01ca41826546bcbc568acb7ea28d0774e5f3983f998eaa3c5d7a09aa36",
    "catalog/h.json": "410e5b30a42409fe7a276f5fe39ee7e3065f29610efb79259bfe51cf5e274ff5",
    "catalog/mg.json": "fcef68c8371505dffc788d9eb53f2882dd45897f600dd00d83b99fd27f2dd5c6",
    "catalog/na.json": "9c7f291cb82b0ad1760eb9a4ebe300a8a9ec31024910c74730ae84325d2d3ab6",
    "catalog/si.json": "bff5cd5219a1cef1ed41eb9734373f29b93d31fa02abc005a7ff08aee8fc3bc4",
    "incident_log.json": "c36052230dcfa1b63797ec1d699ef3c2f83590861da3c441e67a173d4dd2bff2",
    "instruments.json": "f40277abe93df1ee5479b720c286826a572971b34fe678ed1fdfe9c79c1bf080",
    "observations/r01.json": "12bee8178c5c9b7b6b02b5351e00da9b5357833fde5f5880630f1652448daf83",
    "observations/r02.json": "b98aade11832feb7931832e8d68c5c1614aa1619e087478b79bd3d936d9cfe6c",
    "observations/r03.json": "9840cc13dac8f87050f8673a57ee3a09cc061d3cf5172e3f059f405008509d29",
    "observations/r04.json": "40419befacd5a95e08d1a8eed8343d28e23be81a7d898dcc1eada62516d2482f",
    "observations/r05.json": "00c807387e3bc82fdd200b18b4767470d1b286e0c0b3a8adbdfe719530511741",
    "observations/r06.json": "a4c90a199c1deef6a67c432799b47f0ecfb42e7d9b48da6f6a685a99d3adc872",
    "observations/r07.json": "6583c9809445b6fb0bcf297f24bbcb39b8243b4714294a0a4e6276dd29bcdcd7",
    "observations/r08.json": "5220ce9776da7729d9cdbd3a763877738c8fff6444367f5bfc37b85e3d8d9393",
    "pool_state.json": "c9042a03d868ea449097d3477e531943ad57d0373d4bee2115da1892d008980d",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "instrument_bias_state.json": "99e8b946e892fad2eeb1519008ea7421cf13a602f9a5201a4247a32408a481b2",
    "line_utilization.json": "bed028184f44c6a3d2544a0e576e316987892df3190c6f8c0e0119c042d84cba",
    "run_matches.json": "0771a1a655d15d2930093d8a139ffef2f367025e3d91a34c9b0daf61083cb5c8",
    "summary.json": "71393f0fefbdba636005fe00ede11ff179a5af6a34b4840f197eaf651445b6c1",
    "suppressed_catalog.json": "933d767285ccc20914b1d409f4e8d7072e012cf2d4eb89ff51ca93712ca4c232",
}


EXPECTED_FIELD_HASHES = {
    "instrument_bias_state.instruments": "092e587461a8235492b430e211184ab58fc364311faa6418f3313269feb0813f",
    "line_utilization.lines": "96fe007335110ca7d96638818ca49b5bf78b81e4500ca0d2742fe25afd6cfae9",
    "run_matches.runs": "a05d7dda65c4b140bb09f0c6fc15f7813341c166a4493047272f8ab0cd897ff5",
    "summary.catalog_lines_loaded": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
    "summary.ignored_incidents": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.max_run_day": "4a44dc15364204a80fe80e9039455cc1608281820fe2b24f1e5233ade6af1dd5",
    "summary.peaks_blended_conflict": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.peaks_matched": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.peaks_total": "19581e27de7ced00ff1ce50b2047e7a567c76b1cbaebabe5ef03f7c3017bb5b7",
    "summary.peaks_unmatched": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.peaks_weak_suppressed": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.runs_processed": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "suppressed_catalog.entries": "e5da298d961a6324ceae8c2797e9c699829669ecf4af203f18775d7e26e0ab1c",
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
    """Verify emitted JSON files exist and hash-lock to the canonical contract."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        runs = outputs["run_matches.json"]["runs"]
        assert (
            _sha256_bytes(_canonical(runs).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["run_matches.runs"]
        )
        lines = outputs["line_utilization.json"]["lines"]
        assert (
            _sha256_bytes(_canonical(lines).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["line_utilization.lines"]
        )
        inst = outputs["instrument_bias_state.json"]["instruments"]
        assert (
            _sha256_bytes(_canonical(inst).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["instrument_bias_state.instruments"]
        )
        ent = outputs["suppressed_catalog.json"]["entries"]
        assert (
            _sha256_bytes(_canonical(ent).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["suppressed_catalog.entries"]
        )
        summary = outputs["summary.json"]
        for key in (
            "catalog_lines_loaded",
            "ignored_incidents",
            "max_run_day",
            "peaks_blended_conflict",
            "peaks_matched",
            "peaks_total",
            "peaks_unmatched",
            "peaks_weak_suppressed",
            "runs_processed",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(summary[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestStatusCoverage:
    """Exercise every documented peak status on concrete runs."""

    def test_blended_conflict_on_r03(self, outputs: dict[str, object]) -> None:
        """Run r03 must classify its sole peak as blended_conflict."""
        runs = {r["run_id"]: r for r in outputs["run_matches.json"]["runs"]}
        peak = runs["r03"]["peaks"][0]
        assert peak["status"] == "blended_conflict"

    def test_weak_suppressed_on_r02(self, outputs: dict[str, object]) -> None:
        """Run r02 must classify its sole peak as weak_suppressed."""
        runs = {r["run_id"]: r for r in outputs["run_matches.json"]["runs"]}
        peak = runs["r02"]["peaks"][0]
        assert peak["status"] == "weak_suppressed"

    def test_unmatched_on_r04_and_r06(self, outputs: dict[str, object]) -> None:
        """Runs r04 and r06 must each emit unmatched for their peaks."""
        runs = {r["run_id"]: r for r in outputs["run_matches.json"]["runs"]}
        assert runs["r04"]["peaks"][0]["status"] == "unmatched"
        assert runs["r06"]["peaks"][0]["status"] == "unmatched"

    def test_second_peak_unmatched_after_claim_on_r07(self, outputs: dict[str, object]) -> None:
        """Run r07 must match the first duplicate peak and leave the second unmatched."""
        runs = {r["run_id"]: r for r in outputs["run_matches.json"]["runs"]}
        peaks = {p["peak_index"]: p for p in runs["r07"]["peaks"]}
        assert peaks[0]["status"] == "matched"
        assert peaks[1]["status"] == "unmatched"

    def test_matched_hydrogen_r01(self, outputs: dict[str, object]) -> None:
        """Run r01 must match the hydrogen alpha line with zero delta."""
        runs = {r["run_id"]: r for r in outputs["run_matches.json"]["runs"]}
        peak = runs["r01"]["peaks"][0]
        assert peak["status"] == "matched"
        assert peak["line_id"] == "H_ALPHA"
        assert peak["delta_nm"] == 0

    def test_matched_bias_stack_r05(self, outputs: dict[str, object]) -> None:
        """Run r05 must reflect stacked instrument bias when matching hydrogen."""
        runs = {r["run_id"]: r for r in outputs["run_matches.json"]["runs"]}
        peak = runs["r05"]["peaks"][0]
        assert peak["status"] == "matched"
        assert peak["line_id"] == "H_ALPHA"
        assert peak["delta_nm"] == -1

    def test_matched_calcium_r08(self, outputs: dict[str, object]) -> None:
        """Run r08 must match calcium after the scheduled bias shift applies."""
        runs = {r["run_id"]: r for r in outputs["run_matches.json"]["runs"]}
        peak = runs["r08"]["peaks"][0]
        assert peak["status"] == "matched"
        assert peak["line_id"] == "CA_422"


class TestSummaryRollups:
    """Cross-check headline counters against the emitted run table."""

    def test_summary_counts_consistent(self, outputs: dict[str, object]) -> None:
        """Summary counters must equal counts derived from run_matches."""
        summary = outputs["summary.json"]
        runs = outputs["run_matches.json"]["runs"]
        peaks = [p for r in runs for p in r["peaks"]]
        assert summary["peaks_total"] == len(peaks)
        assert summary["peaks_matched"] == sum(1 for p in peaks if p["status"] == "matched")
        assert summary["peaks_unmatched"] == sum(1 for p in peaks if p["status"] == "unmatched")
        assert summary["peaks_weak_suppressed"] == sum(
            1 for p in peaks if p["status"] == "weak_suppressed"
        )
        assert summary["peaks_blended_conflict"] == sum(
            1 for p in peaks if p["status"] == "blended_conflict"
        )
        assert summary["runs_processed"] == len(runs)


class TestSuppressionAndBias:
    """Spot-check incident-driven suppression and bias totals."""

    def test_hydrogen_suppression_active_on_last_day(self, outputs: dict[str, object]) -> None:
        """The suppressed hydrogen entry must remain active on the latest run day."""
        entries = {e["line_id"]: e for e in outputs["suppressed_catalog.json"]["entries"]}
        assert entries["H_ALPHA"]["active_on_last_day"] is True

    def test_instrument_bias_totals(self, outputs: dict[str, object]) -> None:
        """Incident delta totals must reflect only accepted shifts that ever apply."""
        inst = {i["instrument_id"]: i for i in outputs["instrument_bias_state.json"]["instruments"]}
        assert inst["instA"]["incident_delta_total_nm"] == 1
        assert inst["instB"]["incident_delta_total_nm"] == 2
        assert inst["instA"]["final_bias_nm"] == 1
        assert inst["instB"]["final_bias_nm"] == 1
