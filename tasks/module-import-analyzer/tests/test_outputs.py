"""Tests for JavaScript Module Import/Export Static Analyzer."""
import json
from pathlib import Path

ROOT = Path("/app")
OUT_DIR = Path('/app/output') / "module_analysis.json"


def load_output():
    """Load and parse the analysis output JSON."""
    assert OUT_DIR.is_file(), f"Output file not found: {OUT_DIR}"
    text = OUT_DIR.read_text()
    assert text.endswith("\n"), "Output must end with trailing newline"
    return json.loads(text)


# ── Structure & Format ─────────────────────────────────────────────────


def test_01_output_file_exists():
    """Verify the output JSON file exists at the expected path."""
    assert OUT_DIR.is_file(), f"Missing {OUT_DIR}"


def test_02_valid_json():
    """Verify the output is valid JSON."""
    load_output()


def test_03_trailing_newline():
    """Verify the output ends with a trailing newline character."""
    text = OUT_DIR.read_text()
    assert text.endswith("\n"), "Output must end with trailing newline"


def test_04_top_level_keys():
    """Verify all required top-level keys are present and sorted."""
    data = load_output()
    expected = ["cycles", "dependency_graph", "modules",
                "summary", "unreachable_modules", "unused_exports"]
    assert list(data.keys()) == expected


def test_05_two_space_indentation():
    """Verify JSON uses 2-space indentation."""
    text = OUT_DIR.read_text()
    lines = text.split("\n")
    indented = [ln for ln in lines if ln.startswith(" ")]
    assert len(indented) > 0, "No indented lines found"
    for ln in indented:
        stripped = ln.lstrip(" ")
        indent = len(ln) - len(stripped)
        assert indent % 2 == 0, f"Odd indentation ({indent}): {ln[:60]}"


def test_06_keys_sorted_at_all_levels():
    """Verify keys are sorted alphabetically at all nesting levels."""
    data = load_output()

    def check_sorted(obj, path=""):
        if isinstance(obj, dict):
            keys = list(obj.keys())
            assert keys == sorted(keys), f"Unsorted keys at {path}: {keys}"
            for k, v in obj.items():
                check_sorted(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                check_sorted(item, f"{path}[{i}]")

    check_sorted(data)


# ── Summary ────────────────────────────────────────────────────────────


def test_07_summary_keys():
    """Verify summary contains all expected fields."""
    data = load_output()
    expected = ["cycle_count", "max_depth", "reachable_count",
                "side_effect_imports", "total_exports", "total_imports",
                "total_modules", "unreachable_count", "unused_export_count"]
    assert list(data["summary"].keys()) == expected


def test_08_total_modules():
    """Verify total module count is 21."""
    data = load_output()
    assert data["summary"]["total_modules"] == 21


def test_10_total_exports():
    """Verify total export count across all modules is 56."""
    data = load_output()
    assert data["summary"]["total_exports"] == 56


def test_11_cycle_count():
    """Verify exactly 1 cycle detected."""
    data = load_output()
    assert data["summary"]["cycle_count"] == 1


def test_12_max_depth():
    """Verify maximum BFS depth from entry point is 5."""
    data = load_output()
    assert data["summary"]["max_depth"] == 5


def test_13_reachable_count():
    """Verify 19 modules are reachable from entry points."""
    data = load_output()
    assert data["summary"]["reachable_count"] == 19


def test_14_unreachable_count():
    """Verify 2 modules are unreachable."""
    data = load_output()
    assert data["summary"]["unreachable_count"] == 2


def test_15_side_effect_imports():
    """Verify exactly 1 side-effect import across all modules."""
    data = load_output()
    assert data["summary"]["side_effect_imports"] == 1


def test_16_unused_export_count():
    """Verify 25 unused exports detected."""
    data = load_output()
    assert data["summary"]["unused_export_count"] == 25


# ── Dependency Graph ───────────────────────────────────────────────────


def test_17_dep_graph_module_count():
    """Verify dependency graph has entries for all 21 modules."""
    data = load_output()
    assert len(data["dependency_graph"]) == 21


def test_18_dep_graph_index():
    """Verify index.js depends on app.js and polyfills.js."""
    data = load_output()
    assert data["dependency_graph"]["index.js"] == ["app.js", "polyfills.js"]


def test_19_dep_graph_app():
    """Verify app.js depends on config, logger, router."""
    data = load_output()
    assert data["dependency_graph"]["app.js"] == ["config.js", "logger.js", "router.js"]


def test_20_dep_graph_config_includes_reexport():
    """Verify config.js dependency list includes defaults.js (via re-export)."""
    data = load_output()
    assert "defaults.js" in data["dependency_graph"]["config.js"]


def test_21_dep_graph_logger_includes_reexport():
    """Verify logger.js dependency list includes formatters.js (import + re-export)."""
    data = load_output()
    assert "formatters.js" in data["dependency_graph"]["logger.js"]


def test_22_dep_graph_order_handler():
    """Verify handlers/order.js depends on auth, db, helpers, logger."""
    data = load_output()
    expected = ["auth.js", "db.js", "helpers.js", "logger.js"]
    assert data["dependency_graph"]["handlers/order.js"] == expected


def test_23_dep_graph_event_bus():
    """Verify event-bus.js depends on auth.js and logger.js."""
    data = load_output()
    assert data["dependency_graph"]["event-bus.js"] == ["auth.js", "logger.js"]


def test_24_dep_graph_leaf_nodes():
    """Verify leaf modules (constants, defaults, polyfills) have empty dependency lists."""
    data = load_output()
    for mod in ["constants.js", "defaults.js", "polyfills.js"]:
        assert data["dependency_graph"][mod] == [], f"{mod} should have no deps"


def test_25_dep_graph_validators_helpers_cycle():
    """Verify validators and helpers both list each other as dependencies."""
    data = load_output()
    assert "helpers.js" in data["dependency_graph"]["validators.js"]
    assert "validators.js" in data["dependency_graph"]["helpers.js"]


# ── Cycles (SCC) ──────────────────────────────────────────────────────


def test_26_cycles_list():
    """Verify exactly one cycle: helpers.js and validators.js."""
    data = load_output()
    assert len(data["cycles"]) == 1
    assert data["cycles"][0] == ["helpers.js", "validators.js"]


def test_27_cycles_sorted():
    """Verify cycle members are sorted alphabetically."""
    data = load_output()
    for cycle in data["cycles"]:
        assert cycle == sorted(cycle), f"Cycle not sorted: {cycle}"


# ── Unreachable Modules ───────────────────────────────────────────────


def test_28_unreachable_modules():
    """Verify event-bus.js and unused-util.js are unreachable."""
    data = load_output()
    assert data["unreachable_modules"] == ["event-bus.js", "unused-util.js"]


def test_29_unreachable_sorted():
    """Verify unreachable modules list is sorted."""
    data = load_output()
    assert data["unreachable_modules"] == sorted(data["unreachable_modules"])


# ── Module Exports ─────────────────────────────────────────────────────


def test_30_constants_exports():
    """Verify constants.js exports 6 named symbols."""
    data = load_output()
    expected = ["API_PREFIX", "DEBUG", "HASH_ALGORITHM",
                "MAX_LENGTH", "PATTERNS", "SECRET_KEY"]
    assert data["modules"]["constants.js"]["exports"] == expected


def test_31_auth_exports_include_default():
    """Verify auth.js exports authenticate, authorize, and default."""
    data = load_output()
    assert data["modules"]["auth.js"]["exports"] == [
        "authenticate", "authorize", "default"]


def test_32_config_reexports_defaults():
    """Verify config.js exports include re-exported DEFAULT_* from defaults.js."""
    data = load_output()
    exports = data["modules"]["config.js"]["exports"]
    assert "DEFAULT_HOST" in exports
    assert "DEFAULT_PORT" in exports
    assert "DEFAULT_TIMEOUT" in exports
    assert "loadConfig" in exports
    assert "getConfigValue" in exports


def test_33_config_does_not_reexport_default():
    """Verify config.js does not re-export defaults.js's default export (export * excludes default)."""
    data = load_output()
    exports = data["modules"]["config.js"]["exports"]
    assert "default" not in exports


def test_34_logger_exports_include_reexport():
    """Verify logger.js exports include re-exported formatLog."""
    data = load_output()
    exports = data["modules"]["logger.js"]["exports"]
    assert "formatLog" in exports
    assert "Logger" in exports
    assert "createLogger" in exports


def test_35_polyfills_no_exports():
    """Verify polyfills.js has no exports (side-effect only module)."""
    data = load_output()
    assert data["modules"]["polyfills.js"]["exports"] == []


def test_36_defaults_exports():
    """Verify defaults.js exports 3 named constants plus default."""
    data = load_output()
    expected = ["DEFAULT_HOST", "DEFAULT_PORT", "DEFAULT_TIMEOUT", "default"]
    assert data["modules"]["defaults.js"]["exports"] == expected


def test_37_event_bus_exports():
    """Verify event-bus.js exports BusAuth (re-exported default), EventBus, createBus."""
    data = load_output()
    expected = ["BusAuth", "EventBus", "createBus"]
    assert data["modules"]["event-bus.js"]["exports"] == expected


def test_38_order_handler_exports():
    """Verify handlers/order.js exports OrderAuth (re-exported) and handleOrder."""
    data = load_output()
    expected = ["OrderAuth", "handleOrder"]
    assert data["modules"]["handlers/order.js"]["exports"] == expected


def test_39_index_exports_default():
    """Verify index.js exports only default."""
    data = load_output()
    assert data["modules"]["index.js"]["exports"] == ["default"]


# ── Module Imports ─────────────────────────────────────────────────────


def test_40_index_import_count():
    """Verify index.js has 2 imports (default + side-effect)."""
    data = load_output()
    assert data["modules"]["index.js"]["import_count"] == 2


def test_41_index_side_effect_import():
    """Verify index.js has a side-effect import of polyfills.js."""
    data = load_output()
    imps = data["modules"]["index.js"]["imports"]
    se = [i for i in imps if i["type"] == "side-effect"]
    assert len(se) == 1
    assert se[0]["source"] == "polyfills.js"
    assert se[0]["symbols"] == []


def test_42_index_default_import():
    """Verify index.js has a default import from app.js."""
    data = load_output()
    imps = data["modules"]["index.js"]["imports"]
    defaults = [i for i in imps if i["type"] == "default"]
    assert len(defaults) == 1
    assert defaults[0]["source"] == "app.js"
    assert defaults[0]["symbols"] == ["default"]


def test_43_order_namespace_import():
    """Verify handlers/order.js has a namespace import from helpers.js."""
    data = load_output()
    imps = data["modules"]["handlers/order.js"]["imports"]
    ns = [i for i in imps if i["type"] == "namespace"]
    assert len(ns) == 1
    assert ns[0]["source"] == "helpers.js"
    assert ns[0]["symbols"] == ["*"]


def test_44_order_reexport_import():
    """Verify handlers/order.js has a re-export entry from auth.js."""
    data = load_output()
    imps = data["modules"]["handlers/order.js"]["imports"]
    reexp = [i for i in imps if i["type"] == "re-export"]
    assert len(reexp) == 1
    assert reexp[0]["source"] == "auth.js"
    assert reexp[0]["symbols"] == ["default"]


def test_45_config_reexport_entry():
    """Verify config.js imports list includes re-export entry from defaults.js."""
    data = load_output()
    imps = data["modules"]["config.js"]["imports"]
    reexp = [i for i in imps if i["type"] == "re-export"]
    assert len(reexp) == 1
    assert reexp[0]["source"] == "defaults.js"
    assert reexp[0]["symbols"] == ["*"]


def test_46_logger_reexport_entry():
    """Verify logger.js imports list includes re-export entry from formatters.js."""
    data = load_output()
    imps = data["modules"]["logger.js"]["imports"]
    reexp = [i for i in imps if i["type"] == "re-export"]
    assert len(reexp) == 1
    assert reexp[0]["source"] == "formatters.js"


def test_47_router_import_count():
    """Verify router.js has 4 imports."""
    data = load_output()
    assert data["modules"]["router.js"]["import_count"] == 4


def test_48_handler_product_imports():
    """Verify handlers/product.js imports from db, logger, and validators."""
    data = load_output()
    imps = data["modules"]["handlers/product.js"]["imports"]
    sources = [i["source"] for i in imps]
    assert "db.js" in sources
    assert "logger.js" in sources
    assert "validators.js" in sources


# ── Reachability ───────────────────────────────────────────────────────


def test_49_reachable_entry_point():
    """Verify entry point index.js is reachable."""
    data = load_output()
    assert data["modules"]["index.js"]["reachable"] is True


def test_50_reachable_deep_module():
    """Verify crypto-utils.js (depth 5) is reachable."""
    data = load_output()
    assert data["modules"]["crypto-utils.js"]["reachable"] is True


def test_51_unreachable_event_bus():
    """Verify event-bus.js is not reachable."""
    data = load_output()
    assert data["modules"]["event-bus.js"]["reachable"] is False


def test_52_unreachable_unused_util():
    """Verify unused-util.js is not reachable."""
    data = load_output()
    assert data["modules"]["unused-util.js"]["reachable"] is False


def test_53_all_handlers_reachable():
    """Verify all handler modules are reachable."""
    data = load_output()
    for handler in ["handlers/user.js", "handlers/product.js", "handlers/order.js"]:
        assert data["modules"][handler]["reachable"] is True, f"{handler} not reachable"


def test_54_cycle_members_reachable():
    """Verify cycle members (validators, helpers) are reachable."""
    data = load_output()
    assert data["modules"]["validators.js"]["reachable"] is True
    assert data["modules"]["helpers.js"]["reachable"] is True


# ── Unused Exports ─────────────────────────────────────────────────────


def test_55_unused_export_count():
    """Verify 25 unused exports detected."""
    data = load_output()
    assert len(data["unused_exports"]) == 25


def test_56_unused_api_prefix():
    """Verify constants.js API_PREFIX is unused."""
    data = load_output()
    ue = data["unused_exports"]
    assert {"module": "constants.js", "symbol": "API_PREFIX"} in ue


def test_57_unused_generate_salt():
    """Verify crypto-utils.js generateSalt is unused."""
    data = load_output()
    ue = data["unused_exports"]
    assert {"module": "crypto-utils.js", "symbol": "generateSalt"} in ue


def test_58_unused_format_date():
    """Verify formatters.js formatDate is unused."""
    data = load_output()
    ue = data["unused_exports"]
    assert {"module": "formatters.js", "symbol": "formatDate"} in ue


def test_59_unused_config_reexports():
    """Verify config.js re-exported DEFAULT_* symbols are unused (nobody imports them from config)."""
    data = load_output()
    ue = data["unused_exports"]
    for sym in ["DEFAULT_HOST", "DEFAULT_PORT", "DEFAULT_TIMEOUT"]:
        assert {"module": "config.js", "symbol": sym} in ue, f"config.js:{sym} should be unused"


def test_60_unused_logger_reexport():
    """Verify logger.js re-exported formatLog is unused (nobody imports it from logger)."""
    data = load_output()
    ue = data["unused_exports"]
    assert {"module": "logger.js", "symbol": "formatLog"} in ue


def test_61_unused_order_auth():
    """Verify handlers/order.js OrderAuth re-export is unused."""
    data = load_output()
    ue = data["unused_exports"]
    assert {"module": "handlers/order.js", "symbol": "OrderAuth"} in ue


def test_62_unused_event_bus_all():
    """Verify all event-bus.js exports are unused (unreachable module)."""
    data = load_output()
    ue = data["unused_exports"]
    for sym in ["BusAuth", "EventBus", "createBus"]:
        assert {"module": "event-bus.js", "symbol": sym} in ue


def test_63_unused_util_all():
    """Verify all unused-util.js exports are unused."""
    data = load_output()
    ue = data["unused_exports"]
    for sym in ["deprecatedHelper", "legacyFormat"]:
        assert {"module": "unused-util.js", "symbol": sym} in ue


def test_64_unused_app_all():
    """Verify all app.js named exports are unused (only default import from index)."""
    data = load_output()
    ue = data["unused_exports"]
    for sym in ["APP_VERSION", "startApp", "stopApp"]:
        assert {"module": "app.js", "symbol": sym} in ue


def test_65_unused_index_default():
    """Verify index.js default export is unused (entry point, nobody imports it)."""
    data = load_output()
    ue = data["unused_exports"]
    assert {"module": "index.js", "symbol": "default"} in ue


def test_66_debug_not_unused():
    """Verify constants.js DEBUG is NOT unused (imported by unused-util.js)."""
    data = load_output()
    ue = data["unused_exports"]
    assert {"module": "constants.js", "symbol": "DEBUG"} not in ue


def test_67_helpers_exports_not_unused():
    """Verify helpers.js exports are NOT unused (all used via namespace import in order handler)."""
    data = load_output()
    ue = data["unused_exports"]
    for sym in ["formatError", "deepMerge", "debounce"]:
        assert {"module": "helpers.js", "symbol": sym} not in ue


def test_68_defaults_named_not_unused():
    """Verify defaults.js named exports are NOT unused (used via config.js re-export-all)."""
    data = load_output()
    ue = data["unused_exports"]
    for sym in ["DEFAULT_HOST", "DEFAULT_PORT", "DEFAULT_TIMEOUT"]:
        assert {"module": "defaults.js", "symbol": sym} not in ue


def test_69_auth_default_not_unused():
    """Verify auth.js default is NOT unused (re-exported by order and event-bus)."""
    data = load_output()
    ue = data["unused_exports"]
    assert {"module": "auth.js", "symbol": "default"} not in ue


def test_70_unused_exports_sorted():
    """Verify unused_exports array is sorted by module then symbol."""
    data = load_output()
    ue = data["unused_exports"]
    keys = [(e["module"], e["symbol"]) for e in ue]
    assert keys == sorted(keys), "unused_exports not sorted by (module, symbol)"


# ── Cross-Validation ──────────────────────────────────────────────────


def test_71_module_count_matches_graph():
    """Verify modules count matches dependency_graph entries."""
    data = load_output()
    assert len(data["modules"]) == len(data["dependency_graph"])


def test_72_graph_keys_match_module_keys():
    """Verify dependency_graph keys are identical to modules keys."""
    data = load_output()
    assert sorted(data["dependency_graph"].keys()) == sorted(data["modules"].keys())


def test_73_unreachable_matches_reachable_flags():
    """Verify unreachable_modules matches modules with reachable=false."""
    data = load_output()
    not_reachable = sorted(
        m for m, info in data["modules"].items() if not info["reachable"])
    assert not_reachable == data["unreachable_modules"]


def test_74_reachable_count_consistency():
    """Verify reachable_count equals total_modules minus unreachable_count."""
    s = load_output()["summary"]
    assert s["reachable_count"] == s["total_modules"] - s["unreachable_count"]


def test_75_unused_export_count_matches_list():
    """Verify unused_export_count matches length of unused_exports array."""
    data = load_output()
    assert data["summary"]["unused_export_count"] == len(data["unused_exports"])


def test_76_total_imports_matches_sum():
    """Verify total_imports equals sum of all modules' import_count."""
    data = load_output()
    total = sum(m["import_count"] for m in data["modules"].values())
    assert data["summary"]["total_imports"] == total


def test_77_total_exports_matches_sum():
    """Verify total_exports equals sum of all modules' export list lengths."""
    data = load_output()
    total = sum(len(m["exports"]) for m in data["modules"].values())
    assert data["summary"]["total_exports"] == total


def test_78_all_dep_targets_are_modules():
    """Verify every dependency target exists as a module."""
    data = load_output()
    modules = set(data["modules"].keys())
    for mod, deps in data["dependency_graph"].items():
        for dep in deps:
            assert dep in modules, f"{mod} depends on unknown module {dep}"


def test_79_cycle_members_are_modules():
    """Verify all cycle members exist in the modules list."""
    data = load_output()
    modules = set(data["modules"].keys())
    for cycle in data["cycles"]:
        for member in cycle:
            assert member in modules, f"Cycle member {member} not a known module"


def test_80_unused_exports_reference_valid_modules():
    """Verify all unused export entries reference valid modules and symbols."""
    data = load_output()
    for entry in data["unused_exports"]:
        mod = entry["module"]
        sym = entry["symbol"]
        assert mod in data["modules"], f"Unused export module {mod} not found"
        assert sym in data["modules"][mod]["exports"], \
            f"Unused export {mod}:{sym} not in module's export list"


def test_81_import_sources_match_graph():
    """Verify each module's import sources are a subset of its dependency graph entry."""
    data = load_output()
    for mod, info in data["modules"].items():
        import_sources = {i["source"] for i in info["imports"]}
        dep_set = set(data["dependency_graph"].get(mod, []))
        assert import_sources <= dep_set, \
            f"{mod} imports from {import_sources - dep_set} not in dep graph"


def test_82_event_bus_reexport_busauth():
    """Verify event-bus.js re-exports auth.js default as BusAuth."""
    data = load_output()
    imps = data["modules"]["event-bus.js"]["imports"]
    reexp = [i for i in imps if i["type"] == "re-export"]
    assert len(reexp) == 1
    assert reexp[0]["source"] == "auth.js"
    assert reexp[0]["symbols"] == ["default"]


def test_83_handler_user_imports_authorize():
    """Verify handlers/user.js imports authorize from auth.js."""
    data = load_output()
    imps = data["modules"]["handlers/user.js"]["imports"]
    auth_imp = [i for i in imps if i["source"] == "auth.js"]
    assert len(auth_imp) == 1
    assert "authorize" in auth_imp[0]["symbols"]


def test_84_middleware_import_count():
    """Verify middleware.js has 2 imports."""
    data = load_output()
    assert data["modules"]["middleware.js"]["import_count"] == 2


def test_85_db_exports():
    """Verify db.js exports connect, query, transaction."""
    data = load_output()
    assert data["modules"]["db.js"]["exports"] == ["connect", "query", "transaction"]
