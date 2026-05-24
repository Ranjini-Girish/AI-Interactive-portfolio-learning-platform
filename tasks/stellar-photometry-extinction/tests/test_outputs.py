"""Behavioral tests for stellar-photometry-extinction-audit-hard.

The verifier independently recomputes all expected values from the live
fixture files instead of comparing against a static golden report. Several
tests build custom fixture directories to exercise specific edge cases.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest  # noqa: F401
from reference_solver import build_report

APP_ROOT = Path(os.environ.get("APP_ROOT", "/app"))
SEEDED_DATA = Path(os.environ.get("PHOTO_DATA", APP_ROOT / "data"))
BIN = APP_ROOT / "bin" / "photo_audit"

EXPECTED_FILES = {
    "site.json",
    "policy.json",
    "exclusions.json",
    "manifest.json",
    "instrument.json",
    "catalog/standards.csv",
    "catalog/programs.csv",
}

TOP_KEYS = frozenset({
    "findings", "per_night_calibration", "per_star_lightcurves",
    "schema_version", "summary",
})

SUMMARY_KEYS = frozenset({
    "by_finding_type", "by_severity", "calibrated_pairs", "excluded_nights",
    "findings_count", "flagged_outliers", "insufficient_pairs",
    "lightcurves_count", "total_nights", "total_observations",
    "used_program_observations", "used_standard_observations",
    "variable_stars",
})

CALIBRATION_KEYS = frozenset({
    "airmass_max", "airmass_min", "extinction_k", "extinction_k_uncertainty",
    "filter", "n_outliers_flagged", "n_program_observations",
    "n_standards_used", "n_total_observations", "night_id",
    "residual_stddev", "status", "zero_point", "zero_point_uncertainty",
})

LIGHTCURVE_KEYS = frozenset({
    "amplitude_mag", "chi_squared_reduced", "filter", "is_variable",
    "max_calibrated_mag", "mean_calibrated_mag", "min_calibrated_mag",
    "n_nights", "n_observations", "star_id", "status",
    "stddev_calibrated_mag",
})

FINDING_KEYS = frozenset({
    "evidence", "filter", "finding_type", "image_id", "night_id",
    "severity", "severity_rank", "star_id",
})

SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})

FINDING_TYPES = frozenset({
    "insufficient_standards", "bad_night_residuals", "negative_extinction",
    "large_zero_point_uncertainty", "outlier_observation",
    "degenerate_airmass_range", "variable_star_detected",
    "insufficient_lightcurve_observations", "program_star_no_data",
    "excluded_night", "excluded_filter", "excluded_star",
    "excluded_observation",
})

CALIBRATION_STATUSES = frozenset({
    "calibrated", "insufficient_standards", "excluded_night",
    "excluded_filter", "degenerate_airmass_range",
})

LIGHTCURVE_STATUSES = frozenset({
    "calibrated", "insufficient_observations", "no_data",
})


def run_tool(data_dir: Path, out_path: Path) -> dict:
    subprocess.run(
        ["make", "-C", str(APP_ROOT), "build"],
        text=True, capture_output=True, check=True,
    )
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


# ── Fixture integrity ─────────────────────────────────────────────────────

def test_01_fixture_files_exist() -> None:
    """All required input files must be present on the container."""
    for rel in EXPECTED_FILES:
        path = SEEDED_DATA / rel
        assert path.exists(), f"missing fixture: {path}"


def test_02_observation_files_exist() -> None:
    """Every night listed in manifest.json must have its observations file."""
    manifest = json.loads(
        (SEEDED_DATA / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["nights"]:
        obs = SEEDED_DATA / "observations" / entry["observations_file"]
        assert obs.exists(), f"missing observations file: {obs}"


EXPECTED_SHA256: dict[str, str] = {
    "site.json": "388e89b00bb06859574ac3b2e478bc367eb3e06582f363803600be131c1416eb",
    "policy.json": "d69d2bfd7f605f353b11eeb72de6af7f224091eda885488577c8742e21b3a05e",
    "exclusions.json": "a2945cb6ff4cd0b72f7c96b075cc9df962e9a68fad7bfc5edee1eb802b3216bc",
    "manifest.json": "3c7bb8a4042d12f5024fe1efd9c73a4208c658cb0e67fdf19275aa6ba18b06a6",
    "instrument.json": "4b20c1d690ced4fcdd4bb10c84cdddffa830952b75a7bca29cfa1353667dd60a",
    "catalog/standards.csv": "0c15ac352c87e6cfa247cc1b71ac9bc42c42a967009c738efa665ec9be3fcefe",
    "catalog/programs.csv": "1fbc4aa5faf5212c00fd6e63b3c47e36989a317c3bf87e94b6bedbaf988c9584",
    "observations/N001.csv": "677d18a7ac5269e1a64469f3d619e8c5b0b7ebec5deed3c4a6555b4c46711f2b",
    "observations/N002.csv": "3ec92d62353894086f0ec27271d9e857a4b25dc135ee1b0a4c57fcf5fb0fd711",
    "observations/N003.csv": "84e01a3392018f43052fac9fba9988eeb8886c0b15de20e3dfe17f2dcd086674",
    "observations/N004.csv": "97258998193aa64a880ca137253ffb26e3460bcca2b43e98efa9cf35f39ca4ba",
    "observations/N005.csv": "ad107ed4bf0b90a9e2becd6d0b0e211d7a6e474fce6edebec524f89946c82ca7",
    "observations/N006.csv": "2c5df27979f70b3c35d1edb0bf65e771edd09a953279634ad02ea964267f770f",
    "observations/N007.csv": "37c10d7aaa130f647b0304f52f37a08ea4e3bafea282d77da5a3dd5d47fe4c66",
    "observations/N008.csv": "975d0a07bcf6b03117cb1a4b1b36ea7f103fa220fa215a63f58ae59a394d1a6d",
    "observations/N009.csv": "4cef24442e1485b4b662fd239e9acae5d7e36121304545b86d5a7b4ad0682e02",
    "observations/N010.csv": "d833bd7c0a9a80578ab5abe0df9a83de49c12f5410c5fb40e2c0a6e98eb151b2",
    "observations/N011.csv": "c757f515169c787937eab984deb85de5181802f462974ff277661878c8631ed3",
    "observations/N012.csv": "581530957f0e50d2766e721bc0ebd16c3529ac83029f93e1297a7accd1ca60f0",
    "observations/N013.csv": "d9dfb06e32394b05fc50a4a01f5fc078bc56d8d56c03a462bebf498ca0d0325c",
    "observations/N014.csv": "953c2c2117efaf20e316be083fabcf5f98730e27bab6fe4b0010fb165160f8f8",
    "observations/N015.csv": "166a6ef09b8980efc1a0a68668716cc23bcc47ceee26c0d59378fbfb950b2972",
}


def test_03_static_inputs_unmodified() -> None:
    """Seeded inputs must hash to the stored expected SHA256 values."""
    for rel, expected_hash in EXPECTED_SHA256.items():
        path = SEEDED_DATA / rel
        assert path.exists(), f"missing seeded input: {rel}"
        actual_hash = file_sha256(path)
        assert actual_hash == expected_hash, (
            f"{rel} digest changed: expected {expected_hash}, got {actual_hash}")


# ── Schema-shape tests on seeded data ─────────────────────────────────────

def test_05_top_level_keys_and_schema_version(tmp_path: Path) -> None:
    """Report must have exactly the documented top-level keys."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    assert set(actual) == TOP_KEYS
    assert actual["schema_version"] == 1


def test_06_summary_keys_and_severity_buckets(tmp_path: Path) -> None:
    """Summary must contain all documented keys; by_severity has all five."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    assert set(actual["summary"]) == SUMMARY_KEYS
    assert set(actual["summary"]["by_severity"]) == SEVERITIES
    total = sum(actual["summary"]["by_severity"].values())
    assert total == actual["summary"]["findings_count"]


def test_07_calibration_keys_and_sort_order(tmp_path: Path) -> None:
    """Each calibration record has the documented keys and sorted order."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    seen = []
    for row in actual["per_night_calibration"]:
        assert set(row) == CALIBRATION_KEYS
        assert row["status"] in CALIBRATION_STATUSES
        seen.append((row["night_id"], row["filter"]))
    assert seen == sorted(seen)


def test_08_lightcurve_keys_and_sort_order(tmp_path: Path) -> None:
    """Each lightcurve has the documented keys, sorted by (star_id, filter)."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    seen = []
    for row in actual["per_star_lightcurves"]:
        assert set(row) == LIGHTCURVE_KEYS
        assert row["status"] in LIGHTCURVE_STATUSES
        seen.append((row["star_id"], row["filter"]))
    assert seen == sorted(seen)


def test_09_finding_keys_and_sort_order(tmp_path: Path) -> None:
    """Each finding has the documented keys; findings sort by severity desc."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    for f in actual["findings"]:
        assert set(f) == FINDING_KEYS
        assert f["finding_type"] in FINDING_TYPES
        assert f["severity"] in SEVERITIES
    keys = [(-f["severity_rank"], f["finding_type"],
             f["night_id"] or "", f["filter"] or "",
             f["star_id"] or "", f["image_id"] or "")
            for f in actual["findings"]]
    assert keys == sorted(keys)


def test_10_six_decimal_precision(tmp_path: Path) -> None:
    """All non-null floats in calibration & lightcurves rounded to 6dp."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    for row in actual["per_night_calibration"]:
        for k in ["airmass_max", "airmass_min", "extinction_k",
                  "extinction_k_uncertainty", "residual_stddev",
                  "zero_point", "zero_point_uncertainty"]:
            v = row[k]
            if v is not None:
                assert v == round(v, 6), f"{row['night_id']}/{row['filter']}.{k}={v}"
    for row in actual["per_star_lightcurves"]:
        for k in ["amplitude_mag", "chi_squared_reduced",
                  "max_calibrated_mag", "mean_calibrated_mag",
                  "min_calibrated_mag", "stddev_calibrated_mag"]:
            v = row[k]
            if v is not None:
                assert v == round(v, 6), f"{row['star_id']}/{row['filter']}.{k}={v}"


def test_11_json_formatting(tmp_path: Path) -> None:
    """Output must be 2-space indented JSON with sorted keys & trailing newline."""
    run_tool(SEEDED_DATA, tmp_path / "actual.json")
    raw = (tmp_path / "actual.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    canonical = json.dumps(parsed, indent=2, sort_keys=True) + "\n"
    assert raw == canonical, "JSON formatting must match: 2-space, sorted, trailing newline"


# ── Calibration math ──────────────────────────────────────────────────────

def test_12_weighted_least_squares_two_point_recovery(tmp_path: Path) -> None:
    """A controlled fixture should recover an exact extinction slope/zp."""
    data = copy_fixture(tmp_path)
    # Replace observations of N001 entirely with controlled standards
    write_csv(data / "catalog" / "standards.csv", [
        ["star_id", "ra_deg", "dec_deg", "V_mag", "B_mag", "R_mag"],
        ["S1", 100.0, -10.0, "10.000", "10.500", "9.800"],
        ["S2", 100.1, -10.1, "12.000", "12.500", "11.800"],
        ["S3", 100.2, -10.2, "11.000", "11.500", "10.800"],
        ["S4", 100.3, -10.3, "13.000", "13.500", "12.800"],
    ])
    rows = [["image_id", "star_id", "filter", "time_utc", "airmass",
             "exposure_sec", "instrumental_mag", "mag_uncertainty"]]
    # Truth: V-band k=0.20, zp=-23.5; perfect, unit weights
    for sid, vmag in [("S1", 10.0), ("S2", 12.0), ("S3", 11.0), ("S4", 13.0)]:
        for j, X in enumerate([1.0, 1.5, 2.0]):
            m_inst = vmag + 0.2 * X + (-23.5)
            rows.append([f"IMGV-{sid}-{j}", sid, "V",
                         "2025-09-12T00:00:00Z", X, 30,
                         f"{m_inst:.6f}", "0.01"])
    # also B and R (just enough to build the 30 records)
    for sid, bmag in [("S1", 10.5), ("S2", 12.5), ("S3", 11.5), ("S4", 13.5)]:
        for j, X in enumerate([1.0, 1.5, 2.0]):
            m_inst = bmag + 0.3 * X + (-23.6)
            rows.append([f"IMGB-{sid}-{j}", sid, "B",
                         "2025-09-12T00:00:00Z", X, 30,
                         f"{m_inst:.6f}", "0.01"])
    for sid, rmag in [("S1", 9.8), ("S2", 11.8), ("S3", 10.8), ("S4", 12.8)]:
        for j, X in enumerate([1.0, 1.5, 2.0]):
            m_inst = rmag + 0.1 * X + (-23.4)
            rows.append([f"IMGR-{sid}-{j}", sid, "R",
                         "2025-09-12T00:00:00Z", X, 30,
                         f"{m_inst:.6f}", "0.01"])
    write_csv(data / "observations" / "N001.csv", rows)
    # Strip the program star list to avoid contamination
    write_csv(data / "catalog" / "programs.csv", [
        ["star_id", "ra_deg", "dec_deg", "target_type"],
    ])
    # Drop other nights to keep this trivial
    manifest = json.loads((data / "manifest.json").read_text())
    manifest["nights"] = [manifest["nights"][0]]
    (data / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Empty exclusions
    (data / "exclusions.json").write_text(json.dumps({
        "excluded_nights": [], "excluded_filters_per_night": [],
        "excluded_stars": [], "excluded_observations": [],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Zero out color terms so the controlled truth values are recovered exactly
    instr = json.loads((data / "instrument.json").read_text())
    instr["color_terms"] = {f: 0.0 for f in instr["color_terms"]}
    (data / "instrument.json").write_text(
        json.dumps(instr, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    actual = run_tool(data, tmp_path / "actual.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    v = cal[("N001", "V")]
    b = cal[("N001", "B")]
    r = cal[("N001", "R")]
    assert v["status"] == "calibrated"
    assert math.isclose(v["extinction_k"], 0.2, abs_tol=1e-6), v
    assert math.isclose(v["zero_point"], -23.5, abs_tol=1e-6), v
    assert math.isclose(b["extinction_k"], 0.3, abs_tol=1e-6), b
    assert math.isclose(b["zero_point"], -23.6, abs_tol=1e-6), b
    assert math.isclose(r["extinction_k"], 0.1, abs_tol=1e-6), r
    assert math.isclose(r["zero_point"], -23.4, abs_tol=1e-6), r


def test_14_residual_stddev_is_weighted_population(tmp_path: Path) -> None:
    """Residual stddev uses Σw·r² / Σw, not the unweighted population form."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for c in actual["per_night_calibration"]:
        ec = next(x for x in exp["per_night_calibration"]
                  if x["night_id"] == c["night_id"]
                  and x["filter"] == c["filter"])
        assert c["residual_stddev"] == ec["residual_stddev"]


# ── Outlier rejection ─────────────────────────────────────────────────────

def test_15_outlier_rejection_single_pass(tmp_path: Path) -> None:
    """A single MAD pass flags exactly the injected outliers; not iterative."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for c in actual["per_night_calibration"]:
        ec = next(x for x in exp["per_night_calibration"]
                  if x["night_id"] == c["night_id"]
                  and x["filter"] == c["filter"])
        assert c["n_outliers_flagged"] == ec["n_outliers_flagged"]


def test_16_outlier_finding_per_flag(tmp_path: Path) -> None:
    """Every flagged outlier must produce exactly one outlier_observation."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    flagged = sum(c["n_outliers_flagged"]
                  for c in actual["per_night_calibration"])
    outlier_findings = [f for f in actual["findings"]
                        if f["finding_type"] == "outlier_observation"]
    assert len(outlier_findings) == flagged


def test_17_outlier_rollback_when_too_few_remain(tmp_path: Path) -> None:
    """If MAD rejection would drop below min_standards, no rejection happens."""
    data = copy_fixture(tmp_path)
    # Build a tight set of 4 standards, one a clear outlier; min_standards=4
    write_csv(data / "catalog" / "standards.csv", [
        ["star_id", "ra_deg", "dec_deg", "V_mag", "B_mag", "R_mag"],
        ["S1", 100, -10, "10.000", "10.500", "9.800"],
        ["S2", 100, -10, "11.000", "11.500", "10.800"],
        ["S3", 100, -10, "12.000", "12.500", "11.800"],
        ["S4", 100, -10, "13.000", "13.500", "12.800"],
    ])
    write_csv(data / "catalog" / "programs.csv", [
        ["star_id", "ra_deg", "dec_deg", "target_type"],
    ])
    rows = [["image_id", "star_id", "filter", "time_utc", "airmass",
             "exposure_sec", "instrumental_mag", "mag_uncertainty"]]
    truth_k, truth_zp = 0.2, -23.5
    for sid, mag in [("S1", 10.0), ("S2", 11.0), ("S3", 12.0), ("S4", 13.0)]:
        X = 1.0 + 0.5 * (hash(sid) % 4) / 4.0
        rows.append([f"V-{sid}", sid, "V", "2025-09-12T00:00:00Z",
                     X, 30, f"{mag + truth_k * X + truth_zp:.6f}", "0.01"])
    # Force S4 to be a 5σ outlier (large delta) — single huge spike
    for r in rows[1:]:
        if r[1] == "S4":
            old_mag = float(r[6])
            r[6] = f"{old_mag + 2.0:.6f}"
    # Pad with B/R for completeness (won't matter)
    write_csv(data / "observations" / "N001.csv", rows)
    manifest = json.loads((data / "manifest.json").read_text())
    manifest["nights"] = [manifest["nights"][0]]
    (data / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (data / "exclusions.json").write_text(json.dumps({
        "excluded_nights": [], "excluded_filters_per_night": [],
        "excluded_stars": [], "excluded_observations": [],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    actual = run_tool(data, tmp_path / "actual.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    v = cal[("N001", "V")]
    # Must roll back to no rejection because removing S4 leaves only 3 < 4
    assert v["n_outliers_flagged"] == 0, v


# ── Excluded entries ──────────────────────────────────────────────────────

def test_18_excluded_night_yields_excluded_status(tmp_path: Path) -> None:
    """A listed night gets excluded_night status on every filter."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    excl = json.loads((SEEDED_DATA / "exclusions.json").read_text())
    instr = json.loads((SEEDED_DATA / "instrument.json").read_text())
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    for nid in excl["excluded_nights"]:
        for filt in instr["filters"]:
            assert (nid, filt) in cal, f"missing pair {nid}/{filt}"
            assert cal[(nid, filt)]["status"] == "excluded_night", (nid, filt)


def test_19_excluded_filter_per_night(tmp_path: Path) -> None:
    """A filter listed under a non-excluded night gets excluded_filter."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    excl = json.loads((SEEDED_DATA / "exclusions.json").read_text())
    excluded_nights = set(excl.get("excluded_nights", []))
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    for rec in excl["excluded_filters_per_night"]:
        if rec["night_id"] in excluded_nights:
            continue
        for filt in rec["filters"]:
            key = (rec["night_id"], filt)
            assert key in cal, key
            assert cal[key]["status"] == "excluded_filter", key


def test_20_excluded_star_skips_lightcurve(tmp_path: Path) -> None:
    """Stars in excluded_stars never appear as lightcurves and produce no fits."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    excl = json.loads((SEEDED_DATA / "exclusions.json").read_text())
    star_ids_in_lc = {row["star_id"] for row in actual["per_star_lightcurves"]}
    for sid in excl["excluded_stars"]:
        assert sid not in star_ids_in_lc, sid
    # Excluded stars must produce one excluded_star finding each
    excluded_findings = [f for f in actual["findings"]
                         if f["finding_type"] == "excluded_star"]
    assert {f["star_id"] for f in excluded_findings} == set(
        excl["excluded_stars"])


def test_21_excluded_observation_drops_row(tmp_path: Path) -> None:
    """A listed image_id never contributes to fits or lightcurves."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    excl = json.loads((SEEDED_DATA / "exclusions.json").read_text())
    excluded_findings = [f for f in actual["findings"]
                         if f["finding_type"] == "excluded_observation"]
    assert {f["image_id"] for f in excluded_findings} == set(
        excl["excluded_observations"])


# ── Insufficient standards ────────────────────────────────────────────────

def test_22_insufficient_standards_zero_numeric(tmp_path: Path) -> None:
    """insufficient_standards rows have zero slope/zp and matching finding."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    insuf = [c for c in actual["per_night_calibration"]
             if c["status"] == "insufficient_standards"]
    assert insuf, "fixture should have at least one insufficient_standards row"
    for c in insuf:
        assert c["extinction_k"] == 0.0, c
        assert c["zero_point"] == 0.0, c
        assert c["residual_stddev"] == 0.0, c
        assert c["n_outliers_flagged"] == 0, c
        assert c["n_program_observations"] == 0, c
    # Each must be paired with a finding
    findings = [(f["night_id"], f["filter"]) for f in actual["findings"]
                if f["finding_type"] == "insufficient_standards"]
    pairs = [(c["night_id"], c["filter"]) for c in insuf]
    assert sorted(pairs) == sorted(findings)


# ── Lightcurves ───────────────────────────────────────────────────────────

def test_23_lightcurves_skip_excluded_pairs(tmp_path: Path) -> None:
    """An excluded (night, filter) pair contributes no observations to LCs."""
    data = copy_fixture(tmp_path)
    actual = run_tool(data, tmp_path / "actual.json")
    excl = json.loads((data / "exclusions.json").read_text())
    instr = json.loads((data / "instrument.json").read_text())
    valid_filters = set(instr["filters"])
    policy = json.loads((data / "policy.json").read_text())
    max_airmass = float(policy.get("max_airmass", 99.0))
    excluded_filter_pairs = {
        (rec["night_id"], filt)
        for rec in excl["excluded_filters_per_night"]
        for filt in rec["filters"]
    }
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    manifest = json.loads((data / "manifest.json").read_text())
    excluded_nights = set(excl["excluded_nights"])
    excluded_obs = set(excl["excluded_observations"])
    excluded_stars = set(excl["excluded_stars"])
    obs_count = {}
    for entry in manifest["nights"]:
        nid = entry["night_id"]
        if nid in excluded_nights:
            continue
        with (data / "observations" / entry["observations_file"]).open() as fh:
            for row in csv.DictReader(fh):
                if row["filter"] not in valid_filters:
                    continue
                if float(row["airmass"]) > max_airmass:
                    continue
                if row["star_id"] in excluded_stars:
                    continue
                if row["image_id"] in excluded_obs:
                    continue
                if (nid, row["filter"]) in excluded_filter_pairs:
                    continue
                pair_status = cal[(nid, row["filter"])]["status"]
                if pair_status != "calibrated":
                    continue
                obs_count[(row["star_id"], row["filter"])] = (
                    obs_count.get((row["star_id"], row["filter"]), 0) + 1)
    for row in actual["per_star_lightcurves"]:
        key = (row["star_id"], row["filter"])
        assert row["n_observations"] == obs_count.get(key, 0), key


def test_24_variable_star_chi2_threshold(tmp_path: Path) -> None:
    """Variable lightcurves match the chi-squared rule and emit findings."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    pol = json.loads((SEEDED_DATA / "policy.json").read_text())
    thresh = pol["variability_chi2_threshold"]
    min_obs = pol["min_observations_per_lightcurve"]
    variable_pairs = set()
    for row in actual["per_star_lightcurves"]:
        if row["is_variable"]:
            assert row["status"] == "calibrated"
            assert row["chi_squared_reduced"] is not None
            assert row["chi_squared_reduced"] > thresh, row
            assert row["n_observations"] >= min_obs
            variable_pairs.add((row["star_id"], row["filter"]))
    assert variable_pairs, (
        "seeded fixture must contain at least one variable lightcurve")
    finding_pairs = {(f["star_id"], f["filter"]) for f in actual["findings"]
                     if f["finding_type"] == "variable_star_detected"}
    assert finding_pairs == variable_pairs, (
        "variable_star_detected findings must mirror is_variable lightcurves")


def test_25_chi_squared_uses_combined_uncertainty(tmp_path: Path) -> None:
    """χ² is computed with the combined calibrated-magnitude uncertainty."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for actual_row in actual["per_star_lightcurves"]:
        exp_row = next(r for r in exp["per_star_lightcurves"]
                       if r["star_id"] == actual_row["star_id"]
                       and r["filter"] == actual_row["filter"])
        assert actual_row["chi_squared_reduced"] == exp_row["chi_squared_reduced"]


def test_26_program_star_no_data_finding(tmp_path: Path) -> None:
    """Program stars with zero observations in a filter produce no_data."""
    data = copy_fixture(tmp_path)
    # Inject a program star with no observations whatsoever
    progs = list(csv.reader((data / "catalog" / "programs.csv").open()))
    progs.append(["NOOBS_STAR", "200.0", "10.0", "constant"])
    write_csv(data / "catalog" / "programs.csv", progs)
    actual = run_tool(data, tmp_path / "actual.json")
    nodata = [r for r in actual["per_star_lightcurves"]
              if r["star_id"] == "NOOBS_STAR"]
    assert nodata, "NOOBS_STAR should appear with status no_data"
    for r in nodata:
        assert r["status"] == "no_data"
        assert r["chi_squared_reduced"] is None
        assert r["mean_calibrated_mag"] is None


# ── Threshold-driven findings ─────────────────────────────────────────────

def test_27_negative_extinction_finding(tmp_path: Path) -> None:
    """negative_extinction findings exactly cover sub-threshold calibrated pairs."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    pol = json.loads((SEEDED_DATA / "policy.json").read_text())
    thresh = pol["negative_extinction_threshold"]
    finding_pairs = {(f["night_id"], f["filter"]) for f in actual["findings"]
                     if f["finding_type"] == "negative_extinction"}
    expected_pairs = {(c["night_id"], c["filter"])
                      for c in actual["per_night_calibration"]
                      if c["status"] == "calibrated"
                      and c["extinction_k"] < thresh}
    assert expected_pairs, (
        "seeded fixture must contain at least one negative_extinction case")
    assert finding_pairs == expected_pairs, (
        "negative_extinction findings must mirror sub-threshold calibrated pairs")


def test_28_bad_night_residuals_finding(tmp_path: Path) -> None:
    """bad_night_residuals findings exactly cover over-threshold calibrated pairs."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    pol = json.loads((SEEDED_DATA / "policy.json").read_text())
    thresh = pol["bad_night_residual_stddev"]
    finding_pairs = {(f["night_id"], f["filter"]) for f in actual["findings"]
                     if f["finding_type"] == "bad_night_residuals"}
    expected_pairs = {(c["night_id"], c["filter"])
                      for c in actual["per_night_calibration"]
                      if c["status"] == "calibrated"
                      and c["residual_stddev"] > thresh}
    assert expected_pairs, (
        "seeded fixture must contain at least one bad_night_residuals case")
    assert finding_pairs == expected_pairs, (
        "bad_night_residuals findings must mirror over-threshold calibrated pairs")


def test_29_large_zp_uncertainty_finding(tmp_path: Path) -> None:
    """large_zero_point_uncertainty findings exactly cover over-threshold pairs."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    pol = json.loads((SEEDED_DATA / "policy.json").read_text())
    thresh = pol["large_zero_point_uncertainty"]
    finding_pairs = {(f["night_id"], f["filter"]) for f in actual["findings"]
                     if f["finding_type"] == "large_zero_point_uncertainty"}
    expected_pairs = {(c["night_id"], c["filter"])
                      for c in actual["per_night_calibration"]
                      if c["status"] == "calibrated"
                      and c["zero_point_uncertainty"] > thresh}
    assert expected_pairs, (
        "seeded fixture must contain at least one large_zero_point_uncertainty case")
    assert finding_pairs == expected_pairs, (
        "large_zero_point_uncertainty findings must mirror over-threshold pairs")


def test_30_severity_rank_consistency(tmp_path: Path) -> None:
    """Each finding's severity_rank matches policy.severity_ranks[severity]."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    pol = json.loads((SEEDED_DATA / "policy.json").read_text())
    ranks = pol["severity_ranks"]
    for f in actual["findings"]:
        assert f["severity_rank"] == ranks[f["severity"]], f


# ── Summary counts ────────────────────────────────────────────────────────

def test_31_summary_counts_consistency(tmp_path: Path) -> None:
    """summary counts match the lengths of the corresponding lists."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    s = actual["summary"]
    assert s["findings_count"] == len(actual["findings"])
    assert s["lightcurves_count"] == len(actual["per_star_lightcurves"])
    cal = actual["per_night_calibration"]
    assert s["calibrated_pairs"] == sum(1 for c in cal
                                        if c["status"] == "calibrated")
    assert s["insufficient_pairs"] == sum(1 for c in cal
                                          if c["status"] == "insufficient_standards")
    assert s["flagged_outliers"] == sum(c["n_outliers_flagged"] for c in cal
                                       if c["status"] == "calibrated")
    assert s["used_standard_observations"] == sum(c["n_standards_used"]
                                                  for c in cal
                                                  if c["status"] == "calibrated")
    assert s["used_program_observations"] == sum(c["n_program_observations"]
                                                 for c in cal
                                                 if c["status"] == "calibrated")
    assert s["variable_stars"] == sum(1 for r in actual["per_star_lightcurves"]
                                      if r["is_variable"])


def test_32_total_observations_includes_excluded(tmp_path: Path) -> None:
    """summary.total_observations counts every observation row, period."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    manifest = json.loads((SEEDED_DATA / "manifest.json").read_text())
    total = 0
    for entry in manifest["nights"]:
        with (SEEDED_DATA / "observations" / entry["observations_file"]).open() as fh:
            total += sum(1 for _ in csv.DictReader(fh))
    assert actual["summary"]["total_observations"] == total


def test_33_n_total_observations_per_pair(tmp_path: Path) -> None:
    """Per (night, filter), n_total_observations counts every row in that filter."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    manifest = json.loads((SEEDED_DATA / "manifest.json").read_text())
    raw = {(entry["night_id"], filt): 0
           for entry in manifest["nights"]
           for filt in json.loads(
               (SEEDED_DATA / "instrument.json").read_text())["filters"]}
    for entry in manifest["nights"]:
        with (SEEDED_DATA / "observations" / entry["observations_file"]).open() as fh:
            for row in csv.DictReader(fh):
                if (entry["night_id"], row["filter"]) in raw:
                    raw[(entry["night_id"], row["filter"])] += 1
    for c in actual["per_night_calibration"]:
        assert c["n_total_observations"] == raw[(c["night_id"], c["filter"])]


def test_34_calibrated_uncertainty_propagation(tmp_path: Path) -> None:
    """Calibrated uncertainties combine σ_inst, σ_zp, and X·σ_k."""
    # Indirect check via reproducibility - actual stddev/mean depend on σ_cal
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for arow in actual["per_star_lightcurves"]:
        erow = next(r for r in exp["per_star_lightcurves"]
                    if r["star_id"] == arow["star_id"]
                    and r["filter"] == arow["filter"])
        assert arow["mean_calibrated_mag"] == erow["mean_calibrated_mag"]
        assert arow["stddev_calibrated_mag"] == erow["stddev_calibrated_mag"]


# ── Determinism & reproducibility ────────────────────────────────────────

def test_35_two_runs_byte_identical(tmp_path: Path) -> None:
    """Re-running the tool on the same inputs is byte-identical."""
    out1 = tmp_path / "r1.json"
    out2 = tmp_path / "r2.json"
    run_tool(SEEDED_DATA, out1)
    run_tool(SEEDED_DATA, out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_36_data_directory_unmodified(tmp_path: Path) -> None:
    """The tool must not mutate any file under /app/data."""
    snap = {}
    for p in SEEDED_DATA.rglob("*"):
        if p.is_file():
            snap[str(p.relative_to(SEEDED_DATA))] = file_sha256(p)
    run_tool(SEEDED_DATA, tmp_path / "actual.json")
    for rel, h in snap.items():
        assert file_sha256(SEEDED_DATA / rel) == h, (
            f"data file mutated by tool: {rel}")


# ── Degenerate airmass range ──────────────────────────────────────────────

def test_37_degenerate_airmass_range_detection(tmp_path: Path) -> None:
    """N012/R has all standards at airmass=1.5 → degenerate_airmass_range."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    assert ("N012", "R") in cal
    assert cal[("N012", "R")]["status"] == "degenerate_airmass_range"
    assert cal[("N012", "R")]["extinction_k"] == 0.0
    assert cal[("N012", "R")]["zero_point"] == 0.0
    assert cal[("N012", "R")]["residual_stddev"] == 0.0
    assert cal[("N012", "R")]["n_outliers_flagged"] == 0


def test_38_degenerate_airmass_finding(tmp_path: Path) -> None:
    """A degenerate_airmass_range finding must be emitted for N012/R."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    matches = [f for f in actual["findings"]
               if f["finding_type"] == "degenerate_airmass_range"]
    assert len(matches) >= 1
    n012r = [f for f in matches if f["night_id"] == "N012" and f["filter"] == "R"]
    assert len(n012r) == 1
    assert n012r[0]["severity"] == "high"


# ── Negative extinction ──────────────────────────────────────────────────

def test_39_negative_extinction_new_night(tmp_path: Path) -> None:
    """N015/V has k < negative_extinction_threshold → negative_extinction."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    ec = {(c["night_id"], c["filter"]): c
          for c in exp["per_night_calibration"]}
    assert cal[("N015", "V")]["extinction_k"] == ec[("N015", "V")]["extinction_k"]
    pol = json.loads((SEEDED_DATA / "policy.json").read_text())
    assert cal[("N015", "V")]["extinction_k"] < pol["negative_extinction_threshold"]


# ── Bad night residuals ──────────────────────────────────────────────────

def test_40_bad_night_residuals_new_nights(tmp_path: Path) -> None:
    """N013/V and N014/B have residual_stddev > threshold → bad_night_residuals."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    findings = [f for f in actual["findings"]
                if f["finding_type"] == "bad_night_residuals"]
    pairs = {(f["night_id"], f["filter"]) for f in findings}
    assert ("N013", "V") in pairs, "N013/V should trigger bad_night_residuals"
    assert ("N014", "B") in pairs, "N014/B should trigger bad_night_residuals"


def test_41_n013v_sigma_mad_zero_no_rejection(tmp_path: Path) -> None:
    """N013/V has σ_MAD≈0 (outlier dominates) → no rejection pass, n_outliers=0."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    assert cal[("N013", "V")]["n_outliers_flagged"] == 0
    assert cal[("N013", "V")]["status"] == "calibrated"


# ── Excluded filter on excluded night ────────────────────────────────────

def test_42_excluded_filter_on_excluded_night(tmp_path: Path) -> None:
    """N005/B is in excluded_filters_per_night AND N005 is excluded_night.
    Status should be excluded_night (night exclusion takes precedence)."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    assert cal[("N005", "B")]["status"] == "excluded_night"
    assert cal[("N005", "V")]["status"] == "excluded_night"
    assert cal[("N005", "R")]["status"] == "excluded_night"


def test_43_excluded_filter_finding_still_emitted(tmp_path: Path) -> None:
    """An excluded_filter finding for N005/B must be emitted even though
    N005 is also in excluded_nights."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    ef = [f for f in actual["findings"]
          if f["finding_type"] == "excluded_filter"]
    pairs = {(f["night_id"], f["filter"]) for f in ef}
    assert ("N005", "B") in pairs, (
        "excluded_filter finding must be emitted for N005/B "
        "even though N005 is in excluded_nights")
    assert ("N003", "R") in pairs, "excluded_filter for N003/R"
    assert ("N007", "B") in pairs, "excluded_filter for N007/B"
    assert len(ef) == 3, f"expected 3 excluded_filter findings, got {len(ef)}"


# ── Excluded observations from new nights ────────────────────────────────

def test_44_excluded_observations_new_nights(tmp_path: Path) -> None:
    """N011-IMG-0005 and N013-IMG-0008 must appear as excluded_observation findings."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    eo = [f for f in actual["findings"]
          if f["finding_type"] == "excluded_observation"]
    ids = {f["image_id"] for f in eo}
    assert "N011-IMG-0005" in ids
    assert "N013-IMG-0008" in ids
    assert len(eo) == 4


# ── N003/R exclusion ─────────────────────────────────────────────────────

def test_45_n003r_excluded_filter(tmp_path: Path) -> None:
    """N003/R is now an excluded_filter. It must have status excluded_filter
    and zero numeric fields."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    assert cal[("N003", "R")]["status"] == "excluded_filter"
    assert cal[("N003", "R")]["extinction_k"] == 0.0
    assert cal[("N003", "R")]["zero_point"] == 0.0
    assert cal[("N003", "R")]["n_standards_used"] == 0


def test_46_n003r_n_total_observations_still_counted(tmp_path: Path) -> None:
    """Even excluded_filter rows must count n_total_observations."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    assert cal[("N003", "R")]["n_total_observations"] > 0, (
        "excluded_filter rows must still report n_total_observations")


# ── Calibration row count ────────────────────────────────────────────────

def test_47_calibration_row_count(tmp_path: Path) -> None:
    """Total calibration rows = total_nights × len(filters) = 15 × 3 = 45."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    assert len(actual["per_night_calibration"]) == 45


# ── Full lightcurve match against oracle ─────────────────────────────────

def test_49_full_lightcurve_match(tmp_path: Path) -> None:
    """Every lightcurve row must match the oracle exactly."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for er in exp["per_star_lightcurves"]:
        ar = next(r for r in actual["per_star_lightcurves"]
                  if r["star_id"] == er["star_id"]
                  and r["filter"] == er["filter"])
        for key in ("status", "n_observations", "n_nights",
                    "is_variable", "mean_calibrated_mag",
                    "stddev_calibrated_mag", "min_calibrated_mag",
                    "max_calibrated_mag", "amplitude_mag",
                    "chi_squared_reduced"):
            assert ar[key] == er[key], (
                f"{er['star_id']}/{er['filter']}.{key}: "
                f"actual={ar[key]}, expected={er[key]}")


# ── Full findings match against oracle ───────────────────────────────────

def test_50_findings_count_match(tmp_path: Path) -> None:
    """Finding count must match oracle."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    assert len(actual["findings"]) == len(exp["findings"]), (
        f"findings count: actual={len(actual['findings'])}, "
        f"expected={len(exp['findings'])}")


def test_51_findings_type_counts_match(tmp_path: Path) -> None:
    """Each finding_type count must match oracle."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    from collections import Counter
    actual_types = Counter(f["finding_type"] for f in actual["findings"])
    exp_types = Counter(f["finding_type"] for f in exp["findings"])
    assert actual_types == exp_types, (
        f"finding type mismatch:\nactual={dict(actual_types)}\n"
        f"expected={dict(exp_types)}")


# ── N011 calibration specifics ───────────────────────────────────────────

def test_52_n011_calibration_values(tmp_path: Path) -> None:
    """N011 is a well-behaved night; extinction should be close to truth."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    ecal = {(c["night_id"], c["filter"]): c
            for c in exp["per_night_calibration"]}
    for filt in ["B", "V", "R"]:
        ac = cal[("N011", filt)]
        ec = ecal[("N011", filt)]
        assert ac["status"] == "calibrated"
        assert ac["extinction_k"] == ec["extinction_k"]
        assert ac["zero_point"] == ec["zero_point"]


# ── N012 degenerate only in R ────────────────────────────────────────────

def test_53_n012_b_v_calibrated_r_degenerate(tmp_path: Path) -> None:
    """N012: B and V are normally calibrated; only R is degenerate."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    assert cal[("N012", "B")]["status"] == "calibrated"
    assert cal[("N012", "V")]["status"] == "calibrated"
    assert cal[("N012", "R")]["status"] == "degenerate_airmass_range"


# ── Custom fixture: degenerate airmass in isolation ──────────────────────

def test_54_custom_degenerate_airmass(tmp_path: Path) -> None:
    """Custom fixture: all standards at same airmass → degenerate_airmass_range."""
    data = copy_fixture(tmp_path)
    write_csv(data / "catalog" / "standards.csv", [
        ["star_id", "ra_deg", "dec_deg", "V_mag", "B_mag", "R_mag"],
        ["S1", 100, -10, "10.000", "10.500", "9.800"],
        ["S2", 100, -10, "12.000", "12.500", "11.800"],
        ["S3", 100, -10, "11.000", "11.500", "10.800"],
        ["S4", 100, -10, "13.000", "13.500", "12.800"],
        ["S5", 100, -10, "14.000", "14.500", "13.800"],
    ])
    write_csv(data / "catalog" / "programs.csv", [
        ["star_id", "ra_deg", "dec_deg", "target_type"],
    ])
    rows = [["image_id", "star_id", "filter", "time_utc", "airmass",
             "exposure_sec", "instrumental_mag", "mag_uncertainty"]]
    for sid, vmag in [("S1", 10.0), ("S2", 12.0), ("S3", 11.0),
                      ("S4", 13.0), ("S5", 14.0)]:
        rows.append([f"V-{sid}", sid, "V", "2025-09-12T00:00:00Z",
                     1.5, 30, f"{vmag + 0.2 * 1.5 - 23.5:.6f}", "0.01"])
    write_csv(data / "observations" / "N001.csv", rows)
    manifest = json.loads((data / "manifest.json").read_text())
    manifest["nights"] = [manifest["nights"][0]]
    (data / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (data / "exclusions.json").write_text(json.dumps({
        "excluded_nights": [], "excluded_filters_per_night": [],
        "excluded_stars": [], "excluded_observations": [],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    actual = run_tool(data, tmp_path / "actual.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    assert cal[("N001", "V")]["status"] == "degenerate_airmass_range"
    assert cal[("N001", "V")]["airmass_min"] == 1.5
    assert cal[("N001", "V")]["airmass_max"] == 1.5


# ── Custom fixture: σ_MAD = 0 (identical residuals) ─────────────────────

def test_55_sigma_mad_zero_skips_rejection(tmp_path: Path) -> None:
    """When all residuals are identical (σ_MAD=0), no rejection occurs."""
    data = copy_fixture(tmp_path)
    write_csv(data / "catalog" / "standards.csv", [
        ["star_id", "ra_deg", "dec_deg", "V_mag", "B_mag", "R_mag"],
        ["S1", 100, -10, "10.000", "10.500", "9.800"],
        ["S2", 100, -10, "12.000", "12.500", "11.800"],
        ["S3", 100, -10, "11.000", "11.500", "10.800"],
        ["S4", 100, -10, "13.000", "13.500", "12.800"],
    ])
    write_csv(data / "catalog" / "programs.csv", [
        ["star_id", "ra_deg", "dec_deg", "target_type"],
    ])
    k, zp = 0.2, -23.5
    rows = [["image_id", "star_id", "filter", "time_utc", "airmass",
             "exposure_sec", "instrumental_mag", "mag_uncertainty"]]
    for sid, vmag in [("S1", 10.0), ("S2", 12.0), ("S3", 11.0), ("S4", 13.0)]:
        for j, X in enumerate([1.0, 1.5, 2.0]):
            m_inst = vmag + k * X + zp
            rows.append([f"V-{sid}-{j}", sid, "V",
                         "2025-09-12T00:00:00Z", X, 30,
                         f"{m_inst:.6f}", "0.01"])
    write_csv(data / "observations" / "N001.csv", rows)
    manifest = json.loads((data / "manifest.json").read_text())
    manifest["nights"] = [manifest["nights"][0]]
    (data / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (data / "exclusions.json").write_text(json.dumps({
        "excluded_nights": [], "excluded_filters_per_night": [],
        "excluded_stars": [], "excluded_observations": [],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    actual = run_tool(data, tmp_path / "actual.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    v = cal[("N001", "V")]
    assert v["n_outliers_flagged"] == 0, (
        "σ_MAD=0 means no outliers should be flagged")
    assert v["residual_stddev"] == 0.0, (
        "perfect fit should have zero residual stddev")


# ── Custom fixture: excluded_filter on excluded_night ────────────────────

def test_56_excluded_filter_on_excluded_night_custom(tmp_path: Path) -> None:
    """An excluded_filter on an excluded_night: status must be excluded_night,
    and BOTH findings (excluded_night + excluded_filter) are emitted."""
    data = copy_fixture(tmp_path)
    (data / "exclusions.json").write_text(json.dumps({
        "excluded_nights": ["N001"],
        "excluded_filters_per_night": [
            {"night_id": "N001", "filters": ["V"]}
        ],
        "excluded_stars": [],
        "excluded_observations": [],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = json.loads((data / "manifest.json").read_text())
    manifest["nights"] = [manifest["nights"][0]]
    (data / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    actual = run_tool(data, tmp_path / "actual.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    for filt in ["B", "V", "R"]:
        assert cal[("N001", filt)]["status"] == "excluded_night", (
            f"N001/{filt} must be excluded_night (night exclusion overrides)")
    en = [f for f in actual["findings"] if f["finding_type"] == "excluded_night"]
    ef = [f for f in actual["findings"] if f["finding_type"] == "excluded_filter"]
    assert len(en) == 1 and en[0]["night_id"] == "N001"
    assert len(ef) == 1 and ef[0]["night_id"] == "N001" and ef[0]["filter"] == "V"


# ── Custom fixture: excluded observation + excluded star overlap ─────────

def test_57_excluded_obs_for_excluded_star(tmp_path: Path) -> None:
    """An excluded_observation for a row belonging to an excluded_star
    must still emit both findings (excluded_observation + excluded_star)."""
    data = copy_fixture(tmp_path)
    write_csv(data / "catalog" / "standards.csv", [
        ["star_id", "ra_deg", "dec_deg", "V_mag", "B_mag", "R_mag"],
        ["S1", 100, -10, "10.000", "10.500", "9.800"],
        ["S2", 100, -10, "12.000", "12.500", "11.800"],
        ["S3", 100, -10, "11.000", "11.500", "10.800"],
        ["S4", 100, -10, "13.000", "13.500", "12.800"],
        ["BADSTAR", 100, -10, "11.500", "12.000", "11.000"],
    ])
    write_csv(data / "catalog" / "programs.csv", [
        ["star_id", "ra_deg", "dec_deg", "target_type"],
    ])
    rows = [["image_id", "star_id", "filter", "time_utc", "airmass",
             "exposure_sec", "instrumental_mag", "mag_uncertainty"]]
    for sid, vmag in [("S1", 10.0), ("S2", 12.0), ("S3", 11.0), ("S4", 13.0)]:
        for j, X in enumerate([1.0, 1.5, 2.0]):
            rows.append([f"V-{sid}-{j}", sid, "V",
                         "2025-09-12T00:00:00Z", X, 30,
                         f"{vmag + 0.2 * X - 23.5:.6f}", "0.01"])
    rows.append(["BAD-IMG", "BADSTAR", "V", "2025-09-12T00:00:00Z",
                 1.5, 30, "-11.400000", "0.01"])
    write_csv(data / "observations" / "N001.csv", rows)
    manifest = json.loads((data / "manifest.json").read_text())
    manifest["nights"] = [manifest["nights"][0]]
    (data / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (data / "exclusions.json").write_text(json.dumps({
        "excluded_nights": [],
        "excluded_filters_per_night": [],
        "excluded_stars": ["BADSTAR"],
        "excluded_observations": ["BAD-IMG"],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    actual = run_tool(data, tmp_path / "actual.json")
    es = [f for f in actual["findings"] if f["finding_type"] == "excluded_star"]
    eo = [f for f in actual["findings"] if f["finding_type"] == "excluded_observation"]
    assert any(f["star_id"] == "BADSTAR" for f in es), "excluded_star for BADSTAR"
    assert any(f["image_id"] == "BAD-IMG" for f in eo), "excluded_observation for BAD-IMG"


# ── Uncertainty floor test ───────────────────────────────────────────────

def test_58_uncertainty_floor_applied(tmp_path: Path) -> None:
    """Observations with uncertainty below floor must use the floor value."""
    data = copy_fixture(tmp_path)
    write_csv(data / "catalog" / "standards.csv", [
        ["star_id", "ra_deg", "dec_deg", "V_mag", "B_mag", "R_mag"],
        ["S1", 100, -10, "10.000", "10.500", "9.800"],
        ["S2", 100, -10, "12.000", "12.500", "11.800"],
        ["S3", 100, -10, "11.000", "11.500", "10.800"],
        ["S4", 100, -10, "13.000", "13.500", "12.800"],
    ])
    write_csv(data / "catalog" / "programs.csv", [
        ["star_id", "ra_deg", "dec_deg", "target_type"],
        ["P1", 100, -10, "constant"],
    ])
    k, zp = 0.2, -23.5
    rows = [["image_id", "star_id", "filter", "time_utc", "airmass",
             "exposure_sec", "instrumental_mag", "mag_uncertainty"]]
    for sid, vmag in [("S1", 10.0), ("S2", 12.0), ("S3", 11.0), ("S4", 13.0)]:
        for j, X in enumerate([1.0, 1.5, 2.0]):
            m_inst = vmag + k * X + zp
            # S1 observations have uncertainty BELOW floor (0.001 < 0.005)
            unc = "0.001" if sid == "S1" else "0.01"
            rows.append([f"V-{sid}-{j}", sid, "V",
                         "2025-09-12T00:00:00Z", X, 30,
                         f"{m_inst:.6f}", unc])
    # Add program star
    rows.append(["V-P1-0", "P1", "V", "2025-09-12T00:00:00Z",
                 1.5, 30, "-12.000000", "0.001"])
    write_csv(data / "observations" / "N001.csv", rows)
    manifest = json.loads((data / "manifest.json").read_text())
    manifest["nights"] = [manifest["nights"][0]]
    (data / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (data / "exclusions.json").write_text(json.dumps({
        "excluded_nights": [], "excluded_filters_per_night": [],
        "excluded_stars": [], "excluded_observations": [],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    actual = run_tool(data, tmp_path / "actual.json")
    exp = expected(data, tmp_path / "expected.json")
    a_cal = {(c["night_id"], c["filter"]): c
             for c in actual["per_night_calibration"]}
    e_cal = {(c["night_id"], c["filter"]): c
             for c in exp["per_night_calibration"]}
    v = a_cal[("N001", "V")]
    ev = e_cal[("N001", "V")]
    assert v["extinction_k"] == ev["extinction_k"], (
        f"Floor must be applied: actual={v['extinction_k']} expected={ev['extinction_k']}")
    assert v["zero_point"] == ev["zero_point"]


# ── N_total_observations on excluded_night rows ──────────────────────────

def test_59_n_total_obs_on_excluded_night(tmp_path: Path) -> None:
    """excluded_night rows must still count n_total_observations."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for ec in exp["per_night_calibration"]:
        if ec["status"] == "excluded_night":
            ac = next(c for c in actual["per_night_calibration"]
                      if c["night_id"] == ec["night_id"]
                      and c["filter"] == ec["filter"])
            assert ac["n_total_observations"] == ec["n_total_observations"], (
                f"excluded_night {ec['night_id']}/{ec['filter']}: "
                f"n_total_obs actual={ac['n_total_observations']} "
                f"expected={ec['n_total_observations']}")
            assert ac["n_total_observations"] > 0, (
                "excluded_night rows must still count observations")


# ── No scientific notation anywhere ──────────────────────────────────────

def test_60_no_scientific_notation(tmp_path: Path) -> None:
    """No float value in the JSON output may use scientific notation."""
    import re
    run_tool(SEEDED_DATA, tmp_path / "actual.json")
    raw = (tmp_path / "actual.json").read_text(encoding="utf-8")
    sci_matches = re.findall(r':\s*-?[0-9]+\.?[0-9]*[eE][+-]?[0-9]+', raw)
    assert not sci_matches, (
        f"scientific notation found: {sci_matches[:5]}")


# ── Integer vs float type check ──────────────────────────────────────────

def test_61_integer_fields_are_ints(tmp_path: Path) -> None:
    """Certain fields must be JSON integers, not floats."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    int_fields_cal = ["n_outliers_flagged", "n_program_observations",
                      "n_standards_used", "n_total_observations"]
    for c in actual["per_night_calibration"]:
        for k in int_fields_cal:
            assert isinstance(c[k], int), (
                f"{c['night_id']}/{c['filter']}.{k}={c[k]} is {type(c[k])}, not int")
    int_fields_lc = ["n_observations", "n_nights"]
    for r in actual["per_star_lightcurves"]:
        for k in int_fields_lc:
            assert isinstance(r[k], int), (
                f"{r['star_id']}/{r['filter']}.{k}={r[k]} is {type(r[k])}, not int")
    for f in actual["findings"]:
        assert isinstance(f["severity_rank"], int), (
            f"severity_rank={f['severity_rank']} must be int")


# ── Dual-catalog star (standard + program) ───────────────────────────────

def test_62_dual_catalog_star_gets_lightcurve(tmp_path: Path) -> None:
    """STD_006 is in both standards.csv and programs.csv; it must get
    lightcurve entries while still contributing to extinction fits."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    lc_stars = {r["star_id"] for r in actual["per_star_lightcurves"]}
    assert "STD_006" in lc_stars, (
        "STD_006 appears in both catalogs and must get a lightcurve entry")


def test_63_dual_catalog_star_lightcurve_values(tmp_path: Path) -> None:
    """STD_006 lightcurves must match oracle values."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for filt in ["B", "V", "R"]:
        ar = next((r for r in actual["per_star_lightcurves"]
                   if r["star_id"] == "STD_006" and r["filter"] == filt), None)
        er = next((r for r in exp["per_star_lightcurves"]
                   if r["star_id"] == "STD_006" and r["filter"] == filt), None)
        assert ar is not None, f"STD_006/{filt} lightcurve missing"
        assert er is not None
        for key in ("n_observations", "mean_calibrated_mag",
                    "stddev_calibrated_mag", "chi_squared_reduced",
                    "is_variable", "status"):
            assert ar[key] == er[key], (
                f"STD_006/{filt}.{key}: actual={ar[key]} expected={er[key]}")


def test_64_dual_catalog_star_still_in_fits(tmp_path: Path) -> None:
    """STD_006 observations must still contribute to extinction fitting
    (n_standards_used must include STD_006 contributions)."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for c in actual["per_night_calibration"]:
        if c["status"] != "calibrated":
            continue
        ec = next(x for x in exp["per_night_calibration"]
                  if x["night_id"] == c["night_id"]
                  and x["filter"] == c["filter"])
        assert c["n_standards_used"] == ec["n_standards_used"], (
            f"{c['night_id']}/{c['filter']} n_standards_used: "
            f"actual={c['n_standards_used']} expected={ec['n_standards_used']}")


def test_65_dual_catalog_counted_in_program_obs(tmp_path: Path) -> None:
    """STD_006 is a program star, so its observations on calibrated pairs
    must be counted in n_program_observations."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for c in actual["per_night_calibration"]:
        ec = next(x for x in exp["per_night_calibration"]
                  if x["night_id"] == c["night_id"]
                  and x["filter"] == c["filter"])
        assert c["n_program_observations"] == ec["n_program_observations"], (
            f"{c['night_id']}/{c['filter']} n_program_observations: "
            f"actual={c['n_program_observations']} "
            f"expected={ec['n_program_observations']}")


# ── Excluded program star ────────────────────────────────────────────────

def test_66_excluded_program_star(tmp_path: Path) -> None:
    """PROG_D2 is in excluded_stars; it must not appear in lightcurves
    and must produce an excluded_star finding."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    lc_stars = {r["star_id"] for r in actual["per_star_lightcurves"]}
    assert "PROG_D2" not in lc_stars, "excluded PROG_D2 must not get lightcurve"
    excl = json.loads((SEEDED_DATA / "exclusions.json").read_text())
    es_findings = [f for f in actual["findings"]
                   if f["finding_type"] == "excluded_star"]
    es_stars = {f["star_id"] for f in es_findings}
    for sid in excl["excluded_stars"]:
        assert sid in es_stars, f"missing excluded_star finding for {sid}"


def test_67_excluded_star_count(tmp_path: Path) -> None:
    """Two excluded stars (STD_014, PROG_D2) → two excluded_star findings."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    es = [f for f in actual["findings"]
          if f["finding_type"] == "excluded_star"]
    assert len(es) == 2, f"expected 2 excluded_star findings, got {len(es)}"
    assert {f["star_id"] for f in es} == {"STD_014", "PROG_D2"}


# ── No-observations program star ────────────────────────────────────────

def test_68_no_obs_program_star(tmp_path: Path) -> None:
    """PROG_E1 has no observations → all 3 filter lightcurves are no_data."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    for filt in ["B", "V", "R"]:
        row = next((r for r in actual["per_star_lightcurves"]
                    if r["star_id"] == "PROG_E1" and r["filter"] == filt), None)
        assert row is not None, f"PROG_E1/{filt} lightcurve missing"
        assert row["status"] == "no_data", (
            f"PROG_E1/{filt} status={row['status']} should be no_data")
        assert row["chi_squared_reduced"] is None
        assert row["mean_calibrated_mag"] is None
        assert row["n_observations"] == 0


# ── Evidence field structure ─────────────────────────────────────────────

def test_69_excluded_findings_have_empty_evidence(tmp_path: Path) -> None:
    """excluded_night, excluded_filter, excluded_star, excluded_observation
    findings must have evidence == {}."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    for f in actual["findings"]:
        if f["finding_type"] in {"excluded_night", "excluded_filter",
                                  "excluded_star", "excluded_observation"}:
            assert f["evidence"] == {}, (
                f"{f['finding_type']} evidence must be {{}}, "
                f"got {f['evidence']}")


def test_70_excluded_findings_null_fields(tmp_path: Path) -> None:
    """Each exclusion finding must have only the relevant ID populated
    and all other ID fields null."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    for f in actual["findings"]:
        ft = f["finding_type"]
        if ft == "excluded_night":
            assert f["night_id"] is not None
            assert f["filter"] is None
            assert f["star_id"] is None
            assert f["image_id"] is None
        elif ft == "excluded_filter":
            assert f["night_id"] is not None
            assert f["filter"] is not None
            assert f["star_id"] is None
            assert f["image_id"] is None
        elif ft == "excluded_star":
            assert f["night_id"] is None
            assert f["filter"] is None
            assert f["star_id"] is not None
            assert f["image_id"] is None
        elif ft == "excluded_observation":
            assert f["night_id"] is None
            assert f["filter"] is None
            assert f["star_id"] is None
            assert f["image_id"] is not None


def test_71_bad_night_evidence_content(tmp_path: Path) -> None:
    """bad_night_residuals evidence must contain residual_stddev and threshold."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    bad = [f for f in actual["findings"]
           if f["finding_type"] == "bad_night_residuals"]
    exp_bad = [f for f in exp["findings"]
               if f["finding_type"] == "bad_night_residuals"]
    assert len(bad) == len(exp_bad)
    for af in bad:
        assert "residual_stddev" in af["evidence"]
        assert "threshold" in af["evidence"]
        assert "n_standards_used" in af["evidence"]


def test_72_negative_extinction_evidence(tmp_path: Path) -> None:
    """negative_extinction evidence must contain extinction_k and threshold."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    neg = [f for f in actual["findings"]
           if f["finding_type"] == "negative_extinction"]
    assert len(neg) >= 1
    for af in neg:
        assert "extinction_k" in af["evidence"]
        assert "threshold" in af["evidence"]
        ef = next(f for f in expected(SEEDED_DATA, tmp_path / "expected.json")["findings"]
                  if f["finding_type"] == "negative_extinction"
                  and f["night_id"] == af["night_id"]
                  and f["filter"] == af["filter"])
        assert af["evidence"]["extinction_k"] == ef["evidence"]["extinction_k"]


# ── Lightcurve count ─────────────────────────────────────────────────────

def test_73_lightcurve_count_matches_expected(tmp_path: Path) -> None:
    """Lightcurve count must match: (non-excluded program stars) × 3 filters.
    PROG_D2 is excluded, PROG_E1 is new, STD_006 is dual-catalog."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    assert len(actual["per_star_lightcurves"]) == len(exp["per_star_lightcurves"])


def test_74_summary_matches_full_report(tmp_path: Path) -> None:
    """Every summary field must exactly match the corresponding list/count."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for key in exp["summary"]:
        assert actual["summary"][key] == exp["summary"][key], (
            f"summary.{key}: actual={actual['summary'][key]} "
            f"expected={exp['summary'][key]}")


# ── Unknown star in observations ─────────────────────────────────────────

def test_75_unknown_star_counted_in_n_total(tmp_path: Path) -> None:
    """UNKNOWN_STAR/FIELD_STAR rows count toward n_total_observations
    even though the star is not in any catalog."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    ecal = {(c["night_id"], c["filter"]): c
            for c in exp["per_night_calibration"]}
    # N015 has UNKNOWN_STAR in V and B, plus STD_003 in I
    # I band is NOT in instrument.json → ignored entirely
    # UNKNOWN_STAR V and B rows count toward n_total_observations
    for filt in ["V", "B"]:
        assert cal[("N015", filt)]["n_total_observations"] == \
               ecal[("N015", filt)]["n_total_observations"], (
            f"N015/{filt} n_total_obs: "
            f"actual={cal[('N015', filt)]['n_total_observations']} "
            f"expected={ecal[('N015', filt)]['n_total_observations']}")
    # N011 has FIELD_STAR in B
    assert cal[("N011", "B")]["n_total_observations"] == \
           ecal[("N011", "B")]["n_total_observations"], (
        f"N011/B n_total_obs: "
        f"actual={cal[('N011', 'B')]['n_total_observations']} "
        f"expected={ecal[('N011', 'B')]['n_total_observations']}")


def test_76_no_i_band_calibration_row(tmp_path: Path) -> None:
    """N015 has an I-band observation but I is not in instrument.json;
    the calibration output must NOT contain any I-band row."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    filters_seen = {c["filter"] for c in actual["per_night_calibration"]}
    assert "I" not in filters_seen, "I-band rows must not appear"


def test_77_unknown_star_no_lightcurve(tmp_path: Path) -> None:
    """Stars not in programs.csv must never get a lightcurve row."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    lc_stars = {r["star_id"] for r in actual["per_star_lightcurves"]}
    assert "UNKNOWN_STAR" not in lc_stars
    assert "FIELD_STAR" not in lc_stars


# ── Zero uncertainty (floor applied) ────────────────────────────────────

def test_78_zero_uncertainty_observation_included(tmp_path: Path) -> None:
    """N011 has STD_009/V observation with mag_uncertainty=0.0.
    After flooring to 0.005, it must be included in the fit."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    cal = {(c["night_id"], c["filter"]): c
           for c in actual["per_night_calibration"]}
    ecal = {(c["night_id"], c["filter"]): c
            for c in exp["per_night_calibration"]}
    # N011/V should include the zero-uncertainty observation
    assert cal[("N011", "V")]["n_standards_used"] == \
           ecal[("N011", "V")]["n_standards_used"]
    assert cal[("N011", "V")]["extinction_k"] == \
           ecal[("N011", "V")]["extinction_k"]


# ── Missing catalog magnitude ───────────────────────────────────────────

def test_80_missing_catalog_mag_excluded_from_fit(tmp_path: Path) -> None:
    """STD_011 has empty R_mag; it must NOT contribute to any R-band fit
    but must still contribute to V and B fits."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for c in actual["per_night_calibration"]:
        ec = next(x for x in exp["per_night_calibration"]
                  if x["night_id"] == c["night_id"]
                  and x["filter"] == c["filter"])
        assert c["n_standards_used"] == ec["n_standards_used"], (
            f"{c['night_id']}/{c['filter']} n_standards_used: "
            f"actual={c['n_standards_used']} expected={ec['n_standards_used']}")
        assert c["extinction_k"] == ec["extinction_k"], (
            f"{c['night_id']}/{c['filter']} extinction_k: "
            f"actual={c['extinction_k']} expected={ec['extinction_k']}")


# ── Insufficient lightcurve observations ─────────────────────────────────

def test_81_insufficient_lc_observations_status(tmp_path: Path) -> None:
    """PROG_F1 has only 2 observations per filter (below min=4);
    lightcurve status must be insufficient_observations."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    for filt in ["B", "V", "R"]:
        row = next((r for r in actual["per_star_lightcurves"]
                    if r["star_id"] == "PROG_F1" and r["filter"] == filt), None)
        assert row is not None, f"PROG_F1/{filt} lightcurve missing"
        assert row["status"] == "insufficient_observations", (
            f"PROG_F1/{filt} status={row['status']} "
            f"expected insufficient_observations")
        assert row["n_observations"] == 2, (
            f"PROG_F1/{filt} n_obs={row['n_observations']} expected 2")
        assert row["is_variable"] is False
        assert row["chi_squared_reduced"] is None


def test_82_insufficient_lc_still_has_magnitudes(tmp_path: Path) -> None:
    """Even with insufficient observations, PROG_F1 must have
    computed min/max/amplitude/mean/stddev (since n_obs >= 1)."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for filt in ["B", "V", "R"]:
        ar = next(r for r in actual["per_star_lightcurves"]
                  if r["star_id"] == "PROG_F1" and r["filter"] == filt)
        er = next(r for r in exp["per_star_lightcurves"]
                  if r["star_id"] == "PROG_F1" and r["filter"] == filt)
        assert ar["mean_calibrated_mag"] is not None
        assert ar["stddev_calibrated_mag"] is not None
        assert ar["min_calibrated_mag"] is not None
        assert ar["amplitude_mag"] is not None
        assert ar["mean_calibrated_mag"] == er["mean_calibrated_mag"]
        assert ar["amplitude_mag"] == er["amplitude_mag"]


def test_83_insufficient_lc_finding_emitted(tmp_path: Path) -> None:
    """insufficient_lightcurve_observations finding must be emitted for
    each filter of PROG_F1."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    ilc = [f for f in actual["findings"]
           if f["finding_type"] == "insufficient_lightcurve_observations"
           and f["star_id"] == "PROG_F1"]
    assert len(ilc) == 3, (
        f"expected 3 insufficient_lc findings for PROG_F1, got {len(ilc)}")
    filters_found = {f["filter"] for f in ilc}
    assert filters_found == {"B", "V", "R"}


# ── Lightcurve count with new stars ──────────────────────────────────────

def test_84_total_lightcurve_count(tmp_path: Path) -> None:
    """Total lightcurves: 10 non-excluded program stars × 3 filters = 30.
    Stars: PROG_A1,A2,B1,B2,C1,C2,D1,E1,F1,STD_006 (D2 excluded)."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    assert len(actual["per_star_lightcurves"]) == 30
    assert len(actual["per_star_lightcurves"]) == len(exp["per_star_lightcurves"])


# ── Severity rank in findings ────────────────────────────────────────────

def test_85_severity_rank_lookup(tmp_path: Path) -> None:
    """Every finding's severity_rank must match
    policy.severity_ranks[finding_severity[finding_type]]."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    policy = json.loads((SEEDED_DATA / "policy.json").read_text())
    sev_ranks = policy["severity_ranks"]
    for f in actual["findings"]:
        expected_sev = policy["finding_severity"][f["finding_type"]]
        expected_rank = sev_ranks[expected_sev]
        assert f["severity"] == expected_sev, (
            f"{f['finding_type']} severity={f['severity']} "
            f"expected={expected_sev}")
        assert f["severity_rank"] == expected_rank, (
            f"{f['finding_type']} severity_rank={f['severity_rank']} "
            f"expected={expected_rank}")


# ── Color-term correction ───────────────────────────────────────────────

def test_86_color_terms_applied_to_b_and_r(tmp_path: Path) -> None:
    """B (ct=0.04) and R (ct=-0.03) calibration must differ from a
    no-color-term implementation. V (ct=0.0) is unchanged."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for c in actual["per_night_calibration"]:
        ec = next(x for x in exp["per_night_calibration"]
                  if x["night_id"] == c["night_id"]
                  and x["filter"] == c["filter"])
        assert c["extinction_k"] == ec["extinction_k"], (
            f"{c['night_id']}/{c['filter']} extinction_k mismatch: "
            f"actual={c['extinction_k']} expected={ec['extinction_k']}")
        assert c["zero_point"] == ec["zero_point"], (
            f"{c['night_id']}/{c['filter']} zero_point mismatch: "
            f"actual={c['zero_point']} expected={ec['zero_point']}")


def test_87_missing_bmag_drops_std_from_color_corrected_filters(
        tmp_path: Path) -> None:
    """STD_008 has empty B_mag. For B-band (ct=0.04): excluded (missing
    catalog_mag AND can't compute B-V). For R-band (ct=-0.03): excluded
    because B-V color index cannot be computed even though R_mag exists.
    For V-band (ct=0.0): included (no color correction needed)."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for c in actual["per_night_calibration"]:
        ec = next(x for x in exp["per_night_calibration"]
                  if x["night_id"] == c["night_id"]
                  and x["filter"] == c["filter"])
        assert c["n_standards_used"] == ec["n_standards_used"], (
            f"{c['night_id']}/{c['filter']} n_standards_used: "
            f"actual={c['n_standards_used']} expected={ec['n_standards_used']}")


def test_88_calibrated_mag_no_color_term(tmp_path: Path) -> None:
    """Calibrated magnitudes do NOT include color-term correction
    (program stars lack catalog mags for B-V)."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for lc_a in actual["per_star_lightcurves"]:
        lc_e = next(x for x in exp["per_star_lightcurves"]
                    if x["star_id"] == lc_a["star_id"]
                    and x["filter"] == lc_a["filter"])
        assert lc_a["mean_calibrated_mag"] == lc_e["mean_calibrated_mag"], (
            f"{lc_a['star_id']}/{lc_a['filter']} mean_cal: "
            f"actual={lc_a['mean_calibrated_mag']} "
            f"expected={lc_e['mean_calibrated_mag']}")


# ── Max airmass cutoff ──────────────────────────────────────────────────

def test_89_high_airmass_observations_excluded(tmp_path: Path) -> None:
    """Observations with airmass > policy.max_airmass must be excluded from
    fits and lightcurves but still counted in n_total_observations."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    assert actual["summary"]["used_program_observations"] == \
           exp["summary"]["used_program_observations"]
    assert actual["summary"]["used_standard_observations"] == \
           exp["summary"]["used_standard_observations"]
    assert actual["summary"]["total_observations"] == \
           exp["summary"]["total_observations"]


# ── Iterative outlier rejection ─────────────────────────────────────────

def test_90_iterative_rejection_outlier_count(tmp_path: Path) -> None:
    """With max_rejection_passes=2, the total outlier count must match
    oracle across all accepted passes."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    assert actual["summary"]["flagged_outliers"] == \
           exp["summary"]["flagged_outliers"]


def test_91_iterative_rejection_per_night(tmp_path: Path) -> None:
    """Per-night n_outliers_flagged must match oracle."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    for c in actual["per_night_calibration"]:
        ec = next(x for x in exp["per_night_calibration"]
                  if x["night_id"] == c["night_id"]
                  and x["filter"] == c["filter"])
        assert c["n_outliers_flagged"] == ec["n_outliers_flagged"], (
            f"{c['night_id']}/{c['filter']} n_outliers: "
            f"actual={c['n_outliers_flagged']} "
            f"expected={ec['n_outliers_flagged']}")


def test_92_outlier_findings_match(tmp_path: Path) -> None:
    """outlier_observation findings must match oracle count and image_ids."""
    actual = run_tool(SEEDED_DATA, tmp_path / "actual.json")
    exp = expected(SEEDED_DATA, tmp_path / "expected.json")
    a_out = sorted(f["image_id"] for f in actual["findings"]
                   if f["finding_type"] == "outlier_observation")
    e_out = sorted(f["image_id"] for f in exp["findings"]
                   if f["finding_type"] == "outlier_observation")
    assert a_out == e_out, f"outlier image_ids: {a_out} != {e_out}"
