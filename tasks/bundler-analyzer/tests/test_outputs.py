"""Tests for ts-bundler-analyzer-hard."""
import json
import math
import pathlib

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')


def load_report():
    """Load and return the main output JSON report."""
    p = OUT_DIR / "bundle_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


# ── TypeScript enforcement ───────────────────────────────────────────────────


def test_typescript_source_exists():
    """Verify at least one TypeScript source file was created under /app/."""
    app_root = pathlib.Path("/app") if pathlib.pathlib.pathlib.Path("/app/data").is_dir() else ROOT
    ts_files = [
        f for f in app_root.rglob("*.ts")
        if "node_modules" not in str(f) and not f.name.endswith(".d.ts")
    ]
    assert len(ts_files) > 0, "No TypeScript source files found"


def test_compiled_js_exists():
    """Verify TypeScript was compiled producing at least one .js file."""
    app_root = pathlib.Path("/app") if pathlib.pathlib.pathlib.Path("/app/data").is_dir() else ROOT
    js_files = [
        f for f in app_root.rglob("*.js")
        if "node_modules" not in str(f)
    ]
    assert len(js_files) > 0, "No compiled .js files found"


# ── Output structure ─────────────────────────────────────────────────────────


def test_output_file_exists():
    """Verify the bundle_report.json output file was created."""
    assert (OUT_DIR / "bundle_report.json").is_file()


def test_trailing_newline():
    """Verify the output file ends with a trailing newline."""
    raw = (OUT_DIR / "bundle_report.json").read_text(encoding="utf-8")
    assert raw.endswith("\n"), "Output must end with trailing newline"


def test_two_space_indent():
    """Verify the output uses two-space JSON indentation."""
    raw = (OUT_DIR / "bundle_report.json").read_text(encoding="utf-8")
    assert '\t"' not in raw, "Output uses tab indent instead of 2-space"
    parsed = json.loads(raw)
    expected = json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
    assert raw == expected, "JSON formatting does not match indent=2 with trailing newline"


def test_top_level_keys():
    """Verify the output contains exactly the four required top-level keys."""
    required = {"module_graph", "tree_shaking", "chunks", "summary"}
    assert set(R.keys()) == required, f"Expected {required}, got {set(R.keys())}"


def test_module_graph_keys():
    """Verify module_graph section has all required keys."""
    required = {"total_modules", "external_packages", "has_circular_imports", "circular_chains"}
    assert set(R["module_graph"].keys()) == required


def test_tree_shaking_keys():
    """Verify tree_shaking section has all required keys."""
    required = {
        "reachable_modules", "dead_modules", "used_exports", "dead_exports",
        "total_raw_size_bytes", "total_tree_shaken_size_bytes", "shake_savings_bytes",
    }
    assert set(R["tree_shaking"].keys()) == required


def test_chunks_keys():
    """Verify chunks section has entry, async_chunks, and shared keys."""
    required = {"entry", "async_chunks", "shared"}
    assert set(R["chunks"].keys()) == required


def test_summary_keys():
    """Verify summary section has all required keys."""
    required = {
        "total_modules", "reachable_modules", "dead_modules", "total_chunks",
        "entry_size_bytes", "async_sizes_bytes", "shared_size_bytes",
        "total_bundle_size_bytes", "total_raw_size_bytes",
        "shake_savings_bytes", "shake_savings_percent",
    }
    assert set(R["summary"].keys()) == required


# ── Module graph ─────────────────────────────────────────────────────────────


def test_total_modules_count():
    """Verify total internal module count is 14."""
    assert R["module_graph"]["total_modules"] == 14


def test_external_packages():
    """Verify external packages are correctly identified and sorted."""
    assert R["module_graph"]["external_packages"] == ["axios", "lodash", "react"]


def test_has_circular_imports():
    """Verify circular import detection flag is true."""
    assert R["module_graph"]["has_circular_imports"] is True


def test_circular_chain_count():
    """Verify exactly one circular chain is detected."""
    assert len(R["module_graph"]["circular_chains"]) == 1


def test_circular_chain_content():
    """Verify the circular chain between api and config is correctly reported."""
    chain = R["module_graph"]["circular_chains"][0]
    assert chain == ["src/services/api", "src/services/config", "src/services/api"]


def test_circular_chain_starts_alphabetically():
    """Verify circular chains start from the alphabetically smallest module."""
    for chain in R["module_graph"]["circular_chains"]:
        start = chain[0]
        interior = chain[:-1]
        assert start == min(interior), f"Chain {chain} should start with {min(interior)}"


# ── Tree-shaking: reachability ───────────────────────────────────────────────


def test_reachable_modules_count():
    """Verify 13 modules are reachable from entry points."""
    assert len(R["tree_shaking"]["reachable_modules"]) == 13


def test_reachable_modules_content():
    """Verify the exact set of reachable modules."""
    expected = sorted([
        "src/app", "src/components/button", "src/components/chart",
        "src/components/header", "src/index", "src/pages/dashboard",
        "src/pages/settings", "src/services/api", "src/services/config",
        "src/utils/format", "src/utils/render", "src/utils/startup",
        "src/utils/validate",
    ])
    assert R["tree_shaking"]["reachable_modules"] == expected


def test_dead_modules_count():
    """Verify exactly one module is dead."""
    assert len(R["tree_shaking"]["dead_modules"]) == 1


def test_dead_modules_content():
    """Verify footer is the only dead module."""
    assert R["tree_shaking"]["dead_modules"] == ["src/components/footer"]


def test_footer_is_dead():
    """Verify footer module is dead because no reachable module imports it."""
    assert "src/components/footer" in R["tree_shaking"]["dead_modules"]
    assert "src/components/footer" not in R["tree_shaking"]["reachable_modules"]


# ── Tree-shaking: used exports ──────────────────────────────────────────────


def test_used_exports_keys_match_reachable():
    """Verify used_exports contains exactly the reachable modules as keys."""
    ue_keys = sorted(R["tree_shaking"]["used_exports"].keys())
    assert ue_keys == R["tree_shaking"]["reachable_modules"]


def test_app_used_exports():
    """Verify only App is used from src/app."""
    assert R["tree_shaking"]["used_exports"]["src/app"] == ["App"]


def test_button_used_exports():
    """Verify only Button is used from button (ButtonProps is dead)."""
    assert R["tree_shaking"]["used_exports"]["src/components/button"] == ["Button"]


def test_header_used_exports():
    """Verify only Header is used from header (NavBar is dead)."""
    assert R["tree_shaking"]["used_exports"]["src/components/header"] == ["Header"]


def test_format_used_exports():
    """Verify only formatDate is used from format (formatCurrency, formatNumber dead)."""
    assert R["tree_shaking"]["used_exports"]["src/utils/format"] == ["formatDate"]


def test_validate_used_exports():
    """Verify only validate is used from validate (sanitize is dead)."""
    assert R["tree_shaking"]["used_exports"]["src/utils/validate"] == ["validate"]


def test_render_used_exports_namespace():
    """Verify both render and measure are used from render due to namespace import."""
    used = R["tree_shaking"]["used_exports"]["src/utils/render"]
    assert "render" in used, "render export should be used"
    assert "measure" in used, "measure should be used via namespace import '*'"
    assert sorted(used) == ["measure", "render"]


def test_config_used_exports():
    """Verify only config is used from services/config (defaults is dead)."""
    assert R["tree_shaking"]["used_exports"]["src/services/config"] == ["config"]


def test_api_used_exports():
    """Verify only api is used from services/api (request is dead)."""
    assert R["tree_shaking"]["used_exports"]["src/services/api"] == ["api"]


def test_dashboard_used_exports():
    """Verify Dashboard export is used via dynamic import from app."""
    assert R["tree_shaking"]["used_exports"]["src/pages/dashboard"] == ["Dashboard"]


def test_settings_used_exports():
    """Verify Settings export is used via dynamic import from dashboard."""
    assert R["tree_shaking"]["used_exports"]["src/pages/settings"] == ["Settings"]


def test_startup_used_exports():
    """Verify init is used from startup."""
    assert R["tree_shaking"]["used_exports"]["src/utils/startup"] == ["init"]


def test_index_has_no_used_exports():
    """Verify entry point module has no used exports (it has no exports)."""
    assert R["tree_shaking"]["used_exports"]["src/index"] == []


# ── Tree-shaking: dead exports ──────────────────────────────────────────────


def test_dead_exports_count():
    """Verify the correct number of dead exports."""
    assert len(R["tree_shaking"]["dead_exports"]) == 8


def test_dead_exports_sorted():
    """Verify dead exports are sorted by module then name."""
    exports = R["tree_shaking"]["dead_exports"]
    keys = [(e["module"], e["name"]) for e in exports]
    assert keys == sorted(keys), f"Dead exports not sorted: {keys}"


def test_dead_export_buttonprops():
    """Verify ButtonProps (50 bytes) is a dead export."""
    exports = R["tree_shaking"]["dead_exports"]
    match = [e for e in exports if e["name"] == "ButtonProps"]
    assert len(match) == 1
    assert match[0]["module"] == "src/components/button"
    assert match[0]["size_bytes"] == 50


def test_dead_export_navbar():
    """Verify NavBar (150 bytes) is a dead export."""
    exports = R["tree_shaking"]["dead_exports"]
    match = [e for e in exports if e["name"] == "NavBar"]
    assert len(match) == 1
    assert match[0]["size_bytes"] == 150


def test_dead_export_footer():
    """Verify Footer (180 bytes) from dead module is a dead export."""
    exports = R["tree_shaking"]["dead_exports"]
    match = [e for e in exports if e["name"] == "Footer"]
    assert len(match) == 1
    assert match[0]["module"] == "src/components/footer"


def test_measure_is_not_dead():
    """Verify measure from render is NOT dead (used via namespace import)."""
    dead_names = [(e["module"], e["name"]) for e in R["tree_shaking"]["dead_exports"]]
    assert ("src/utils/render", "measure") not in dead_names


def test_dead_export_request():
    """Verify request (150 bytes) from api is dead."""
    exports = R["tree_shaking"]["dead_exports"]
    match = [e for e in exports if e["name"] == "request"]
    assert len(match) == 1
    assert match[0]["module"] == "src/services/api"


def test_dead_export_defaults():
    """Verify defaults (100 bytes) from config is dead."""
    exports = R["tree_shaking"]["dead_exports"]
    match = [e for e in exports if e["name"] == "defaults"]
    assert len(match) == 1
    assert match[0]["module"] == "src/services/config"


# ── Tree-shaking: sizes ─────────────────────────────────────────────────────


def test_total_raw_size():
    """Verify total raw size across all modules is 4160 bytes."""
    assert R["tree_shaking"]["total_raw_size_bytes"] == 4160


def test_total_tree_shaken_size():
    """Verify total tree-shaken size of reachable modules is 3305 bytes."""
    assert R["tree_shaking"]["total_tree_shaken_size_bytes"] == 3305


def test_shake_savings_bytes():
    """Verify shake savings is 855 bytes."""
    assert R["tree_shaking"]["shake_savings_bytes"] == 855


# ── Chunks: entry ────────────────────────────────────────────────────────────


def test_entry_chunk_modules():
    """Verify the entry chunk contains exactly the statically reachable modules."""
    expected = sorted([
        "src/app", "src/components/button", "src/components/header",
        "src/index", "src/services/api", "src/services/config",
        "src/utils/format", "src/utils/startup", "src/utils/validate",
    ])
    assert R["chunks"]["entry"]["modules"] == expected


def test_entry_chunk_module_count():
    """Verify the entry chunk has 9 modules."""
    assert len(R["chunks"]["entry"]["modules"]) == 9


def test_entry_chunk_size():
    """Verify entry chunk size is 1925 bytes."""
    assert R["chunks"]["entry"]["size_bytes"] == 1925


def test_footer_not_in_entry():
    """Verify the dead footer module is not in the entry chunk."""
    assert "src/components/footer" not in R["chunks"]["entry"]["modules"]


def test_chart_not_in_entry():
    """Verify chart (async-only) is not in the entry chunk."""
    assert "src/components/chart" not in R["chunks"]["entry"]["modules"]


def test_render_not_in_entry():
    """Verify render (shared chunk) is not in the entry chunk."""
    assert "src/utils/render" not in R["chunks"]["entry"]["modules"]


# ── Chunks: async ────────────────────────────────────────────────────────────


def test_async_chunks_count():
    """Verify exactly two async chunks are created."""
    assert len(R["chunks"]["async_chunks"]) == 2


def test_async_chunks_sorted_by_name():
    """Verify async chunks are sorted by name."""
    names = [ac["name"] for ac in R["chunks"]["async_chunks"]]
    assert names == sorted(names)


def test_dashboard_async_chunk_name():
    """Verify dashboard async chunk has correct name."""
    ac = R["chunks"]["async_chunks"][0]
    assert ac["name"] == "async-src/pages/dashboard"


def test_dashboard_async_chunk_modules():
    """Verify dashboard async chunk contains dashboard and chart."""
    ac = R["chunks"]["async_chunks"][0]
    assert ac["modules"] == ["src/components/chart", "src/pages/dashboard"]


def test_dashboard_async_chunk_size():
    """Verify dashboard async chunk size is 725 bytes (chart=300 + dashboard=425)."""
    ac = R["chunks"]["async_chunks"][0]
    assert ac["size_bytes"] == 725


def test_dashboard_async_trigger_source():
    """Verify dashboard async chunk is triggered by src/app."""
    ac = R["chunks"]["async_chunks"][0]
    assert ac["trigger_source"] == "src/app"


def test_dashboard_async_trigger_module():
    """Verify dashboard async chunk trigger module is src/pages/dashboard."""
    ac = R["chunks"]["async_chunks"][0]
    assert ac["trigger_module"] == "src/pages/dashboard"


def test_settings_async_chunk_name():
    """Verify settings async chunk has correct name."""
    ac = R["chunks"]["async_chunks"][1]
    assert ac["name"] == "async-src/pages/settings"


def test_settings_async_chunk_modules():
    """Verify settings async chunk contains only settings."""
    ac = R["chunks"]["async_chunks"][1]
    assert ac["modules"] == ["src/pages/settings"]


def test_settings_async_chunk_size():
    """Verify settings async chunk size is 375 bytes."""
    ac = R["chunks"]["async_chunks"][1]
    assert ac["size_bytes"] == 375


def test_settings_async_trigger_source():
    """Verify settings async chunk is triggered by dashboard."""
    ac = R["chunks"]["async_chunks"][1]
    assert ac["trigger_source"] == "src/pages/dashboard"


# ── Chunks: shared ───────────────────────────────────────────────────────────


def test_shared_chunk_modules():
    """Verify shared chunk contains only render module."""
    assert R["chunks"]["shared"]["modules"] == ["src/utils/render"]


def test_shared_chunk_size():
    """Verify shared chunk size is 280 bytes (base=10 + render=180 + measure=90)."""
    assert R["chunks"]["shared"]["size_bytes"] == 280


def test_render_not_in_any_async_chunk():
    """Verify render is in shared chunk, not duplicated in async chunks."""
    for ac in R["chunks"]["async_chunks"]:
        assert "src/utils/render" not in ac["modules"], \
            f"render should be in shared chunk, not {ac['name']}"


# ── Summary ──────────────────────────────────────────────────────────────────


def test_summary_total_modules():
    """Verify summary total_modules is 14."""
    assert R["summary"]["total_modules"] == 14


def test_summary_reachable_modules():
    """Verify summary reachable_modules count is 13."""
    assert R["summary"]["reachable_modules"] == 13


def test_summary_dead_modules():
    """Verify summary dead_modules count is 1."""
    assert R["summary"]["dead_modules"] == 1


def test_summary_total_chunks():
    """Verify total_chunks is 4 (entry + 2 async + shared)."""
    assert R["summary"]["total_chunks"] == 4


def test_summary_entry_size():
    """Verify summary entry_size_bytes matches entry chunk."""
    assert R["summary"]["entry_size_bytes"] == R["chunks"]["entry"]["size_bytes"]


def test_summary_async_sizes():
    """Verify summary async_sizes_bytes matches async chunk sizes."""
    expected = [ac["size_bytes"] for ac in R["chunks"]["async_chunks"]]
    assert R["summary"]["async_sizes_bytes"] == expected


def test_summary_shared_size():
    """Verify summary shared_size_bytes matches shared chunk."""
    assert R["summary"]["shared_size_bytes"] == R["chunks"]["shared"]["size_bytes"]


def test_summary_total_bundle_size():
    """Verify total_bundle_size_bytes is 3305."""
    assert R["summary"]["total_bundle_size_bytes"] == 3305


def test_summary_shake_savings_percent():
    """Verify shake_savings_percent is 20.55 (rounded to 2 decimal places)."""
    assert math.isclose(R["summary"]["shake_savings_percent"], 20.55, abs_tol=0.01)


def test_summary_raw_size():
    """Verify summary total_raw_size_bytes is 4160."""
    assert R["summary"]["total_raw_size_bytes"] == 4160


def test_summary_savings_bytes():
    """Verify summary shake_savings_bytes is 855."""
    assert R["summary"]["shake_savings_bytes"] == 855


# ── Cross-field consistency ──────────────────────────────────────────────────


def test_reachable_plus_dead_equals_total():
    """Verify reachable + dead module counts equal total modules."""
    total = R["summary"]["total_modules"]
    reachable = R["summary"]["reachable_modules"]
    dead = R["summary"]["dead_modules"]
    assert reachable + dead == total


def test_bundle_equals_sum_of_chunks():
    """Verify total_bundle_size equals sum of all chunk sizes."""
    entry = R["chunks"]["entry"]["size_bytes"]
    async_total = sum(ac["size_bytes"] for ac in R["chunks"]["async_chunks"])
    shared = R["chunks"]["shared"]["size_bytes"]
    assert R["summary"]["total_bundle_size_bytes"] == entry + async_total + shared


def test_raw_minus_savings_equals_shaken():
    """Verify raw - savings = tree-shaken size."""
    raw = R["tree_shaking"]["total_raw_size_bytes"]
    savings = R["tree_shaking"]["shake_savings_bytes"]
    shaken = R["tree_shaking"]["total_tree_shaken_size_bytes"]
    assert raw - savings == shaken


def test_entry_modules_not_in_async():
    """Verify no entry chunk module appears in any async chunk."""
    entry_mods = set(R["chunks"]["entry"]["modules"])
    for ac in R["chunks"]["async_chunks"]:
        overlap = entry_mods & set(ac["modules"])
        assert not overlap, f"Entry modules {overlap} found in {ac['name']}"


def test_shared_not_in_entry():
    """Verify shared chunk modules are not in the entry chunk."""
    shared_mods = set(R["chunks"]["shared"]["modules"])
    entry_mods = set(R["chunks"]["entry"]["modules"])
    overlap = shared_mods & entry_mods
    assert not overlap, f"Shared modules {overlap} found in entry chunk"


def test_all_reachable_modules_assigned_to_chunk():
    """Verify every reachable module appears in exactly one chunk."""
    all_chunked = set(R["chunks"]["entry"]["modules"])
    for ac in R["chunks"]["async_chunks"]:
        all_chunked.update(ac["modules"])
    all_chunked.update(R["chunks"]["shared"]["modules"])
    reachable = set(R["tree_shaking"]["reachable_modules"])
    assert all_chunked == reachable, f"Mismatch: chunked={all_chunked}, reachable={reachable}"


def test_dead_modules_not_in_any_chunk():
    """Verify dead modules do not appear in any chunk."""
    all_chunked = set(R["chunks"]["entry"]["modules"])
    for ac in R["chunks"]["async_chunks"]:
        all_chunked.update(ac["modules"])
    all_chunked.update(R["chunks"]["shared"]["modules"])
    dead = set(R["tree_shaking"]["dead_modules"])
    overlap = dead & all_chunked
    assert not overlap, f"Dead modules {overlap} found in chunks"


# ── Gotcha-specific tests ───────────────────────────────────────────────────


def test_gotcha_base_size_in_entry_chunk():
    """Verify entry chunk includes base_size_bytes (not just export sizes)."""
    entry_size = R["chunks"]["entry"]["size_bytes"]
    assert entry_size == 1925, (
        "Entry chunk size should include base_size_bytes for each module"
    )


def test_gotcha_namespace_import_measure():
    """Verify namespace import marks measure as used despite no direct named import."""
    used = R["tree_shaking"]["used_exports"].get("src/utils/render", [])
    assert "measure" in used, (
        "Namespace import '*' from dashboard should mark all render exports as used"
    )


def test_gotcha_side_effects_module_included():
    """Verify startup module with side_effects=true is included in entry chunk."""
    assert "src/utils/startup" in R["chunks"]["entry"]["modules"]


def test_gotcha_dynamic_imports_mark_exports_used():
    """Verify dynamic import targets have their exports marked as used."""
    assert "Dashboard" in R["tree_shaking"]["used_exports"].get("src/pages/dashboard", [])
    assert "Settings" in R["tree_shaking"]["used_exports"].get("src/pages/settings", [])


def test_gotcha_circular_does_not_break_reachability():
    """Verify circular imports between api and config do not prevent reachability."""
    assert "src/services/api" in R["tree_shaking"]["reachable_modules"]
    assert "src/services/config" in R["tree_shaking"]["reachable_modules"]


def test_gotcha_shared_threshold():
    """Verify shared chunk only contains modules meeting min_shared_size_bytes."""
    config = json.loads((DATA_DIR / "config.json").read_text(encoding="utf-8"))
    min_size = config["min_shared_size_bytes"]
    shared_size = R["chunks"]["shared"]["size_bytes"]
    if R["chunks"]["shared"]["modules"]:
        assert shared_size >= min_size, (
            f"Shared chunk size {shared_size} below threshold {min_size}"
        )
