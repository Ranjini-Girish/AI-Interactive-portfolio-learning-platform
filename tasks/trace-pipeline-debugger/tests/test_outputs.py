"""Tests for the trace pipeline debugger task."""
import json
from pathlib import Path

import pytest

REPORT_PATH = Path("/app/output/trace_report.json")


@pytest.fixture(scope="session")
def report():
    """Load the generated report."""
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def results(report):
    return report["results"]


# ═══════════════════════════════════════════════════════════════
# File existence & format
# ═══════════════════════════════════════════════════════════════
def test_output_file_exists():
    """Verify the output report file was created."""
    assert REPORT_PATH.exists()


def test_report_is_valid_json():
    """Verify the output is valid JSON."""
    json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def test_report_top_level_keys(report):
    """Verify report has required top-level keys."""
    assert set(report.keys()) == {"metadata", "results", "integrity"}


# ═══════════════════════════════════════════════════════════════
# Metadata
# ═══════════════════════════════════════════════════════════════
def test_metadata_fields(report):
    """Verify metadata contains required fields."""
    md = report["metadata"]
    assert "generated_at" in md
    assert "config_hash" in md
    assert md["span_files_processed"] == 7
    assert md["total_spans_parsed"] == 77


# ═══════════════════════════════════════════════════════════════
# Trace summary
# ═══════════════════════════════════════════════════════════════
def test_trace_count(results):
    """Verify all 20 traces were constructed."""
    assert results["trace_summary"]["total_traces"] == 20


def test_complete_traces(results):
    """All traces should have root spans."""
    assert results["trace_summary"]["complete_traces"] == 20
    assert results["trace_summary"]["incomplete_traces"] == 0


def test_avg_spans_per_trace(results):
    """Avg should be 77/20 = 3.85."""
    avg = results["trace_summary"]["avg_spans_per_trace"]
    assert abs(avg - 3.85) < 0.01


# ═══════════════════════════════════════════════════════════════
# Service stats — span counts
# ═══════════════════════════════════════════════════════════════
def test_service_list(results):
    """Verify all 7 services are present."""
    services = set(results["service_stats"].keys())
    expected = {
        "api-gateway", "auth-service", "user-service",
        "order-service", "inventory-service",
        "payment-service", "notification-service"
    }
    assert services == expected


def test_gateway_span_count(results):
    """Gateway should have all 20 spans (including error ones)."""
    assert results["service_stats"]["api-gateway"]["span_count"] == 20


def test_auth_span_count(results):
    assert results["service_stats"]["auth-service"]["span_count"] == 20


def test_user_span_count(results):
    assert results["service_stats"]["user-service"]["span_count"] == 8


def test_order_span_count(results):
    assert results["service_stats"]["order-service"]["span_count"] == 12


def test_inventory_span_count(results):
    assert results["service_stats"]["inventory-service"]["span_count"] == 7


def test_payment_span_count(results):
    assert results["service_stats"]["payment-service"]["span_count"] == 5


def test_notification_span_count(results):
    assert results["service_stats"]["notification-service"]["span_count"] == 5


# ═══════════════════════════════════════════════════════════════
# Error counts and rates
# ═══════════════════════════════════════════════════════════════
def test_gateway_errors(results):
    """Gateway has 2 error spans (traces 005, 014)."""
    gw = results["service_stats"]["api-gateway"]
    assert gw["error_count"] == 2
    assert abs(gw["error_rate"] - 0.1) < 0.001


def test_order_errors(results):
    """Order has 1 error span (trace 010)."""
    ors = results["service_stats"]["order-service"]
    assert ors["error_count"] == 1


def test_payment_errors(results):
    """Payment has 1 error span (trace 017)."""
    pm = results["service_stats"]["payment-service"]
    assert pm["error_count"] == 1
    assert abs(pm["error_rate"] - 0.2) < 0.001


def test_auth_no_errors(results):
    """Auth service should have zero errors."""
    assert results["service_stats"]["auth-service"]["error_count"] == 0


# ═══════════════════════════════════════════════════════════════
# Latency values — verifies correct duration computation and sort
# ═══════════════════════════════════════════════════════════════
def test_gateway_latency_range(results):
    """Gateway latencies should be in realistic ms range."""
    lat = results["service_stats"]["api-gateway"]["latency"]
    assert lat["min"] == 150
    assert lat["max"] == 2400


def test_gateway_p50(results):
    """Gateway P50 must be 250 (requires correct numeric sort)."""
    assert results["service_stats"]["api-gateway"]["latency"]["p50"] == 250


def test_gateway_p99(results):
    """Gateway P99 must be 2400."""
    assert results["service_stats"]["api-gateway"]["latency"]["p99"] == 2400


def test_auth_latency_range(results):
    lat = results["service_stats"]["auth-service"]["latency"]
    assert lat["min"] == 18
    assert lat["max"] == 48


def test_user_p50(results):
    """User P50 should be 60."""
    assert results["service_stats"]["user-service"]["latency"]["p50"] == 60


def test_order_p50(results):
    """Order P50 should be 120."""
    assert results["service_stats"]["order-service"]["latency"]["p50"] == 120


def test_percentiles_ordered(results):
    """For every service, p50 <= p90 <= p95 <= p99."""
    for svc, data in results["service_stats"].items():
        lat = data["latency"]
        assert lat["p50"] <= lat["p90"] <= lat["p95"] <= lat["p99"], \
            f"{svc}: percentiles not in order"


def test_latencies_are_milliseconds(results):
    """All latency values should be in ms range (> 1), not seconds."""
    for svc, data in results["service_stats"].items():
        lat = data["latency"]
        assert lat["mean"] > 1, f"{svc} mean latency {lat['mean']} looks like seconds, not ms"
        assert lat["min"] > 1, f"{svc} min latency too small"


# ═══════════════════════════════════════════════════════════════
# Self-consistency checks
# ═══════════════════════════════════════════════════════════════
def test_error_rate_consistency(results):
    """error_rate should equal error_count / span_count for each service."""
    for svc, data in results["service_stats"].items():
        if data["span_count"] > 0:
            expected = data["error_count"] / data["span_count"]
            assert abs(data["error_rate"] - expected) < 0.001, \
                f"{svc}: error_rate {data['error_rate']} != {expected}"


def test_total_spans_across_services(results):
    """Sum of all service span_counts should equal 77."""
    total = sum(d["span_count"] for d in results["service_stats"].values())
    assert total == 77


# ═══════════════════════════════════════════════════════════════
# Dependency graph
# ═══════════════════════════════════════════════════════════════
def test_dependency_graph_structure(results):
    """Dependency graph should have edges with source, target, call_count."""
    graph = results["dependency_graph"]
    assert isinstance(graph, list)
    for edge in graph:
        assert "source" in edge
        assert "target" in edge
        assert "call_count" in edge


def test_dependency_edge_count(results):
    """Should have exactly 6 inter-service dependency edges."""
    assert len(results["dependency_graph"]) == 6


def test_gateway_to_auth_edge(results):
    """Gateway calls auth 20 times."""
    graph = results["dependency_graph"]
    edge = next((e for e in graph if e["source"] == "api-gateway" and e["target"] == "auth-service"), None)
    assert edge is not None, "Missing api-gateway -> auth-service edge"
    assert edge["call_count"] == 20


def test_gateway_to_user_edge(results):
    """Gateway calls user-service 8 times."""
    graph = results["dependency_graph"]
    edge = next((e for e in graph if e["source"] == "api-gateway" and e["target"] == "user-service"), None)
    assert edge is not None
    assert edge["call_count"] == 8


def test_order_to_payment_edge(results):
    """Order calls payment 5 times."""
    graph = results["dependency_graph"]
    edge = next((e for e in graph if e["source"] == "order-service" and e["target"] == "payment-service"), None)
    assert edge is not None
    assert edge["call_count"] == 5


# ═══════════════════════════════════════════════════════════════
# Anomaly detection
# ═══════════════════════════════════════════════════════════════
def test_anomaly_count(results):
    """Exactly 1 anomaly should be detected (gateway 2400ms span)."""
    assert len(results["anomalies"]) == 1


def test_anomaly_is_gateway(results):
    """The detected anomaly should be in api-gateway service."""
    anom = results["anomalies"][0]
    assert anom["service"] == "api-gateway"
    assert anom["span_id"] == "sp-014-gw"


def test_anomaly_z_score(results):
    """Anomaly z-score should be above threshold."""
    anom = results["anomalies"][0]
    assert anom["z_score"] > anom["threshold"]


def test_anomaly_latency_ms(results):
    """Anomalous span latency should be 2400ms."""
    anom = results["anomalies"][0]
    assert anom["latency_ms"] == 2400


# ═══════════════════════════════════════════════════════════════
# Integrity hash
# ═══════════════════════════════════════════════════════════════
def test_integrity_hash_format(report):
    """Hash should start with 'sha256:' followed by 64 hex chars."""
    h = report["integrity"]["results_hash"]
    assert h.startswith("sha256:")
    hex_part = h[7:]
    assert len(hex_part) == 64
    assert all(c in "0123456789abcdef" for c in hex_part)


def test_integrity_hash_deterministic(report):
    """Hash should be deterministic (same results -> same hash)."""
    h = report["integrity"]["results_hash"]
    assert h.startswith("sha256:")
    assert len(h) == 71


# ═══════════════════════════════════════════════════════════════
# Language verification
# ═══════════════════════════════════════════════════════════════
def test_solution_is_javascript():
    """Verify the solution uses JavaScript (not Python)."""
    js_files = list(Path("/app/src").rglob("*.js"))
    assert len(js_files) > 0, "No .js files found in /app/src"
