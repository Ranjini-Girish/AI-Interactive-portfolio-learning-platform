"""Behavioral tests
 for seismic-localization-qc-hard.

The verifier independently recomputes all expected values from the live fixture
files rather than comparing to a static golden report. Several tests build
custom fixture directories to exercise specific edge cases.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest  # noqa: F401
from reference_solver import build_report

APP_ROOT = Path(os.environ.get("APP_ROOT", "/app"))
SEEDED_DATA = Path(os.environ.get("SEISMIC_DATA", APP_ROOT / "data"))
BIN = APP_ROOT / "bin" / "seismic_audit"

EXPECTED_FILES = {
    "network/stations.csv",
    "velocity/velocity_layers.csv",
    "catalog/events.csv",
    "picks/picks.csv",
    "policy.json",
    "magnitude_model.json",
    "exclusions.json",
}

TOP_KEYS = frozenset({"schema_version", "summary", "events", "findings"})
SUMMARY_KEYS = frozenset({
    "by_finding_type", "by_severity", "event_count", "excluded_events",
    "findings_count", "localized_events", "mean_magnitude", "station_count",
    "total_picks_used", "total_rejected_picks",
})
EVENT_KEYS = frozenset({
    "azimuth_gap_deg", "depth_km", "event_id", "findings", "ml", "ml_uncertainty",
    "nearest_station_km", "origin_time_s", "phase_counts", "rejected_pick_count",
    "rms_residual_s", "source_pick_ids", "status", "used_pick_count", "x_km", "y_km",
})
FINDING_KEYS = frozenset({
    "event_id", "evidence", "finding_type", "pick_id",
    "severity", "severity_rank", "station_id",
})
SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
FINDING_TYPES = frozenset({
    "insufficient_picks", "high_residual_rms", "large_azimuth_gap",
    "depth_at_boundary", "shallow_depth", "station_distance_warning",
    "magnitude_outlier", "rejected_pick",
})


def run_tool(data_dir: Path, out_path: Path) -> dict:
    subprocess.run(["make", "-C", str(APP_ROOT), "build"],
                   text=True, capture_output=True, check=True)
    result = subprocess.run(
        [str(BIN), "--data", str(data_dir), "--out", str(out_path)],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, (
        f"tool failed (exit={result.returncode})\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert out_path.exists(), "tool did not write requested report"
    raw = out_path.read_text(encoding="utf-8")
    assert raw.endswith("\n"), "report must end with a trailing newline"
    assert "\r" not in raw, "report must use Unix line endings"
    return json.loads(raw)


def expected(data_dir: Path, out_path: Path) -> dict:
    return build_report(data_dir, out_path)


def copy_fixture(tmp_path: Path) -> Path:
    dst = tmp_path / "data"
    shutil.copytree(SEEDED_DATA, dst)
    return dst


def write_csv(path: Path, rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── Fixture integrity ────────────────────────────────────────────────────────

def test_01_fixture_files_exist() -> None:
    """All required input files must be present on the container."""
    for rel in EXPECTED_FILES:
        path = SEEDED_DATA / rel
        assert path.exists(), f"missing fixture: {path}"


KNOWN_HASHES: dict[str, str] = {
    "catalog/events.csv":         "a4bb0d5e007b7e0c641284e0a67d27a3fdd0b33efdab634877c6dc9f2cc149e8",
    "exclusions.json":            "f4370652f76592c08d83affe25b3b47356e0a0e5f6124258e926105c8f8d8c4f",
    "magnitude_model.json":       "970269ef09e749e8a4f0f3917c896c627a5a87518d832674e046d56588a102ad",
    "network/stations.csv":       "0984138405afe105fdee33723fc59379e27cf99a2960f5b823bfbe049087ad69",
    "picks/picks.csv":            "c0058600f2e9a5ee17fed00cbfac1d73df7691c02dfd92c178537dc1c7e693de",
    "policy.json":                "947f26cdf10bde9ebdde25dcebed2c6bb55d063f0b123910e290a09323962d32",
    "velocity/velocity_layers.csv": "cf9fc1b8e86dcf056e3b6e51140a58b22cea9e3f247146abfdd670208eca2317",
}


def test_02_fixture_hashes_are_stable() -> None:
    """Input data files must not have been mutated by the agent."""
    for rel, expected_hash in KNOWN_HASHES.items():
        actual_hash = file_sha256(SEEDED_DATA / rel)
        assert actual_hash == expected_hash, (
            f"data file tampered: {rel}\n"
            f"  expected: {expected_hash}\n"
            f"  actual:   {actual_hash}"
        )


# ── Full report ──────────────────────────────────────────────────────────────

def test_03_seeded_report_matches_algorithm(tmp_path: Path) -> None:
    """The tool's output on the seeded data must exactly match the reference."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    assert actual == exp


def test_04_schema_version_and_top_level_keys(tmp_path: Path) -> None:
    """Report must have exactly the four documented top-level keys and schema_version == 1."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    assert set(actual) == TOP_KEYS
    assert actual["schema_version"] == 1


def test_05_summary_keys_and_severity_buckets(tmp_path: Path) -> None:
    """Summary must contain all documented keys; by_severity must have all five severity
    levels present (even at zero); their counts must sum to findings_count."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    assert set(actual["summary"]) == SUMMARY_KEYS
    assert set(actual["summary"]["by_severity"]) == SEVERITIES
    total = sum(actual["summary"]["by_severity"].values())
    assert total == actual["summary"]["findings_count"]


def test_06_event_keys_and_sort_order(tmp_path: Path) -> None:
    """Events array must be sorted by event_id and each event must have all required keys."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    ids = [e["event_id"] for e in actual["events"]]
    assert ids == sorted(ids)
    for e in actual["events"]:
        assert set(e) >= EVENT_KEYS


def test_07_finding_keys_and_sort_order(tmp_path: Path) -> None:
    """Each finding must have exactly the documented keys; findings must be sorted by
    severity_rank descending then finding_type, event_id, station_id, pick_id ascending."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    for f in actual["findings"]:
        assert set(f) == FINDING_KEYS
        assert f["finding_type"] in FINDING_TYPES
    ranks = [(-f["severity_rank"], f["finding_type"], f["event_id"] or "",
              f["station_id"] or "", f["pick_id"] or "") for f in actual["findings"]]
    assert ranks == sorted(ranks)


def test_08_excluded_events_have_null_fields(tmp_path: Path) -> None:
    """Events with status='excluded' must have null for all location, origin, RMS,
    azimuth gap, nearest station, and magnitude fields, with used_pick_count=0."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    for e in actual["events"]:
        if e["status"] == "excluded":
            for key in ["x_km", "y_km", "depth_km", "origin_time_s",
                        "rms_residual_s", "azimuth_gap_deg", "nearest_station_km",
                        "ml", "ml_uncertainty"]:
                assert e[key] is None, f"{e['event_id']}.{key} should be null"
            assert e["used_pick_count"] == 0
            assert e["source_pick_ids"] == []


# ── Pick eligibility ─────────────────────────────────────────────────────────

def test_09_pick_eligibility_contract(tmp_path: Path) -> None:
    """Verify all six pick rejection reasons using their documented check order.

    T01-T04 are eligible (4 picks → localized). T05-T09 are each rejected for a
    distinct reason per the ordered check chain in docs/findings.md:
    unknown_station > station_disabled > excluded_station >
    unknown_phase > nonpositive_weight > pick_status.
    """
    data = copy_fixture(tmp_path)
    write_csv(data / "catalog" / "events.csv", [
        ["event_id", "prior_x_km", "prior_y_km", "prior_depth_km", "prior_origin_time_s", "status"],
        ["TEST", 10, 8, 6, 99.7, ""],
    ])
    write_csv(data / "picks" / "picks.csv", [
        ["pick_id", "event_id", "station_id", "phase", "arrival_time_s", "weight", "status", "amplitude"],
        ["T01", "TEST", "STA01", "P", 102.0, 1.0, "use", ""],
        ["T02", "TEST", "STA02", "P", 103.0, 1.2, "use", ""],
        ["T03", "TEST", "STA03", "P", 103.5, 1.1, "use", ""],
        ["T04", "TEST", "STA04", "S", 107.0, 0.8, "use", ""],
        ["T05", "TEST", "STA05", "S", 107.4, 0.9, "manual", ""],   # pick_status
        ["T06", "TEST", "STA06", "P", 104.0, 1.0, "use", ""],      # station_disabled
        ["T07", "TEST", "GHOST", "P", 104.0, 1.0, "use", ""],      # unknown_station
        ["T08", "TEST", "STA02", "X", 104.0, 1.0, "use", ""],      # unknown_phase
        ["T09", "TEST", "STA02", "P", 104.0, 0.0, "use", ""],      # nonpositive_weight
    ])
    actual = run_tool(data, tmp_path / "actual.json")
    ev = actual["events"][0]
    assert ev["event_id"] == "TEST"
    assert ev["status"] == "localized", f"expected localized, got {ev['status']}"
    assert ev["used_pick_count"] == 4, f"expected 4 used picks, got {ev['used_pick_count']}"
    assert ev["rejected_pick_count"] == 5, "expected 5 rejected (total 9 - 4 used)"
    reasons = {f["evidence"]["reason"] for f in actual["findings"]
               if f["finding_type"] == "rejected_pick" and f["event_id"] == "TEST"}
    assert "pick_status" in reasons, f"missing pick_status; got {reasons}"
    assert "station_disabled" in reasons, f"missing station_disabled; got {reasons}"
    assert "unknown_station" in reasons, f"missing unknown_station; got {reasons}"
    assert "unknown_phase" in reasons, f"missing unknown_phase; got {reasons}"
    assert "nonpositive_weight" in reasons, f"missing nonpositive_weight; got {reasons}"
    # STA06 is disabled (enabled=false) → must be station_disabled, NOT excluded_station
    t06 = next((f for f in actual["findings"]
                if f["finding_type"] == "rejected_pick" and f.get("pick_id") == "T06"), None)
    assert t06 is not None, "no rejected_pick finding for T06"
    assert t06["evidence"]["reason"] == "station_disabled", (
        f"STA06 (enabled=false) must give station_disabled, got {t06['evidence']['reason']}")


def test_10_excluded_station_picks_are_rejected(tmp_path: Path) -> None:
    """An ENABLED station in exclusions.json yields reason=excluded_station (not station_disabled).

    STA_EX is enabled=true but listed in excluded_stations. This proves excluded_station
    is checked independently after the station_disabled check.
    """
    data = copy_fixture(tmp_path)
    with (data / "network" / "stations.csv").open("a", encoding="utf-8") as fh:
        fh.write("STA_EX,5,5,0.10,0.0,true\n")
    excl = json.loads((data / "exclusions.json").read_text(encoding="utf-8"))
    excl["excluded_stations"].append("STA_EX")
    (data / "exclusions.json").write_text(
        json.dumps(excl, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(data / "catalog" / "events.csv", [
        ["event_id", "prior_x_km", "prior_y_km", "prior_depth_km", "prior_origin_time_s", "status"],
        ["XTEST", 10, 8, 6, 99.7, ""],
    ])
    write_csv(data / "picks" / "picks.csv", [
        ["pick_id", "event_id", "station_id", "phase", "arrival_time_s", "weight", "status", "amplitude"],
        ["E01", "XTEST", "STA01", "P", 102.0, 1.0, "use", ""],
        ["E02", "XTEST", "STA02", "P", 103.0, 1.0, "use", ""],
        ["E03", "XTEST", "STA03", "P", 103.5, 1.0, "use", ""],
        ["E04", "XTEST", "STA04", "S", 107.0, 1.0, "use", ""],
        ["E05", "XTEST", "STA_EX", "P", 104.5, 1.0, "use", ""],   # enabled but excluded
    ])
    actual = run_tool(data, tmp_path / "actual.json")
    ev = actual["events"][0]
    assert ev["event_id"] == "XTEST"
    assert ev["status"] == "localized"
    assert ev["used_pick_count"] == 4
    assert ev["rejected_pick_count"] == 1
    e05 = next((f for f in actual["findings"]
                if f["finding_type"] == "rejected_pick" and f.get("pick_id") == "E05"), None)
    assert e05 is not None, "no rejected_pick finding for E05 (STA_EX)"
    assert e05["evidence"]["reason"] == "excluded_station", (
        f"enabled-but-excluded station must give excluded_station, "
        f"got {e05['evidence']['reason']}")


# ── Depth boundaries ─────────────────────────────────────────────────────────

def test_11_depth_at_max_boundary_finding(tmp_path: Path) -> None:
    """Event localized at max depth emits depth_at_boundary."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    boundary_findings = [f for f in exp["findings"] if f["finding_type"] == "depth_at_boundary"]
    actual_boundary = [f for f in actual["findings"] if f["finding_type"] == "depth_at_boundary"]
    assert actual_boundary == boundary_findings


def test_12_shallow_depth_finding(tmp_path: Path) -> None:
    """Event with depth < shallow_depth_km emits shallow_depth finding."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    shallow_actual = [f for f in actual["findings"] if f["finding_type"] == "shallow_depth"]
    shallow_exp = [f for f in exp["findings"] if f["finding_type"] == "shallow_depth"]
    assert shallow_actual == shallow_exp


# ── Velocity model ───────────────────────────────────────────────────────────

def test_13_inclusive_deep_layer_boundary(tmp_path: Path) -> None:
    """The deepest layer boundary is inclusive — depth == bottom_depth_km gets that velocity."""
    data = copy_fixture(tmp_path)
    write_csv(data / "catalog" / "events.csv", [
        ["event_id", "prior_x_km", "prior_y_km", "prior_depth_km", "prior_origin_time_s", "status"],
        ["DEEP", -8, -4, 24, 200, ""],
    ])
    write_csv(data / "picks" / "picks.csv", [
        ["pick_id", "event_id", "station_id", "phase", "arrival_time_s", "weight", "status", "amplitude"],
        ["D01", "DEEP", "STA01", "P", 204.0, 1.0, "use", ""],
        ["D02", "DEEP", "STA02", "P", 206.0, 1.0, "use", ""],
        ["D03", "DEEP", "STA03", "S", 212.0, 0.8, "use", ""],
        ["D04", "DEEP", "STA04", "P", 204.5, 1.1, "use", ""],
        ["D05", "DEEP", "STA05", "S", 209.0, 1.0, "use", ""],
    ])
    actual = run_tool(data, tmp_path / "actual.json")
    exp = expected(data, tmp_path / "expected.json")
    assert actual == exp
    assert actual["events"][0]["status"] == "localized"


# ── Magnitude estimation ────────────────────────────────────────────────────

def test_14_magnitude_is_computed(tmp_path: Path) -> None:
    """Events with enough amplitude observations get ml and ml_uncertainty."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for a_ev, e_ev in zip(actual["events"], exp["events"]):
        assert a_ev["ml"] == e_ev["ml"], f"{a_ev['event_id']} ml mismatch"
        assert a_ev["ml_uncertainty"] == e_ev["ml_uncertainty"]


def test_15_summary_mean_magnitude(tmp_path: Path) -> None:
    """Summary mean_magnitude averages all non-null event magnitudes."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    assert actual["summary"]["mean_magnitude"] == exp["summary"]["mean_magnitude"]


# ── Azimuth gap ──────────────────────────────────────────────────────────────

def test_16_azimuth_gap_wraparound(tmp_path: Path) -> None:
    """Azimuth gap must include the wraparound from last to first angle."""
    data = copy_fixture(tmp_path)
    write_csv(data / "network" / "stations.csv", [
        ["station_id", "x_km", "y_km", "elevation_km", "bias_s", "enabled"],
        ["N01", 10, 0, 0.0, 0.0, "true"],
        ["N02", 10, 1, 0.0, 0.0, "true"],
        ["N03", 10, -1, 0.0, 0.0, "true"],
        ["W01", -20, 0, 0.0, 0.0, "true"],
    ])
    write_csv(data / "catalog" / "events.csv", [
        ["event_id", "prior_x_km", "prior_y_km", "prior_depth_km", "prior_origin_time_s", "status"],
        ["GAP", 0, 0, 4, 10, ""],
    ])
    write_csv(data / "picks" / "picks.csv", [
        ["pick_id", "event_id", "station_id", "phase", "arrival_time_s", "weight", "status", "amplitude"],
        ["G01", "GAP", "N01", "P", 11.8, 1, "use", ""],
        ["G02", "GAP", "N02", "P", 11.9, 1, "use", ""],
        ["G03", "GAP", "N03", "P", 11.9, 1, "use", ""],
        ["G04", "GAP", "W01", "S", 16.1, 1, "use", ""],
    ])
    (data / "exclusions.json").write_text(
        json.dumps({"excluded_stations": [], "excluded_events": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    actual = run_tool(data, tmp_path / "actual.json")
    exp = expected(data, tmp_path / "expected.json")
    assert actual == exp
    assert actual["events"][0]["azimuth_gap_deg"] == exp["events"][0]["azimuth_gap_deg"]


# ── Numeric precision ────────────────────────────────────────────────────────

def test_17_six_decimal_precision(tmp_path: Path) -> None:
    """All floating-point output fields are rounded to exactly 6 decimal places."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    for e in actual["events"]:
        for key in ["x_km", "y_km", "depth_km", "origin_time_s", "rms_residual_s",
                    "azimuth_gap_deg", "nearest_station_km", "ml", "ml_uncertainty"]:
            v = e[key]
            if v is not None:
                assert v == round(v, 6), f"{e['event_id']}.{key}={v} not rounded to 6dp"


def test_18_json_formatting(tmp_path: Path) -> None:
    """Output must be 2-space indented JSON with sorted keys and trailing newline."""
    run_tool(SEEDED_DATA, tmp_path / "actual.json")
    raw = (tmp_path / "actual.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    canonical = json.dumps(parsed, indent=2, sort_keys=True) + "\n"
    assert raw == canonical, "JSON formatting does not match: 2-space indent, sorted keys, trailing newline"


# ── Outlier rejection ────────────────────────────────────────────────────────

def test_19_residual_rejection_reruns_search(tmp_path: Path) -> None:
    """When a pick is rejected by residual, the search reruns without it."""
    data = copy_fixture(tmp_path)
    pol = json.loads((data / "policy.json").read_text(encoding="utf-8"))
    pol["residual_reject_s"] = 0.15
    (data / "policy.json").write_text(json.dumps(pol, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(data / "catalog" / "events.csv", [
        ["event_id", "prior_x_km", "prior_y_km", "prior_depth_km", "prior_origin_time_s", "status"],
        ["REJ", 10, 8, 6, 99.7, "review"],
    ])
    write_csv(data / "picks" / "picks.csv", [
        ["pick_id", "event_id", "station_id", "phase", "arrival_time_s", "weight", "status", "amplitude"],
        ["R01", "REJ", "STA01", "P", 102.0, 1.0, "use", ""],
        ["R02", "REJ", "STA02", "P", 103.0, 1.2, "use", ""],
        ["R03", "REJ", "STA03", "P", 103.5, 1.1, "use", ""],
        ["R04", "REJ", "STA04", "S", 107.0, 0.8, "use", ""],
        ["R05", "REJ", "STA05", "S", 200.0, 0.9, "use", ""],
    ])
    actual = run_tool(data, tmp_path / "actual.json")
    exp = expected(data, tmp_path / "expected.json")
    assert actual == exp
    assert actual["events"][0]["rejected_pick_count"] == exp["events"][0]["rejected_pick_count"]
    assert actual["events"][0]["used_pick_count"] == exp["events"][0]["used_pick_count"]


# ── Counts and consistency ───────────────────────────────────────────────────

def test_20_counts_are_consistent(tmp_path: Path) -> None:
    """Summary counts must equal the corresponding list lengths and per-event sums."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    s = actual["summary"]
    assert s["event_count"] == len(actual["events"])
    assert s["localized_events"] == sum(1 for e in actual["events"] if e["status"] == "localized")
    assert s["findings_count"] == len(actual["findings"])
    assert s["total_picks_used"] == sum(e["used_pick_count"] for e in actual["events"])
    assert s["total_rejected_picks"] == sum(e["rejected_pick_count"] for e in actual["events"])


def test_21_source_pick_ids_are_sorted(tmp_path: Path) -> None:
    """source_pick_ids must be sorted lexicographically for every event."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    for e in actual["events"]:
        assert e["source_pick_ids"] == sorted(e["source_pick_ids"])


def test_22_phase_counts_match_used_picks(tmp_path: Path) -> None:
    """phase_counts must reflect only used picks (source_pick_ids) and both P and S
    keys must be present even when zero."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for a_ev, e_ev in zip(actual["events"], exp["events"]):
        assert a_ev["phase_counts"] == e_ev["phase_counts"]


# ── Custom fixture: insufficient picks ───────────────────────────────────────

def test_23_insufficient_picks_finding(tmp_path: Path) -> None:
    """Event with 2 eligible picks (below min_usable_picks=4) is not localized.

    rejected_pick_count = total_raw_picks - used_pick_count = 2 - 0 = 2.
    All raw picks count as rejected when the event cannot be localized.
    """
    data = copy_fixture(tmp_path)
    write_csv(data / "catalog" / "events.csv", [
        ["event_id", "prior_x_km", "prior_y_km", "prior_depth_km", "prior_origin_time_s", "status"],
        ["FEW", 10, 8, 6, 99.7, ""],
    ])
    write_csv(data / "picks" / "picks.csv", [
        ["pick_id", "event_id", "station_id", "phase", "arrival_time_s", "weight", "status", "amplitude"],
        ["F01", "FEW", "STA01", "P", 102.0, 1.0, "use", ""],
        ["F02", "FEW", "STA02", "P", 103.0, 1.0, "use", ""],
    ])
    actual = run_tool(data, tmp_path / "actual.json")
    ev = actual["events"][0]
    assert ev["event_id"] == "FEW"
    assert ev["status"] == "insufficient_picks"
    assert ev["used_pick_count"] == 0
    # rejected_pick_count = len(raw) - used = 2 - 0 = 2
    assert ev["rejected_pick_count"] == 2, (
        f"expected rejected_pick_count=2 (all raw picks), got {ev['rejected_pick_count']}")
    for key in ["x_km", "y_km", "depth_km", "origin_time_s", "rms_residual_s",
                "azimuth_gap_deg", "nearest_station_km", "ml", "ml_uncertainty"]:
        assert ev[key] is None, f"{key} must be null for insufficient_picks event"
    insuff = [f for f in actual["findings"] if f["finding_type"] == "insufficient_picks"]
    assert len(insuff) == 1
    assert insuff[0]["evidence"]["eligible_picks"] == 2
    assert insuff[0]["evidence"]["min_required"] == 4
