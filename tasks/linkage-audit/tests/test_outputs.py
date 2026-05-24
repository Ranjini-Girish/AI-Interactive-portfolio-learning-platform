"""Tests for C++ linkage audit report."""
import json
import os
import stat
from pathlib import Path

_docker = Path("/app/output")
if _docker.exists() and os.name != "nt":
    ROOT = Path("/app")
else:
    ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if (ROOT / "environment" / "output").exists():
        ROOT = ROOT / "environment"
OUT_DIR = Path('/app/output')
PROJECT = ROOT / "project"
BUILD = ROOT / "build"


def load_report():
    """Load and return the main audit report JSON."""
    p = OUT_DIR / "audit_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


# ─── C++ binary enforcement tests ────────────────────────────────────────────


def test_cpp_binary_exists():
    """Verify the compiled C++ analyzer binary is present at /app/build/analyzer."""
    if os.name == "nt":
        return
    binary = BUILD / "analyzer"
    assert binary.is_file(), f"Missing compiled C++ binary: {binary}"


def test_cpp_binary_executable():
    """Verify the compiled binary has executable permissions."""
    if os.name == "nt":
        return
    binary = BUILD / "analyzer"
    assert binary.is_file(), f"Binary not found: {binary}"
    mode = binary.stat().st_mode
    assert mode & stat.S_IXUSR, f"Binary lacks execute permission: {oct(mode)}"


def test_cpp_binary_is_elf():
    """Verify the binary is a compiled ELF executable, not a script wrapper."""
    if os.name == "nt":
        return
    binary = BUILD / "analyzer"
    assert binary.is_file(), f"Binary not found: {binary}"
    with open(binary, "rb") as f:
        magic = f.read(4)
    assert magic == b'\x7fELF', "Binary is not a compiled ELF executable"


# ─── Structure tests ─────────────────────────────────────────────────────────


def test_output_file_exists():
    """Verify the audit report file was created."""
    assert (OUT_DIR / "audit_report.json").is_file()


def test_top_level_keys():
    """Verify the report has exactly the required top-level keys."""
    required = {"schema_version", "summary", "include_analysis",
                "link_resolution", "rebuild_impact", "quality_findings"}
    assert set(R.keys()) == required, f"Keys: {sorted(R.keys())}"


def test_schema_version():
    """Verify schema_version is integer 1."""
    assert R["schema_version"] == 1
    assert isinstance(R["schema_version"], int)


def test_top_level_types():
    """Verify each top-level key has the correct type."""
    assert isinstance(R["summary"], dict)
    assert isinstance(R["include_analysis"], list)
    assert isinstance(R["link_resolution"], list)
    assert isinstance(R["rebuild_impact"], dict)
    assert isinstance(R["quality_findings"], list)


def test_include_analysis_count():
    """Verify the correct number of compilation units are analyzed."""
    assert len(R["include_analysis"]) == 14


# ─── Summary tests ───────────────────────────────────────────────────────────


def test_summary_total_compilation_units():
    """Verify total compilation unit count."""
    assert R["summary"]["total_compilation_units"] == 14


def test_summary_total_headers():
    """Verify total header count."""
    assert R["summary"]["total_headers"] == 10


def test_summary_total_targets():
    """Verify total target count."""
    assert R["summary"]["total_targets"] == 4


def test_summary_targets_resolved():
    """Verify that exactly 2 targets resolve cleanly."""
    assert R["summary"]["targets_resolved"] == 2


def test_summary_targets_with_issues():
    """Verify that exactly 2 targets have issues."""
    assert R["summary"]["targets_with_issues"] == 2


def test_summary_total_findings():
    """Verify total findings count equals sum of all finding types."""
    total = R["summary"]["total_findings"]
    assert total == len(R["quality_findings"])
    assert total == 11


def test_summary_by_severity_critical():
    """Verify critical severity count (ODR violations)."""
    assert R["summary"]["by_severity"]["critical"] == 1


def test_summary_by_severity_high():
    """Verify high severity count (unresolved symbols)."""
    assert R["summary"]["by_severity"]["high"] == 2


def test_summary_by_severity_low():
    """Verify low severity count (unused library members)."""
    assert R["summary"]["by_severity"]["low"] == 8


def test_summary_by_severity_zeros():
    """Verify medium and info severities are present with zero count."""
    assert R["summary"]["by_severity"]["medium"] == 0
    assert R["summary"]["by_severity"]["info"] == 0


def test_summary_all_severity_keys_present():
    """Verify all five severity keys exist even when zero."""
    for k in ("critical", "high", "medium", "low", "info"):
        assert k in R["summary"]["by_severity"]


def test_summary_by_finding_type():
    """Verify finding type breakdown."""
    bft = R["summary"]["by_finding_type"]
    assert bft["odr_violation"] == 1
    assert bft["unresolved_symbol"] == 2
    assert bft["unused_library_member"] == 8


def test_summary_recompile_count():
    """Verify the number of compilation units needing recompilation."""
    assert R["summary"]["recompile_count"] == 5


def test_summary_relink_count():
    """Verify the number of targets needing relinking."""
    assert R["summary"]["relink_count"] == 3


# ─── Include analysis tests ──────────────────────────────────────────────────


def test_include_analysis_sorted():
    """Verify include_analysis is sorted by compilation_unit."""
    units = [e["compilation_unit"] for e in R["include_analysis"]]
    assert units == sorted(units)


def test_all_units_have_required_keys():
    """Verify every include_analysis entry has all required keys."""
    required = {"compilation_unit", "direct_includes", "transitive_closure",
                "include_depth", "n_effective_headers"}
    for e in R["include_analysis"]:
        assert set(e.keys()) == required, f"{e['compilation_unit']}: {e.keys()}"


def _get_unit(name):
    """Helper to find a compilation unit entry."""
    for e in R["include_analysis"]:
        if e["compilation_unit"] == name:
            return e
    raise AssertionError(f"Missing unit: {name}")


def test_main_cpp_direct_includes():
    """Verify main.cpp's direct includes are sorted and correct."""
    e = _get_unit("src/main.cpp")
    expected = ["include/logger.h", "include/math_utils.h",
                "include/serializer.h", "include/string_utils.h"]
    assert e["direct_includes"] == expected


def test_main_cpp_transitive_closure():
    """Verify main.cpp's transitive closure includes types.h exactly once."""
    e = _get_unit("src/main.cpp")
    expected = ["include/logger.h", "include/math_utils.h",
                "include/serializer.h", "include/string_utils.h",
                "include/types.h"]
    assert e["transitive_closure"] == expected


def test_main_cpp_depth():
    """Verify main.cpp include depth is 2 (main->math_utils->types)."""
    assert _get_unit("src/main.cpp")["include_depth"] == 2


def test_main_cpp_n_effective():
    """Verify main.cpp has 5 effective headers."""
    assert _get_unit("src/main.cpp")["n_effective_headers"] == 5


def test_util_cpp_no_includes():
    """Verify util.cpp has no includes at all."""
    e = _get_unit("src/util.cpp")
    assert e["direct_includes"] == []
    assert e["transitive_closure"] == []
    assert e["include_depth"] == 0
    assert e["n_effective_headers"] == 0


def test_logger_cpp_depth_one():
    """Verify logger.cpp has depth 1 (includes only leaf headers)."""
    e = _get_unit("src/logger.cpp")
    assert e["include_depth"] == 1
    assert set(e["direct_includes"]) == {"include/config.h", "include/logger.h"}


def test_thread_manager_depth_three():
    """Verify thread_manager.cpp has depth 3 (thread_pool->cache->types)."""
    e = _get_unit("src/thread_manager.cpp")
    assert e["include_depth"] == 3


def test_thread_manager_closure():
    """Verify thread_manager.cpp closure includes cache.h transitively."""
    e = _get_unit("src/thread_manager.cpp")
    assert "include/cache.h" in e["transitive_closure"]
    assert "include/types.h" in e["transitive_closure"]
    assert "include/thread_pool.h" in e["transitive_closure"]
    assert e["n_effective_headers"] == 4


def test_types_h_dedup_in_main():
    """Verify types.h appears exactly once in main.cpp despite multiple paths."""
    e = _get_unit("src/main.cpp")
    count = e["transitive_closure"].count("include/types.h")
    assert count == 1, f"types.h appears {count} times"


def test_network_client_closure_has_config():
    """Verify network_client.cpp closure includes config.h through network.h."""
    e = _get_unit("src/network_client.cpp")
    assert "include/config.h" in e["transitive_closure"]
    assert "include/network.h" in e["transitive_closure"]


def test_network_client_headers():
    """Verify network_client.cpp has 5 effective headers."""
    e = _get_unit("src/network_client.cpp")
    assert e["n_effective_headers"] == 5


def test_serializer_impl_closure():
    """Verify serializer_impl.cpp closure is serializer.h + types.h."""
    e = _get_unit("src/serializer_impl.cpp")
    assert e["transitive_closure"] == ["include/serializer.h", "include/types.h"]


def test_pipeline_main_closure():
    """Verify pipeline_main.cpp closure includes types.h once."""
    e = _get_unit("src/pipeline_main.cpp")
    expected = ["include/math_utils.h", "include/string_utils.h", "include/types.h"]
    assert e["transitive_closure"] == expected


def test_worker_main_closure():
    """Verify worker_main.cpp transitive closure is correct."""
    e = _get_unit("src/worker_main.cpp")
    expected = ["include/cache.h", "include/config.h", "include/math_utils.h",
                "include/network.h", "include/types.h"]
    assert e["transitive_closure"] == expected


def test_processor_a_closure():
    """Verify processor_a.cpp closure has 3 headers."""
    e = _get_unit("src/processor_a.cpp")
    assert e["n_effective_headers"] == 3
    assert "include/types.h" in e["transitive_closure"]


def test_processor_b_closure():
    """Verify processor_b.cpp closure has 2 headers."""
    e = _get_unit("src/processor_b.cpp")
    assert e["transitive_closure"] == ["include/math_utils.h", "include/types.h"]


def test_n_effective_matches_closure_len():
    """Verify n_effective_headers equals len(transitive_closure) for all units."""
    for e in R["include_analysis"]:
        assert e["n_effective_headers"] == len(e["transitive_closure"]), \
            f"{e['compilation_unit']}: {e['n_effective_headers']} != {len(e['transitive_closure'])}"


# ─── Link resolution tests ───────────────────────────────────────────────────


def test_link_resolution_count():
    """Verify there are exactly 4 link resolution entries."""
    assert len(R["link_resolution"]) == 4


def test_link_resolution_sorted():
    """Verify link_resolution is sorted by target name."""
    names = [r["target"] for r in R["link_resolution"]]
    assert names == sorted(names)


def _get_target(name):
    """Helper to find a link resolution entry by target name."""
    for r in R["link_resolution"]:
        if r["target"] == name:
            return r
    raise AssertionError(f"Missing target: {name}")


def test_server_resolved():
    """Verify server target resolves with no issues."""
    t = _get_target("server")
    assert t["status"] == "resolved"
    assert t["unresolved_symbols"] == []
    assert t["odr_violations"] == []


def test_server_included_units():
    """Verify server pulls in only the needed members."""
    t = _get_target("server")
    expected = ["src/logger.cpp", "src/main.cpp",
                "src/math_engine.cpp", "src/string_formatter.cpp"]
    assert t["included_units"] == expected


def test_server_skipped_members():
    """Verify server skips unneeded libio members (archive semantics)."""
    t = _get_target("server")
    expected = ["src/cache_manager.cpp", "src/network_client.cpp",
                "src/serializer_impl.cpp"]
    assert t["skipped_members"] == expected


def test_server_archive_semantics():
    """Verify not all library members are linked — only needed ones."""
    t = _get_target("server")
    assert "src/cache_manager.cpp" not in t["included_units"]
    assert "src/network_client.cpp" not in t["included_units"]


def test_pipeline_unresolved():
    """Verify pipeline target has unresolved status."""
    t = _get_target("pipeline")
    assert t["status"] == "unresolved"


def test_pipeline_unresolved_log_message():
    """Verify pipeline's unresolved symbol is log_message (intra-library skip)."""
    t = _get_target("pipeline")
    assert "log_message" in t["unresolved_symbols"]


def test_pipeline_odr_violation():
    """Verify pipeline detects ODR violation for 'process' symbol."""
    t = _get_target("pipeline")
    assert len(t["odr_violations"]) == 1
    odr = t["odr_violations"][0]
    assert odr["symbol"] == "process"
    assert "src/processor_a.cpp" in odr["units"]
    assert "src/processor_b.cpp" in odr["units"]


def test_pipeline_included_units():
    """Verify pipeline's included compilation units."""
    t = _get_target("pipeline")
    expected = ["src/math_engine.cpp", "src/pipeline_main.cpp",
                "src/processor_a.cpp", "src/processor_b.cpp",
                "src/string_formatter.cpp"]
    assert t["included_units"] == expected


def test_pipeline_logger_skipped():
    """Verify logger.cpp is SKIPPED in pipeline (single-pass ordering gotcha)."""
    t = _get_target("pipeline")
    assert "src/logger.cpp" in t["skipped_members"]
    assert "src/logger.cpp" not in t["included_units"]


def test_worker_unresolved():
    """Verify worker target has unresolved status."""
    t = _get_target("worker")
    assert t["status"] == "unresolved"


def test_worker_unresolved_log_message():
    """Verify worker's unresolved symbol is log_message (intra-library skip)."""
    t = _get_target("worker")
    assert "log_message" in t["unresolved_symbols"]


def test_worker_logger_skipped():
    """Verify logger.cpp is SKIPPED in worker (processed before needed)."""
    t = _get_target("worker")
    assert "src/logger.cpp" in t["skipped_members"]


def test_worker_included_units():
    """Verify worker's included compilation units."""
    t = _get_target("worker")
    expected = ["src/cache_manager.cpp", "src/math_engine.cpp",
                "src/network_client.cpp", "src/worker_main.cpp"]
    assert t["included_units"] == expected


def test_worker_no_odr():
    """Verify worker has no ODR violations."""
    t = _get_target("worker")
    assert t["odr_violations"] == []


def test_plugin_host_resolved():
    """Verify plugin_host resolves cleanly."""
    t = _get_target("plugin_host")
    assert t["status"] == "resolved"
    assert t["unresolved_symbols"] == []


def test_plugin_host_included_units():
    """Verify plugin_host's included units (util.cpp as object)."""
    t = _get_target("plugin_host")
    expected = ["src/logger.cpp", "src/main.cpp", "src/math_engine.cpp",
                "src/string_formatter.cpp", "src/util.cpp"]
    assert t["included_units"] == expected


def test_plugin_host_skipped():
    """Verify plugin_host skips unneeded libplugin members."""
    t = _get_target("plugin_host")
    assert "src/plugin_loader.cpp" in t["skipped_members"]
    assert "src/thread_manager.cpp" in t["skipped_members"]


def test_plugin_host_no_odr():
    """Verify plugin_host has no ODR violations despite util.cpp local symbol."""
    t = _get_target("plugin_host")
    assert t["odr_violations"] == []


def test_all_targets_have_required_keys():
    """Verify every link resolution entry has all required keys."""
    required = {"target", "included_units", "skipped_members",
                "unresolved_symbols", "odr_violations", "status"}
    for r in R["link_resolution"]:
        assert set(r.keys()) == required, f"{r['target']}: {r.keys()}"


# ─── Rebuild impact tests ────────────────────────────────────────────────────


def test_rebuild_dirty_files():
    """Verify dirty_files matches input."""
    assert R["rebuild_impact"]["dirty_files"] == ["include/config.h", "src/util.cpp"]


def test_recompile_set():
    """Verify the full recompile set is correct."""
    expected = ["src/logger.cpp", "src/network_client.cpp",
                "src/plugin_loader.cpp", "src/util.cpp",
                "src/worker_main.cpp"]
    assert R["rebuild_impact"]["recompile_set"] == expected


def test_recompile_logger_from_config():
    """Verify logger.cpp needs recompile (directly includes config.h)."""
    assert "src/logger.cpp" in R["rebuild_impact"]["recompile_set"]


def test_recompile_network_client_from_config():
    """Verify network_client.cpp needs recompile (config.h via network.h)."""
    assert "src/network_client.cpp" in R["rebuild_impact"]["recompile_set"]


def test_recompile_worker_main_from_config():
    """Verify worker_main.cpp needs recompile (config.h via network.h)."""
    assert "src/worker_main.cpp" in R["rebuild_impact"]["recompile_set"]


def test_recompile_plugin_loader_from_config():
    """Verify plugin_loader.cpp needs recompile (config.h via plugin_api.h)."""
    assert "src/plugin_loader.cpp" in R["rebuild_impact"]["recompile_set"]


def test_recompile_util_directly_dirty():
    """Verify util.cpp needs recompile (directly listed as dirty)."""
    assert "src/util.cpp" in R["rebuild_impact"]["recompile_set"]


def test_no_recompile_main_cpp():
    """Verify main.cpp does NOT need recompile (no config.h in closure)."""
    assert "src/main.cpp" not in R["rebuild_impact"]["recompile_set"]


def test_no_recompile_math_engine():
    """Verify math_engine.cpp does NOT need recompile."""
    assert "src/math_engine.cpp" not in R["rebuild_impact"]["recompile_set"]


def test_relink_targets():
    """Verify the correct set of targets needs relinking."""
    expected = ["plugin_host", "server", "worker"]
    assert R["rebuild_impact"]["relink_targets"] == expected


def test_pipeline_not_relinked():
    """Verify pipeline does NOT need relink (logger.cpp skipped, not included)."""
    assert "pipeline" not in R["rebuild_impact"]["relink_targets"]


def test_server_relinked():
    """Verify server needs relink because logger.cpp (included) is dirty."""
    assert "server" in R["rebuild_impact"]["relink_targets"]


def test_plugin_host_relinked():
    """Verify plugin_host needs relink (util.cpp and logger.cpp included)."""
    assert "plugin_host" in R["rebuild_impact"]["relink_targets"]


# ─── Quality findings tests ──────────────────────────────────────────────────


def test_findings_count():
    """Verify total number of quality findings."""
    assert len(R["quality_findings"]) == 11


def test_findings_sorted_by_severity():
    """Verify findings are sorted by severity_rank ascending."""
    ranks = [f["severity_rank"] for f in R["quality_findings"]]
    assert ranks == sorted(ranks)


def test_findings_first_is_odr():
    """Verify the first finding is the ODR violation (highest severity)."""
    f = R["quality_findings"][0]
    assert f["finding_type"] == "odr_violation"
    assert f["severity"] == "critical"
    assert f["severity_rank"] == 1


def test_findings_odr_details():
    """Verify ODR violation finding has correct details."""
    f = R["quality_findings"][0]
    assert f["target"] == "pipeline"
    assert f["symbol"] == "process"
    assert f["units"] == ["src/processor_a.cpp", "src/processor_b.cpp"]
    assert f["library"] is None
    assert f["member"] is None


def test_findings_unresolved_count():
    """Verify exactly 2 unresolved_symbol findings."""
    unresolved = [f for f in R["quality_findings"]
                  if f["finding_type"] == "unresolved_symbol"]
    assert len(unresolved) == 2


def test_findings_unresolved_targets():
    """Verify unresolved findings are for pipeline and worker."""
    unresolved = [f for f in R["quality_findings"]
                  if f["finding_type"] == "unresolved_symbol"]
    targets = sorted(f["target"] for f in unresolved)
    assert targets == ["pipeline", "worker"]


def test_findings_unresolved_symbol_is_log_message():
    """Verify both unresolved findings are for log_message."""
    unresolved = [f for f in R["quality_findings"]
                  if f["finding_type"] == "unresolved_symbol"]
    for f in unresolved:
        assert f["symbol"] == "log_message"


def test_findings_unused_member_count():
    """Verify exactly 8 unused_library_member findings."""
    unused = [f for f in R["quality_findings"]
              if f["finding_type"] == "unused_library_member"]
    assert len(unused) == 8


def test_findings_all_have_required_keys():
    """Verify every finding has all required keys."""
    required = {"finding_type", "severity", "severity_rank", "target",
                "library", "symbol", "member", "units"}
    for f in R["quality_findings"]:
        assert set(f.keys()) == required, f"Missing keys in {f}"


def test_findings_null_handling():
    """Verify null fields are correct per finding type."""
    for f in R["quality_findings"]:
        if f["finding_type"] == "odr_violation":
            assert f["library"] is None
            assert f["member"] is None
            assert f["units"] is not None
        elif f["finding_type"] == "unresolved_symbol":
            assert f["library"] is None
            assert f["member"] is None
            assert f["units"] is None
        elif f["finding_type"] == "unused_library_member":
            assert f["symbol"] is None
            assert f["units"] is None
            assert f["library"] is not None
            assert f["member"] is not None


def test_findings_pipeline_unused_logger():
    """Verify pipeline has unused_library_member for logger.cpp in libcore."""
    unused = [f for f in R["quality_findings"]
              if f["finding_type"] == "unused_library_member"
              and f["target"] == "pipeline"]
    members = [f["member"] for f in unused]
    assert "src/logger.cpp" in members


def test_findings_server_unused_io():
    """Verify server has 3 unused members from libio."""
    unused = [f for f in R["quality_findings"]
              if f["finding_type"] == "unused_library_member"
              and f["target"] == "server"]
    assert len(unused) == 3
    members = sorted(f["member"] for f in unused)
    assert members == ["src/cache_manager.cpp", "src/network_client.cpp",
                       "src/serializer_impl.cpp"]


def test_findings_sort_within_same_severity():
    """Verify findings with same severity_rank are sorted by type, target, key."""
    low_findings = [f for f in R["quality_findings"]
                    if f["severity_rank"] == 4]
    keys = [(f["finding_type"], f["target"], f["member"] or "")
            for f in low_findings]
    assert keys == sorted(keys)
