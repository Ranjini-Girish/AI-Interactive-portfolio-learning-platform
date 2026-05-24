"""Tests for the DAG Pipeline Event Processor."""
import json
import hashlib
import os
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_ROOT", "/app"))
REPORT_PATH = APP / "output" / "pipeline_report.json"
PIPELINE_PATH = APP / "data" / "pipeline.json"
EVENTS_PATH = APP / "data" / "events.json"


@pytest.fixture(scope="session")
def report():
    """Load the generated pipeline report."""
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def pipeline():
    """Load the pipeline definition."""
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def events():
    """Load the event data."""
    return json.loads(EVENTS_PATH.read_text(encoding="utf-8"))


# === STRUCTURAL TESTS ===

def test_01_report_exists():
    """Report file must exist at the specified path."""
    assert REPORT_PATH.exists()


def test_02_valid_json(report):
    """Report must be valid JSON."""
    assert isinstance(report, dict)


def test_03_top_level_keys(report):
    """Report must have exactly the eight prescribed top-level keys in order."""
    expected = [
        "pipeline_id", "total_events", "node_stats", "sink_stats",
        "category_stats", "routing_summary", "latency_summary", "integrity_hash"
    ]
    assert list(report.keys()) == expected


def test_04_pipeline_id(report):
    """pipeline_id must match the pipeline config."""
    assert report["pipeline_id"] == "evt-proc-v3"


def test_05_total_events(report):
    """25 events must be processed."""
    assert report["total_events"] == 25


# === NODE STATS ===

def test_06_node_stats_keys(report, pipeline):
    """All pipeline nodes must appear in node_stats."""
    expected_nodes = sorted(n["node_id"] for n in pipeline["nodes"])
    assert sorted(report["node_stats"].keys()) == expected_nodes


def test_07_node_stats_sorted(report):
    """node_stats keys must be sorted alphabetically."""
    assert list(report["node_stats"].keys()) == sorted(report["node_stats"].keys())


def test_08_ingest_events_processed(report):
    """Source node processes every event through every applicable path: 75 total."""
    assert report["node_stats"]["ingest"]["events_processed"] == 75


def test_09_validate_events_processed(report):
    """validate node receives 25 events (one per event)."""
    assert report["node_stats"]["validate"]["events_processed"] == 25


def test_10_enrich_events_processed(report):
    """enrich node receives 50 events (25 events x 2 paths through enrich)."""
    assert report["node_stats"]["enrich"]["events_processed"] == 50


def test_11_aggregate_events_processed(report):
    """aggregate node receives 50 events (25 via validate + 25 via enrich)."""
    assert report["node_stats"]["aggregate"]["events_processed"] == 50


def test_12_ingest_latency_contribution(report):
    """ingest: weight=1.0, latency=round(1.0*12)=12, contribution=75*12=900."""
    assert report["node_stats"]["ingest"]["total_latency_contribution_ms"] == 900


def test_13_score_latency_contribution(report):
    """score: weight=4.0, latency=round(4.0*12)=48, contribution=50*48=2400."""
    assert report["node_stats"]["score"]["total_latency_contribution_ms"] == 2400


def test_14_validate_latency_contribution(report):
    """validate: weight=2.5, latency=round(2.5*12)=30, contribution=25*30=750."""
    assert report["node_stats"]["validate"]["total_latency_contribution_ms"] == 750


# === ROUTING ===

def test_15_routing_sink_a_count(report):
    """Events with priority > 7 routed to sink_a via each of 2 paths = 16."""
    assert report["routing_summary"]["sink_a_count"] == 16


def test_16_routing_sink_b_count(report):
    """Events with priority <= 7 routed to sink_b via each of 2 paths = 34."""
    assert report["routing_summary"]["sink_b_count"] == 34


def test_17_routing_archive_count(report):
    """All 25 events reach archive via the enrich path."""
    assert report["routing_summary"]["archive_count"] == 25


def test_18_routing_sum_consistency(report):
    """sink_a + sink_b must equal 2 * total_events (each event takes 2 routed paths)."""
    total = report["routing_summary"]["sink_a_count"] + report["routing_summary"]["sink_b_count"]
    assert total == 2 * report["total_events"]


# === SINK STATS ===

def test_19_sink_stats_keys(report):
    """Exactly three sinks must be reported."""
    assert sorted(report["sink_stats"].keys()) == ["archive", "sink_a", "sink_b"]


def test_20_archive_events_received(report):
    """Archive receives all 25 events."""
    assert report["sink_stats"]["archive"]["events_received"] == 25


def test_21_sink_a_events_received(report):
    """sink_a receives 16 events (8 high-priority events x 2 paths)."""
    assert report["sink_stats"]["sink_a"]["events_received"] == 16


def test_22_sink_b_events_received(report):
    """sink_b receives 34 events."""
    assert report["sink_stats"]["sink_b"]["events_received"] == 34


def test_23_archive_max_window_throughput(report):
    """Archive max sliding window throughput must be 13."""
    assert report["sink_stats"]["archive"]["max_window_throughput"] == 13


def test_24_sink_a_max_window_throughput(report):
    """sink_a max sliding window throughput must be 8."""
    assert report["sink_stats"]["sink_a"]["max_window_throughput"] == 8


def test_25_sink_b_max_window_throughput(report):
    """sink_b max sliding window throughput must be 18."""
    assert report["sink_stats"]["sink_b"]["max_window_throughput"] == 18


# === CATEGORY STATS ===

def test_26_category_stats_keys(report):
    """Three categories must be present."""
    assert sorted(report["category_stats"].keys()) == [
        "environmental", "hydraulic", "mechanical"
    ]


def test_27_environmental_count(report):
    """13 environmental events."""
    assert report["category_stats"]["environmental"]["count"] == 13


def test_28_hydraulic_count(report):
    """6 hydraulic events."""
    assert report["category_stats"]["hydraulic"]["count"] == 6


def test_29_mechanical_count(report):
    """6 mechanical events."""
    assert report["category_stats"]["mechanical"]["count"] == 6


def test_30_environmental_avg_priority(report):
    """Environmental avg_priority = (3+8+9+4+6+8+5+6+7+10+5+7+6)/13 = 6.4615."""
    assert abs(report["category_stats"]["environmental"]["avg_priority"] - 6.4615) < 0.001


def test_31_hydraulic_avg_priority(report):
    """Hydraulic avg_priority = (2+10+3+2+9+8)/6 = 5.6667."""
    assert abs(report["category_stats"]["hydraulic"]["avg_priority"] - 5.6667) < 0.001


def test_32_mechanical_avg_priority(report):
    """Mechanical avg_priority = (5+7+4+1+9+3)/6 = 4.8333."""
    assert abs(report["category_stats"]["mechanical"]["avg_priority"] - 4.8333) < 0.001


def test_33_environmental_weighted_harmonic_mean(report):
    """Environmental weighted_avg_latency_ms must use harmonic mean formula."""
    val = report["category_stats"]["environmental"]["weighted_avg_latency_ms"]
    assert abs(val - 84.2088) < 0.1, (
        f"Expected ~84.2088 (weighted harmonic mean), got {val}. "
        "Arithmetic mean would give a different value."
    )


def test_34_hydraulic_weighted_harmonic_mean(report):
    """Hydraulic weighted_avg_latency_ms must use harmonic mean formula."""
    val = report["category_stats"]["hydraulic"]["weighted_avg_latency_ms"]
    assert abs(val - 84.0602) < 0.1


def test_35_mechanical_weighted_harmonic_mean(report):
    """Mechanical weighted_avg_latency_ms must use harmonic mean formula."""
    val = report["category_stats"]["mechanical"]["weighted_avg_latency_ms"]
    assert abs(val - 84.2507) < 0.1


# === LATENCY SUMMARY ===

def test_36_avg_end_to_end_latency(report):
    """Average end-to-end latency across all events, rounded to 4 decimal places."""
    assert abs(report["latency_summary"]["avg_end_to_end_latency_ms"] - 159.36) < 0.01


def test_37_max_end_to_end_latency(report):
    """Maximum end-to-end latency."""
    assert report["latency_summary"]["max_end_to_end_latency_ms"] == 160


def test_38_min_end_to_end_latency(report):
    """Minimum end-to-end latency."""
    assert report["latency_summary"]["min_end_to_end_latency_ms"] == 158


# === INTEGRITY HASH ===

def test_39_integrity_hash_present(report):
    """Integrity hash must be a 64-char hex string."""
    h = report["integrity_hash"]
    assert isinstance(h, str) and len(h) == 64


def test_40_integrity_hash_value(report):
    """Integrity hash must match expected SHA-256."""
    expected = "05fd2eac295cb6cf4d44c4cadd2f4665ccff70d03e62e7dd518afc927ed0c097"
    assert report["integrity_hash"] == expected, (
        f"Hash mismatch: expected {expected}, got {report['integrity_hash']}"
    )


def test_41_integrity_hash_self_consistent(report, pipeline, events):
    """Recompute integrity hash from report data and verify it matches."""
    nodes = {n["node_id"]: n for n in pipeline["nodes"]}
    lat_per = pipeline["latency_per_unit_weight_ms"]
    routing_rules = pipeline["routing_rules"]

    node_lat = {}
    for nid, n in nodes.items():
        node_lat[nid] = round(n["weight"] * lat_per)

    source = next(n for n in nodes.values() if n["type"] == "source")

    def find_paths(nid, path):
        path = path + [nid]
        n = nodes[nid]
        if not n["outputs"]:
            yield path
            return
        for out in n["outputs"]:
            yield from find_paths(out, path)

    all_paths = list(find_paths(source["node_id"], []))

    sorted_events = sorted(events, key=lambda e: (e["timestamp"], e["event_id"]))

    lines = []
    for evt in sorted_events:
        sinks = []
        for path in all_paths:
            skip = False
            for i, nid in enumerate(path):
                if nid in routing_rules:
                    rule = routing_rules[nid]
                    val = evt["payload"][rule["field"]]
                    dest = rule["above"] if val > rule["threshold"] else rule["at_or_below"]
                    if i + 1 < len(path) and path[i + 1] != dest:
                        skip = True
                        break
            if skip:
                continue
            cum = sum(node_lat[nid] for nid in path)
            sinks.append((path[-1], cum))

        sinks.sort(key=lambda x: x[0])
        for sink_id, e2e in sinks:
            lines.append(f"{evt['event_id']}|{sink_id}|{e2e}|{evt['payload']['priority']}")

    expected_hash = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    assert report["integrity_hash"] == expected_hash


# === JSON FORMAT ===

def test_42_trailing_newline():
    """Output must end with exactly one trailing newline."""
    content = REPORT_PATH.read_bytes()
    assert content.endswith(b"\n")
    assert not content.endswith(b"\n\n")


def test_43_two_space_indent(report):
    """JSON must use 2-space indentation."""
    content = REPORT_PATH.read_text(encoding="utf-8")
    expected = json.dumps(json.loads(content), indent=2) + "\n"
    assert content == expected


# === CROSS-VALIDATION ===

def test_44_node_latency_formula(report, pipeline):
    """Verify node latency contributions match the formula: events * round(weight * base)."""
    base = pipeline["latency_per_unit_weight_ms"]
    for node in pipeline["nodes"]:
        nid = node["node_id"]
        expected_lat = round(node["weight"] * base)
        ns = report["node_stats"][nid]
        assert ns["total_latency_contribution_ms"] == ns["events_processed"] * expected_lat, (
            f"Node {nid}: expected {ns['events_processed']}*{expected_lat}="
            f"{ns['events_processed'] * expected_lat}, "
            f"got {ns['total_latency_contribution_ms']}"
        )


def test_45_events_received_consistency(report):
    """Sum of events_received across sinks must equal sum of all sink paths."""
    total_sink_events = sum(
        s["events_received"] for s in report["sink_stats"].values()
    )
    routing = report["routing_summary"]
    assert total_sink_events == (
        routing["sink_a_count"] + routing["sink_b_count"] + routing["archive_count"]
    )


def test_46_category_count_sum(report):
    """Sum of category counts must equal total_events."""
    total = sum(c["count"] for c in report["category_stats"].values())
    assert total == report["total_events"]


# === LANGUAGE VERIFICATION ===

def test_47_solution_is_javascript():
    """Solution must be implemented in JavaScript."""
    js_files = list((APP / "src").rglob("*.js"))
    assert len(js_files) > 0, "No .js files found in /app/src"


def test_48_no_python_solution():
    """No Python scripts should implement the solution."""
    for fn in APP.iterdir():
        if fn.suffix == ".py" and fn.name not in ("__init__.py", "test_outputs.py"):
            content = fn.read_text(encoding="utf-8", errors="replace")
            assert "pipeline" not in content.lower() or "report" not in content.lower(), (
                f"Found Python file {fn.name} that appears to implement the pipeline"
            )


# === ANTI-CHEAT ===

def test_49_data_files_unmodified(pipeline, events):
    """Input data files must not be modified."""
    assert len(pipeline["nodes"]) == 9
    assert len(events) == 25
    assert pipeline["pipeline_id"] == "evt-proc-v3"


def test_50_source_files_present():
    """Core JavaScript source files must exist."""
    required = [
        "main.js", "pipeline.js", "events.js", "processor.js",
        "routing.js", "stats.js", "window.js", "category.js",
        "latency.js", "hash.js", "report.js"
    ]
    for fn in required:
        assert (APP / "src" / fn).exists(), f"Missing source file: {fn}"


def test_51_events_js_build_tag():
    """events.js must retain its build-time canary tag."""
    content = (APP / "src" / "events.js").read_text(encoding="utf-8")
    assert "build-tag: dag-a7f3e2d1b9c4" in content


def test_52_pipeline_js_build_tag():
    """pipeline.js must retain its build-time canary tag."""
    content = (APP / "src" / "pipeline.js").read_text(encoding="utf-8")
    assert "build-tag: dag-c8e5f1a3d6b2" in content


def test_53_routing_js_build_tag():
    """routing.js must retain its build-time canary tag."""
    content = (APP / "src" / "routing.js").read_text(encoding="utf-8")
    assert "build-tag: dag-d4b7c9e2f1a5" in content


def test_54_category_js_build_tag():
    """category.js must retain its build-time canary tag."""
    content = (APP / "src" / "category.js").read_text(encoding="utf-8")
    assert "build-tag: dag-e6a2d8f3c5b1" in content


def test_55_hash_js_build_tag():
    """hash.js must retain its build-time canary tag."""
    content = (APP / "src" / "hash.js").read_text(encoding="utf-8")
    assert "build-tag: dag-f1c3b5a7d9e2" in content


def test_56_latency_js_build_tag():
    """latency.js must retain its build-time canary tag."""
    content = (APP / "src" / "latency.js").read_text(encoding="utf-8")
    assert "build-tag: dag-b9d1e4f6a3c7" in content


def test_57_window_js_build_tag():
    """window.js must retain its build-time canary tag."""
    content = (APP / "src" / "window.js").read_text(encoding="utf-8")
    assert "build-tag: dag-a5e7c2d4f8b1" in content


def test_58_unmodified_files_intact():
    """Infrastructure files that should not be modified must retain original SHA-256."""
    expected = {
        "main.js": "c503909c63a5de54caac2220413aa94ca70a85c6b82123f11a0aec0f6e6c8c9d",
        "processor.js": "90115796d71cdc6b32625ea2a23a4b0310ed8c5477dcaace571a77ced1855579",
        "report.js": "10f21a8c3c2b7934020d65cec0fd493d549d98ec64a7eae573d7a630afe44600",
        "stats.js": "c6993b92611f70cf2acf976cfdba77614a322cd31f7f54c1129276d1959507e8",
        "validation.js": "fc5daef59fc2c174b577aeb28491e0fdf73ba35a5ecfb60068ddb248147c81fb",
        "utils.js": "7ca7158ed611121f22e4c5dcd8a031f85695989cdd67d5e37725bf47184ffbbb",
    }
    for fn, exp_hash in expected.items():
        if exp_hash.endswith("_HASH"):
            continue
        fp = APP / "src" / fn
        if fp.exists():
            actual = hashlib.sha256(fp.read_bytes()).hexdigest()
            assert actual == exp_hash, f"{fn} was modified (hash mismatch)"


def test_59_latency_summary_uses_per_event_max(report):
    """min latency must be >= 44 (archive path), confirming per-event max is used."""
    assert report["latency_summary"]["min_end_to_end_latency_ms"] >= 100, (
        f"min_end_to_end_latency_ms={report['latency_summary']['min_end_to_end_latency_ms']}, "
        "which suggests per-sink latencies are used instead of per-event max"
    )
