"""Tests for timeseries-aggregator-debug-hard."""
import json
import hashlib
import re
from pathlib import Path

import pytest

REPORT_PATH = Path("/app/output/report.json")
ROOT = Path("/app")


@pytest.fixture(scope="session")
def report():
    """Load the generated report JSON. Deferred to avoid crashing collection."""
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def raw_report():
    """Load raw report text for format and hash verification."""
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    return REPORT_PATH.read_text(encoding="utf-8")


def _sensor(report, sid):
    return next(s for s in report["sensor_summaries"] if s["sensor_id"] == sid)


# ════════════════════════════════════════════════════════════
# File existence and format
# ════════════════════════════════════════════════════════════

def test_output_file_exists():
    """Report file must exist at the expected path."""
    assert REPORT_PATH.exists()


def test_report_is_valid_json():
    """Report must be parseable JSON."""
    json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def test_top_level_keys(report):
    """Report must contain exactly metadata, sensor_summaries, and integrity."""
    assert set(report.keys()) == {"metadata", "sensor_summaries", "integrity"}


# ════════════════════════════════════════════════════════════
# Metadata correctness
# ════════════════════════════════════════════════════════════

def test_total_records(report):
    """7 CSV files with 20 rows each = 140 total records."""
    assert report["metadata"]["total_records"] == 140


def test_filtered_records(report):
    """2 degraded rows in TEMP-01 filtered out → 138 remain."""
    assert report["metadata"]["filtered_records"] == 138


def test_sensors_processed(report):
    """All 7 distinct sensor IDs must appear."""
    assert report["metadata"]["sensors_processed"] == 7


def test_time_range_start(report):
    """Time range start is the earliest reading timestamp."""
    assert report["metadata"]["time_range"]["start"] == "2024-01-15T10:00:00Z"


def test_time_range_end(report):
    """Time range end is the latest reading timestamp."""
    assert report["metadata"]["time_range"]["end"] == "2024-01-15T10:19:00Z"


def test_config_hash_format(report):
    """Config hash must be a 64-char hex SHA-256 string."""
    h = report["metadata"]["config_hash"]
    assert re.fullmatch(r"[0-9a-f]{64}", h), f"Invalid config hash format: {h}"


# ════════════════════════════════════════════════════════════
# Sort order (catches Bug 4: descending instead of ascending)
# ════════════════════════════════════════════════════════════

def test_sensor_order_ascending(report):
    """Sensor summaries must be sorted ascending by sensor_id."""
    ids = [s["sensor_id"] for s in report["sensor_summaries"]]
    assert ids == sorted(ids), f"Expected ascending order, got {ids}"


def test_first_sensor_is_humid01(report):
    """First sensor in sorted order must be HUMID-01."""
    assert report["sensor_summaries"][0]["sensor_id"] == "HUMID-01"


def test_last_sensor_is_temp03(report):
    """Last sensor in sorted order must be TEMP-03."""
    assert report["sensor_summaries"][-1]["sensor_id"] == "TEMP-03"


# ════════════════════════════════════════════════════════════
# Record counts per sensor
# ════════════════════════════════════════════════════════════

def test_temp01_record_count(report):
    """TEMP-01 has 2 degraded readings filtered → 18 remain."""
    assert _sensor(report, "TEMP-01")["record_count"] == 18


def test_temp02_record_count(report):
    """TEMP-02 has no filtered readings → 20."""
    assert _sensor(report, "TEMP-02")["record_count"] == 20


def test_humid02_record_count(report):
    """HUMID-02 has 1 acceptable (kept) + 19 good → 20."""
    assert _sensor(report, "HUMID-02")["record_count"] == 20


# ════════════════════════════════════════════════════════════
# Bucket self-consistency (catches Bug 6: boundary double-count)
# ════════════════════════════════════════════════════════════

def test_bucket_count_sum_equals_record_count(report):
    """Sum of per-bucket counts must equal sensor record_count (no double-counting)."""
    for s in report["sensor_summaries"]:
        total = sum(b["count"] for b in s["buckets"])
        assert total == s["record_count"], (
            f"{s['sensor_id']}: bucket count sum {total} != record_count {s['record_count']}"
        )


def test_temp01_has_four_buckets(report):
    """TEMP-01 readings span 4 time buckets."""
    assert len(_sensor(report, "TEMP-01")["buckets"]) == 4


def test_temp01_bucket1_count(report):
    """TEMP-01 bucket 1 has 4 readings (1 degraded filtered from 5)."""
    assert _sensor(report, "TEMP-01")["buckets"][0]["count"] == 4


def test_temp02_bucket1_count(report):
    """TEMP-02 bucket 1 has exactly 5 readings (none filtered)."""
    assert _sensor(report, "TEMP-02")["buckets"][0]["count"] == 5


def test_all_sensors_have_four_buckets(report):
    """Every sensor has readings across exactly 4 time buckets."""
    for s in report["sensor_summaries"]:
        assert len(s["buckets"]) == 4, (
            f"{s['sensor_id']} has {len(s['buckets'])} buckets, expected 4"
        )


# ════════════════════════════════════════════════════════════
# Statistical value checks (catches Bug 1: N vs N-1 stddev)
# ════════════════════════════════════════════════════════════

def test_temp01_bucket1_mean(report):
    """TEMP-01 bucket 1 mean = (23.5+23.8+24.1+24.3)/4 = 23.925."""
    assert abs(_sensor(report, "TEMP-01")["buckets"][0]["mean"] - 23.925) < 0.001


def test_temp01_bucket1_stddev_sample(report):
    """TEMP-01 bucket 1 sample stddev (N-1) must be exactly 0.35."""
    assert abs(_sensor(report, "TEMP-01")["buckets"][0]["stddev"] - 0.35) < 0.001


def test_temp02_bucket2_mean(report):
    """TEMP-02 bucket 2 mean = (35.2+36.1+36.8+37.5+36.2)/5 = 36.36."""
    assert abs(_sensor(report, "TEMP-02")["buckets"][1]["mean"] - 36.36) < 0.001


def test_temp03_bucket1_mean(report):
    """TEMP-03 bucket 1 mean = (20.0+20.5+21.0+21.5+22.0)/5 = 21.0."""
    assert abs(_sensor(report, "TEMP-03")["buckets"][0]["mean"] - 21.0) < 0.001


def test_humid02_bucket2_max(report):
    """HUMID-02 bucket 2 max = 93.0 (from acceptable-quality reading)."""
    assert abs(_sensor(report, "HUMID-02")["buckets"][1]["max"] - 93.0) < 0.1


# ════════════════════════════════════════════════════════════
# Violation detection (catches Bug 2: inverted gt operator)
# ════════════════════════════════════════════════════════════

def test_total_violations_count(report):
    """Exactly 3 violations: 1 TEMP-02 mean>35, 2 HUMID-02 max>90."""
    total = sum(len(s["violations"]) for s in report["sensor_summaries"])
    assert total == 3, f"Expected 3 violations, got {total}"


def test_temp02_has_one_violation(report):
    """TEMP-02 has exactly 1 violation (bucket 2 mean > 35)."""
    s = _sensor(report, "TEMP-02")
    assert len(s["violations"]) == 1


def test_temp02_violation_metric(report):
    """TEMP-02 violation is on the mean metric."""
    v = _sensor(report, "TEMP-02")["violations"][0]
    assert v["metric"] == "mean"


def test_temp02_violation_threshold(report):
    """TEMP-02 violation threshold is 35.0."""
    v = _sensor(report, "TEMP-02")["violations"][0]
    assert abs(v["threshold"] - 35.0) < 0.01


def test_humid02_has_two_violations(report):
    """HUMID-02 has 2 violations (buckets 2 and 3 max > 90)."""
    s = _sensor(report, "HUMID-02")
    assert len(s["violations"]) == 2


def test_humid02_violation_metrics_are_max(report):
    """Both HUMID-02 violations are on the max metric."""
    for v in _sensor(report, "HUMID-02")["violations"]:
        assert v["metric"] == "max"


def test_no_pressure_violations(report):
    """PRESS sensors have no threshold rules and thus no violations."""
    for s in report["sensor_summaries"]:
        if s["sensor_id"].startswith("PRESS-"):
            assert len(s["violations"]) == 0, (
                f"{s['sensor_id']} should have no violations"
            )


def test_temp01_no_violations(report):
    """TEMP-01 means are all below 35 → no violations."""
    assert len(_sensor(report, "TEMP-01")["violations"]) == 0


# ════════════════════════════════════════════════════════════
# Float precision (catches Bug 3: hardcoded 6 instead of 4)
# ════════════════════════════════════════════════════════════

def test_float_values_have_four_decimal_places(raw_report):
    """All metric floats must use exactly 4 decimal places per config."""
    float_matches = re.findall(
        r'"(?:mean|min|max|stddev|value|threshold)": (\d+\.\d+)',
        raw_report,
    )
    assert len(float_matches) > 0, "No float values found in report"
    for val_str in float_matches:
        decimal_part = val_str.split(".")[1]
        assert len(decimal_part) == 4, (
            f"Expected 4 decimal places, got {len(decimal_part)} in {val_str}"
        )


# ════════════════════════════════════════════════════════════
# Integrity hash (catches Bug 5: hashing full_json vs summaries)
# ════════════════════════════════════════════════════════════

def test_integrity_hash_format(report):
    """Hash must be 'sha256:' followed by 64 hex characters."""
    h = report["integrity"]["results_hash"]
    assert h.startswith("sha256:"), f"Hash must start with 'sha256:', got {h[:10]}"
    hex_part = h[7:]
    assert re.fullmatch(r"[0-9a-f]{64}", hex_part), f"Invalid hex: {hex_part}"


def test_integrity_hash_matches_summaries(raw_report):
    """Hash must cover only sensor_summaries JSON, not the full report."""
    report = json.loads(raw_report)
    start_marker = '"sensor_summaries": '
    start_idx = raw_report.index(start_marker) + len(start_marker)
    end_marker = ',\n  "integrity"'
    end_idx = raw_report.index(end_marker)
    summaries_text = raw_report[start_idx:end_idx]
    expected = "sha256:" + hashlib.sha256(summaries_text.encode()).hexdigest()
    assert report["integrity"]["results_hash"] == expected, (
        "Hash does not match SHA-256 of sensor_summaries array"
    )


# ════════════════════════════════════════════════════════════
# C++ language verification (anti-Python-shortcut)
# ════════════════════════════════════════════════════════════

def test_compiled_binary_exists():
    """Compiled binary must exist at /app/build/sensor_tool."""
    assert (ROOT / "build" / "sensor_tool").is_file(), (
        "Compiled binary not found — solution must be compiled C++"
    )


def test_binary_is_elf_executable():
    """Binary must be a real ELF executable, not a script wrapper."""
    binary = ROOT / "build" / "sensor_tool"
    with open(binary, "rb") as f:
        magic = f.read(4)
    assert magic == b"\x7fELF", (
        f"Binary is not ELF (magic: {magic!r}). Must be compiled C++."
    )


def test_object_files_present():
    """Compilation must produce .o object files in the build directory."""
    build_dir = ROOT / "build"
    o_files = list(build_dir.glob("*.o"))
    assert len(o_files) >= 5, (
        f"Expected >=5 .o files, found {len(o_files)}. C++ compilation required."
    )


def test_makefile_exists():
    """Makefile must remain present (used for building)."""
    assert (ROOT / "Makefile").is_file()


def test_data_files_not_modified():
    """All 7 CSV data files must still exist in /app/data/."""
    data_dir = ROOT / "data"
    csv_files = sorted(f.name for f in data_dir.glob("*.csv"))
    assert len(csv_files) == 7, f"Expected 7 CSV files, found {len(csv_files)}"
