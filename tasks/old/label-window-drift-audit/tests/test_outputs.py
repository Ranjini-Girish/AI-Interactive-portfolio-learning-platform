"""Behavioral tests for the label window drift audit task."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("LWD_DATA_DIR", "/app/labelops"))
AUDIT_DIR = Path(os.environ.get("LWD_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "dataset_lineage.json",
    "incident_trace.json",
    "model_readiness.json",
    "summary.json",
    "window_drift.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "f4fa4d7352d9d692d530605fd02b28c5e0f7579867a61006357906e67ea329ee",
    "ancillary/note-1.json": "73e9503642ba06b73576299c65991082fb1b07c05952e7ed9750665031024548",
    "ancillary/note-2.json": "adb0508c172872d949690147cb828ecef5b0accfb782d32d818283b49e28424f",
    "ancillary/note-3.json": "1b9eaed37508ada09a9357b109a371e94f2f3fa3869127bd27e18c8ffa1b29da",
    "datasets/ds-alpha.json": "cd2673ffe3a5e621ca7412ad49cea642f23aefed6f167d33435e3d92cf42d198",
    "datasets/ds-beta.json": "62669d5e111818d550aced0f502363f88a53b15ceb143589a8c04aae6b4add09",
    "datasets/ds-cycle-a.json": "4150c19dd01d0fe362a10967315ab2b255792370061c04886e3a718c4f56d7b9",
    "datasets/ds-cycle-b.json": "8e1a0d94774be6848ff853f7e1f9b27091a8a010df44bbebc038f8d7e957e2d2",
    "datasets/ds-delta.json": "9281d05f9cc71f02f4eecc4a8992f40afdc966b32dfbd3ef0559b15117461125",
    "datasets/ds-epsilon.json": "8787a3fb723e8fcab0be80e45d9c07dfa52016d6610d776ad6f1450b69284624",
    "datasets/ds-gamma.json": "fb82df6f31d67cf121fb4b03efce4166eaf8ba562a0c9377aaffc0c37d87c1fb",
    "incidents.json": "fa4f1ee24481470053ae8b21d5eff777c096ec1976e1bd599fdb8de34140207e",
    "models/m-alpha-canary.json": "db2efdd23ea8543915e56845d4aa8ed945b43a6a7ddc882c84d9bb10d73bff1a",
    "models/m-alpha.json": "da16c495b8117f1703802f896bf767db830b2bde61a3a9dd1cb00abff1c6da0d",
    "models/m-beta.json": "f61ce009645bebddbc639169e3414acb62b79201f41f610c91688d2adc2169c4",
    "models/m-cycle.json": "122518929f6b4641b3d19e362100880a1d947462371363e388c15097ac1d1836",
    "models/m-delta.json": "04fb018caf79f8ff4a159d5e76363312d246d382a3506f7293e6fd7695c08d7e",
    "models/m-epsilon.json": "a2dab7ec4c0b213d82c4b11ec54382ff8a43ec7e677fb543310a359919e80a35",
    "policy.json": "40481e5d2a37c2093cd9f554c0e1887ec4ef53ff32215db0441658541759ca52",
    "pool_state.json": "72dc34d1d40eab4aa421434c153f21eadd9053d18e097bdd9ab597b193c46c53",
    "windows/w-alpha-1.json": "255c7d018825abb893f7187b3715b56de3a86b6355fa22bb4042382a165ffb31",
    "windows/w-alpha-2.json": "afab4c4d4e5783950167c8b5da98d1c889963eed56c757c3fed0315611536283",
    "windows/w-alpha-3.json": "6f621364408d9b700c0fbff8a6b60ac7c38ad32ad65e4d6e80cdbd5d19b96b09",
    "windows/w-alpha-4.json": "d87c08c296bf3eb63e9a7bffe5892f081d2620a0c1c56584f9c43237c563e7ac",
    "windows/w-alpha-5.json": "74f970517f438654e0138a8a1c7d3a071f3e4dc34f947d131cf085d343965b7a",
    "windows/w-beta-1.json": "1b7611044e4035da316c151390f16cd645813038bd279e37cf813b0f33f9117e",
    "windows/w-beta-2.json": "86b5edb8f733a8f92bbd14771577f6b0ea1bff46c2d22d26b968b91ce81a2909",
    "windows/w-cycle-1.json": "48556042e2b9fca05c2318b0ff28e74e86e7489dcb131d0e736703703881f7b3",
    "windows/w-cycle-2.json": "7e8b1f9d13ba509f0003bc3c61b95e10e1c56956551e8a045991a75f0aaa53f7",
    "windows/w-delta-1.json": "96266235ae5942e812a44c2f23b2e5cdcb60ff00126c08d5556d2ec1bd621dcd",
    "windows/w-epsilon-1.json": "e36a4f64e4382d3318846b1b6c230b82d20aebed0d163fea01b4ee489bc2a9ca",
    "windows/w-gamma-1.json": "440a2e4902c51f810ffcf11d4471bb2716997bb3f7ecbf569c3d72d0fd198233"
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "dataset_lineage.json": "2a7e2631a621f00f687f530e612eb2010cd93305f81d05b35f91bac7d773b1f5",
    "incident_trace.json": "a616d403a9f68c501343e2e0ef06b67c7799ae5ffebcb8036ddbebf532e5a94d",
    "model_readiness.json": "f976f721598df02dbf179e485c551df3235f31eac924c34f7e101642d0c5b6dd",
    "summary.json": "c1044750bed5397e2bd9f5da660db3e628a534f5df39261d4f936700fac73120",
    "window_drift.json": "c3034071fbf7f91de45849cf51c7558228f6504218ea3a18200bb53afbf129be"
}

EXPECTED_FIELD_HASHES = {
    "dataset_lineage.datasets": "a6763710203eb51d45b8e86ad9f78c71e078839e6c7b7c288c187f960b97acf8",
    "incident_trace.events": "100637a25e3a55d3b669f4a2ea23f2e5c7e551823bc15e39a484676efee6f91c",
    "model_readiness.models": "d04b5a2e7f36bae75a770a49c33a8da6eccf22882d83ce0aa4a4853d71daa30c",
    "summary.model_status_counts": "757b778205650912b1332e1b775fed988b4af59dd7a215a96ffb35ca5167d342",
    "window_drift.windows": "73fdaa839e3cfd569dfbcc8e801a94af47d6f94369db6a8e88ac8e28d1509ce2"
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


@pytest.fixture(scope="session")
def windows(outputs: dict[str, object]) -> dict[str, dict[str, object]]:
    """Index window rows by window id."""
    report = outputs["window_drift.json"]
    assert isinstance(report, dict)
    return {str(row["window_id"]): row for row in report["windows"]}


@pytest.fixture(scope="session")
def datasets(outputs: dict[str, object]) -> dict[str, dict[str, object]]:
    """Index dataset rows by dataset id."""
    report = outputs["dataset_lineage.json"]
    assert isinstance(report, dict)
    return {str(row["dataset_id"]): row for row in report["datasets"]}


@pytest.fixture(scope="session")
def models(outputs: dict[str, object]) -> dict[str, dict[str, object]]:
    """Index model rows by model id."""
    report = outputs["model_readiness.json"]
    assert isinstance(report, dict)
    return {str(row["model_id"]): row for row in report["models"]}


class TestInputIntegrity:
    """Verify the mounted workspace matches the frozen fixture bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the data directory must match its digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            assert _sha256_bytes(path.read_bytes()) == expected


class TestReportStructure:
    """Verify emitted JSON files and key fields follow the canonical contract."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Every emitted report must match the pinned canonical JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            assert _sha256_bytes(_canonical(outputs[name]).encode()) == expected

    def test_selected_field_hashes(self, outputs: dict[str, object]) -> None:
        """Nested fields that carry the main decisions must match their digests."""
        assert _sha256_bytes(_canonical(outputs["window_drift.json"]["windows"]).encode()) == EXPECTED_FIELD_HASHES["window_drift.windows"]
        assert _sha256_bytes(_canonical(outputs["dataset_lineage.json"]["datasets"]).encode()) == EXPECTED_FIELD_HASHES["dataset_lineage.datasets"]
        assert _sha256_bytes(_canonical(outputs["model_readiness.json"]["models"]).encode()) == EXPECTED_FIELD_HASHES["model_readiness.models"]
        assert _sha256_bytes(_canonical(outputs["incident_trace.json"]["events"]).encode()) == EXPECTED_FIELD_HASHES["incident_trace.events"]
        assert _sha256_bytes(_canonical(outputs["summary.json"]["model_status_counts"]).encode()) == EXPECTED_FIELD_HASHES["summary.model_status_counts"]

    def test_top_level_keys_are_exact(self, outputs: dict[str, object]) -> None:
        """Reports must not add or omit top-level keys."""
        assert set(outputs["window_drift.json"]) == {"status_counts", "windows"}
        assert set(outputs["dataset_lineage.json"]) == {"compromised_datasets", "datasets", "lineage_status_counts"}
        assert set(outputs["model_readiness.json"]) == {"models", "readiness_counts"}
        assert set(outputs["incident_trace.json"]) == {"accepted_event_count", "events", "ignored_event_count"}
        assert set(outputs["summary.json"]) == {"blocked_window_count", "current_day", "dataset_status_counts", "ignored_incident_events", "model_status_counts", "total_windows"}


class TestDatasetLineage:
    """Check transitive lineage and compromise outcomes."""

    def test_compromise_cascades_to_descendant_dataset(self, datasets: dict[str, dict[str, object]]) -> None:
        """A compromised parent dataset must taint non-cyclic descendants."""
        assert datasets["ds-beta"]["lineage_status"] == "compromised"
        assert datasets["ds-gamma"]["lineage_status"] == "compromised"
        assert datasets["ds-gamma"]["compromise_sources"] == ["evt-003"]

    def test_cycle_and_missing_parent_are_classified(self, datasets: dict[str, dict[str, object]]) -> None:
        """Lineage cycles and absent parents must use distinct blocking statuses."""
        assert datasets["ds-cycle-a"]["lineage_status"] == "cyclic"
        assert datasets["ds-delta"]["lineage_status"] == "missing_parent"
        assert datasets["ds-delta"]["parent_depth"] == -1


class TestWindowDrift:
    """Check drift, credits, freezes, and precedence in window rows."""

    def test_relabel_credit_decays_across_window_descendants(self, windows: dict[str, dict[str, object]]) -> None:
        """A relabel credit must shrink by dependency hop before drift comparison."""
        assert windows["w-alpha-2"]["effective_credit_bps"] == 500
        assert windows["w-alpha-3"]["effective_credit_bps"] == 200
        assert windows["w-alpha-2"]["status"] == "drift_warning"

    def test_freeze_overrides_later_drift_for_descendants(self, windows: dict[str, dict[str, object]]) -> None:
        """A freeze event must mark the target and bounded descendants before drift gates."""
        assert windows["w-alpha-3"]["status"] == "frozen"
        assert windows["w-alpha-4"]["status"] == "frozen_dependency"
        assert windows["w-alpha-5"]["status"] == "frozen_dependency"

    def test_compromised_lineage_precedes_window_dependency_state(self, windows: dict[str, dict[str, object]]) -> None:
        """Dataset compromise must dominate otherwise ordinary window calculations."""
        assert windows["w-beta-2"]["status"] == "compromised"
        assert windows["w-gamma-1"]["status"] == "compromised"


class TestModelReadiness:
    """Check model readiness precedence and eligibility rows."""

    def test_model_hold_precedes_promotion_for_clean_dataset(self, models: dict[str, dict[str, object]]) -> None:
        """An accepted hold must stop a model that otherwise has enough windows."""
        assert models["m-alpha"]["status"] == "hold"
        assert models["m-alpha"]["eligible_window_count"] == 2

    def test_canary_promotes_without_hold(self, models: dict[str, dict[str, object]]) -> None:
        """A clean model with enough eligible windows and score should promote."""
        assert models["m-alpha-canary"]["status"] == "promote"
        assert models["m-alpha-canary"]["eligible_windows"] == ["w-alpha-1", "w-alpha-2"]

    def test_quarantine_statuses_precede_score_checks(self, models: dict[str, dict[str, object]]) -> None:
        """Lineage defects and compromises must block models before score gates."""
        assert models["m-beta"]["status"] == "quarantine_compromise"
        assert models["m-cycle"]["status"] == "quarantine_lineage"
        assert models["m-delta"]["status"] == "quarantine_lineage"

    def test_below_score_remains_distinct_from_window_shortage(self, models: dict[str, dict[str, object]]) -> None:
        """A model with enough eligible windows but low score must report below_score."""
        assert models["m-epsilon"]["status"] == "below_score"


class TestIncidentTrace:
    """Check accepted, ignored, and superseded event accounting."""

    def test_event_decisions_cover_all_rejection_reasons(self, outputs: dict[str, object]) -> None:
        """The trace should expose future, rejected, missing, unsupported, and superseded cases."""
        report = outputs["incident_trace.json"]
        reasons = {row["reason"] for row in report["events"]}
        assert {"future_event", "missing_target", "rejected_event", "superseded_event", "unsupported_kind"} <= reasons
        assert report["accepted_event_count"] == 4
        assert report["ignored_event_count"] == 6


class TestImplementationLanguage:
    """Verify the submitted implementation is a reproducible Go program."""

    def test_go_binary_recreates_reports(self, tmp_path: Path) -> None:
        """The compiled Go binary must regenerate byte-identical report content."""
        src = Path("/app/src/main.go")
        binary = Path("/app/bin/label-window-drift-audit")
        assert src.is_file(), "missing Go source at /app/src/main.go"
        assert "package main" in src.read_text(encoding="utf-8")
        assert binary.is_file(), "missing compiled audit binary"
        assert os.access(binary, os.X_OK), "audit binary is not executable"
        rerun_dir = tmp_path / "rerun"
        rerun_dir.mkdir()
        env = os.environ.copy()
        env["LWD_DATA_DIR"] = str(DATA_DIR)
        env["LWD_AUDIT_DIR"] = str(rerun_dir)
        subprocess.run([str(binary)], check=True, env=env, cwd="/app")
        for name in OUTPUT_FILES:
            assert (rerun_dir / name).read_bytes() == (AUDIT_DIR / name).read_bytes()
