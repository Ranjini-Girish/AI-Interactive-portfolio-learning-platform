"""Behavioral tests for the labkit multi-plate assay audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("LKA_DATA_DIR", "/app/labkit"))
AUDIT_DIR = Path(os.environ.get("LKA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "well_results.json",
    "batch_assay_rollup.json",
    "curve_diagnostics.json",
    "lot_disposition.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "919f682115022ff16f9c79657242cdb39f1517db1cd373d03b0b0b7f21698d12",
    "assays.json": "8b96318f8f427c2d15337b149102be7138930fbdc947ee6b26fb4b58bde0eca9",
    "batches/index.json": "50451abb9217848d09069a4c5cfe598c64ce1e2221bef139b7c13d274bb2d20c",
    "incident_log.json": "899f2714e7bb0de5a483297a966f963eb29a8e6ecaced5700592babacdba567f",
    "lots/registry.json": "b1e40992dc76119370dc07df0fabe91c5db806b2892e505d2398cf53332d87fa",
    "meta/run_types.json": "263d20967f7a47fd749c6e1e850844025d7c4106b7d1496ba56fa053ffc694d7",
    "meta/study_phase.json": "cc349aa0881abcdbd7bd242cc44f3cdfbbebe8abca93bb64df8e4fecb7c5b161",
    "plates/p01.json": "9cc05c0f8e302016dcdeb09eae0c5ab2f6d5ec5f0e1a54859ebff48dd35ea2cd",
    "plates/p02.json": "d43b6b363991aa785d325b37e992da965dc5bc939caefb3274602ee6ae9d14e2",
    "plates/p03.json": "3f079ec070864c63ccc36766f9b1a7e3585c1adeaf1e69118db476efd1bcd0df",
    "plates/p04.json": "9793a6c19e4d9009bc4203f5f39320b49216a2709cd4b73e16b3061990d6c480",
    "plates/p05.json": "bc4792809311c00e99ca89786551204cb90dbc47d73afa79e485c87e36074289",
    "plates/p06.json": "afcb0e3fc0c5ac4a17fa8fcd98f812eb7f54369ab14edacfb7596a93fd10fdf1",
    "plates/p07.json": "ca63b1d0b074cb2074cf4a613ed0d417e750637477ec02f3e7e808ff42275930",
    "plates/p08.json": "41d0ee63b84074f2f12a5e88502d08407949b18e665574409c531bbdf80a53f0",
    "policy.json": "5928bf8643f03e7473b0b26a6da147c4c12effa4c2e5c5b737487f00bb4a5046",
    "pool_state.json": "c640908f806b7b9f70b6f1c32398a7027fbe16bb882cc4a6b293b73a83fccc89",
    "profiles/cal_offsets.json": "fdf9cfdc834ba5a661528275f5527971d15eec8711de574e601379bf08e88ab8",
    "profiles/instrument_map.json": "bd3163b1503dc192badd458e2980bc4f0b29f6bee0ccf1921d4b46b327660d42",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "batch_assay_rollup.json": "155cc05f1650aa315974b5fedc1d29c2f20674ffe910306d4f544fae62c98572",
    "curve_diagnostics.json": "29ecb0fcb3997922b657d9ae69a54edfe99302f0bd07c8cb20a429ea632d288e",
    "lot_disposition.json": "d7226f508392de0eb6797f6a5ff81e284470a615efa301fe7578a5f9e6308587",
    "summary.json": "640b589ef0790de5659fa012954397d3279c544843e4f916575b06f239166110",
    "well_results.json": "64e259ec29c43580b2c452a5a8909b2e6fa99915cb612abc1a4500b31b7fbd6c",
}


EXPECTED_FIELD_HASHES = {
    "batch_assay_rollup.entries": "3dbc60d113f6d6fc1ee712fb44214c904b683312b7ee699888f5ffc6df7a3838",
    "curve_diagnostics.plates": "8c97e39546cafa1c268b40a8469616540311002cc68dac2125255eac6997d307",
    "lot_disposition.lots": "bd25f6735621815d5a7a0a096dc02502eaf8169bd099bbc85d33e2e30da42fe4",
    "summary.current_day": "c2356069e9d1e79ca924378153cfbbfb4d4416b1f99d41a2940bfdb66c5319db",
    "summary.disposition_counts": "cee587a68b305e591d81e67e1439b23dc495a5f7394c289392603afc8b6469e6",
    "summary.ignored_incident_events": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.plates_loaded": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "summary.recall_lot_count": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "well_results.wells": "d6ecdbb13d5d2ba63db90839f716a42838628a50386b2bdaa7b39296305990f6",
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
    """Verify the mounted labkit workspace matches the frozen reference bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the labkit directory must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"hash mismatch for {rel}"


class TestOutputCanonicalHashes:
    """Byte-stable canonical JSON hashes for the five audit artifacts."""

    def test_well_results_canonical_hash(self, outputs: dict[str, object]) -> None:
        """well_results.json must match the canonical structural hash."""
        name = "well_results.json"
        digest = hashlib.sha256(_canonical(outputs[name]).encode("utf-8")).hexdigest()
        assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES[name]

    def test_batch_assay_rollup_canonical_hash(self, outputs: dict[str, object]) -> None:
        """batch_assay_rollup.json must match the canonical structural hash."""
        name = "batch_assay_rollup.json"
        digest = hashlib.sha256(_canonical(outputs[name]).encode("utf-8")).hexdigest()
        assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES[name]

    def test_curve_diagnostics_canonical_hash(self, outputs: dict[str, object]) -> None:
        """curve_diagnostics.json must match the canonical structural hash."""
        name = "curve_diagnostics.json"
        digest = hashlib.sha256(_canonical(outputs[name]).encode("utf-8")).hexdigest()
        assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES[name]

    def test_lot_disposition_canonical_hash(self, outputs: dict[str, object]) -> None:
        """lot_disposition.json must match the canonical structural hash."""
        name = "lot_disposition.json"
        digest = hashlib.sha256(_canonical(outputs[name]).encode("utf-8")).hexdigest()
        assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES[name]

    def test_summary_canonical_hash(self, outputs: dict[str, object]) -> None:
        """summary.json must match the canonical structural hash."""
        name = "summary.json"
        digest = hashlib.sha256(_canonical(outputs[name]).encode("utf-8")).hexdigest()
        assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES[name]


class TestFieldHashes:
    """Field-scoped hashes catch silent edits inside large arrays."""

    def test_well_list_field_hash(self, outputs: dict[str, object]) -> None:
        """The wells array must match its pinned canonical hash."""
        wells = outputs["well_results.json"]["wells"]
        digest = hashlib.sha256(_canonical(wells).encode("utf-8")).hexdigest()
        assert digest == EXPECTED_FIELD_HASHES["well_results.wells"]

    def test_batch_entries_field_hash(self, outputs: dict[str, object]) -> None:
        """The batch rollup entries must match their pinned canonical hash."""
        entries = outputs["batch_assay_rollup.json"]["entries"]
        digest = hashlib.sha256(_canonical(entries).encode("utf-8")).hexdigest()
        assert digest == EXPECTED_FIELD_HASHES["batch_assay_rollup.entries"]

    def test_curve_plates_field_hash(self, outputs: dict[str, object]) -> None:
        """The curve diagnostics plate rows must match their pinned canonical hash."""
        plates = outputs["curve_diagnostics.json"]["plates"]
        digest = hashlib.sha256(_canonical(plates).encode("utf-8")).hexdigest()
        assert digest == EXPECTED_FIELD_HASHES["curve_diagnostics.plates"]

    def test_lot_rows_field_hash(self, outputs: dict[str, object]) -> None:
        """The lot disposition rows must match their pinned canonical hash."""
        lots = outputs["lot_disposition.json"]["lots"]
        digest = hashlib.sha256(_canonical(lots).encode("utf-8")).hexdigest()
        assert digest == EXPECTED_FIELD_HASHES["lot_disposition.lots"]

    def test_summary_scalar_field_hashes(self, outputs: dict[str, object]) -> None:
        """Summary scalar fields must remain aligned with aggregate expectations."""
        summary = outputs["summary.json"]
        for field in (
            "current_day",
            "disposition_counts",
            "ignored_incident_events",
            "plates_loaded",
            "recall_lot_count",
        ):
            digest = hashlib.sha256(_canonical(summary[field]).encode("utf-8")).hexdigest()
            assert digest == EXPECTED_FIELD_HASHES[f"summary.{field}"]


class TestReportStructure:
    """Schema-level checks that stay aligned with `/app/labkit/SPEC.md`."""

    def test_well_keys_sorted_and_unique(self, outputs: dict[str, object]) -> None:
        """well_key values must be strictly ascending with no duplicates."""
        wells = outputs["well_results.json"]["wells"]
        keys = [w["well_key"] for w in wells]
        assert keys == sorted(keys)
        assert len(keys) == len(set(keys))

    def test_batch_entries_sorted(self, outputs: dict[str, object]) -> None:
        """Batch rollup entries follow (batch_id, assay_id) lexicographic order."""
        entries = outputs["batch_assay_rollup.json"]["entries"]
        tuples = [(e["batch_id"], e["assay_id"]) for e in entries]
        assert tuples == sorted(tuples)

    def test_curve_rows_sorted(self, outputs: dict[str, object]) -> None:
        """Curve diagnostics follow (plate_id, assay_id) lexicographic order."""
        plates = outputs["curve_diagnostics.json"]["plates"]
        tuples = [(p["plate_id"], p["assay_id"]) for p in plates]
        assert tuples == sorted(tuples)

    def test_summary_keys_complete(self, outputs: dict[str, object]) -> None:
        """summary.json exposes only the documented aggregate keys."""
        summary = outputs["summary.json"]
        assert set(summary.keys()) == {
            "current_day",
            "disposition_counts",
            "ignored_incident_events",
            "plates_loaded",
            "recall_lot_count",
        }


class TestSemanticClassifications:
    """Positive coverage for representative dispositions named in the spec."""

    def test_frozen_recall_well_on_bad_lot(self, outputs: dict[str, object]) -> None:
        """A recalled lot forces frozen_recall with the mandated detail prefix."""
        wells = {w["well_key"]: w for w in outputs["well_results.json"]["wells"]}
        row = wells["P06:B01"]
        assert row["disposition"] == "frozen_recall"
        assert row["detail"] == "recall:LOT_BAD"

    def test_drift_alert_wells_on_batch_b3(self, outputs: dict[str, object]) -> None:
        """Batch B3 on the current day must surface drift_alert for qualifying wells."""
        wells = {w["well_key"]: w for w in outputs["well_results.json"]["wells"]}
        assert wells["P05:B01"]["disposition"] == "drift_alert"
        assert wells["P05:B02"]["disposition"] == "drift_alert"

    def test_blank_degraded_on_insufficient_blanks(self, outputs: dict[str, object]) -> None:
        """Plate P03 triggers blank_fallback for every sample on that plate."""
        wells = {w["well_key"]: w for w in outputs["well_results.json"]["wells"]}
        assert wells["P03:B01"]["disposition"] == "blank_degraded"
        assert wells["P03:B02"]["disposition"] == "blank_degraded"

    def test_curve_unusable_on_single_std(self, outputs: dict[str, object]) -> None:
        """Plate P04 cannot fit a line through a single standard point."""
        wells = {w["well_key"]: w for w in outputs["well_results.json"]["wells"]}
        assert wells["P04:D01"]["disposition"] == "curve_unusable"

    def test_batch_b2_roll_up_reports_no_history(self, outputs: dict[str, object]) -> None:
        """Batch B2 has no historic medians yet but still reports the current median."""
        entries = {e["batch_id"]: e for e in outputs["batch_assay_rollup.json"]["entries"]}
        row = entries["B2"]
        assert row["drift_status"] == "no_history"
        assert row["historic_median_net"] is None
        assert row["sample_median_net"] == pytest.approx(2.9448)

    def test_batch_b4_roll_up_insufficient_samples(self, outputs: dict[str, object]) -> None:
        """Batch B4 exists in the index but has no matching wells."""
        entries = {e["batch_id"]: e for e in outputs["batch_assay_rollup.json"]["entries"]}
        row = entries["B4"]
        assert row["sample_count_used"] == 0
        assert row["sample_median_net"] is None
        assert row["drift_status"] == "no_history"

    def test_lot_bad_marked_recalled(self, outputs: dict[str, object]) -> None:
        """LOT_BAD must be flagged as recalled with a positive affected count."""
        lots = {lot["lot_id"]: lot for lot in outputs["lot_disposition.json"]["lots"]}
        assert lots["LOT_BAD"]["recalled"] is True
        assert lots["LOT_BAD"]["affected_wells"] >= 1

    def test_disposition_counts_sum_to_well_total(self, outputs: dict[str, object]) -> None:
        """Summary disposition histogram must cover every emitted well row."""
        wells = outputs["well_results.json"]["wells"]
        summary = outputs["summary.json"]
        total = sum(summary["disposition_counts"].values())
        assert total == len(wells)


class TestIndependentBlankMedian:
    """Small closed-form checks that do not depend on the full reference pipeline."""

    def test_p01_blank_median_matches_policy_math(self) -> None:
        """Plate P01 blanks average to 0.03 so sample nets are raw minus 0.03."""
        plate = _load_json(DATA_DIR / "plates" / "p01.json")
        blanks = [w["raw_value"] for w in plate["wells"] if w["role"] == "blank"]
        median = sum(blanks) / len(blanks)
        assert median == pytest.approx(0.03)
        samples = [w for w in plate["wells"] if w["role"] == "sample"]
        for s in samples:
            assert s["raw_value"] - median == pytest.approx(s["raw_value"] - 0.03)
