"""Tests for the Rust task scheduler (hardened)."""
import json
import math
import hashlib
from pathlib import Path

import pytest

REPORT_PATH = Path("/app/output/report.json")


@pytest.fixture(scope="session")
def report():
    """Load the generated report."""
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════
# Top-level structure
# ═══════════════════════════════════════════════════════════════
def test_output_file_exists():
    assert REPORT_PATH.exists()


def test_report_is_valid_json():
    json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def test_report_trailing_newline():
    assert REPORT_PATH.read_text(encoding="utf-8").endswith("}\n")


def test_report_two_space_indent():
    text = REPORT_PATH.read_text(encoding="utf-8")
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped and stripped[0] not in "{}[]":
            indent = len(line) - len(stripped)
            assert indent % 2 == 0


def test_report_top_level_keys(report):
    assert set(report.keys()) == {
        "schedule", "critical_path", "group_stats", "summary", "integrity_hash"
    }


# ═══════════════════════════════════════════════════════════════
# Schedule: structure
# ═══════════════════════════════════════════════════════════════
def test_schedule_is_list(report):
    assert isinstance(report["schedule"], list)


def test_schedule_length(report):
    assert len(report["schedule"]) == 20


def test_schedule_task_keys(report):
    required = {
        "task_id", "name", "group", "priority",
        "start_time", "end_time", "duration_ms", "depth",
        "dependencies", "resources",
    }
    for entry in report["schedule"]:
        assert required.issubset(set(entry.keys()))


def test_schedule_all_task_ids_present(report):
    ids = {e["task_id"] for e in report["schedule"]}
    expected = {
        "fetch_deps", "lint_config", "gen_proto",
        "compile_lib", "compile_app", "compile_cli",
        "test_unit", "test_integ", "test_e2e",
        "lint_code", "security_scan",
        "docs_api", "docs_guide",
        "package_lib", "package_app",
        "deploy_staging", "smoke_test", "deploy_prod",
        "notify_team", "cleanup",
    }
    assert ids == expected


# ═══════════════════════════════════════════════════════════════
# Schedule: topological order
# ═══════════════════════════════════════════════════════════════
def test_schedule_order(report):
    order = [e["task_id"] for e in report["schedule"]]
    expected = [
        "lint_config", "docs_guide", "fetch_deps", "compile_lib",
        "docs_api", "lint_code", "test_unit", "gen_proto",
        "compile_app", "package_lib", "test_integ", "compile_cli",
        "test_e2e", "security_scan", "package_app", "deploy_staging",
        "smoke_test", "deploy_prod", "cleanup", "notify_team",
    ]
    assert order == expected


def test_topological_ordering_valid(report):
    order = [e["task_id"] for e in report["schedule"]]
    pos = {tid: i for i, tid in enumerate(order)}
    for e in report["schedule"]:
        for dep in e["dependencies"]:
            assert pos[dep] < pos[e["task_id"]]


def test_all_twenty_tasks_scheduled(report):
    assert len(report["schedule"]) == 20


# ═══════════════════════════════════════════════════════════════
# Schedule: timing
# ═══════════════════════════════════════════════════════════════
def test_end_time_equals_start_plus_duration(report):
    for e in report["schedule"]:
        assert e["end_time"] == e["start_time"] + e["duration_ms"]


def test_start_time_respects_dependencies(report):
    end_map = {e["task_id"]: e["end_time"] for e in report["schedule"]}
    for e in report["schedule"]:
        if e["dependencies"]:
            max_dep_end = max(end_map[d] for d in e["dependencies"])
            assert e["start_time"] >= max_dep_end


def test_lint_config_schedule(report):
    t = next(e for e in report["schedule"] if e["task_id"] == "lint_config")
    assert t["start_time"] == 0
    assert t["end_time"] == 150
    assert t["depth"] == 0


def test_fetch_deps_schedule(report):
    t = next(e for e in report["schedule"] if e["task_id"] == "fetch_deps")
    assert t["start_time"] == 0
    assert t["end_time"] == 300
    assert t["depth"] == 0


def test_gen_proto_schedule(report):
    t = next(e for e in report["schedule"] if e["task_id"] == "gen_proto")
    assert t["start_time"] == 0
    assert t["end_time"] == 450
    assert t["depth"] == 0


def test_compile_app_start_time(report):
    """compile_app depends on fetch_deps(300) and gen_proto(450). Start = max = 450."""
    t = next(e for e in report["schedule"] if e["task_id"] == "compile_app")
    assert t["start_time"] == 450


def test_compile_app_end_time(report):
    t = next(e for e in report["schedule"] if e["task_id"] == "compile_app")
    assert t["end_time"] == 1250


def test_test_integ_start_time(report):
    """test_integ depends on compile_lib(900) and compile_app(1250). Start = max = 1250."""
    t = next(e for e in report["schedule"] if e["task_id"] == "test_integ")
    assert t["start_time"] == 1250


def test_security_scan_start_time(report):
    """security_scan depends on compile_app(1250) and compile_cli(700). Start = max = 1250."""
    t = next(e for e in report["schedule"] if e["task_id"] == "security_scan")
    assert t["start_time"] == 1250


def test_package_lib_start_time(report):
    """package_lib depends on test_unit(1600) and lint_code(1150). Start = max = 1600."""
    t = next(e for e in report["schedule"] if e["task_id"] == "package_lib")
    assert t["start_time"] == 1600


def test_package_app_start_time(report):
    """package_app depends on test_integ(2450), test_e2e(2750), security_scan(2150). Start = max = 2750."""
    t = next(e for e in report["schedule"] if e["task_id"] == "package_app")
    assert t["start_time"] == 2750


def test_deploy_staging_start_time(report):
    """deploy_staging depends on package_lib(1800) and package_app(3100). Start = max = 3100."""
    t = next(e for e in report["schedule"] if e["task_id"] == "deploy_staging")
    assert t["start_time"] == 3100


def test_deploy_prod_start_time(report):
    """deploy_prod depends on smoke_test(4100), docs_api(1250), docs_guide(650). Start = max = 4100."""
    t = next(e for e in report["schedule"] if e["task_id"] == "deploy_prod")
    assert t["start_time"] == 4100


def test_deploy_prod_end_time(report):
    t = next(e for e in report["schedule"] if e["task_id"] == "deploy_prod")
    assert t["end_time"] == 5200


def test_cleanup_schedule(report):
    t = next(e for e in report["schedule"] if e["task_id"] == "cleanup")
    assert t["start_time"] == 5200
    assert t["end_time"] == 5350
    assert t["depth"] == 7


def test_notify_team_schedule(report):
    t = next(e for e in report["schedule"] if e["task_id"] == "notify_team")
    assert t["start_time"] == 5200
    assert t["end_time"] == 5300
    assert t["depth"] == 7


# ═══════════════════════════════════════════════════════════════
# Depth tests
# ═══════════════════════════════════════════════════════════════
def test_root_nodes_depth_zero(report):
    for tid in ["lint_config", "fetch_deps", "gen_proto"]:
        t = next(e for e in report["schedule"] if e["task_id"] == tid)
        assert t["depth"] == 0


def test_depth_values(report):
    depth_map = {e["task_id"]: e["depth"] for e in report["schedule"]}
    assert depth_map["compile_lib"] == 1
    assert depth_map["compile_app"] == 1
    assert depth_map["compile_cli"] == 1
    assert depth_map["docs_guide"] == 1
    assert depth_map["test_unit"] == 2
    assert depth_map["test_integ"] == 2
    assert depth_map["test_e2e"] == 2
    assert depth_map["lint_code"] == 2
    assert depth_map["security_scan"] == 2
    assert depth_map["docs_api"] == 2
    assert depth_map["package_lib"] == 3
    assert depth_map["package_app"] == 3
    assert depth_map["deploy_staging"] == 4
    assert depth_map["smoke_test"] == 5
    assert depth_map["deploy_prod"] == 6
    assert depth_map["notify_team"] == 7
    assert depth_map["cleanup"] == 7


def test_depth_is_max_parent_plus_one(report):
    sched_map = {e["task_id"]: e for e in report["schedule"]}
    for e in report["schedule"]:
        if e["dependencies"]:
            max_parent_depth = max(sched_map[d]["depth"] for d in e["dependencies"])
            assert e["depth"] == max_parent_depth + 1


def test_compile_app_depth_multi_root(report):
    """compile_app depends on fetch_deps(depth=0) and gen_proto(depth=0). Depth = max(0,0)+1 = 1."""
    t = next(e for e in report["schedule"] if e["task_id"] == "compile_app")
    assert t["depth"] == 1


def test_security_scan_depth(report):
    """security_scan depends on compile_app(depth=1) and compile_cli(depth=1). Depth = max(1,1)+1 = 2."""
    t = next(e for e in report["schedule"] if e["task_id"] == "security_scan")
    assert t["depth"] == 2


# ═══════════════════════════════════════════════════════════════
# Critical path
# ═══════════════════════════════════════════════════════════════
def test_critical_path_structure(report):
    cp = report["critical_path"]
    assert "total_duration" in cp
    assert "tasks" in cp
    assert isinstance(cp["tasks"], list)


def test_critical_path_total_duration(report):
    assert report["critical_path"]["total_duration"] == 5350


def test_critical_path_tasks(report):
    expected = [
        "gen_proto", "compile_app", "test_e2e", "package_app",
        "deploy_staging", "smoke_test", "deploy_prod", "cleanup",
    ]
    assert report["critical_path"]["tasks"] == expected


def test_critical_path_is_contiguous(report):
    path = report["critical_path"]["tasks"]
    sched_map = {e["task_id"]: e for e in report["schedule"]}
    for i in range(1, len(path)):
        deps = sched_map[path[i]]["dependencies"]
        assert path[i - 1] in deps


def test_critical_path_duration_matches_sum(report):
    path = report["critical_path"]["tasks"]
    sched_map = {e["task_id"]: e for e in report["schedule"]}
    total = sum(sched_map[tid]["duration_ms"] for tid in path)
    assert total == report["critical_path"]["total_duration"]


def test_critical_path_equals_makespan(report):
    assert report["critical_path"]["total_duration"] == report["summary"]["makespan"]


# ═══════════════════════════════════════════════════════════════
# Group stats
# ═══════════════════════════════════════════════════════════════
def test_group_stats_keys(report):
    assert set(report["group_stats"].keys()) == {
        "build", "deploy", "docs", "ops", "package", "quality", "setup", "test"
    }


def test_group_stats_sorted(report):
    keys = list(report["group_stats"].keys())
    assert keys == sorted(keys)


def test_build_group(report):
    g = report["group_stats"]["build"]
    assert g["task_count"] == 3
    assert g["total_duration"] == 1800
    assert math.isclose(g["avg_duration"], 600.0, abs_tol=0.01)
    assert g["max_priority"] == 4
    assert g["total_resources"] == 5


def test_deploy_group(report):
    g = report["group_stats"]["deploy"]
    assert g["task_count"] == 2
    assert g["total_duration"] == 1700
    assert math.isclose(g["avg_duration"], 850.0, abs_tol=0.01)
    assert g["max_priority"] == 5
    assert g["total_resources"] == 5


def test_docs_group(report):
    g = report["group_stats"]["docs"]
    assert g["task_count"] == 2
    assert g["total_duration"] == 850
    assert math.isclose(g["avg_duration"], 425.0, abs_tol=0.01)
    assert g["max_priority"] == 2
    assert g["total_resources"] == 2


def test_ops_group(report):
    g = report["group_stats"]["ops"]
    assert g["task_count"] == 2
    assert g["total_duration"] == 250
    assert math.isclose(g["avg_duration"], 125.0, abs_tol=0.01)
    assert g["max_priority"] == 1
    assert g["total_resources"] == 2


def test_package_group(report):
    g = report["group_stats"]["package"]
    assert g["task_count"] == 2
    assert g["total_duration"] == 550
    assert math.isclose(g["avg_duration"], 275.0, abs_tol=0.01)
    assert g["max_priority"] == 4
    assert g["total_resources"] == 3


def test_quality_group(report):
    g = report["group_stats"]["quality"]
    assert g["task_count"] == 2
    assert g["total_duration"] == 1150
    assert math.isclose(g["avg_duration"], 575.0, abs_tol=0.01)
    assert g["max_priority"] == 5
    assert g["total_resources"] == 3


def test_setup_group(report):
    g = report["group_stats"]["setup"]
    assert g["task_count"] == 3
    assert g["total_duration"] == 900
    assert math.isclose(g["avg_duration"], 300.0, abs_tol=0.01)
    assert g["max_priority"] == 3
    assert g["total_resources"] == 4


def test_test_group(report):
    g = report["group_stats"]["test"]
    assert g["task_count"] == 4
    assert g["total_duration"] == 3800
    assert math.isclose(g["avg_duration"], 950.0, abs_tol=0.01)
    assert g["max_priority"] == 4
    assert g["total_resources"] == 7


def test_group_avg_is_float(report):
    for name, g in report["group_stats"].items():
        assert isinstance(g["avg_duration"], float)


def test_group_task_count_sums_to_total(report):
    total = sum(g["task_count"] for g in report["group_stats"].values())
    assert total == 20


# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
def test_summary_total_tasks(report):
    assert report["summary"]["total_tasks"] == 20


def test_summary_total_duration(report):
    assert report["summary"]["total_duration"] == 11000


def test_summary_makespan(report):
    assert report["summary"]["makespan"] == 5350


def test_summary_parallelism_ratio(report):
    assert math.isclose(report["summary"]["parallelism_ratio"], 2.06, abs_tol=0.01)


def test_parallelism_ratio_not_truncated(report):
    """Parallelism ratio must use rounding, not truncation. 11000/5350 = 2.0560... rounds to 2.06."""
    assert report["summary"]["parallelism_ratio"] != 2.05, (
        "Got 2.05; parallelism_ratio should be rounded (2.06), not truncated (2.05)"
    )


def test_summary_total_resources(report):
    assert report["summary"]["total_resources"] == 31


def test_makespan_equals_max_end_time(report):
    max_end = max(e["end_time"] for e in report["schedule"])
    assert report["summary"]["makespan"] == max_end


# ═══════════════════════════════════════════════════════════════
# Integrity hash
# ═══════════════════════════════════════════════════════════════
def test_integrity_hash_exists(report):
    assert "integrity_hash" in report
    assert len(report["integrity_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in report["integrity_hash"])


def test_integrity_hash_value(report):
    assert report["integrity_hash"] == \
        "358ad60518508ec5ec17ae9c231447ad0d824a43c5c69deab41aaa29bf87f144"


def test_integrity_hash_self_consistent(report):
    """Recompute the chained SHA-256 from schedule entries and verify."""
    prev = ""
    for s in report["schedule"]:
        line = f"{s['task_id']}|{s['start_time']}|{s['end_time']}|{s['depth']}|{s['resources']}"
        prev = hashlib.sha256((prev + line).encode()).hexdigest()
    assert report["integrity_hash"] == prev


# ═══════════════════════════════════════════════════════════════
# Bug-sensitive tests
# ═══════════════════════════════════════════════════════════════
def test_min_priority_first_in_topo(report):
    """Bug 1: lint_config (prio 1) must be first in topo order."""
    order = [e["task_id"] for e in report["schedule"]]
    assert order[0] == "lint_config"


def test_docs_guide_second(report):
    """Bug 1: docs_guide (prio 2, depends on lint_config) should come right after lint_config."""
    order = [e["task_id"] for e in report["schedule"]]
    assert order[1] == "docs_guide"


def test_package_waits_for_all_deps(report):
    """Bug 3: package_app starts at 2750 (max of deps), not min."""
    t = next(e for e in report["schedule"] if e["task_id"] == "package_app")
    assert t["start_time"] == 2750


def test_deploy_staging_waits_for_all_deps(report):
    """Bug 3: deploy_staging starts at 3100, not 1800."""
    t = next(e for e in report["schedule"] if e["task_id"] == "deploy_staging")
    assert t["start_time"] == 3100


def test_avg_not_truncated_setup(report):
    """Bug 5: setup avg = 900/3 = 300.0 (happens to be exact, but must be float)."""
    g = report["group_stats"]["setup"]
    assert isinstance(g["avg_duration"], float)


def test_max_priority_not_min(report):
    """Bug 6: build max_priority should be 4 (max), not 2 (min)."""
    assert report["group_stats"]["build"]["max_priority"] == 4


def test_quality_max_priority(report):
    """Bug 6: quality has priorities 1 and 5. Max is 5, not 1."""
    assert report["group_stats"]["quality"]["max_priority"] == 5


def test_total_resources_not_duration(report):
    """Bug 9: summary total_resources should be 31, not 11000 (total_duration)."""
    assert report["summary"]["total_resources"] == 31
    assert report["summary"]["total_resources"] != report["summary"]["total_duration"]


def test_group_resources_not_duration(report):
    """Bug 9: build total_resources should be 5, not 1800."""
    assert report["group_stats"]["build"]["total_resources"] == 5


# ═══════════════════════════════════════════════════════════════
# Anti-cheat: build-tag canary checks
# ═══════════════════════════════════════════════════════════════
def _read_src(name):
    """Read a source file from /app/src/."""
    return Path(f"/app/src/{name}").read_text(encoding="utf-8")


def test_graph_build_tag():
    """Verify graph.rs preserves its build-tag marker."""
    assert "build-tag: sched-4a7f9e2d1b3c" in _read_src("graph.rs")


def test_scheduler_build_tag():
    """Verify scheduler.rs preserves its build-tag marker."""
    assert "build-tag: sched-5b8e1f3c2d4a" in _read_src("scheduler.rs")


def test_critical_build_tag():
    """Verify critical.rs preserves its build-tag marker."""
    assert "build-tag: sched-6c9d2e4f3a5b" in _read_src("critical.rs")


def test_stats_build_tag():
    """Verify stats.rs preserves its build-tag marker."""
    assert "build-tag: sched-7d0e3f5a4b6c" in _read_src("stats.rs")


def test_report_build_tag():
    """Verify report.rs preserves its build-tag marker."""
    assert "build-tag: sched-8e1f4a6b5c7d" in _read_src("report.rs")


# ═══════════════════════════════════════════════════════════════
# Anti-cheat: unmodified files retain key structures
# ═══════════════════════════════════════════════════════════════
_UNMODIFIED_SIGNATURES = {
    "task.rs": ["pub struct Task", "pub struct TaskFile", "pub fn dependency_count"],
    "cache.rs": ["pub struct ComputeCache", "use std::collections::HashMap"],
    "config.rs": ["pub struct SchedulerConfig", "max_parallelism"],
    "validator.rs": ["pub fn validate_tasks", "Duplicate task IDs"],
    "main.rs": ["fn main()", "report::build_report", "topological_sort"],
    "metrics.rs": ["pub struct PerfMetrics", "pub fn start", "pub fn stop"],
    "format.rs": ["pub fn format_duration", "#[allow(dead_code)]"],
    "priority.rs": ["Ordering", "#[allow(dead_code)]"],
    "traversal.rs": ["use crate::task::Task", "VecDeque"],
    "errors.rs": ["use std::fmt", "#[derive(Debug)]"],
}


def test_unmodified_files_intact():
    """Verify files that should not be modified still contain their expected structures."""
    for name, signatures in _UNMODIFIED_SIGNATURES.items():
        content = _read_src(name)
        for sig in signatures:
            assert sig in content, (
                f"{name} appears to have been rewritten: expected '{sig}' to be present"
            )


def test_data_files_not_modified():
    """Verify data/tasks.json has not been tampered with."""
    content = Path("/app/data/tasks.json").read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    assert actual == "e1c2f980f2dea0b1c0a1c9e6313713beeb07a517e2bcfb92954116c856fc9f72"


# ═══════════════════════════════════════════════════════════════
# Anti-cheat: modified files retain expected structure
# ═══════════════════════════════════════════════════════════════
def test_graph_structure():
    """Verify graph.rs still contains key algorithmic structures."""
    content = _read_src("graph.rs")
    assert "pub fn topological_sort" in content
    assert "BinaryHeap" in content or "binary_heap" in content.lower()
    assert "in_degree" in content


def test_scheduler_structure():
    """Verify scheduler.rs still contains scheduling logic."""
    content = _read_src("scheduler.rs")
    assert "pub fn schedule" in content
    assert "pub struct ScheduledTask" in content
    assert "start_time" in content


def test_critical_structure():
    """Verify critical.rs still contains critical path logic."""
    content = _read_src("critical.rs")
    assert "pub fn find_critical_path" in content
    assert "pub struct CriticalPath" in content


def test_stats_structure():
    """Verify stats.rs still contains group stats and summary logic."""
    content = _read_src("stats.rs")
    assert "pub fn compute_group_stats" in content
    assert "pub fn compute_summary" in content
    assert "pub struct GroupStats" in content
    assert "pub struct Summary" in content


def test_report_structure():
    """Verify report.rs still contains report building logic."""
    content = _read_src("report.rs")
    assert "pub fn build_report" in content
    assert "integrity_hash" in content or "Sha256" in content
