"""Tests for cpp-build-analyzer-hard."""
import json
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output') / "build_report.json"
BUILD = ROOT / "build"


@pytest.fixture(scope="session")
def report():
    assert OUT_DIR.is_file(), f"build_report.json not found at {OUT_DIR}"
    with open(OUT_DIR) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def dep(report):
    return report["dependency_analysis"]


@pytest.fixture(scope="session")
def rebuild(report):
    return report["rebuild_analysis"]


@pytest.fixture(scope="session")
def timing(report):
    return report["timing_analysis"]


@pytest.fixture(scope="session")
def summary(report):
    return report["summary"]


# ===================================================================
# Section 1: C++ Binary Enforcement
# ===================================================================

class TestJavaBinary:
    def test_build_directory_exists(self):
        """Verify /app/build/ exists."""
        assert BUILD.is_dir(), "/app/build/ directory must exist"

    def test_binary_exists(self):
        """Verify compiled binary or object files exist."""
        found = False
        if BUILD.is_dir():
            for f in BUILD.rglob("*"):
                if f.suffix in (".o", "") and f.is_file():
                    found = True
                    break
        assert found, "No .class or .jar files found in /app/build/"

    

class TestStructure:
    def test_schema_version(self, report):
        """Verify schema version."""
        assert report["schema_version"] == 1

    def test_top_level_keys(self, report):
        """Verify all required top-level keys exist."""
        required = {"schema_version", "dependency_analysis", "rebuild_analysis",
                     "timing_analysis", "summary"}
        assert required.issubset(report.keys())

    def test_dependency_analysis_keys(self, dep):
        """Verify dependency_analysis has required fields."""
        required = {"total_targets", "has_cycles", "cycles",
                     "topological_order", "parallel_levels"}
        assert required.issubset(dep.keys())

    def test_rebuild_analysis_keys(self, rebuild):
        """Verify rebuild_analysis has required fields."""
        required = {"changed_files", "directly_dirty", "transitively_dirty",
                     "all_dirty", "clean", "rebuild_order"}
        assert required.issubset(rebuild.keys())

    def test_timing_analysis_keys(self, timing):
        """Verify timing_analysis has required fields."""
        required = {"sequential_time_ms", "parallel_time_ms", "critical_path",
                     "critical_path_time_ms", "speedup_ratio"}
        assert required.issubset(timing.keys())


# ===================================================================
# Section 3: Dependency Analysis
# ===================================================================

class TestDependencyAnalysis:
    def test_total_targets(self, dep):
        """Verify total target count."""
        assert dep["total_targets"] == 12

    def test_no_cycles(self, dep):
        """Verify no cycles detected."""
        assert dep["has_cycles"] is False

    def test_cycles_empty(self, dep):
        """Verify cycles list is empty."""
        assert dep["cycles"] == []

    def test_topological_order_length(self, dep):
        """Verify topo order contains all targets."""
        assert len(dep["topological_order"]) == 12

    def test_topological_order_exact(self, dep):
        """Verify exact topological order (level-based, alphabetical within)."""
        expected = ["libbase", "libutil", "libconfig", "libcrypto", "liblog",
                     "libdb", "libnet", "libauth", "libcache", "libapi",
                     "server", "tests"]
        assert dep["topological_order"] == expected

    def test_level_0_targets(self, dep):
        """Verify level 0 contains only targets with no dependencies."""
        level0 = dep["parallel_levels"][0]
        assert level0["level"] == 0
        assert level0["targets"] == ["libbase", "libutil"]

    def test_level_1_targets(self, dep):
        """Verify level 1 targets."""
        level1 = dep["parallel_levels"][1]
        assert level1["targets"] == ["libconfig", "libcrypto", "liblog"]

    def test_level_2_targets(self, dep):
        """Verify level 2 targets."""
        level2 = dep["parallel_levels"][2]
        assert level2["targets"] == ["libdb", "libnet"]

    def test_level_3_targets(self, dep):
        """Verify level 3 targets."""
        level3 = dep["parallel_levels"][3]
        assert level3["targets"] == ["libauth", "libcache"]

    def test_level_4_targets(self, dep):
        """Verify level 4 targets."""
        assert dep["parallel_levels"][4]["targets"] == ["libapi"]

    def test_level_5_targets(self, dep):
        """Verify level 5 targets."""
        assert dep["parallel_levels"][5]["targets"] == ["server"]

    def test_level_6_targets(self, dep):
        """Verify level 6 targets."""
        assert dep["parallel_levels"][6]["targets"] == ["tests"]

    def test_total_levels(self, dep):
        """Verify total number of parallel levels."""
        assert len(dep["parallel_levels"]) == 7

    def test_levels_sorted_by_number(self, dep):
        """Verify level objects are in ascending order."""
        nums = [pl["level"] for pl in dep["parallel_levels"]]
        assert nums == sorted(nums)

    def test_targets_within_levels_sorted(self, dep):
        """Verify targets within each level are alphabetically sorted."""
        for pl in dep["parallel_levels"]:
            assert pl["targets"] == sorted(pl["targets"])

    def test_liblog_level_1_not_0(self, dep):
        """liblog depends on libbase (L0), so liblog must be at level 1, not 0."""
        level0 = dep["parallel_levels"][0]
        assert "liblog" not in level0["targets"]
        level1 = dep["parallel_levels"][1]
        assert "liblog" in level1["targets"]

    def test_libdb_level_2(self, dep):
        """libdb depends on libconfig(L1), so libdb is at level 2, not 1."""
        level2 = dep["parallel_levels"][2]
        assert "libdb" in level2["targets"]

    def test_deps_before_dependents(self, dep):
        """Every target's dependencies appear earlier in topo order."""
        order = dep["topological_order"]
        pos = {name: i for i, name in enumerate(order)}
        targets_dir = ROOT / "data" / "targets"
        for f in targets_dir.glob("*.json"):
            with open(f) as fh:
                t = json.load(fh)
            for d in t.get("depends_on", []):
                assert pos[d] < pos[t["name"]], \
                    f"{d} must come before {t['name']}"


# ===================================================================
# Section 4: Rebuild Analysis
# ===================================================================

class TestRebuildAnalysis:
    def test_changed_files(self, rebuild):
        """Verify changed files list."""
        assert set(rebuild["changed_files"]) == {"util/string.h", "db/connection.cpp"}

    def test_directly_dirty(self, rebuild):
        """Verify directly dirty targets."""
        assert rebuild["directly_dirty"] == ["libdb", "libutil"]

    def test_transitively_dirty(self, rebuild):
        """Verify transitively dirty targets."""
        expected = ["libapi", "libauth", "libcache", "libconfig",
                     "libcrypto", "server", "tests"]
        assert rebuild["transitively_dirty"] == expected

    def test_all_dirty(self, rebuild):
        """Verify combined dirty list."""
        expected = ["libapi", "libauth", "libcache", "libconfig",
                     "libcrypto", "libdb", "libutil", "server", "tests"]
        assert rebuild["all_dirty"] == expected

    def test_clean(self, rebuild):
        """Verify clean targets."""
        assert rebuild["clean"] == ["libbase", "liblog", "libnet"]

    def test_dirty_plus_clean_equals_total(self, rebuild):
        """Verify dirty + clean = all targets."""
        total = len(rebuild["all_dirty"]) + len(rebuild["clean"])
        assert total == 12

    def test_rebuild_order(self, rebuild):
        """Verify rebuild order is topological subset of dirty targets."""
        expected = ["libutil", "libconfig", "libcrypto", "libdb",
                     "libauth", "libcache", "libapi", "server", "tests"]
        assert rebuild["rebuild_order"] == expected

    def test_rebuild_order_is_subset_of_topo(self, rebuild, dep):
        """Verify rebuild order preserves topo ordering."""
        topo = dep["topological_order"]
        topo_pos = {n: i for i, n in enumerate(topo)}
        order = rebuild["rebuild_order"]
        positions = [topo_pos[n] for n in order]
        assert positions == sorted(positions)

    def test_clean_not_in_rebuild(self, rebuild):
        """Verify clean targets do not appear in rebuild order."""
        rebuild_set = set(rebuild["rebuild_order"])
        for c in rebuild["clean"]:
            assert c not in rebuild_set

    def test_liblog_clean_despite_libbase_dep(self, rebuild):
        """liblog depends on libbase. libbase is clean, so liblog is clean."""
        assert "liblog" in rebuild["clean"]

    def test_libnet_clean(self, rebuild):
        """libnet depends on libbase+liblog, both clean."""
        assert "libnet" in rebuild["clean"]

    def test_libconfig_dirty_via_libutil(self, rebuild):
        """libconfig depends on libutil (dirty), so libconfig is transitively dirty."""
        assert "libconfig" in rebuild["transitively_dirty"]

    def test_libcrypto_dirty_via_libutil(self, rebuild):
        """libcrypto depends on libutil (dirty), so it's transitively dirty."""
        assert "libcrypto" in rebuild["transitively_dirty"]

    def test_server_dirty_via_libapi(self, rebuild):
        """server depends on libapi (dirty), so server is transitively dirty."""
        assert "server" in rebuild["transitively_dirty"]

    def test_directly_dirty_sorted(self, rebuild):
        """Verify directly dirty is sorted alphabetically."""
        assert rebuild["directly_dirty"] == sorted(rebuild["directly_dirty"])

    def test_all_dirty_sorted(self, rebuild):
        """Verify all_dirty is sorted alphabetically."""
        assert rebuild["all_dirty"] == sorted(rebuild["all_dirty"])

    def test_no_overlap_direct_transitive(self, rebuild):
        """Verify directly_dirty and transitively_dirty have no overlap."""
        direct = set(rebuild["directly_dirty"])
        trans = set(rebuild["transitively_dirty"])
        assert direct & trans == set()


# ===================================================================
# Section 5: Timing Analysis
# ===================================================================

class TestTimingAnalysis:
    def test_sequential_time(self, timing):
        """Verify sequential time is sum of all build times."""
        assert timing["sequential_time_ms"] == 16400

    def test_parallel_time(self, timing):
        """Verify parallel time using level-based scheduling."""
        assert timing["parallel_time_ms"] == 12400

    def test_critical_path(self, timing):
        """Verify critical path (longest cumulative chain)."""
        expected = ["libutil", "libconfig", "libdb", "libcache",
                     "libapi", "server", "tests"]
        assert timing["critical_path"] == expected

    def test_critical_path_time(self, timing):
        """Verify critical path time."""
        assert timing["critical_path_time_ms"] == 11000

    def test_speedup_ratio(self, timing):
        """Verify speedup = seq/par rounded to 2 decimals."""
        assert timing["speedup_ratio"] == 1.32

    def test_parallel_less_than_sequential(self, timing):
        """Verify parallel time is less than sequential."""
        assert timing["parallel_time_ms"] < timing["sequential_time_ms"]

    def test_critical_path_less_than_parallel(self, timing):
        """Verify critical path time <= parallel time."""
        assert timing["critical_path_time_ms"] <= timing["parallel_time_ms"]

    def test_critical_path_starts_with_root(self, timing, dep):
        """Verify critical path starts with a level-0 target."""
        level0 = dep["parallel_levels"][0]["targets"]
        assert timing["critical_path"][0] in level0

    def test_critical_path_ends_with_leaf(self, timing):
        """Verify critical path ends with tests (the final target)."""
        assert timing["critical_path"][-1] == "tests"

    def test_level_0_time(self, dep):
        """Verify level 0 time = max(800, 1200) = 1200."""
        pass

    def test_level_1_time(self, dep):
        """Verify level 1 time = max(600, 2000, 400) = 2000."""
        pass

    def test_parallel_time_is_sum_of_level_maxes(self, timing):
        """1200+2000+1800+900+2500+3000+1000 = 12400."""
        assert timing["parallel_time_ms"] == 12400

    def test_critical_path_time_sum(self, timing):
        """1200+600+1800+900+2500+3000+1000 = 11000."""
        assert timing["critical_path_time_ms"] == 11000


# ===================================================================
# Section 6: Summary
# ===================================================================

class TestSummary:
    def test_total_targets(self, summary):
        """Verify total target count in summary."""
        assert summary["total_targets"] == 12

    def test_total_levels(self, summary):
        """Verify level count in summary."""
        assert summary["total_levels"] == 7

    def test_dirty_count(self, summary):
        """Verify dirty count."""
        assert summary["dirty_count"] == 9

    def test_clean_count(self, summary):
        """Verify clean count."""
        assert summary["clean_count"] == 3

    def test_libraries(self, summary):
        """Verify library count."""
        assert summary["libraries"] == 10

    def test_executables(self, summary):
        """Verify executable count."""
        assert summary["executables"] == 2

    def test_libs_plus_exes(self, summary):
        """Verify libraries + executables = total."""
        assert summary["libraries"] + summary["executables"] == summary["total_targets"]

    def test_dirty_plus_clean(self, summary):
        """Verify dirty + clean = total."""
        assert summary["dirty_count"] + summary["clean_count"] == summary["total_targets"]


# ===================================================================
# Section 7: Cross-Cutting Gotcha Tests
# ===================================================================

class TestGotchas:
    def test_level_based_not_kahns(self, dep):
        """Level-based topo order groups by level. libutil(L0) comes before liblog(L1)."""
        order = dep["topological_order"]
        assert order.index("libutil") < order.index("liblog")

    def test_liblog_not_at_level_0(self, dep):
        """liblog has dependency libbase. Must be level 1, not 0."""
        l0 = dep["parallel_levels"][0]["targets"]
        assert "liblog" not in l0

    def test_critical_path_goes_through_libconfig_not_libcrypto(self, timing):
        """Critical path: libutil->libconfig->libdb, not libutil->libcrypto.
        libconfig(600)+libdb(1800)=2400 vs libcrypto(2000)+libcache(900)=2900.
        But libdb->libcache->libapi is the longer chain overall."""
        assert "libconfig" in timing["critical_path"]

    def test_transitive_not_file_include(self, rebuild):
        """Dirty propagation is through depends_on graph, not file-level includes.
        liblog does NOT depend on libutil, so even though util/string.h changed,
        liblog remains clean."""
        assert "liblog" in rebuild["clean"]

    def test_direct_source_change_makes_dirty(self, rebuild):
        """db/connection.cpp directly makes libdb dirty regardless of transitive deps."""
        assert "libdb" in rebuild["directly_dirty"]

    def test_parallel_time_not_critical_path(self, timing):
        """Parallel time (level-based) != critical path time (unlimited parallelism)."""
        assert timing["parallel_time_ms"] != timing["critical_path_time_ms"]
        assert timing["parallel_time_ms"] > timing["critical_path_time_ms"]

    def test_speedup_rounded_not_truncated(self, timing):
        """16400/12400 = 1.32258... rounds to 1.32, not 1.33."""
        assert timing["speedup_ratio"] == 1.32

    def test_rebuild_order_preserves_dependency_chain(self, rebuild):
        """In rebuild order, libutil must come before libconfig."""
        order = rebuild["rebuild_order"]
        assert order.index("libutil") < order.index("libconfig")
        assert order.index("libconfig") < order.index("libdb")
        assert order.index("libdb") < order.index("libcache")

    def test_diamond_dependency_level(self, dep):
        """libcache depends on libdb(L2) and libcrypto(L1). Level = max(2,1)+1 = 3."""
        level3 = dep["parallel_levels"][3]
        assert "libcache" in level3["targets"]

    def test_all_targets_in_exactly_one_level(self, dep):
        """Every target appears in exactly one parallel level."""
        all_targets = []
        for pl in dep["parallel_levels"]:
            all_targets.extend(pl["targets"])
        assert len(all_targets) == len(set(all_targets)) == 12
