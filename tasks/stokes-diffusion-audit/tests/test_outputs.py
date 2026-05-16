"""Behavioral tests for the Stokes diffusion audit task."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SDA_DATA_DIR", "/app/stokes_lab"))
AUDIT_DIR = Path(os.environ.get("SDA_AUDIT_DIR", "/app/audit"))

RESULTS = AUDIT_DIR / "diffusion_results.json"
ANOMALIES = AUDIT_DIR / "anomalies.json"
SUMMARY = AUDIT_DIR / "summary.json"

BINARY = Path("/app/bin/stokesdiff")

EXPECTED_ENTRY_KEYS = {
    "d_stokes_nm2_per_s",
    "hydrodynamic_radius_nm_used",
    "measurement_id",
    "probe_id",
    "solute_id",
    "solvent_id",
    "status",
    "temp_effective_K",
    "viscosity_cP_used",
}


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "489edc949d50209b0db96efddec9dc77ec25eb9b6050efefaca6f6ffc0e2bb70",
    "incident_log.json": "c2a1fae06803a2e565fa7c5e11cfdbd68d2773a1c96be00dda0a7539bff70885",
    "measurements/m-a01.json": "c589f8a030c83c5c6eb98b5a69d15cbeab0d6e2701d38bb13f8448fbac3156ff",
    "measurements/m-a02.json": "54b83a088646c29bbc749a1f5d43e48fc73a3cb40e43947adda6fe71c6db314c",
    "measurements/m-a03.json": "ad6dfd1e534dcc92d6b33e9a5cd2b0eecc20ffe1031f1850e2fb3aca3c061e79",
    "measurements/m-a04.json": "a425ac1f7587299b4f9a0d4c09ddc9b829dc551b6ad49664f78baf4bc3f9b6ed",
    "measurements/m-a05.json": "a533e8d7ed8138a695dfb3500e7641069562296c0fb059b5944ba73c6ad75ead",
    "measurements/m-a06.json": "f378539ca8d4671e30c9591ed6d60a1c6171a5514c75976b4a8d48577608fb5b",
    "measurements/m-a07.json": "74922ecff671c639ca5d75e9d340b757445fdbfde2447d509980c628c7680ff4",
    "measurements/m-a08.json": "21d5a03cd0e257d9bd00b5d8fa2e79d15d71e7c7708c0f2c13d1d07b77f7cda4",
    "measurements/m-a09.json": "be3c1cddc1d48b879b1f7e7f3343dfa76c130ef52d3fc5ebd8aa00635a0fc35b",
    "measurements/m-a10.json": "0454b2b6dfc4e7b6d6e110970579d86f95862a94209913780c4f8d3300de0969",
    "measurements/m-a11.json": "2fe2f7d200079491de2e1c9aa0e73073d992c92b1516bd0f8f448e23174467e2",
    "measurements/m-a12.json": "cf427406fdf5815fcabc933d18d1ea1a0794a218108b283b75009bbb6880bf67",
    "measurements/m-a13.json": "87b2333a968eb54dda83d23749bee114f9e909691e3b846b5a7623528aad173c",
    "measurements/m-a14.json": "aaa7abf408aa8d39ae01abcd2619394fdc46139c718fb4bcc75f250d03d02f78",
    "meta/deco01.json": "8845eb23a56ea78c5a7cfd5d494cae3fc7f6a5dd2d91fa144d632301f00e6f79",
    "meta/deco02.json": "8845eb23a56ea78c5a7cfd5d494cae3fc7f6a5dd2d91fa144d632301f00e6f79",
    "meta/deco03.json": "8845eb23a56ea78c5a7cfd5d494cae3fc7f6a5dd2d91fa144d632301f00e6f79",
    "meta/deco04.json": "8845eb23a56ea78c5a7cfd5d494cae3fc7f6a5dd2d91fa144d632301f00e6f79",
    "meta/deco05.json": "8845eb23a56ea78c5a7cfd5d494cae3fc7f6a5dd2d91fa144d632301f00e6f79",
    "meta/deco06.json": "8845eb23a56ea78c5a7cfd5d494cae3fc7f6a5dd2d91fa144d632301f00e6f79",
    "pool_state.json": "74d3cfe15cb3f4cddd52cd4800bcc244bedff07709c5cb091abea88697bfe1d4",
    "probes/p1.json": "bd1e3af9d9d4d96fc550ecfaaf3adf14d1a0d7737bda84914dc9e2af45d4d21e",
    "probes/p2.json": "d190057d0a8e49c5b7abdfbdf1932033bcf26c6f27008661d049d3d6acc04b8a",
    "probes/p3.json": "4972f1e3926f3e065ecb3f9919ab235d3eb3cc15f3175d742ad8d20b709ad70d",
    "probes/p4.json": "340e77eb5bcf54c040c0213dcff36f7398224aa77dc17d7c3f6d4fc815e0b17e",
    "solvents/acetone.json": "b0cc89fc84a47488c10f3a77c2751ce1d7d4c716fc6786bc250e23143b7d76a0",
    "solvents/cyclohexane.json": "65852539e546670f55b6c91545fe459b813610083f52dc0edc11a20d80e7bad0",
    "solvents/dmso.json": "f827de6f8a34ab41711fa466293c54bfd5ae5b01a91a22b3dc03f2409c153184",
    "solvents/water.json": "5dbe8e9cecfcbcb5bce2ea34477d9b2381ade98cb924232a0f1aa61a36b1de7e",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "anomalies.json": "721d5c15336b86ec1eda8d6fbf61fdda18c2e5f5c14812a293bcd2755135d372",
    "diffusion_results.json": "167be0b36b03587f0b6339b61a6886e6bd25e929e4916d89e4ded0bda62d9d32",
    "summary.json": "82200face11ebdb6b7b8eed2d2fb7120fb66730116cebfcda2473f3674f6b708",
}


EXPECTED_FIELD_HASHES = {
    "anomalies.applied_events": "2f1ec53d9a14f9b60e6ffc5a5a52c793a40bde2baa07df2f267eb11904c7b436",
    "diffusion_results.entries": "2386a21d3010470b6ad76998cf7b7ea64b2d1318acc1dddbf93e176bb1376293",
    "summary.drift_capped_count": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.ignored_incident_events": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "summary.measurements_total": "8527a891e224136950ff32ca212b45bc93f69fbb801c3b1ebedac52775f99e61",
    "summary.ok_count": "19581e27de7ced00ff1ce50b2047e7a567c76b1cbaebabe5ef03f7c3017bb5b7",
    "summary.probe_void_count": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.radius_clamped_count": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.solvent_void_count": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.viscosity_extrapolation_high_count": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.viscosity_extrapolation_low_count": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def diffusion_results() -> dict[str, object]:
    """Load diffusion_results.json once."""
    return _load_json(RESULTS)


@pytest.fixture(scope="session")
def anomalies() -> dict[str, object]:
    """Load anomalies.json once."""
    return _load_json(ANOMALIES)


@pytest.fixture(scope="session")
def summary() -> dict[str, object]:
    """Load summary.json once."""
    return _load_json(SUMMARY)


class TestInputIntegrity:
    """Pinned digests for every shipped fixture under the laboratory bundle."""

    def test_each_input_file_sha256(self) -> None:
        """Each relative path under the bundle must match its frozen digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestOutputIntegrity:
    """Byte-level checks for emitted JSON artifacts."""

    def test_diffusion_results_canonical_hash(self) -> None:
        """diffusion_results.json must match the pinned SHA-256."""
        digest = _sha256_bytes(RESULTS.read_bytes())
        assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES["diffusion_results.json"]

    def test_anomalies_canonical_hash(self) -> None:
        """anomalies.json must match the pinned SHA-256."""
        digest = _sha256_bytes(ANOMALIES.read_bytes())
        assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES["anomalies.json"]

    def test_summary_canonical_hash(self) -> None:
        """summary.json must match the pinned SHA-256."""
        digest = _sha256_bytes(SUMMARY.read_bytes())
        assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES["summary.json"]

    def test_field_hashes(self, diffusion_results: dict, anomalies: dict, summary: dict) -> None:
        """Major sections must match canonical structural hashes."""
        bundles = [
            ("diffusion_results.entries", diffusion_results.get("entries")),
            ("anomalies.applied_events", anomalies.get("applied_events")),
            ("summary.drift_capped_count", summary.get("drift_capped_count")),
            ("summary.ignored_incident_events", summary.get("ignored_incident_events")),
            ("summary.measurements_total", summary.get("measurements_total")),
            ("summary.ok_count", summary.get("ok_count")),
            ("summary.probe_void_count", summary.get("probe_void_count")),
            ("summary.radius_clamped_count", summary.get("radius_clamped_count")),
            ("summary.solvent_void_count", summary.get("solvent_void_count")),
            ("summary.viscosity_extrapolation_high_count", summary.get("viscosity_extrapolation_high_count")),
            ("summary.viscosity_extrapolation_low_count", summary.get("viscosity_extrapolation_low_count")),
        ]
        for key, payload in bundles:
            expected = EXPECTED_FIELD_HASHES[key]
            digest = _sha256_bytes(_canonical(payload).encode("utf-8"))
            assert digest == expected, f"field hash mismatch for {key}"


class TestStructure:
    """Schema-level expectations derived from the published spec text."""

    def test_diffusion_top_level_keys(self, diffusion_results: dict) -> None:
        """diffusion_results.json exposes only the documented top-level key."""
        assert set(diffusion_results.keys()) == {"entries"}

    def test_entries_sorted_by_measurement_id(self, diffusion_results: dict) -> None:
        """Entries sort ascending by measurement_id."""
        entries = diffusion_results["entries"]
        assert isinstance(entries, list)
        ids = [str(e["measurement_id"]) for e in entries]
        assert ids == sorted(ids)

    def test_anomaly_event_ids_sorted(self, anomalies: dict) -> None:
        """applied_events must be sorted ascending."""
        evs = anomalies["applied_events"]
        assert evs == sorted(evs)

    def test_summary_partition_counts(self, summary: dict) -> None:
        """Disposition buckets partition the measurement total."""
        total = int(summary["measurements_total"])
        ok_c = int(summary["ok_count"])
        pv = int(summary["probe_void_count"])
        sv = int(summary["solvent_void_count"])
        assert ok_c + pv + sv == total

    def test_summary_top_level_keys(self, summary: dict) -> None:
        """summary.json exposes exactly the aggregate keys named in the contract."""
        assert set(summary.keys()) == {
            "drift_capped_count",
            "ignored_incident_events",
            "measurements_total",
            "ok_count",
            "probe_void_count",
            "radius_clamped_count",
            "solvent_void_count",
            "viscosity_extrapolation_high_count",
            "viscosity_extrapolation_low_count",
        }

    def test_each_entry_row_key_set(self, diffusion_results: dict) -> None:
        """Each diffusion row object carries exactly the field names from SPEC.md."""
        entries = diffusion_results["entries"]
        assert isinstance(entries, list)
        for row in entries:
            assert set(row.keys()) == EXPECTED_ENTRY_KEYS


class TestImplementationArtifacts:
    """Go layout, binary presence, and SDA_* directory routing."""

    def test_go_sources_under_app_src_use_package_main(self) -> None:
        """At least one Go file under /app/src declares package main."""
        src_dir = Path("/app/src")
        go_files = list(src_dir.glob("*.go"))
        assert len(go_files) >= 1, "expected at least one .go file under /app/src/"
        for gf in go_files:
            text = gf.read_text(encoding="utf-8")
            assert "package main" in text, f"{gf} must declare package main"

    def test_stokesdiff_binary_exists_and_executable(self) -> None:
        """The linked helper must exist at /app/bin/stokesdiff and be executable."""
        assert BINARY.is_file(), "missing /app/bin/stokesdiff"
        assert os.access(BINARY, os.X_OK), "/app/bin/stokesdiff is not executable"

    def test_binary_writes_outputs_under_sda_audit_dir(self, tmp_path: Path) -> None:
        """With SDA_AUDIT_DIR unset in the default layout, rerunning with a custom audit
        path must recreate the same three canonical files there."""
        out_dir = tmp_path / "alt_audit"
        out_dir.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("SDA_AUDIT_DIR", "SDA_DATA_DIR")}
        env["SDA_AUDIT_DIR"] = str(out_dir)
        res = subprocess.run(
            [str(BINARY)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert res.returncode == 0, res.stderr
        for name, expected_hash in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            written = out_dir / name
            assert written.is_file(), f"missing {name} under custom SDA_AUDIT_DIR"
            digest = _sha256_bytes(written.read_bytes())
            assert digest == expected_hash, f"hash mismatch for {name} under SDA_AUDIT_DIR"

    def test_binary_reads_inputs_from_sda_data_dir(self, tmp_path: Path) -> None:
        """A full copy of the bundle at SDA_DATA_DIR must yield byte-identical outputs."""
        lab_copy = tmp_path / "lab_mirror"
        shutil.copytree(DATA_DIR, lab_copy)
        out_dir = tmp_path / "out_mirror"
        out_dir.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("SDA_AUDIT_DIR", "SDA_DATA_DIR")}
        env["SDA_DATA_DIR"] = str(lab_copy)
        env["SDA_AUDIT_DIR"] = str(out_dir)
        res = subprocess.run(
            [str(BINARY)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert res.returncode == 0, res.stderr
        for name, expected_hash in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            written = out_dir / name
            assert written.is_file()
            digest = _sha256_bytes(written.read_bytes())
            assert digest == expected_hash, f"hash mismatch for {name} under SDA_DATA_DIR copy"


class TestDispositionCoverage:
    """Positive coverage for each emitted disposition string."""

    def test_probe_void_present(self, diffusion_results: dict) -> None:
        """At least one entry reports probe_void, including the m-a04 stiction row."""
        entries = diffusion_results["entries"]
        statuses = {str(e["status"]) for e in entries}
        assert "probe_void" in statuses
        probe_rows = [e for e in entries if str(e["status"]) == "probe_void"]
        assert any(str(e["measurement_id"]) == "m-a04" for e in probe_rows)

    def test_solvent_void_present(self, diffusion_results: dict) -> None:
        """At least one entry reports solvent_void; m-a06 must be void."""
        entries = diffusion_results["entries"]
        assert any(str(e["status"]) == "solvent_void" for e in entries)
        hit = next(e for e in entries if str(e["measurement_id"]) == "m-a06")
        assert str(hit["status"]) == "solvent_void"

    def test_ok_rows_emit_numeric_fields(self, diffusion_results: dict) -> None:
        """Entries marked ok expose numeric temperature, viscosity, radius, and diffusion."""
        for e in diffusion_results["entries"]:
            if str(e["status"]) != "ok":
                continue
            assert isinstance(e["temp_effective_K"], (int, float))
            assert isinstance(e["viscosity_cP_used"], (int, float))
            assert isinstance(e["hydrodynamic_radius_nm_used"], (int, float))
            assert isinstance(e["d_stokes_nm2_per_s"], (int, float))


class TestRecallLift:
    """Coverage for the recall_lift cancellation rule."""

    def test_lifted_measurement_becomes_ok(self, diffusion_results: dict) -> None:
        """m-a12 (probe p1, water, day 22) must be lifted past the recall and ok."""
        entries = diffusion_results["entries"]
        hit = next(e for e in entries if str(e["measurement_id"]) == "m-a12")
        assert str(hit["status"]) == "ok"
        assert isinstance(hit["temp_effective_K"], (int, float))

    def test_probe_scoped_lift_does_not_save_other_probe(self, diffusion_results: dict) -> None:
        """m-a13 (probe p2, water, day 22) must remain solvent_void because the lift is scoped to p1."""
        entries = diffusion_results["entries"]
        hit = next(e for e in entries if str(e["measurement_id"]) == "m-a13")
        assert str(hit["status"]) == "solvent_void"
        assert hit["d_stokes_nm2_per_s"] is None


class TestAnomalyBundle:
    """Cross-checks for the applied incident identifiers."""

    def test_expected_applied_event_ids(self, anomalies: dict) -> None:
        """Every accepted incident that influences an ok row or activates void precedence appears as applied."""
        applied = set(anomalies["applied_events"])
        expected = {
            "ev-bench-p1-dmso-02",
            "ev-bench-p2-acetone-05b",
            "ev-drift-p1-02",
            "ev-drift-p1-08",
            "ev-drift-p1-10",
            "ev-drift-p1-13",
            "ev-drift-p2-01",
            "ev-drift-p3-07",
            "ev-drift-p3-a03",
            "ev-lift-water-p1",
            "ev-recall-water",
            "ev-stict-p3",
            "ev-stict-p4-early",
        }
        assert expected == applied

    def test_recall_floor_bench_omitted_from_applied(self, anomalies: dict) -> None:
        """A bench correction on or before the latest solvent recall day must not appear when filtered out."""
        applied = set(anomalies["applied_events"])
        assert "ev-bench-p1-water-17" not in applied

    def test_drift_only_for_void_rows_omitted(self, anomalies: dict) -> None:
        """A drift whose every eligible measurement is voided must not be listed as applied."""
        applied = set(anomalies["applied_events"])
        assert "ev-drift-p3-a04only" not in applied

    def test_bench_only_for_void_rows_omitted(self, anomalies: dict) -> None:
        """A bench correction that only wins for voided measurements must not be listed."""
        applied = set(anomalies["applied_events"])
        assert "ev-bench-p3-water-11" not in applied

    def test_lift_without_matching_recall_omitted(self, anomalies: dict) -> None:
        """A recall_lift that applies but has no matching solvent_recall to cancel must not be listed."""
        applied = set(anomalies["applied_events"])
        assert "ev-lift-acetone-wildcard" not in applied

    def test_multi_window_drift_emitted_together(self, anomalies: dict) -> None:
        """Distinct drift events that fall in the same measurement's window must all be emitted."""
        applied = set(anomalies["applied_events"])
        assert {"ev-drift-p1-10", "ev-drift-p1-13"}.issubset(applied)
        assert {"ev-drift-p1-08", "ev-drift-p1-10"}.issubset(applied)
        assert {"ev-drift-p3-a03", "ev-drift-p3-07"}.issubset(applied)

    def test_old_drift_outside_window_omitted_when_no_other_row_rescues(self, anomalies: dict) -> None:
        """A drift event whose only eligible measurement reaches no ok row in its window must not be listed."""
        applied = set(anomalies["applied_events"])
        assert "ev-drift-p2-01" in applied


class TestCompoundRules:
    """Cross-checks for drift cap, stiction lookback, and split viscosity temperature."""

    def test_drift_capped_count_positive(self, summary: dict) -> None:
        """At least one measurement exceeds the pool drift cap after window summation."""
        assert int(summary["drift_capped_count"]) >= 1

    def test_m_a14_ok_despite_expired_stiction(self, diffusion_results: dict) -> None:
        """m-a14 (p4, day 15) stays ok because the day-1 stiction falls outside the lookback window."""
        entries = diffusion_results["entries"]
        hit = next(e for e in entries if str(e["measurement_id"]) == "m-a14")
        assert str(hit["status"]) == "ok"
        assert isinstance(hit["d_stokes_nm2_per_s"], (int, float))

    def test_m_a09_void_from_lookback_stiction(self, diffusion_results: dict) -> None:
        """m-a09 (p4, day 1) is probe_void because stiction on the same run day is inside the window."""
        entries = diffusion_results["entries"]
        hit = next(e for e in entries if str(e["measurement_id"]) == "m-a09")
        assert str(hit["status"]) == "probe_void"

    def test_m_a12_lifted_without_recall_floor_bench(self, diffusion_results: dict) -> None:
        """m-a12 omits the day-17 water bench delta because recall floor R=18 zeroes bench selection."""
        entries = diffusion_results["entries"]
        hit = next(e for e in entries if str(e["measurement_id"]) == "m-a12")
        assert str(hit["status"]) == "ok"
        assert hit["temp_effective_K"] == pytest.approx(298.75, abs=0.001)


class TestDispositionExpectedShape:
    """Concrete row-level cross-checks for selected entries."""

    def test_m_a07_drift_falls_outside_window(self, diffusion_results: dict) -> None:
        """m-a07 (p2, water, day 10) has a drift at day 1 that falls outside the 7-day inclusive window, so T_eff omits its contribution."""
        entries = diffusion_results["entries"]
        hit = next(e for e in entries if str(e["measurement_id"]) == "m-a07")
        assert str(hit["status"]) == "ok"
        assert isinstance(hit["temp_effective_K"], (int, float))
