"""Tests for the Streaming Statistics Pipeline Auditor."""

import json
import hashlib
import math
import os
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_ROOT", "/app"))
REPORT_PATH = APP / "output" / "pipeline_audit.json"
CONFIG_DIR = APP / "config"
STREAMS_DIR = APP / "streams"
PIPELINES_DIR = APP / "pipelines"


@pytest.fixture(scope="session")
def report():
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    with open(REPORT_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def config():
    with open(CONFIG_DIR / "pipeline.json") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def streams():
    s = {}
    for fn in sorted(os.listdir(STREAMS_DIR)):
        if fn.endswith(".json"):
            with open(STREAMS_DIR / fn) as f:
                d = json.load(f)
                s[d["stream_id"]] = d
    return s


@pytest.fixture(scope="session")
def pipelines():
    p = {}
    for fn in sorted(os.listdir(PIPELINES_DIR)):
        if fn.endswith(".json"):
            with open(PIPELINES_DIR / fn) as f:
                d = json.load(f)
                p[d["stream_id"]] = d
    return p


def compute_source_hashes():
    hashes = {}
    for d in [CONFIG_DIR, STREAMS_DIR, PIPELINES_DIR]:
        for dp, dns, fns in os.walk(d):
            dns.sort()
            for fn in sorted(fns):
                fp = os.path.join(dp, fn)
                rel = os.path.relpath(fp, APP).replace("\\", "/")
                with open(fp, "rb") as fh:
                    hashes[rel] = hashlib.sha256(fh.read()).hexdigest()
    return dict(sorted(hashes.items()))


def get_stream_audit(report, stream_id):
    return next(a for a in report["stream_audits"] if a["stream_id"] == stream_id)


FIXTURE_HASHES = {
    "config/pipeline.json": None,
}


# ===================================================================
# STRUCTURAL TESTS
# ===================================================================


def test_01_report_exists():
    """pipeline_audit.json must exist at /app/output/."""
    assert REPORT_PATH.exists()


def test_02_report_valid_json(report):
    """Report must be a valid JSON object (dict)."""
    assert isinstance(report, dict)


def test_03_top_level_keys(report):
    """Report must contain exactly: schema_version, summary, source_sha256, stream_audits, findings."""
    expected = {"schema_version", "summary", "source_sha256", "stream_audits", "findings"}
    assert set(report.keys()) == expected


def test_04_schema_version(report):
    """schema_version must be integer 1."""
    assert report["schema_version"] == 1
    assert isinstance(report["schema_version"], int)


def test_05_summary_keys(report):
    """Summary must include total_streams, total_observations, total_findings, findings_by_type, findings_by_severity."""
    s = report["summary"]
    expected = {"total_streams", "total_observations", "total_findings",
                "findings_by_type", "findings_by_severity"}
    assert set(s.keys()) == expected


def test_06_summary_counts(report, streams):
    """Summary counts must match actual stream count and total observations."""
    s = report["summary"]
    assert s["total_streams"] == len(streams)
    total_obs = sum(len(sc["observations"]) for sc in streams.values())
    assert s["total_observations"] == total_obs
    assert s["total_findings"] == len(report["findings"])


def test_07_source_hashes_present(report):
    """source_sha256 must be a dict with 25 file hashes (config + streams + pipelines)."""
    hashes = report["source_sha256"]
    assert isinstance(hashes, dict)
    assert len(hashes) == 25


def test_08_source_hashes_correct(report):
    """Every source_sha256 entry must match the SHA-256 of the actual input file."""
    computed = compute_source_hashes()
    reported = report["source_sha256"]
    assert set(reported.keys()) == set(computed.keys())
    for key in computed:
        assert reported[key] == computed[key], f"Hash mismatch for {key}"


def test_09_stream_audit_count(report, streams):
    """Number of stream_audits entries must equal the number of streams."""
    assert len(report["stream_audits"]) == len(streams)


def test_10_stream_audits_sorted(report):
    """stream_audits must be sorted by stream_id in ascending order."""
    sids = [a["stream_id"] for a in report["stream_audits"]]
    assert sids == sorted(sids)


def test_11_total_streams(report):
    """total_streams must be 12."""
    assert report["summary"]["total_streams"] == 12


def test_12_total_observations(report):
    """total_observations must be 206."""
    assert report["summary"]["total_observations"] == 206


def test_13_total_findings(report):
    """total_findings must be 7."""
    assert report["summary"]["total_findings"] == 7


def test_14_findings_by_severity_all_five_keys(report):
    """findings_by_severity must contain ALL 5 severity levels even if count is 0."""
    fbs = report["summary"]["findings_by_severity"]
    for sev in ["critical", "high", "medium", "low", "info"]:
        assert sev in fbs, f"findings_by_severity missing '{sev}' key"


def test_15_findings_by_severity_exact(report):
    """Exact finding counts per severity: critical=3, high=1, medium=1, low=1, info=1."""
    fbs = report["summary"]["findings_by_severity"]
    assert fbs["critical"] == 3
    assert fbs["high"] == 1
    assert fbs["medium"] == 1
    assert fbs["low"] == 1
    assert fbs["info"] == 1


def test_16_findings_by_type_exact(report):
    """Exact finding counts by type."""
    fbt = report["summary"]["findings_by_type"]
    assert fbt.get("extreme_outlier") == 3
    assert fbt.get("change_point") == 1
    assert fbt.get("data_gap") == 1
    assert fbt.get("stale_data") == 1
    assert fbt.get("insufficient_data") == 1


# ===================================================================
# STREAM 01: BASIC STATS & PERCENTILES (Exclusive/R-6 Method)
# ===================================================================


def test_17_s01_basic_stats_counts(report):
    """Stream 01 has 20 observations, all valid, no nulls."""
    sa = get_stream_audit(report, "stream_01")
    bs = sa["basic_stats"]
    assert bs["count"] == 20
    assert bs["valid_count"] == 20
    assert bs["null_count"] == 0


def test_18_s01_mean(report):
    """Stream 01 mean = 155/20 = 7.75."""
    sa = get_stream_audit(report, "stream_01")
    assert sa["basic_stats"]["mean"] == 7.75


def test_19_s01_population_variance(report):
    """Stream 01 population variance = 303.75/20 = 15.1875.
    Models using sample variance (N-1) get 15.986842 instead."""
    sa = get_stream_audit(report, "stream_01")
    assert sa["basic_stats"]["variance"] == 15.1875


def test_20_s01_sample_variance(report):
    """Stream 01 sample_variance (always N-1) = 303.75/19 ≈ 15.986842."""
    sa = get_stream_audit(report, "stream_01")
    assert math.isclose(sa["basic_stats"]["sample_variance"], 15.986842, abs_tol=1e-4)


def test_21_s01_std_dev(report):
    """Stream 01 std_dev = sqrt(population_variance) ≈ 3.897114."""
    sa = get_stream_audit(report, "stream_01")
    assert math.isclose(sa["basic_stats"]["std_dev"], 3.897114, abs_tol=1e-4)


def test_22_s01_min_max(report):
    """Stream 01 min=1, max=15."""
    sa = get_stream_audit(report, "stream_01")
    assert sa["basic_stats"]["min"] == 1
    assert sa["basic_stats"]["max"] == 15


def test_23_s01_percentile_p25_exclusive(report):
    """Stream 01 p25 with exclusive method (R-6): h=(20+1)*0.25=5.25,
    interpolation gives 4.25. An agent using R-7 gets h=(20-1)*0.25+1=5.75,
    giving 4.75 — which is WRONG."""
    sa = get_stream_audit(report, "stream_01")
    assert sa["percentiles"]["p25"] == 4.25, (
        f"p25 must be 4.25 (exclusive/R-6), got {sa['percentiles']['p25']}"
    )


def test_24_s01_percentile_p50(report):
    """Stream 01 p50 = 7.5."""
    sa = get_stream_audit(report, "stream_01")
    assert sa["percentiles"]["p50"] == 7.5


def test_25_s01_percentile_p75_exclusive(report):
    """Stream 01 p75 with exclusive method: h=(20+1)*0.75=15.75,
    gives 10.75. R-7 gives h=15.25 → 10.25 — WRONG."""
    sa = get_stream_audit(report, "stream_01")
    assert sa["percentiles"]["p75"] == 10.75, (
        f"p75 must be 10.75 (exclusive/R-6), got {sa['percentiles']['p75']}"
    )


def test_26_s01_percentile_p5(report):
    """Stream 01 p5: h=1.05, lerp(sorted[0],sorted[1],0.05) = 1 + 0.05*1 = 1.05."""
    sa = get_stream_audit(report, "stream_01")
    assert sa["percentiles"]["p5"] == 1.05


def test_27_s01_percentile_p95(report):
    """Stream 01 p95: h=19.95, lerp(sorted[18],sorted[19],0.95) = 14 + 0.95*1 = 14.95."""
    sa = get_stream_audit(report, "stream_01")
    assert sa["percentiles"]["p95"] == 14.95


def test_28_s01_no_findings(report):
    """Stream 01 has zero findings."""
    sa = get_stream_audit(report, "stream_01")
    assert len(sa["findings"]) == 0


# ===================================================================
# STREAM 02: OUTLIER DETECTION (Modified Z-Score with MAD)
# ===================================================================


def test_29_s02_outlier_median(report):
    """Stream 02 median of 20 values: median = (100.2 + 100.2)/2 = 100.2."""
    sa = get_stream_audit(report, "stream_02")
    assert sa["outliers"]["median"] == 100.2


def test_30_s02_outlier_mad(report):
    """Stream 02 MAD = median of |xi - 100.2| = 0.1."""
    sa = get_stream_audit(report, "stream_02")
    assert sa["outliers"]["mad"] == 0.1


def test_31_s02_outlier_count(report):
    """Stream 02 has exactly 2 outlier points (200.0 and -50.0)."""
    sa = get_stream_audit(report, "stream_02")
    assert len(sa["outliers"]["points"]) == 2


def test_32_s02_outlier_200(report):
    """200.0 at index 18: z = |200-100.2|/(1.4826*0.1) ≈ 673.14, extreme_outlier."""
    sa = get_stream_audit(report, "stream_02")
    p = next(o for o in sa["outliers"]["points"] if o["index"] == 18)
    assert p["value"] == 200.0
    assert p["finding_type"] == "extreme_outlier"
    assert math.isclose(p["z_score"], 673.141778, abs_tol=0.01)


def test_33_s02_outlier_neg50(report):
    """-50.0 at index 19: z = |-50-100.2|/(1.4826*0.1) ≈ 1013.09, extreme_outlier."""
    sa = get_stream_audit(report, "stream_02")
    p = next(o for o in sa["outliers"]["points"] if o["index"] == 19)
    assert p["value"] == -50.0
    assert p["finding_type"] == "extreme_outlier"
    assert math.isclose(p["z_score"], 1013.085121, abs_tol=0.01)


def test_34_s02_normal_values_not_outlier(report):
    """Values like 100.0 and 100.4 have z ≈ 1.35, which is < 3.5 threshold."""
    sa = get_stream_audit(report, "stream_02")
    for p in sa["outliers"]["points"]:
        assert p["index"] in [18, 19], f"Unexpected outlier at index {p['index']}"


def test_35_s02_findings_count(report):
    """Stream 02 has exactly 2 findings (both extreme_outlier)."""
    sa = get_stream_audit(report, "stream_02")
    assert len(sa["findings"]) == 2
    assert all(f["finding_type"] == "extreme_outlier" for f in sa["findings"])


def test_36_s02_findings_evidence_structure(report):
    """Outlier finding evidence must contain index, value, z_score, median, mad."""
    sa = get_stream_audit(report, "stream_02")
    for f in sa["findings"]:
        ev = f["evidence"]
        assert "index" in ev
        assert "value" in ev
        assert "z_score" in ev
        assert "median" in ev
        assert "mad" in ev


# ===================================================================
# STREAM 03: NaN HANDLING & ROLLING STATS
# ===================================================================


def test_37_s03_count_valid_null(report):
    """Stream 03 has 20 observations, 17 valid, 3 null."""
    sa = get_stream_audit(report, "stream_03")
    bs = sa["basic_stats"]
    assert bs["count"] == 20
    assert bs["valid_count"] == 17
    assert bs["null_count"] == 3


def test_38_s03_mean(report):
    """Stream 03 mean computed from 17 valid values ≈ 59.105882."""
    sa = get_stream_audit(report, "stream_03")
    assert math.isclose(sa["basic_stats"]["mean"], 59.105882, abs_tol=1e-4)


def test_39_s03_variance_from_valid_only(report):
    """Variance is computed from 17 valid values (denominator 17, not 20)."""
    sa = get_stream_audit(report, "stream_03")
    assert math.isclose(sa["basic_stats"]["variance"], 4.866436, abs_tol=1e-4)


def test_40_s03_sample_variance_n_minus_1(report):
    """Sample variance uses N-1=16 as denominator."""
    sa = get_stream_audit(report, "stream_03")
    assert math.isclose(sa["basic_stats"]["sample_variance"], 5.170588, abs_tol=1e-4)


def test_41_s03_percentiles_from_valid(report):
    """Percentiles computed from 17 valid values only. p50 = 59.0."""
    sa = get_stream_audit(report, "stream_03")
    assert sa["percentiles"]["p50"] == 59.0


def test_42_s03_percentile_p25(report):
    """Stream 03 p25 from 17 valid values using exclusive method: h=18*0.25=4.5."""
    sa = get_stream_audit(report, "stream_03")
    assert math.isclose(sa["percentiles"]["p25"], 57.6, abs_tol=0.01)


def test_43_s03_percentile_p75(report):
    """Stream 03 p75 from 17 valid values using exclusive method."""
    sa = get_stream_audit(report, "stream_03")
    assert math.isclose(sa["percentiles"]["p75"], 60.6, abs_tol=0.01)


def test_44_s03_rolling_mean_length(report):
    """Rolling stats arrays must match observation count (20)."""
    sa = get_stream_audit(report, "stream_03")
    assert len(sa["rolling_stats"]["rolling_mean"]) == 20
    assert len(sa["rolling_stats"]["rolling_std"]) == 20


def test_45_s03_rolling_nan_omit(report):
    """With nan_policy='omit', rolling stats skip null values. Positions 3, 6, 12
    have null observations but rolling windows around them still compute from
    valid values only (no null results unless too few valid values)."""
    sa = get_stream_audit(report, "stream_03")
    rm = sa["rolling_stats"]["rolling_mean"]
    for i in range(20):
        assert rm[i] is not None, f"Rolling mean at index {i} should not be null with omit policy"


def test_46_s03_rolling_mean_at_boundary(report):
    """Rolling mean at index 0: window [0,2], valid values [55.0,60.2,58.1]
    (index 0,1,2). Mean ≈ 57.766667."""
    sa = get_stream_audit(report, "stream_03")
    assert math.isclose(sa["rolling_stats"]["rolling_mean"][0], 57.766667, abs_tol=1e-4)


def test_47_s03_no_findings(report):
    """Stream 03 has zero findings."""
    sa = get_stream_audit(report, "stream_03")
    assert len(sa["findings"]) == 0


# ===================================================================
# STREAM 04: CUSUM CHANGE-POINT DETECTION
# ===================================================================


def test_48_s04_change_point_count(report):
    """Stream 04 has exactly 1 change point."""
    sa = get_stream_audit(report, "stream_04")
    assert len(sa["change_points"]) == 1


def test_49_s04_change_point_index(report):
    """Change point at index 22. The CUSUM target is the mean of the first 10
    observations (not the overall mean). target = 5.01. An agent using overall
    mean ≈ 6.503 would detect the change much later or not at all."""
    sa = get_stream_audit(report, "stream_04")
    cp = sa["change_points"][0]
    assert cp["index"] == 22


def test_50_s04_change_point_direction(report):
    """Change point is an upward shift."""
    sa = get_stream_audit(report, "stream_04")
    assert sa["change_points"][0]["direction"] == "up"


def test_51_s04_change_point_cusum_value(report):
    """CUSUM value at change point ≈ 15.82."""
    sa = get_stream_audit(report, "stream_04")
    assert math.isclose(sa["change_points"][0]["cusum_value"], 15.82, abs_tol=0.01)


def test_52_s04_change_point_timestamp(report):
    """Change point timestamp = 1000000 + 22*60 = 1001320."""
    sa = get_stream_audit(report, "stream_04")
    assert sa["change_points"][0]["timestamp"] == 1001320


def test_53_s04_basic_stats_mean(report):
    """Stream 04 overall mean ≈ 6.503333. An agent that uses this as the CUSUM
    target instead of warmup mean (5.01) will get different results."""
    sa = get_stream_audit(report, "stream_04")
    assert math.isclose(sa["basic_stats"]["mean"], 6.503333, abs_tol=1e-4)


def test_54_s04_findings(report):
    """Stream 04 has exactly 1 finding (change_point)."""
    sa = get_stream_audit(report, "stream_04")
    assert len(sa["findings"]) == 1
    assert sa["findings"][0]["finding_type"] == "change_point"


# ===================================================================
# STREAM 05: GAP ANALYSIS
# ===================================================================


def test_55_s05_gap_count(report):
    """Stream 05 has exactly 1 gap meeting min_gap_duration threshold."""
    sa = get_stream_audit(report, "stream_05")
    assert len(sa["gaps"]) == 1


def test_56_s05_gap_duration(report):
    """The qualifying gap has duration = 660 seconds (>= min_gap_duration 300)."""
    sa = get_stream_audit(report, "stream_05")
    assert sa["gaps"][0]["duration"] == 660


def test_57_s05_gap_timestamps(report):
    """Gap starts at t=1001020, ends at t=1001680."""
    sa = get_stream_audit(report, "stream_05")
    assert sa["gaps"][0]["start_timestamp"] == 1001020
    assert sa["gaps"][0]["end_timestamp"] == 1001680


def test_58_s05_short_gap_excluded(report):
    """The 180s gap between indices 9 and 10 is excluded because
    180 < min_gap_duration (300). Only 1 gap is reported."""
    sa = get_stream_audit(report, "stream_05")
    for gap in sa["gaps"]:
        assert gap["duration"] >= 300, "Gaps shorter than min_gap_duration must be excluded"


def test_59_s05_findings(report):
    """Stream 05 has exactly 1 finding (data_gap)."""
    sa = get_stream_audit(report, "stream_05")
    assert len(sa["findings"]) == 1
    assert sa["findings"][0]["finding_type"] == "data_gap"


def test_60_s05_gap_evidence(report):
    """Gap finding evidence must contain start_timestamp, end_timestamp, duration."""
    sa = get_stream_audit(report, "stream_05")
    ev = sa["findings"][0]["evidence"]
    assert "start_timestamp" in ev
    assert "end_timestamp" in ev
    assert "duration" in ev


# ===================================================================
# STREAM 06: EMA WITH HALFLIFE ALPHA
# ===================================================================


def test_61_s06_ema_length(report):
    """EMA array must have same length as observations (15)."""
    sa = get_stream_audit(report, "stream_06")
    assert len(sa["ema"]) == 15


def test_62_s06_ema_first_value(report):
    """First EMA value equals first observation (10.0)."""
    sa = get_stream_audit(report, "stream_06")
    assert sa["ema"][0] == 10.0


def test_63_s06_ema_second_value(report):
    """Second EMA: alpha = 1 - exp(-ln(2)/5) ≈ 0.12945.
    ema[1] = 0.12945*12 + 0.87055*10 ≈ 10.2589.
    An agent using alpha=2/(5+1)=0.3333 gets 10.6667 — WRONG."""
    sa = get_stream_audit(report, "stream_06")
    assert math.isclose(sa["ema"][1], 10.258899, abs_tol=1e-4), (
        f"EMA[1] must be ≈10.2589 (halflife alpha), got {sa['ema'][1]}"
    )


def test_64_s06_ema_third_value(report):
    """ema[2] ≈ 9.966486 with halflife alpha. Span formula gives ≈ 9.778 — WRONG."""
    sa = get_stream_audit(report, "stream_06")
    assert math.isclose(sa["ema"][2], 9.966486, abs_tol=1e-4)


def test_65_s06_ema_fifth_value(report):
    """ema[4] ≈ 10.667512. Verifies accumulation of correct alpha."""
    sa = get_stream_audit(report, "stream_06")
    assert math.isclose(sa["ema"][4], 10.667512, abs_tol=1e-4)


def test_66_s06_ema_last_value(report):
    """ema[14] ≈ 11.747161."""
    sa = get_stream_audit(report, "stream_06")
    assert math.isclose(sa["ema"][14], 11.747161, abs_tol=1e-4)


def test_67_s06_ema_mid_values(report):
    """ema[7] ≈ 11.108467, ema[8] ≈ 11.741673."""
    sa = get_stream_audit(report, "stream_06")
    assert math.isclose(sa["ema"][7], 11.108467, abs_tol=1e-4)
    assert math.isclose(sa["ema"][8], 11.741673, abs_tol=1e-4)


def test_68_s06_no_findings(report):
    """Stream 06 has zero findings."""
    sa = get_stream_audit(report, "stream_06")
    assert len(sa["findings"]) == 0


# ===================================================================
# STREAM 07: SMALL N PERCENTILES
# ===================================================================


def test_69_s07_basic_stats(report):
    """Stream 07 has 8 observations. mean ≈ 7.0375."""
    sa = get_stream_audit(report, "stream_07")
    assert sa["basic_stats"]["count"] == 8
    assert math.isclose(sa["basic_stats"]["mean"], 7.0375, abs_tol=1e-4)


def test_70_s07_percentile_p25(report):
    """With N=8, exclusive: h=9*0.25=2.25. sorted=[6.5,6.8,6.9,7.0,7.1,7.2,7.3,7.5].
    lerp(s[1],s[2],0.25) = 6.8+0.25*0.1 = 6.825.
    R-7 gives h=7*0.25+1=2.75, lerp(s[1],s[2],0.75) = 6.8+0.75*0.1 = 6.875 — WRONG."""
    sa = get_stream_audit(report, "stream_07")
    assert sa["percentiles"]["p25"] == 6.825, (
        f"p25 must be 6.825 (exclusive/R-6), got {sa['percentiles']['p25']}"
    )


def test_71_s07_percentile_p50(report):
    """Stream 07 p50: h=9*0.5=4.5, lerp(s[3],s[4],0.5) = 7.0+0.5*0.1 = 7.05."""
    sa = get_stream_audit(report, "stream_07")
    assert sa["percentiles"]["p50"] == 7.05


def test_72_s07_percentile_p75(report):
    """Stream 07 p75: h=9*0.75=6.75, lerp(s[5],s[6],0.75) = 7.2+0.75*0.1 = 7.275.
    R-7 gives h=7*0.75+1=6.25, lerp(s[5],s[6],0.25) = 7.2+0.25*0.1 = 7.225 — WRONG."""
    sa = get_stream_audit(report, "stream_07")
    assert sa["percentiles"]["p75"] == 7.275, (
        f"p75 must be 7.275 (exclusive/R-6), got {sa['percentiles']['p75']}"
    )


def test_73_s07_percentile_p5_clamp(report):
    """Stream 07 p5: h=9*0.05=0.45 < 1, clamp to s[0] = 6.5."""
    sa = get_stream_audit(report, "stream_07")
    assert sa["percentiles"]["p5"] == 6.5


def test_74_s07_percentile_p95_clamp(report):
    """Stream 07 p95: h=9*0.95=8.55 > 8, clamp to s[7] = 7.5."""
    sa = get_stream_audit(report, "stream_07")
    assert sa["percentiles"]["p95"] == 7.5


# ===================================================================
# STREAM 08: STALE DATA_DIR DETECTION
# ===================================================================


def test_75_s08_stale_run_count(report):
    """Stream 08 has exactly 1 stale run."""
    sa = get_stream_audit(report, "stream_08")
    assert len(sa["stale_runs"]) == 1


def test_76_s08_stale_run_details(report):
    """Stale run: indices 12-19, length=8, value=1500."""
    sa = get_stream_audit(report, "stream_08")
    run = sa["stale_runs"][0]
    assert run["start_index"] == 12
    assert run["end_index"] == 19
    assert run["run_length"] == 8
    assert run["value"] == 1500


def test_77_s08_stale_finding(report):
    """Stream 08 has exactly 1 stale_data finding."""
    sa = get_stream_audit(report, "stream_08")
    assert len(sa["findings"]) == 1
    assert sa["findings"][0]["finding_type"] == "stale_data"
    assert sa["findings"][0]["severity"] == "low"


def test_78_s08_stale_evidence(report):
    """Stale data finding evidence must contain start_index, end_index, run_length, value."""
    sa = get_stream_audit(report, "stream_08")
    ev = sa["findings"][0]["evidence"]
    assert ev["start_index"] == 12
    assert ev["end_index"] == 19
    assert ev["run_length"] == 8


def test_79_s08_basic_stats(report):
    """Stream 08 mean = 30175/20 = 1508.75."""
    sa = get_stream_audit(report, "stream_08")
    assert sa["basic_stats"]["mean"] == 1508.75


# ===================================================================
# STREAM 09: WEIGHTED LEAST SQUARES TREND
# ===================================================================


def test_80_s09_trend_slope(report):
    """Stream 09 trend slope ≈ 1.997744 (uniform weights)."""
    sa = get_stream_audit(report, "stream_09")
    assert math.isclose(sa["trend"]["slope"], 1.997744, abs_tol=1e-4)


def test_81_s09_trend_intercept(report):
    """Stream 09 trend intercept ≈ 50.501429."""
    sa = get_stream_audit(report, "stream_09")
    assert math.isclose(sa["trend"]["intercept"], 50.501429, abs_tol=1e-4)


def test_82_s09_trend_r_squared(report):
    """Stream 09 R² ≈ 0.999319 (near-perfect linear trend)."""
    sa = get_stream_audit(report, "stream_09")
    assert math.isclose(sa["trend"]["r_squared"], 0.999319, abs_tol=1e-4)


def test_83_s09_basic_stats(report):
    """Stream 09 mean = 69.48."""
    sa = get_stream_audit(report, "stream_09")
    assert math.isclose(sa["basic_stats"]["mean"], 69.48, abs_tol=1e-4)


def test_84_s09_no_findings(report):
    """Stream 09 has zero findings."""
    sa = get_stream_audit(report, "stream_09")
    assert len(sa["findings"]) == 0


# ===================================================================
# STREAM 10: CONSTANT DATA_DIR (variance=0, MAD=0, no outliers)
# ===================================================================


def test_85_s10_variance_zero(report):
    """Constant stream: variance = 0, std_dev = 0."""
    sa = get_stream_audit(report, "stream_10")
    assert sa["basic_stats"]["variance"] == 0.0
    assert sa["basic_stats"]["std_dev"] == 0.0


def test_86_s10_sample_variance_zero(report):
    """Constant stream sample_variance = 0.0 (all deviations are zero)."""
    sa = get_stream_audit(report, "stream_10")
    assert sa["basic_stats"]["sample_variance"] == 0.0


def test_87_s10_percentiles_constant(report):
    """All percentiles equal the constant value 42.0."""
    sa = get_stream_audit(report, "stream_10")
    for key in ["p25", "p50", "p75"]:
        assert sa["percentiles"][key] == 42.0


def test_88_s10_outlier_mad_zero(report):
    """MAD = 0 for constant stream. Median = 42.0."""
    sa = get_stream_audit(report, "stream_10")
    assert sa["outliers"]["mad"] == 0.0
    assert sa["outliers"]["median"] == 42.0


def test_89_s10_no_outliers(report):
    """All values = median = 42.0, so all z-scores = 0 (not outlier).
    An agent that treats MAD=0 as 'everything is outlier' will fail."""
    sa = get_stream_audit(report, "stream_10")
    assert len(sa["outliers"]["points"]) == 0


def test_90_s10_no_findings(report):
    """Stream 10 has zero findings."""
    sa = get_stream_audit(report, "stream_10")
    assert len(sa["findings"]) == 0


# ===================================================================
# STREAM 11: MAD=0 WITH ONE DIFFERENT VALUE (Infinity Z-Score)
# ===================================================================


def test_91_s11_outlier_median(report):
    """Stream 11: 10 values of 100.0, one 105.0. Median = 100.0."""
    sa = get_stream_audit(report, "stream_11")
    assert sa["outliers"]["median"] == 100.0


def test_92_s11_outlier_mad_zero(report):
    """MAD = 0 (median of deviations: 10 zeros and one 5 → median = 0)."""
    sa = get_stream_audit(report, "stream_11")
    assert sa["outliers"]["mad"] == 0.0


def test_93_s11_one_outlier(report):
    """Exactly 1 outlier: value 105.0 at index 5."""
    sa = get_stream_audit(report, "stream_11")
    assert len(sa["outliers"]["points"]) == 1
    p = sa["outliers"]["points"][0]
    assert p["index"] == 5
    assert p["value"] == 105.0


def test_94_s11_outlier_type_extreme(report):
    """MAD=0 with differing value → z-score = infinity → extreme_outlier."""
    sa = get_stream_audit(report, "stream_11")
    p = sa["outliers"]["points"][0]
    assert p["finding_type"] == "extreme_outlier"


def test_95_s11_outlier_z_score_null(report):
    """When z-score is infinity, it is represented as null in JSON."""
    sa = get_stream_audit(report, "stream_11")
    p = sa["outliers"]["points"][0]
    assert p["z_score"] is None, "Infinite z-score must be null in JSON"


def test_96_s11_findings(report):
    """Stream 11 has exactly 1 finding (extreme_outlier)."""
    sa = get_stream_audit(report, "stream_11")
    assert len(sa["findings"]) == 1
    assert sa["findings"][0]["finding_type"] == "extreme_outlier"


def test_97_s11_basic_stats(report):
    """Stream 11 mean = (100*10 + 105)/11 ≈ 100.454545."""
    sa = get_stream_audit(report, "stream_11")
    assert math.isclose(sa["basic_stats"]["mean"], 100.454545, abs_tol=1e-4)


# ===================================================================
# STREAM 12: INSUFFICIENT DATA_DIR
# ===================================================================


def test_98_s12_insufficient_data(report):
    """Stream 12 has 2 valid observations < min_observations (5) → insufficient_data."""
    sa = get_stream_audit(report, "stream_12")
    insuf = [f for f in sa["findings"] if f["finding_type"] == "insufficient_data"]
    assert len(insuf) == 1


def test_99_s12_insufficient_evidence(report):
    """Insufficient data evidence must contain valid_count and min_required."""
    sa = get_stream_audit(report, "stream_12")
    f = sa["findings"][0]
    assert f["evidence"]["valid_count"] == 2
    assert f["evidence"]["min_required"] == 5


def test_100_s12_basic_stats_computed(report):
    """Basic stats are still computed even with insufficient data."""
    sa = get_stream_audit(report, "stream_12")
    assert "basic_stats" in sa
    assert sa["basic_stats"]["mean"] == 27.5


def test_101_s12_population_variance(report):
    """Stream 12 population_variance = ((25-27.5)^2 + (30-27.5)^2)/2 = 6.25."""
    sa = get_stream_audit(report, "stream_12")
    assert sa["basic_stats"]["variance"] == 6.25


def test_102_s12_sample_variance(report):
    """Stream 12 sample_variance = 12.5/1 = 12.5 (N-1=1)."""
    sa = get_stream_audit(report, "stream_12")
    assert sa["basic_stats"]["sample_variance"] == 12.5


def test_103_s12_std_dev(report):
    """Stream 12 std_dev = sqrt(6.25) = 2.5 (population)."""
    sa = get_stream_audit(report, "stream_12")
    assert sa["basic_stats"]["std_dev"] == 2.5


def test_104_s12_no_percentiles(report):
    """Percentiles are skipped for insufficient data streams."""
    sa = get_stream_audit(report, "stream_12")
    assert "percentiles" not in sa


def test_105_s12_only_basic_stats(report):
    """Only basic_stats is computed. Other analyses are skipped."""
    sa = get_stream_audit(report, "stream_12")
    assert "basic_stats" in sa
    assert "percentiles" not in sa
    assert "ema" not in sa
    assert "outliers" not in sa


# ===================================================================
# CROSS-VALIDATION & GLOBAL FINDING TESTS
# ===================================================================


def test_106_global_findings_count(report):
    """Global findings array has exactly 7 entries."""
    assert len(report["findings"]) == 7


def test_107_global_findings_severity_order(report, config):
    """Global findings must be sorted by severity rank (ascending)."""
    sev_ranks = config["severity_ranks"]
    findings = report["findings"]
    for i in range(len(findings) - 1):
        r1 = sev_ranks.get(findings[i]["severity"], 99)
        r2 = sev_ranks.get(findings[i + 1]["severity"], 99)
        assert r1 <= r2, (
            f"Finding {i} severity {findings[i]['severity']} must come before {findings[i + 1]['severity']}"
        )


def test_108_global_findings_sort_includes_stream_id(report, config):
    """Global findings sorted by (severity_rank, finding_type, stream_id, sort_key)."""
    sev_ranks = config["severity_ranks"]
    findings = report["findings"]
    for i in range(len(findings) - 1):
        a, b = findings[i], findings[i + 1]
        ea, eb = a["evidence"], b["evidence"]
        sk_a = ea.get("index", ea.get("start_timestamp", ea.get("start_index", 0)))
        sk_b = eb.get("index", eb.get("start_timestamp", eb.get("start_index", 0)))
        if sk_a is None:
            sk_a = float('inf')
        if sk_b is None:
            sk_b = float('inf')
        key_a = (sev_ranks.get(a["severity"], 99), a["finding_type"], a["stream_id"], sk_a)
        key_b = (sev_ranks.get(b["severity"], 99), b["finding_type"], b["stream_id"], sk_b)
        assert key_a <= key_b, f"Global finding {i} sort key {key_a} > next {key_b}"


def test_109_all_findings_have_stream_id(report):
    """Every finding must have a stream_id field."""
    for f in report["findings"]:
        assert "stream_id" in f, f"Global finding missing stream_id: {f}"


def test_110_all_findings_have_evidence(report):
    """Every finding must have an evidence dict."""
    for f in report["findings"]:
        assert "evidence" in f
        assert isinstance(f["evidence"], dict)


def test_111_all_findings_have_severity(report):
    """Every finding must have a severity field from the config."""
    valid_sevs = {"critical", "high", "medium", "low", "info"}
    for f in report["findings"]:
        assert f["severity"] in valid_sevs


def test_112_finding_keys_exact(report):
    """Each finding must have exactly: finding_type, severity, stream_id, evidence."""
    expected_keys = {"finding_type", "severity", "stream_id", "evidence"}
    for f in report["findings"]:
        assert set(f.keys()) == expected_keys, (
            f"Finding keys {set(f.keys())} != expected {expected_keys}"
        )


def test_113_per_stream_findings_sum(report):
    """Sum of per-stream finding counts must equal total global findings."""
    per_stream = sum(len(a.get("findings", [])) for a in report["stream_audits"])
    assert per_stream == report["summary"]["total_findings"]


def test_114_findings_by_type_matches_array(report):
    """findings_by_type must match counts computed from the findings array."""
    fbt = {}
    for f in report["findings"]:
        fbt[f["finding_type"]] = fbt.get(f["finding_type"], 0) + 1
    assert report["summary"]["findings_by_type"] == fbt


def test_115_findings_by_severity_matches_array(report):
    """findings_by_severity must match counts from the findings array."""
    fbs = {}
    for f in report["findings"]:
        fbs[f["severity"]] = fbs.get(f["severity"], 0) + 1
    reported = report["summary"]["findings_by_severity"]
    for sev in ["critical", "high", "medium", "low", "info"]:
        assert reported.get(sev, 0) == fbs.get(sev, 0)


def test_116_all_streams_present(report):
    """All 12 stream_ids must be present in stream_audits."""
    sids = {a["stream_id"] for a in report["stream_audits"]}
    for i in range(1, 13):
        expected = f"stream_{i:02d}"
        assert expected in sids, f"Missing stream_audit for {expected}"


# ===================================================================
# ADDITIONAL PRECISION & EDGE CASE TESTS
# ===================================================================


def test_117_s01_variance_is_population_not_sample(report):
    """Config says variance_type='population'. variance field MUST use denominator N=20,
    giving 15.1875. An agent that always uses sample variance gets 15.986842."""
    sa = get_stream_audit(report, "stream_01")
    assert sa["basic_stats"]["variance"] != 15.986842, (
        "variance appears to use sample formula (N-1); must use population (N)"
    )
    assert sa["basic_stats"]["variance"] == 15.1875


def test_118_s01_both_variances_present(report):
    """Both variance (population) and sample_variance (N-1) must be reported."""
    sa = get_stream_audit(report, "stream_01")
    bs = sa["basic_stats"]
    assert "variance" in bs
    assert "sample_variance" in bs
    assert bs["variance"] != bs["sample_variance"], (
        "variance and sample_variance must differ (N vs N-1)"
    )


def test_119_s06_ema_alpha_not_span(report):
    """Verify EMA uses halflife formula, not span formula.
    With span alpha=2/6=0.3333: ema[1] = 0.3333*12 + 0.6667*10 = 10.6667.
    With halflife alpha: ema[1] ≈ 10.2589. Must not be ≈10.667."""
    sa = get_stream_audit(report, "stream_06")
    assert not math.isclose(sa["ema"][1], 10.6667, abs_tol=0.01), (
        "EMA appears to use span formula (2/(span+1)); must use halflife formula"
    )


def test_120_s06_ema_all_non_null(report):
    """Stream 06 has no null observations, so all EMA values must be non-null."""
    sa = get_stream_audit(report, "stream_06")
    for i, v in enumerate(sa["ema"]):
        assert v is not None, f"EMA[{i}] should not be null"


def test_121_s02_basic_stats_mean(report):
    """Stream 02 mean = (sum of all 20 values including outliers)/20 = 97.68."""
    sa = get_stream_audit(report, "stream_02")
    assert math.isclose(sa["basic_stats"]["mean"], 97.68, abs_tol=1e-4)


def test_122_s02_basic_stats_min_max(report):
    """Stream 02 min = -50.0, max = 200.0."""
    sa = get_stream_audit(report, "stream_02")
    assert sa["basic_stats"]["min"] == -50.0
    assert sa["basic_stats"]["max"] == 200.0


def test_123_s05_basic_stats(report):
    """Stream 05: 25 observations, mean ≈ 20.904."""
    sa = get_stream_audit(report, "stream_05")
    assert sa["basic_stats"]["count"] == 25
    assert math.isclose(sa["basic_stats"]["mean"], 20.904, abs_tol=1e-3)


def test_124_s08_basic_stats_variance(report):
    """Stream 08 population variance = 124.6875."""
    sa = get_stream_audit(report, "stream_08")
    assert math.isclose(sa["basic_stats"]["variance"], 124.6875, abs_tol=1e-4)


def test_125_s09_population_variance(report):
    """Stream 09 population variance ≈ 132.7906."""
    sa = get_stream_audit(report, "stream_09")
    assert math.isclose(sa["basic_stats"]["variance"], 132.7906, abs_tol=1e-3)


def test_126_s09_sample_variance(report):
    """Stream 09 sample variance ≈ 139.779579."""
    sa = get_stream_audit(report, "stream_09")
    assert math.isclose(sa["basic_stats"]["sample_variance"], 139.779579, abs_tol=1e-3)


def test_127_s10_mean(report):
    """Stream 10 (constant 42) mean = 42.0."""
    sa = get_stream_audit(report, "stream_10")
    assert sa["basic_stats"]["mean"] == 42.0


def test_128_s10_min_max(report):
    """Stream 10 min = max = 42.0."""
    sa = get_stream_audit(report, "stream_10")
    assert sa["basic_stats"]["min"] == 42.0
    assert sa["basic_stats"]["max"] == 42.0


def test_129_s11_population_variance(report):
    """Stream 11 pop_var ≈ 2.066116."""
    sa = get_stream_audit(report, "stream_11")
    assert math.isclose(sa["basic_stats"]["variance"], 2.066116, abs_tol=1e-4)


def test_130_s11_sample_variance(report):
    """Stream 11 sample_var ≈ 2.272727 (N-1=10)."""
    sa = get_stream_audit(report, "stream_11")
    assert math.isclose(sa["basic_stats"]["sample_variance"], 2.272727, abs_tol=1e-4)


def test_131_extreme_outlier_findings_critical(report):
    """All extreme_outlier findings must have severity 'critical'."""
    for f in report["findings"]:
        if f["finding_type"] == "extreme_outlier":
            assert f["severity"] == "critical"


def test_132_change_point_finding_high(report):
    """change_point findings must have severity 'high'."""
    for f in report["findings"]:
        if f["finding_type"] == "change_point":
            assert f["severity"] == "high"


def test_133_data_gap_finding_medium(report):
    """data_gap findings must have severity 'medium'."""
    for f in report["findings"]:
        if f["finding_type"] == "data_gap":
            assert f["severity"] == "medium"


def test_134_stale_data_finding_low(report):
    """stale_data findings must have severity 'low'."""
    for f in report["findings"]:
        if f["finding_type"] == "stale_data":
            assert f["severity"] == "low"


def test_135_insufficient_data_finding_info(report):
    """insufficient_data findings must have severity 'info'."""
    for f in report["findings"]:
        if f["finding_type"] == "insufficient_data":
            assert f["severity"] == "info"


def test_136_s03_min_max(report):
    """Stream 03: min=55.0, max=63.2 (from valid values only)."""
    sa = get_stream_audit(report, "stream_03")
    assert sa["basic_stats"]["min"] == 55.0
    assert sa["basic_stats"]["max"] == 63.2


def test_137_s04_min_max(report):
    """Stream 04: min=4.8, max=8.2."""
    sa = get_stream_audit(report, "stream_04")
    assert sa["basic_stats"]["min"] == 4.8
    assert sa["basic_stats"]["max"] == 8.2


def test_138_s07_variance(report):
    """Stream 07 population variance ≈ 0.084844."""
    sa = get_stream_audit(report, "stream_07")
    assert math.isclose(sa["basic_stats"]["variance"], 0.084844, abs_tol=1e-4)


def test_139_s07_no_findings(report):
    """Stream 07 has zero findings."""
    sa = get_stream_audit(report, "stream_07")
    assert len(sa["findings"]) == 0


def test_140_s06_basic_stats(report):
    """Stream 06: mean=11.8, population_variance ≈ 6.826667."""
    sa = get_stream_audit(report, "stream_06")
    assert math.isclose(sa["basic_stats"]["mean"], 11.8, abs_tol=1e-4)
    assert math.isclose(sa["basic_stats"]["variance"], 6.826667, abs_tol=1e-4)


def test_141_s03_rolling_std_at_boundary(report):
    """Rolling std at index 0: window [0,2], valid values [55.0,60.2,58.1].
    Pop std ≈ 2.135936."""
    sa = get_stream_audit(report, "stream_03")
    assert math.isclose(sa["rolling_stats"]["rolling_std"][0], 2.135936, abs_tol=1e-4)


def test_142_s03_rolling_uses_pop_std(report):
    """Rolling stats use POPULATION std_dev (divides by N within window),
    regardless of global variance_type setting."""
    sa = get_stream_audit(report, "stream_03")
    vals = [55.0, 60.2, 58.1]
    m = sum(vals) / 3
    pop_std = math.sqrt(sum((x - m) ** 2 for x in vals) / 3)
    samp_std = math.sqrt(sum((x - m) ** 2 for x in vals) / 2)
    assert math.isclose(sa["rolling_stats"]["rolling_std"][0], pop_std, abs_tol=1e-4)
    assert not math.isclose(sa["rolling_stats"]["rolling_std"][0], samp_std, abs_tol=1e-4)


def test_143_s04_cusum_warmup_mean_not_overall(report):
    """CUSUM target must be mean of first 10 observations (5.01), NOT overall mean (6.503).
    The change point at index 22 only works with warmup target."""
    sa = get_stream_audit(report, "stream_04")
    assert sa["change_points"][0]["index"] == 22, (
        "Change point index should be 22 (warmup target=5.01). "
        "A different index suggests the overall mean was used as target."
    )


def test_144_s05_gap_not_including_short_gap(report):
    """The 180s gap at timestamps ~1000540 to ~1000780 must NOT be reported
    because 180 < min_gap_duration (300)."""
    sa = get_stream_audit(report, "stream_05")
    for gap in sa["gaps"]:
        assert gap["duration"] != 180, "Short gap (180s) should not be reported"


def test_145_s08_stale_not_short_runs(report):
    """Only runs >= stale_count(6) are reported. Runs of 2-5 identical values
    that might exist earlier in the stream must not generate findings."""
    sa = get_stream_audit(report, "stream_08")
    for run in sa["stale_runs"]:
        assert run["run_length"] >= 6


def test_146_s12_findings_count(report):
    """Stream 12 has exactly 1 finding (insufficient_data)."""
    sa = get_stream_audit(report, "stream_12")
    assert len(sa["findings"]) == 1
    assert sa["findings"][0]["finding_type"] == "insufficient_data"


def test_147_s11_ten_values_not_outlier(report):
    """The 10 values of 100.0 must NOT be flagged as outliers (z=0 when MAD=0
    and value==median)."""
    sa = get_stream_audit(report, "stream_11")
    for p in sa["outliers"]["points"]:
        assert p["value"] != 100.0, "Value 100.0 (equal to median) must not be outlier"


def test_148_float_rounding(report):
    """All non-integer float values must be rounded to 6 decimal places."""
    sa = get_stream_audit(report, "stream_06")
    for v in sa["ema"]:
        if v is not None and v != int(v):
            s = str(v)
            if '.' in s:
                decimals = len(s.split('.')[1])
                assert decimals <= 6, f"Value {v} has more than 6 decimal places"


def test_149_s09_trend_not_null(report):
    """Stream 09 trend fields must all be non-null (20 data points, clear trend)."""
    sa = get_stream_audit(report, "stream_09")
    assert sa["trend"]["slope"] is not None
    assert sa["trend"]["intercept"] is not None
    assert sa["trend"]["r_squared"] is not None


def test_150_global_critical_findings_first(report):
    """The first findings in the global list must be critical severity."""
    findings = report["findings"]
    assert findings[0]["severity"] == "critical"
    assert findings[1]["severity"] == "critical"
    assert findings[2]["severity"] == "critical"


def test_151_global_info_findings_last(report):
    """The last finding must be info severity (insufficient_data)."""
    findings = report["findings"]
    assert findings[-1]["severity"] == "info"
    assert findings[-1]["finding_type"] == "insufficient_data"


def test_152_s02_outlier_strict_greater(report):
    """Outlier comparison uses strict > (not >=). A value with z exactly equal
    to threshold would NOT be an outlier."""
    sa = get_stream_audit(report, "stream_02")
    for p in sa["outliers"]["points"]:
        if p["z_score"] is not None:
            assert p["z_score"] > 3.5


def test_153_s10_count_15(report):
    """Stream 10 has exactly 15 observations."""
    sa = get_stream_audit(report, "stream_10")
    assert sa["basic_stats"]["count"] == 15


def test_154_s11_count_11(report):
    """Stream 11 has exactly 11 observations."""
    sa = get_stream_audit(report, "stream_11")
    assert sa["basic_stats"]["count"] == 11


def test_155_s04_cusum_evidence(report):
    """Change point evidence must contain index, timestamp, direction, cusum_value."""
    sa = get_stream_audit(report, "stream_04")
    ev = sa["findings"][0]["evidence"]
    assert "index" in ev
    assert "timestamp" in ev
    assert "direction" in ev
    assert "cusum_value" in ev


def test_156_every_stream_has_findings_key(report):
    """Every stream audit must have a 'findings' key (even if empty array)."""
    for sa in report["stream_audits"]:
        assert "findings" in sa, f"{sa['stream_id']} missing 'findings' key"


def test_157_s03_std_dev(report):
    """Stream 03 std_dev ≈ 2.206 (population)."""
    sa = get_stream_audit(report, "stream_03")
    assert math.isclose(sa["basic_stats"]["std_dev"], 2.206, abs_tol=0.001)


def test_158_s07_sample_variance(report):
    """Stream 07 sample variance ≈ 0.096964."""
    sa = get_stream_audit(report, "stream_07")
    assert math.isclose(sa["basic_stats"]["sample_variance"], 0.096964, abs_tol=1e-4)


def test_159_s08_sample_variance(report):
    """Stream 08 sample variance = 131.25."""
    sa = get_stream_audit(report, "stream_08")
    assert sa["basic_stats"]["sample_variance"] == 131.25


def test_160_s04_variance(report):
    """Stream 04 population variance ≈ 2.254989."""
    sa = get_stream_audit(report, "stream_04")
    assert math.isclose(sa["basic_stats"]["variance"], 2.254989, abs_tol=1e-4)


# ===================================================================
# C++ BINARY ENFORCEMENT TESTS
# ===================================================================


def test_161_build_binary_exists():
    """A compiled pipeline_audit binary must exist at /usr/local/bin/pipeline_audit."""
    binary = Path("/usr/local/bin/pipeline_audit")
    assert binary.exists(), "Compiled binary not found at /usr/local/bin/pipeline_audit"


def test_162_binary_is_elf():
    """The binary must be a compiled executable, not a script."""
    binary = Path("/usr/local/bin/pipeline_audit")
    assert binary.exists(), "Binary not found"
    with open(binary, "rb") as f:
        magic = f.read(4)
    assert magic == b'\x7fELF', (
        f"Binary must be a compiled ELF executable, got magic bytes: {magic!r}"
    )


def test_163_binary_runs_successfully():
    """The compiled binary must run without crashing (exit code 0)."""
    import subprocess
    result = subprocess.run(
        ["/usr/local/bin/pipeline_audit", "/app"],
        capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, (
        f"Binary exited with code {result.returncode}. stderr: {result.stderr[:500]}"
    )


def test_164_cpp_source_modified():
    """pipeline_audit.cpp must be modified from the stub (more than 25 lines)."""
    cpp_path = APP / "pipeline_audit.cpp"
    assert cpp_path.exists(), "pipeline_audit.cpp not found"
    with open(cpp_path) as f:
        lines = f.readlines()
    assert len(lines) > 50, (
        f"pipeline_audit.cpp has only {len(lines)} lines — appears to be the unmodified stub"
    )


def test_165_no_python_solution():
    """No .py files should exist in /app/ (solution must be C++, not Python)."""
    import glob
    py_files = glob.glob("/app/*.py") + glob.glob("/app/src/*.py")
    assert len(py_files) == 0, (
        f"Python solution files found in /app/: {py_files}. Solution must be C++."
    )
