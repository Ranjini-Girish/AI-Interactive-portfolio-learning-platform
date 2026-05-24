"""Tests for bash-log-pipeline-debugger task."""
import json
import math
import pathlib


ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
REPORT_PATH = OUT_DIR / "report.json"

FLOAT_TOL = 1e-3


def load_report():
    """Load and return the report JSON."""
    assert REPORT_PATH.is_file(), f"Missing output file: {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


R = load_report()


# ═══════════════════════════════════════════════════════════════════════
# Structural tests
# ═══════════════════════════════════════════════════════════════════════


def test_report_exists():
    """Verify the report file was created."""
    assert REPORT_PATH.is_file()


def test_report_valid_json():
    """Verify the report is valid JSON."""
    data = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_top_level_keys():
    """Verify the report has all required sections."""
    expected = {"summary", "service_stats", "incidents", "trace_summary"}
    assert set(R.keys()) == expected, f"Keys: {sorted(R.keys())}"


def test_summary_keys():
    """Verify summary has all required fields."""
    expected = {
        "total_events", "unique_traces", "services",
        "incidents", "time_range_start", "time_range_end",
    }
    assert set(R["summary"].keys()) == expected


def test_service_stat_keys():
    """Verify each service stat entry has required fields."""
    expected = {"service", "events", "errors", "error_rate", "avg_latency_ms"}
    for s in R["service_stats"]:
        assert set(s.keys()) == expected, f"Missing keys in {s['service']}"


# ═══════════════════════════════════════════════════════════════════════
# Summary tests
# ═══════════════════════════════════════════════════════════════════════


def test_total_events():
    """Verify the total event count is correct."""
    assert R["summary"]["total_events"] == 45, (
        f"Expected 45 total events, got {R['summary']['total_events']}"
    )


def test_unique_traces():
    """Verify the number of unique traces."""
    assert R["summary"]["unique_traces"] == 15


def test_service_count():
    """Verify 5 services were detected."""
    assert R["summary"]["services"] == 5


def test_incident_count():
    """Verify 3 incidents were detected."""
    assert R["summary"]["incidents"] == 3


def test_time_range_start():
    """Verify the earliest event timestamp."""
    assert R["summary"]["time_range_start"] == 1705305312


def test_time_range_end():
    """Verify the latest event timestamp."""
    assert R["summary"]["time_range_end"] == 1705311658


# ═══════════════════════════════════════════════════════════════════════
# Service statistics tests
# ═══════════════════════════════════════════════════════════════════════


def _svc(name):
    """Helper to get service stats by name."""
    for s in R["service_stats"]:
        if s["service"] == name:
            return s
    raise AssertionError(f"Service '{name}' not found in service_stats")


def test_five_services_present():
    """Verify all 5 services appear in stats."""
    names = [s["service"] for s in R["service_stats"]]
    assert set(names) == {"auth", "cache", "database", "queue", "webserver"}


def test_services_sorted():
    """Verify services are sorted alphabetically."""
    names = [s["service"] for s in R["service_stats"]]
    assert names == sorted(names), f"Service order wrong: {names}"


def test_auth_events():
    """Verify auth service event count."""
    assert _svc("auth")["events"] == 9


def test_auth_errors():
    """Verify auth service error count."""
    assert _svc("auth")["errors"] == 2


def test_auth_error_rate():
    """Verify auth error rate (2/9)."""
    assert math.isclose(_svc("auth")["error_rate"], 2 / 9, abs_tol=FLOAT_TOL)


def test_auth_avg_latency():
    """Verify auth average latency."""
    expected = (82 + 150 + 12 + 15 + 95 + 180 + 11 + 88 + 14) / 9
    assert math.isclose(
        _svc("auth")["avg_latency_ms"], expected, abs_tol=FLOAT_TOL
    )


def test_cache_events():
    """Verify cache service event count."""
    assert _svc("cache")["events"] == 8


def test_cache_errors():
    """Verify cache has zero errors."""
    assert _svc("cache")["errors"] == 0


def test_cache_error_rate():
    """Verify cache error rate is 0."""
    assert _svc("cache")["error_rate"] == 0


def test_database_events():
    """Verify database service event count."""
    assert _svc("database")["events"] == 10


def test_database_errors():
    """Verify database has exactly 1 error."""
    assert _svc("database")["errors"] == 1


def test_database_error_rate():
    """Verify database error rate (1/10 = 0.1)."""
    assert math.isclose(_svc("database")["error_rate"], 0.1, abs_tol=FLOAT_TOL)


def test_database_avg_latency():
    """Verify database average latency exceeds 200ms."""
    expected = (35 + 28 + 42 + 31 + 650 + 38 + 550 + 33 + 580 + 40) / 10
    assert math.isclose(
        _svc("database")["avg_latency_ms"], expected, abs_tol=FLOAT_TOL
    )


def test_queue_events():
    """Verify queue service event count."""
    assert _svc("queue")["events"] == 3


def test_queue_errors():
    """Verify queue has exactly 1 error."""
    assert _svc("queue")["errors"] == 1


def test_queue_error_rate():
    """Verify queue error rate (1/3)."""
    assert math.isclose(
        _svc("queue")["error_rate"], 1 / 3, abs_tol=FLOAT_TOL
    )


def test_webserver_events():
    """Verify webserver service event count."""
    assert _svc("webserver")["events"] == 15


def test_webserver_errors():
    """Verify webserver has exactly 1 error (500 status)."""
    assert _svc("webserver")["errors"] == 1


def test_webserver_error_rate():
    """Verify webserver error rate (1/15)."""
    assert math.isclose(
        _svc("webserver")["error_rate"], 1 / 15, abs_tol=FLOAT_TOL
    )


def test_webserver_avg_latency():
    """Verify webserver average latency."""
    expected = (
        12 + 145 + 89 + 67 + 52 + 38 + 312 + 95 + 230 + 8 + 44 + 290
        + 110 + 88 + 65
    ) / 15
    assert math.isclose(
        _svc("webserver")["avg_latency_ms"], expected, abs_tol=FLOAT_TOL
    )


# ═══════════════════════════════════════════════════════════════════════
# Cross-field consistency tests
# ═══════════════════════════════════════════════════════════════════════


def test_total_events_matches_sum():
    """Verify sum of per-service events equals total."""
    svc_total = sum(s["events"] for s in R["service_stats"])
    assert svc_total == R["summary"]["total_events"]


def test_error_rate_consistency():
    """Verify error_rate = errors / events for each service."""
    for s in R["service_stats"]:
        if s["events"] > 0:
            expected = s["errors"] / s["events"]
            assert math.isclose(s["error_rate"], expected, abs_tol=FLOAT_TOL), (
                f"{s['service']}: error_rate {s['error_rate']} != {expected}"
            )


def test_trace_events_sum():
    """Verify sum of trace event counts equals total events."""
    trace_total = sum(t["events"] for t in R["trace_summary"])
    assert trace_total == R["summary"]["total_events"], (
        f"Trace total {trace_total} != summary total {R['summary']['total_events']}"
    )


# ═══════════════════════════════════════════════════════════════════════
# Incident tests
# ═══════════════════════════════════════════════════════════════════════


def test_incident_list_length():
    """Verify exactly 3 incidents detected."""
    assert len(R["incidents"]) == 3


def test_auth_high_error_rate_incident():
    """Verify auth high_error_rate incident exists."""
    found = [
        i for i in R["incidents"]
        if i["service"] == "auth" and i["type"] == "high_error_rate"
    ]
    assert len(found) == 1, "Missing auth high_error_rate incident"
    assert math.isclose(found[0]["value"], 2 / 9, abs_tol=FLOAT_TOL)


def test_database_high_latency_incident():
    """Verify database high_avg_latency incident exists."""
    found = [
        i for i in R["incidents"]
        if i["service"] == "database" and i["type"] == "high_avg_latency"
    ]
    assert len(found) == 1, "Missing database high_avg_latency incident"
    assert found[0]["value"] > 200.0


def test_queue_high_error_rate_incident():
    """Verify queue high_error_rate incident exists."""
    found = [
        i for i in R["incidents"]
        if i["service"] == "queue" and i["type"] == "high_error_rate"
    ]
    assert len(found) == 1, "Missing queue high_error_rate incident"
    assert math.isclose(found[0]["value"], 1 / 3, abs_tol=FLOAT_TOL)


def test_no_webserver_error_incident():
    """Verify webserver is NOT flagged as high_error_rate."""
    found = [
        i for i in R["incidents"]
        if i["service"] == "webserver" and i["type"] == "high_error_rate"
    ]
    assert len(found) == 0, "Webserver should not be flagged for high error rate"


def test_no_database_error_incident():
    """Verify database is NOT flagged as high_error_rate (rate equals threshold)."""
    found = [
        i for i in R["incidents"]
        if i["service"] == "database" and i["type"] == "high_error_rate"
    ]
    assert len(found) == 0, (
        "Database error rate 0.1 equals threshold 0.1 — should not be flagged"
    )


# ═══════════════════════════════════════════════════════════════════════
# Trace summary tests
# ═══════════════════════════════════════════════════════════════════════


def _trace(tid):
    """Helper to get trace summary by trace_id."""
    for t in R["trace_summary"]:
        if t["trace_id"] == tid:
            return t
    raise AssertionError(f"Trace '{tid}' not found")


def test_trace_count():
    """Verify 15 traces in the summary."""
    assert len(R["trace_summary"]) == 15


def test_traces_sorted():
    """Verify traces are sorted by trace_id."""
    ids = [t["trace_id"] for t in R["trace_summary"]]
    assert ids == sorted(ids)


def test_trace_001():
    """Verify tr_001: 2 events, 2 services, no error."""
    t = _trace("tr_001")
    assert t["events"] == 2
    assert t["services"] == 2
    assert t["has_error"] is False


def test_trace_002():
    """Verify tr_002: 4 events (web, auth, cache, db), no error."""
    t = _trace("tr_002")
    assert t["events"] == 4
    assert t["services"] == 4
    assert t["has_error"] is False


def test_trace_003():
    """Verify tr_003: 2 events (web, auth), has error."""
    t = _trace("tr_003")
    assert t["events"] == 2
    assert t["services"] == 2
    assert t["has_error"] is True


def test_trace_006():
    """Verify tr_006: 4 events (web, auth, cache, db), no error."""
    t = _trace("tr_006")
    assert t["events"] == 4
    assert t["services"] == 4


def test_trace_008():
    """Verify tr_008: 5 events (all 5 services), no error."""
    t = _trace("tr_008")
    assert t["events"] == 5
    assert t["services"] == 5
    assert t["has_error"] is False


def test_trace_009():
    """Verify tr_009: 3 events (web, auth, db), has error."""
    t = _trace("tr_009")
    assert t["events"] == 3
    assert t["services"] == 3
    assert t["has_error"] is True


def test_trace_014():
    """Verify tr_014: 5 events (all 5 services), no error."""
    t = _trace("tr_014")
    assert t["events"] == 5
    assert t["services"] == 5
    assert t["has_error"] is False


def test_trace_015():
    """Verify tr_015: 2 events (web, queue), has error."""
    t = _trace("tr_015")
    assert t["events"] == 2
    assert t["services"] == 2
    assert t["has_error"] is True


def test_no_extra_error_traces():
    """Verify only traces 003, 009, 015 have errors."""
    error_traces = [t["trace_id"] for t in R["trace_summary"] if t["has_error"]]
    assert sorted(error_traces) == ["tr_003", "tr_009", "tr_015"]


# ═══════════════════════════════════════════════════════════════════════
# Pipeline script integrity tests
# ═══════════════════════════════════════════════════════════════════════


def test_pipeline_script_exists():
    """Verify the main pipeline script exists."""
    assert (ROOT / "pipeline.sh").is_file()


def test_parser_scripts_exist():
    """Verify all parser scripts exist."""
    for svc in ["webserver", "database", "auth", "cache", "queue"]:
        p = ROOT / "parsers" / f"parse_{svc}.sh"
        assert p.is_file(), f"Missing parser: {p}"


def test_transform_scripts_exist():
    """Verify transform scripts exist."""
    for name in ["normalize_timestamps", "deduplicate", "enrich_events"]:
        p = ROOT / "transforms" / f"{name}.sh"
        assert p.is_file(), f"Missing transform: {p}"


def test_analysis_scripts_exist():
    """Verify analysis scripts exist."""
    for name in ["correlate", "aggregate", "detect_incidents"]:
        p = ROOT / "analysis" / f"{name}.sh"
        assert p.is_file(), f"Missing analysis script: {p}"


def test_scripts_are_bash():
    """Verify key scripts use bash shebang (not Python wrappers)."""
    for script in [
        ROOT / "pipeline.sh",
        ROOT / "parsers" / "parse_auth.sh",
        ROOT / "transforms" / "normalize_timestamps.sh",
        ROOT / "analysis" / "correlate.sh",
    ]:
        content = script.read_text(encoding="utf-8")
        assert content.startswith("#!/bin/bash"), (
            f"{script.name} must use bash, not a Python wrapper"
        )
        assert "import json" not in content, (
            f"{script.name} must not be a Python script"
        )
