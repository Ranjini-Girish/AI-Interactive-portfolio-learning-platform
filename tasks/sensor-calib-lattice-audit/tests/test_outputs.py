"""Behavioral tests for the sensor calibration lattice audit task."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SCLA_DATA_DIR", "/app/sensor_lattice"))
AUDIT_DIR = Path(os.environ.get("SCLA_AUDIT_DIR", "/app/audit"))
SRC_DIR = Path(os.environ.get("SCLA_SRC_DIR", "/app/src"))
BIN_DIR = Path(os.environ.get("SCLA_BIN_DIR", "/app/bin"))

OUTPUT_FILES = (
    "calibration_plan.json",
    "lab_ledger.json",
    "lineage_risk.json",
    "recall_windows.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "eb518a1286621a8125202a69a76ce24f3cca5f9b3769d36c9baa6b2d08ad99fa",
    "batches/batch-a1.json": "3a4bc2eee81965cd863460bcb67e3d3a92b772aa9af6dff96281c4d71d484a6b",
    "batches/batch-a2.json": "1165a99b6c688a7aff7e21d18e633c4df14a960893577a085240d43089c5ec32",
    "batches/batch-b1.json": "4eaf4a0469db6d880be7454e58356a23e74a935ae97223537e4b76621c0b2208",
    "batches/batch-b2.json": "81343c40b5ab3c83d875b48e860e1c63e291b3f26971b40808950a6867980ced",
    "batches/batch-g1.json": "cadaa23106a1b07a7115a3fa03c4fcf68bfc5532ef77e90e2b8f1a3995592380",
    "batches/batch-g2.json": "9c66aa80df7088a6fad9afcdd2b1d8f00223f628975872619bdf82f59a19d903",
    "incident_log.json": "3007f63a52090c08b91be60375ff996a1a7a310be6a71a00c7c357d085920dbb",
    "labs/lab-alpha.json": "61511ff4e1b890deb7285b9b27f79fd470dd2791034941cc5573e417754b7a88",
    "labs/lab-beta.json": "5461b039dd4569a648dc248b7b0ad2425d7604695ed27826eab86eb45871c889",
    "labs/lab-gamma.json": "42d7408340cb4c76344bcf59d65c74d87c75e7923868a3d7b98aecf6d875f92d",
    "policy.json": "23c82789bbd75ea9e0b0d94cce90332f1a764772178f0b15d11707dc0c51d929",
    "pool_state.json": "cec950bad6f7a7af6e9ef7636bac2f695a2df99f770a755ef07492e69198db0b",
    "sensors/s-alpha-01.json": "fa0f6c3820259c54dbbe210ce2ab25ffb2de12acf28de73a3744ed9980a6e771",
    "sensors/s-alpha-02.json": "aa7632e9a634d4222d84b1bcfe88d86d51653349000c7b7d67948f28b65b222b",
    "sensors/s-alpha-03.json": "e52bd965ec0ecdd654aa7f8b9b291d242a6583c8b5eb445ceb9bae1f121f3cb4",
    "sensors/s-alpha-04.json": "8beae9a0911181d48f93c89fd71fc976cde2a3dcd08f3b17d3449dbb61fd1d9e",
    "sensors/s-beta-01.json": "01bdf65b34d3bfd3708ba85cd4f40b1321b1f3296d14d17d4b04c5fc4703c462",
    "sensors/s-beta-02.json": "6f66103aec7f3e1ad8f26d489213c2c4b441f086c659afed8d093af9dcfb00ca",
    "sensors/s-beta-03.json": "4ab34de694e24de8543e1f933ef2a5f5fe78bf7523f86e5563d32b6ba0d8acf5",
    "sensors/s-beta-04.json": "78b0faaa51e18ac9907a49ce69d0c857e3e04ea059cff9ab78f0e334e3f09a4b",
    "sensors/s-beta-05.json": "5229fd2a487e3e797d5493793e48cb5c54ca532fe8b2fa93dac4a1dccf48f29f",
    "sensors/s-gamma-01.json": "11e77b9c43012e576e943b7bcf0a1006af5d6d69671c0200fd38ccefc3f808d3",
    "sensors/s-gamma-02.json": "a7394baf9a716a6a1e6cc4006134a28928a411c874727bdd48a68e6b7d5f70c4",
    "sensors/s-gamma-03.json": "54a7f038a3c5c7c968ec7f8323d3bf1ef933c8b357b42248403c9c37969d3356",
    "sensors/s-gamma-04.json": "5ed0f120ac297bc0d6769c6b94b7a5c1571ba91f637e89c94092d63b67d35eb1",
    "sensors/s-gamma-05.json": "933ff5ca56c5db70d453ce086caa38abd5d844210a640e254667328b9e13f333",
    "sensors/s-gamma-06.json": "dd4039dc58ec151b2a09e6e0dc43a317c959495c1317104d4398dbe3405d4dcf",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "calibration_plan.json": "30562d2a75ffcc33f076e911df3c15d730d6f8f50ff7236a4ef71c72d482efd6",
    "lab_ledger.json": "4299e009ad6a005bf2faa48c70c223107e6676c937fdb80d06b46a1d13bd7d38",
    "lineage_risk.json": "963bcb7592f5729cefde4bf2d240a40b9b49acee8a660ebb2f9a4cb021128ad9",
    "recall_windows.json": "fe33193fb328126ef25a1054886f21ea809b9db858e6cf0f667c82822ce20b08",
    "summary.json": "36d1d15dd8569da8a26d1a15d3ce8e059d230818c276f49b48e53cc238e5d0d2",
}

EXPECTED_FIELD_HASHES = {
    "calibration_plan.sensors": "046cf9ed7247d4ee06120f931e1554c7e6f1cb9afe72372c87774b91309cf652",
    "lab_ledger.labs": "c1db0b44e331c795f3b855b7698eb63f7a4edaca192555f11013bcbb846085f6",
    "lineage_risk.sensors": "355ccc37859160650347962bf18b5b6e84702cfc09d3180868ae737869d66d89",
    "recall_windows.sensors": "4c787710815178b981b9e53304048beec437a0c79d9f4b6b7609e1cb0368d6af",
    "summary.accepted_sensors": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.applied_incident_events": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.capacity_deferred_sensors": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.cyclic_sensors": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.ignored_incident_events": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.lab_frozen_sensors": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.needs_review_sensors": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.quarantined_sensors": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "summary.recall_due_sensors": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.sensors_total": "e629fa6598d732768f7c726b4b621285f9c3b85303900aa912017db7617d8bdb",
    "summary.suppressed_sensors": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
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
    """Verify the mounted sensor workspace matches the frozen reference bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the data directory must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            assert _sha256_bytes(path.read_bytes()) == expected


class TestImplementationLanguage:
    """Verify the requested Go implementation is present and replayable."""

    def test_go_program_and_binary_exist(self) -> None:
        """The agent must provide the requested Go source file and executable."""
        source = SRC_DIR / "main.go"
        assert source.is_file()
        assert "package main" in source.read_text(encoding="utf-8")
        binary = BIN_DIR / ("sensor-auditor.exe" if os.name == "nt" else "sensor-auditor")
        assert binary.is_file()

    def test_binary_replays_canonical_outputs(self, tmp_path: Path) -> None:
        """Re-running the executable must reproduce all canonical output hashes."""
        binary = BIN_DIR / ("sensor-auditor.exe" if os.name == "nt" else "sensor-auditor")
        if not binary.exists() and os.name != "nt":
            binary = BIN_DIR / "sensor-auditor"
        replay_dir = tmp_path / "audit"
        replay_dir.mkdir()
        env = os.environ.copy()
        env["SCLA_DATA_DIR"] = str(DATA_DIR)
        env["SCLA_AUDIT_DIR"] = str(replay_dir)
        subprocess.run([str(binary)], check=True, env=env, timeout=20)
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            payload = _load_json(replay_dir / name)
            assert _sha256_bytes(_canonical(payload).encode("utf-8")) == expected


class TestReportStructure:
    """Verify emitted JSON files exist and hash-lock to the canonical contract."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            assert _sha256_bytes(_canonical(outputs[name]).encode("utf-8")) == expected

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        for name, key in (
            ("calibration_plan.json", "sensors"),
            ("lab_ledger.json", "labs"),
            ("lineage_risk.json", "sensors"),
            ("recall_windows.json", "sensors"),
        ):
            payload = outputs[name]
            assert isinstance(payload, dict)
            field = f"{name[:-5]}.{key}"
            assert (
                _sha256_bytes(_canonical(payload[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        for key in sorted(summary):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(summary[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestCalibrationPlan:
    """Spot-check status precedence and capacity placement semantics."""

    def _row(self, outputs: dict[str, object], sensor_id: str) -> dict[str, object]:
        rows = outputs["calibration_plan.json"]["sensors"]
        for row in rows:
            if row["sensor_id"] == sensor_id:
                return row
        raise AssertionError(f"missing sensor row {sensor_id}")

    def test_rows_sorted_by_sensor_id(self, outputs: dict[str, object]) -> None:
        """Calibration rows must be sorted in ascending ASCII sensor order."""
        rows = outputs["calibration_plan.json"]["sensors"]
        ids = [str(row["sensor_id"]) for row in rows]
        assert ids == sorted(ids)

    def test_bias_adjusted_review_status(self, outputs: dict[str, object]) -> None:
        """A silver sensor crosses the residual threshold after lab bias is applied."""
        row = self._row(outputs, "s-alpha-02")
        assert row["status"] == "needs_review"
        assert row["adjusted_residual_ppm"] == 9
        assert row["decision_reason"] == "residual_or_uncertainty"

    def test_alpha_capacity_defers_gold_after_first_gold(
        self, outputs: dict[str, object]
    ) -> None:
        """The alpha lab has no remaining units for the second gold candidate."""
        row = self._row(outputs, "s-alpha-04")
        assert row["status"] == "capacity_deferred"
        assert row["capacity_rank"] is None

    def test_lab_freeze_precedes_capacity(self, outputs: dict[str, object]) -> None:
        """Frozen beta sensors are not capacity-placed even with unused lab capacity."""
        row = self._row(outputs, "s-beta-03")
        assert row["status"] == "lab_frozen"
        assert row["decision_reason"] == "lab_freeze"

    def test_suppressed_sensor_excluded(self, outputs: dict[str, object]) -> None:
        """A suppressed sensor is neither placed nor classified by thresholds."""
        row = self._row(outputs, "s-gamma-05")
        assert row["status"] == "suppressed"
        assert row["capacity_rank"] is None


class TestLineageRisk:
    """Verify contamination propagation and dependency-cycle handling."""

    def _row(self, outputs: dict[str, object], sensor_id: str) -> dict[str, object]:
        rows = outputs["lineage_risk.json"]["sensors"]
        for row in rows:
            if row["sensor_id"] == sensor_id:
                return row
        raise AssertionError(f"missing lineage row {sensor_id}")

    def test_transitive_contamination_descendant(self, outputs: dict[str, object]) -> None:
        """A downstream sensor outside the contaminated batch inherits taint."""
        row = self._row(outputs, "s-beta-05")
        assert row["lineage_status"] == "tainted"
        assert row["taint_source"] == "s-beta-02"
        assert row["taint_hops"] == 1

    def test_cycle_members_are_reported(self, outputs: dict[str, object]) -> None:
        """The gamma pair reports both members of its dependency cycle."""
        row = self._row(outputs, "s-gamma-03")
        assert row["lineage_status"] == "cyclic"
        assert row["cycle_members"] == ["s-gamma-03", "s-gamma-04"]

    def test_cyclic_sensor_is_quarantined(self, outputs: dict[str, object]) -> None:
        """A cycle forces quarantine in the calibration plan."""
        rows = outputs["calibration_plan.json"]["sensors"]
        row = next(r for r in rows if r["sensor_id"] == "s-gamma-04")
        assert row["status"] == "quarantined"
        assert row["decision_reason"] == "dependency_cycle"


class TestRecallWindows:
    """Verify recall windows compose with suppression and quarantine precedence."""

    def _row(self, outputs: dict[str, object], sensor_id: str) -> dict[str, object]:
        rows = outputs["recall_windows.json"]["sensors"]
        for row in rows:
            if row["sensor_id"] == sensor_id:
                return row
        raise AssertionError(f"missing recall row {sensor_id}")

    def test_recall_extend_keeps_old_gold_current(
        self, outputs: dict[str, object]
    ) -> None:
        """The gold recall extension changes the effective window for alpha gold."""
        row = self._row(outputs, "s-alpha-04")
        assert row["age_days"] == 38
        assert row["effective_recall_days"] == 45
        assert row["recall_state"] == "current"

    def test_bronze_old_batch_is_due(self, outputs: dict[str, object]) -> None:
        """A bronze sensor from the old gamma batch is recall due."""
        row = self._row(outputs, "s-gamma-06")
        assert row["recall_state"] == "due"
        assert row["age_days"] == 60

    def test_quarantine_masks_recall_due(self, outputs: dict[str, object]) -> None:
        """Cyclic gold sensors are reported as quarantined instead of due."""
        row = self._row(outputs, "s-gamma-03")
        assert row["recall_state"] == "quarantined"


class TestLabLedgerAndSummary:
    """Verify ledgers and summary counts are internally consistent."""

    def test_alpha_ledger_tracks_capacity_deferred(
        self, outputs: dict[str, object]
    ) -> None:
        """Alpha consumes all capacity and lists the two deferred sensors."""
        alpha = outputs["lab_ledger.json"]["labs"]["lab-alpha"]
        assert alpha["capacity_used"] == 5
        assert alpha["capacity_remaining"] == 0
        assert alpha["deferred_sensors"] == ["s-alpha-03", "s-alpha-04"]

    def test_beta_ledger_remains_unused_when_frozen(
        self, outputs: dict[str, object]
    ) -> None:
        """The frozen beta lab keeps its base capacity unused."""
        beta = outputs["lab_ledger.json"]["labs"]["lab-beta"]
        assert beta["frozen"] is True
        assert beta["capacity_used"] == 0
        assert beta["capacity_remaining"] == 3

    def test_summary_status_counts_partition_sensors(
        self, outputs: dict[str, object]
    ) -> None:
        """All status counters sum to the total sensor count."""
        sm = outputs["summary.json"]
        total = (
            sm["accepted_sensors"]
            + sm["needs_review_sensors"]
            + sm["recall_due_sensors"]
            + sm["capacity_deferred_sensors"]
            + sm["lab_frozen_sensors"]
            + sm["quarantined_sensors"]
            + sm["suppressed_sensors"]
        )
        assert total == sm["sensors_total"]
        assert sm["sensors_total"] == 15

    def test_event_counts_include_superseded_duplicate(
        self, outputs: dict[str, object]
    ) -> None:
        """The older freeze event is ignored after duplicate resolution."""
        sm = outputs["summary.json"]
        assert sm["applied_incident_events"] == 4
        assert sm["ignored_incident_events"] == 4
