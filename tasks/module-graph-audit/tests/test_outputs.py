"""Tests for js-module-graph-audit-hard."""
import json
import math
import pathlib
import hashlib

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

FLOAT_TOL = 5e-7


def load_report():
    p = OUT_DIR / "module_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()

# Helpers
MODULES = {m["module_id"]: m for m in R["modules"]}


def get_mod(mid):
    assert mid in MODULES, f"Module {mid} not in report"
    return MODULES[mid]


# ─── Output file structure ───────────────────────────────────────────────────

def test_output_file_exists():
    assert (OUT_DIR / "module_report.json").is_file()


def test_output_trailing_newline():
    raw = (OUT_DIR / "module_report.json").read_text(encoding="utf-8")
    assert raw.endswith("}\n"), "JSON must end with trailing newline"


def test_json_two_space_indent():
    raw = (OUT_DIR / "module_report.json").read_text(encoding="utf-8")
    lines = raw.rstrip("\n").split("\n")
    assert len(lines) > 1, "JSON appears to be minified"
    for i, line in enumerate(lines):
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        assert "\t" not in line, f"Line {i+1} uses tab indentation"
        if stripped and indent > 0:
            assert indent % 2 == 0, f"Line {i+1}: indent {indent} not multiple of 2"


def test_top_level_keys():
    required = {"config", "modules", "dependency_edges",
                "circular_dependencies", "tree_shaking", "summary"}
    assert set(R.keys()) == required


def test_top_level_key_order():
    keys = list(R.keys())
    expected = ["config", "modules", "dependency_edges",
                "circular_dependencies", "tree_shaking", "summary"]
    assert keys == expected


# ─── Config section ──────────────────────────────────────────────────────────

def test_config_has_entry_points():
    assert R["config"]["entry_points"] == ["index.js"]


def test_config_has_output_precision():
    assert R["config"]["output_precision"] == 6


def test_config_has_base_path():
    assert "base_path" in R["config"]


def test_config_include_dynamic():
    assert R["config"]["include_dynamic_imports"] is True


# ─── Summary section ─────────────────────────────────────────────────────────

def test_total_modules():
    assert R["summary"]["total_modules"] == 17


def test_total_modules_matches_array():
    assert R["summary"]["total_modules"] == len(R["modules"])


def test_total_static_edges():
    assert R["summary"]["total_static_edges"] == 30


def test_total_static_edges_matches():
    static = [e for e in R["dependency_edges"] if e["type"] == "static"]
    assert R["summary"]["total_static_edges"] == len(static)


def test_total_dynamic_edges():
    assert R["summary"]["total_dynamic_edges"] == 1


def test_total_dynamic_edges_matches():
    dyn = [e for e in R["dependency_edges"] if e["type"] == "dynamic"]
    assert R["summary"]["total_dynamic_edges"] == len(dyn)


def test_circular_dependency_count():
    assert R["summary"]["circular_dependency_count"] == 2


def test_circular_count_matches_array():
    assert R["summary"]["circular_dependency_count"] == len(R["circular_dependencies"])


def test_total_named_exports():
    assert R["summary"]["total_named_exports"] == 44


def test_total_named_exports_matches():
    total = sum(len(m["named_exports"]) for m in R["modules"])
    assert R["summary"]["total_named_exports"] == total


def test_total_re_exports():
    assert R["summary"]["total_re_exports"] == 3


def test_total_re_exports_matches():
    total = sum(len(m["re_exports"]) for m in R["modules"])
    assert R["summary"]["total_re_exports"] == total


def test_modules_with_default_export():
    assert R["summary"]["modules_with_default_export"] == 4


def test_default_export_count_matches():
    count = sum(1 for m in R["modules"] if m["has_default_export"])
    assert R["summary"]["modules_with_default_export"] == count


def test_side_effect_only_imports():
    assert R["summary"]["side_effect_only_imports"] == 1


def test_side_effect_count_matches():
    count = sum(
        1 for m in R["modules"]
        for imp in m["static_imports"]
        if len(imp["specifiers"]) == 0
    )
    assert R["summary"]["side_effect_only_imports"] == count


def test_avg_afferent_coupling():
    assert math.isclose(
        R["summary"]["avg_afferent_coupling"], 1.764706, abs_tol=FLOAT_TOL
    )


def test_avg_efferent_coupling():
    assert math.isclose(
        R["summary"]["avg_efferent_coupling"], 1.764706, abs_tol=FLOAT_TOL
    )


def test_avg_coupling_computed_correctly():
    ca_sum = sum(m["afferent_coupling"] for m in R["modules"])
    ce_sum = sum(m["efferent_coupling"] for m in R["modules"])
    n = len(R["modules"])
    assert math.isclose(R["summary"]["avg_afferent_coupling"],
                        ca_sum / n, abs_tol=FLOAT_TOL)
    assert math.isclose(R["summary"]["avg_efferent_coupling"],
                        ce_sum / n, abs_tol=FLOAT_TOL)


# ─── Module list ─────────────────────────────────────────────────────────────

def test_modules_sorted_by_id():
    ids = [m["module_id"] for m in R["modules"]]
    assert ids == sorted(ids)


def test_all_17_modules_present():
    expected = sorted([
        "admin.js", "app.js", "auth.js", "config.js", "constants.js",
        "db.js", "errors.js", "events.js", "helpers.js", "index.js",
        "logger.js", "middleware.js", "models.js", "polyfill.js",
        "router.js", "utils.js", "validators.js",
    ])
    actual = sorted(m["module_id"] for m in R["modules"])
    assert actual == expected


def test_module_has_required_fields():
    required = {"module_id", "source_size", "named_exports",
                "has_default_export", "re_exports", "static_imports",
                "dynamic_imports", "afferent_coupling", "efferent_coupling",
                "instability", "layer"}
    for m in R["modules"]:
        assert required.issubset(set(m.keys())), (
            f"{m['module_id']} missing: {required - set(m.keys())}")


# ─── Per-module: named exports ───────────────────────────────────────────────

def test_constants_named_exports():
    m = get_mod("constants.js")
    assert m["named_exports"] == sorted([
        "API_PREFIX", "ENV_DEFAULTS", "FIELD_LIMITS",
        "MAX_CONNECTIONS", "MAX_RETRIES", "PATTERNS", "VERSION",
    ])


def test_constants_has_7_exports():
    assert len(get_mod("constants.js")["named_exports"]) == 7


def test_app_named_exports():
    assert get_mod("app.js")["named_exports"] == ["createApp", "startApp", "stopApp"]


def test_router_named_exports():
    assert get_mod("router.js")["named_exports"] == ["defineRoutes", "handleRequest"]


def test_auth_named_exports():
    assert get_mod("auth.js")["named_exports"] == [
        "authenticate", "createToken", "getSession"]


def test_db_named_exports():
    assert get_mod("db.js")["named_exports"] == [
        "ConnectionPool", "getConnection", "query"]


def test_errors_named_exports():
    assert get_mod("errors.js")["named_exports"] == [
        "AppError", "AuthError", "NotFoundError", "ValidationError"]


def test_events_named_exports():
    assert get_mod("events.js")["named_exports"] == [
        "EVENT_TYPES", "EventBus", "createEvent"]


def test_polyfill_no_exports():
    m = get_mod("polyfill.js")
    assert m["named_exports"] == []
    assert m["has_default_export"] is False


def test_index_no_exports():
    m = get_mod("index.js")
    assert m["named_exports"] == []
    assert m["has_default_export"] is False


def test_utils_no_named_exports():
    assert get_mod("utils.js")["named_exports"] == []


def test_helpers_named_exports():
    assert get_mod("helpers.js")["named_exports"] == [
        "debounce", "memoize", "retry"]


# ─── Per-module: default exports ─────────────────────────────────────────────

def test_router_has_default_export():
    assert get_mod("router.js")["has_default_export"] is True


def test_config_has_default_export():
    assert get_mod("config.js")["has_default_export"] is True


def test_helpers_has_default_export():
    assert get_mod("helpers.js")["has_default_export"] is True


def test_admin_has_default_export():
    assert get_mod("admin.js")["has_default_export"] is True


def test_app_no_default():
    assert get_mod("app.js")["has_default_export"] is False


def test_constants_no_default():
    assert get_mod("constants.js")["has_default_export"] is False


# ─── Per-module: re-exports (utils.js) ───────────────────────────────────────

def test_utils_has_3_reexports():
    assert len(get_mod("utils.js")["re_exports"]) == 3


def test_utils_reexport_all_from_helpers():
    reexps = get_mod("utils.js")["re_exports"]
    all_helpers = [r for r in reexps
                   if r["source"] == "helpers.js" and r["is_all"] is True]
    assert len(all_helpers) == 1
    assert all_helpers[0]["names"] == []


def test_utils_reexport_default_from_helpers():
    reexps = get_mod("utils.js")["re_exports"]
    named_helpers = [r for r in reexps
                     if r["source"] == "helpers.js" and r["is_all"] is False]
    assert len(named_helpers) == 1
    assert named_helpers[0]["names"] == ["default"]


def test_utils_reexport_version_from_constants():
    reexps = get_mod("utils.js")["re_exports"]
    consts = [r for r in reexps if r["source"] == "constants.js"]
    assert len(consts) == 1
    assert consts[0]["names"] == ["VERSION"]
    assert consts[0]["is_all"] is False


def test_no_other_module_has_reexports():
    for m in R["modules"]:
        if m["module_id"] != "utils.js":
            assert len(m["re_exports"]) == 0, (
                f"{m['module_id']} should have no re-exports")


# ─── Per-module: static imports ──────────────────────────────────────────────

def test_index_imports_3_modules():
    imps = get_mod("index.js")["static_imports"]
    assert len(imps) == 3


def test_index_side_effect_import_polyfill():
    imps = get_mod("index.js")["static_imports"]
    poly = [i for i in imps if i["source"] == "polyfill.js"]
    assert len(poly) == 1
    assert poly[0]["specifiers"] == []


def test_app_namespace_import_router():
    imps = get_mod("app.js")["static_imports"]
    rt = [i for i in imps if i["source"] == "router.js"]
    assert len(rt) == 1
    assert rt[0]["specifiers"] == [{"type": "namespace", "name": "*"}]


def test_config_multiline_import():
    imps = get_mod("config.js")["static_imports"]
    c = [i for i in imps if i["source"] == "constants.js"]
    assert len(c) == 1
    names = sorted(s["name"] for s in c[0]["specifiers"])
    assert names == ["ENV_DEFAULTS", "MAX_CONNECTIONS"]


def test_utils_no_static_imports():
    assert get_mod("utils.js")["static_imports"] == []


def test_polyfill_no_imports():
    m = get_mod("polyfill.js")
    assert m["static_imports"] == []
    assert m["dynamic_imports"] == []


def test_constants_no_imports():
    m = get_mod("constants.js")
    assert m["static_imports"] == []
    assert m["dynamic_imports"] == []


# ─── Per-module: dynamic imports ─────────────────────────────────────────────

def test_router_dynamic_import_admin():
    assert get_mod("router.js")["dynamic_imports"] == ["admin.js"]


def test_only_router_has_dynamic_import():
    for m in R["modules"]:
        if m["module_id"] != "router.js":
            assert m["dynamic_imports"] == [], (
                f"{m['module_id']} should have no dynamic imports")


# ─── Coupling metrics ────────────────────────────────────────────────────────

def test_constants_afferent_5():
    assert get_mod("constants.js")["afferent_coupling"] == 5


def test_constants_efferent_0():
    assert get_mod("constants.js")["efferent_coupling"] == 0


def test_constants_instability_0():
    assert get_mod("constants.js")["instability"] == 0.0


def test_index_afferent_0():
    assert get_mod("index.js")["afferent_coupling"] == 0


def test_index_efferent_3():
    assert get_mod("index.js")["efferent_coupling"] == 3


def test_index_instability_1():
    assert get_mod("index.js")["instability"] == 1.0


def test_logger_afferent_4():
    assert get_mod("logger.js")["afferent_coupling"] == 4


def test_logger_instability():
    assert math.isclose(get_mod("logger.js")["instability"],
                        0.333333, abs_tol=FLOAT_TOL)


def test_config_afferent_4():
    assert get_mod("config.js")["afferent_coupling"] == 4


def test_config_instability():
    assert math.isclose(get_mod("config.js")["instability"],
                        0.2, abs_tol=FLOAT_TOL)


def test_admin_afferent_0_dynamic_not_counted():
    assert get_mod("admin.js")["afferent_coupling"] == 0


def test_admin_instability_1():
    assert get_mod("admin.js")["instability"] == 1.0


def test_auth_coupling():
    m = get_mod("auth.js")
    assert m["afferent_coupling"] == 3
    assert m["efferent_coupling"] == 3
    assert m["instability"] == 0.5


def test_middleware_coupling():
    m = get_mod("middleware.js")
    assert m["afferent_coupling"] == 2
    assert m["efferent_coupling"] == 2
    assert m["instability"] == 0.5


def test_instability_consistency():
    for m in R["modules"]:
        ca = m["afferent_coupling"]
        ce = m["efferent_coupling"]
        if ca + ce == 0:
            assert m["instability"] is None
        else:
            expected = ce / (ca + ce)
            assert math.isclose(m["instability"], expected, abs_tol=FLOAT_TOL), (
                f"{m['module_id']}: expected {expected}, got {m['instability']}")


# ─── Dependency edges ────────────────────────────────────────────────────────

def test_total_edges_31():
    assert len(R["dependency_edges"]) == 31


def test_edges_sorted():
    keys = [(e["source"], e["target"], e["type"])
            for e in R["dependency_edges"]]
    assert keys == sorted(keys)


def test_edge_types_valid():
    for e in R["dependency_edges"]:
        assert e["type"] in ("static", "dynamic")


def test_reexport_creates_static_edge():
    edges = R["dependency_edges"]
    utils_helpers = [e for e in edges
                     if e["source"] == "utils.js"
                     and e["target"] == "helpers.js"
                     and e["type"] == "static"]
    assert len(utils_helpers) == 1


def test_reexport_creates_static_edge_constants():
    edges = R["dependency_edges"]
    utils_const = [e for e in edges
                   if e["source"] == "utils.js"
                   and e["target"] == "constants.js"
                   and e["type"] == "static"]
    assert len(utils_const) == 1


def test_dynamic_edge_router_admin():
    edges = R["dependency_edges"]
    dyn = [e for e in edges
           if e["source"] == "router.js"
           and e["target"] == "admin.js"
           and e["type"] == "dynamic"]
    assert len(dyn) == 1


def test_no_self_edges():
    for e in R["dependency_edges"]:
        assert e["source"] != e["target"]


def test_auth_middleware_edges_both_directions():
    edges = R["dependency_edges"]
    a2m = any(e["source"] == "auth.js" and e["target"] == "middleware.js"
              for e in edges)
    m2a = any(e["source"] == "middleware.js" and e["target"] == "auth.js"
              for e in edges)
    assert a2m and m2a


def test_events_logger_edges_both_directions():
    edges = R["dependency_edges"]
    e2l = any(e["source"] == "events.js" and e["target"] == "logger.js"
              for e in edges)
    l2e = any(e["source"] == "logger.js" and e["target"] == "events.js"
              for e in edges)
    assert e2l and l2e


# ─── Circular dependencies ──────────────────────────────────────────────────

def test_circular_deps_count():
    assert len(R["circular_dependencies"]) == 2


def test_circular_deps_sorted_by_cycle_id():
    ids = [c["cycle_id"] for c in R["circular_dependencies"]]
    assert ids == sorted(ids)


def test_scc_auth_middleware():
    scc1 = R["circular_dependencies"][0]
    assert scc1["modules"] == ["auth.js", "middleware.js"]
    assert scc1["representative"] == "auth.js"
    assert scc1["cycle_id"] == 1


def test_scc_events_logger():
    scc2 = R["circular_dependencies"][1]
    assert scc2["modules"] == ["events.js", "logger.js"]
    assert scc2["representative"] == "events.js"
    assert scc2["cycle_id"] == 2


def test_scc_modules_sorted():
    for cd in R["circular_dependencies"]:
        assert cd["modules"] == sorted(cd["modules"])


def test_scc_representative_is_first():
    for cd in R["circular_dependencies"]:
        assert cd["representative"] == cd["modules"][0]


# ─── Topological layers ─────────────────────────────────────────────────────

def test_constants_layer_0():
    assert get_mod("constants.js")["layer"] == 0


def test_polyfill_layer_0():
    assert get_mod("polyfill.js")["layer"] == 0


def test_errors_layer_1():
    assert get_mod("errors.js")["layer"] == 1


def test_helpers_layer_1():
    assert get_mod("helpers.js")["layer"] == 1


def test_config_layer_1():
    assert get_mod("config.js")["layer"] == 1


def test_events_logger_same_layer():
    assert get_mod("events.js")["layer"] == get_mod("logger.js")["layer"]


def test_events_layer_2():
    assert get_mod("events.js")["layer"] == 2


def test_validators_layer_2():
    assert get_mod("validators.js")["layer"] == 2


def test_utils_layer_2():
    assert get_mod("utils.js")["layer"] == 2


def test_db_layer_3():
    assert get_mod("db.js")["layer"] == 3


def test_auth_middleware_same_layer():
    assert get_mod("auth.js")["layer"] == get_mod("middleware.js")["layer"]


def test_auth_layer_4():
    assert get_mod("auth.js")["layer"] == 4


def test_models_layer_4():
    assert get_mod("models.js")["layer"] == 4


def test_router_layer_5():
    assert get_mod("router.js")["layer"] == 5


def test_admin_layer_5():
    assert get_mod("admin.js")["layer"] == 5


def test_app_layer_6():
    assert get_mod("app.js")["layer"] == 6


def test_index_layer_7():
    assert get_mod("index.js")["layer"] == 7


def test_leaf_modules_layer_0():
    for m in R["modules"]:
        if m["efferent_coupling"] == 0 and len(m["dynamic_imports"]) == 0:
            assert m["layer"] == 0, f"{m['module_id']} should be layer 0"


# ─── Tree shaking ───────────────────────────────────────────────────────────

def test_ts_entry_points():
    assert R["tree_shaking"]["entry_points"] == ["index.js"]


def test_ts_reachable_15_modules():
    assert len(R["tree_shaking"]["reachable_modules"]) == 15


def test_ts_unreachable_2_modules():
    assert R["tree_shaking"]["unreachable_modules"] == ["helpers.js", "utils.js"]


def test_ts_reachable_sorted():
    rm = R["tree_shaking"]["reachable_modules"]
    assert rm == sorted(rm)


def test_ts_unreachable_sorted():
    um = R["tree_shaking"]["unreachable_modules"]
    assert um == sorted(um)


def test_ts_reachable_plus_unreachable_equals_all():
    rm = set(R["tree_shaking"]["reachable_modules"])
    um = set(R["tree_shaking"]["unreachable_modules"])
    all_mods = {m["module_id"] for m in R["modules"]}
    assert rm | um == all_mods
    assert rm & um == set()


def test_ts_original_size():
    expected = sum(m["source_size"] for m in R["modules"])
    assert R["tree_shaking"]["original_size"] == expected


def test_ts_tree_shaken_size():
    reachable = set(R["tree_shaking"]["reachable_modules"])
    expected = sum(m["source_size"] for m in R["modules"]
                   if m["module_id"] in reachable)
    assert R["tree_shaking"]["tree_shaken_size"] == expected


def test_ts_savings_ratio():
    orig = R["tree_shaking"]["original_size"]
    ts = R["tree_shaking"]["tree_shaken_size"]
    expected = (orig - ts) / orig
    assert math.isclose(R["tree_shaking"]["savings_ratio"],
                        expected, abs_tol=FLOAT_TOL)


def test_ts_savings_ratio_value():
    assert math.isclose(R["tree_shaking"]["savings_ratio"],
                        0.073218, abs_tol=FLOAT_TOL)


# ─── Tree shaking: used exports ─────────────────────────────────────────────

def test_ts_used_app_createApp():
    assert R["tree_shaking"]["used_exports"]["app.js"] == ["createApp"]


def test_ts_used_router_namespace_all_named():
    used = R["tree_shaking"]["used_exports"]["router.js"]
    assert "defineRoutes" in used
    assert "handleRequest" in used


def test_ts_namespace_does_not_include_default():
    used = R["tree_shaking"]["used_exports"].get("router.js", [])
    assert "default" not in used


def test_ts_used_admin_all_exports_dynamic():
    used = R["tree_shaking"]["used_exports"]["admin.js"]
    assert sorted(used) == ["default", "deleteUser", "listUsers"]


def test_ts_used_config_loadConfig():
    assert R["tree_shaking"]["used_exports"]["config.js"] == ["loadConfig"]


def test_ts_used_constants():
    used = R["tree_shaking"]["used_exports"]["constants.js"]
    assert sorted(used) == sorted([
        "ENV_DEFAULTS", "FIELD_LIMITS", "MAX_CONNECTIONS", "PATTERNS", "VERSION"
    ])


def test_ts_used_logger():
    used = R["tree_shaking"]["used_exports"]["logger.js"]
    assert sorted(used) == ["createLogger", "log"]


def test_ts_used_middleware():
    used = R["tree_shaking"]["used_exports"]["middleware.js"]
    assert sorted(used) == ["applyMiddleware", "rateLimiter"]


def test_ts_used_auth():
    used = R["tree_shaking"]["used_exports"]["auth.js"]
    assert sorted(used) == ["authenticate", "getSession"]


def test_ts_used_db():
    used = R["tree_shaking"]["used_exports"]["db.js"]
    assert sorted(used) == ["getConnection", "query"]


def test_ts_used_errors():
    assert R["tree_shaking"]["used_exports"]["errors.js"] == ["ValidationError"]


def test_ts_used_events():
    assert R["tree_shaking"]["used_exports"]["events.js"] == ["EventBus"]


def test_ts_used_models():
    used = R["tree_shaking"]["used_exports"]["models.js"]
    assert sorted(used) == ["OrderModel", "UserModel"]


def test_ts_used_validators():
    used = R["tree_shaking"]["used_exports"]["validators.js"]
    assert sorted(used) == ["validateField", "validateRequest"]


# ─── Tree shaking: unused exports ────────────────────────────────────────────

def test_ts_unused_app():
    assert sorted(R["tree_shaking"]["unused_exports"]["app.js"]) == [
        "startApp", "stopApp"]


def test_ts_unused_auth():
    assert R["tree_shaking"]["unused_exports"]["auth.js"] == ["createToken"]


def test_ts_unused_config_includes_default():
    unused = R["tree_shaking"]["unused_exports"]["config.js"]
    assert "default" in unused
    assert "validateConfig" in unused


def test_ts_unused_constants():
    unused = R["tree_shaking"]["unused_exports"]["constants.js"]
    assert sorted(unused) == ["API_PREFIX", "MAX_RETRIES"]


def test_ts_unused_db():
    assert R["tree_shaking"]["unused_exports"]["db.js"] == ["ConnectionPool"]


def test_ts_unused_errors():
    unused = R["tree_shaking"]["unused_exports"]["errors.js"]
    assert sorted(unused) == ["AppError", "AuthError", "NotFoundError"]


def test_ts_unused_events():
    unused = R["tree_shaking"]["unused_exports"]["events.js"]
    assert sorted(unused) == ["EVENT_TYPES", "createEvent"]


def test_ts_unused_logger():
    assert R["tree_shaking"]["unused_exports"]["logger.js"] == ["LOG_LEVELS"]


def test_ts_unused_middleware():
    assert R["tree_shaking"]["unused_exports"]["middleware.js"] == ["corsMiddleware"]


def test_ts_unused_models():
    assert R["tree_shaking"]["unused_exports"]["models.js"] == ["ProductModel"]


def test_ts_unused_router_default():
    assert R["tree_shaking"]["unused_exports"]["router.js"] == ["default"]


def test_ts_unused_validators():
    assert R["tree_shaking"]["unused_exports"]["validators.js"] == ["sanitize"]


def test_ts_polyfill_not_in_used():
    assert "polyfill.js" not in R["tree_shaking"]["used_exports"]


def test_ts_polyfill_not_in_unused():
    assert "polyfill.js" not in R["tree_shaking"]["unused_exports"]


def test_ts_index_not_in_used():
    assert "index.js" not in R["tree_shaking"]["used_exports"]


def test_ts_unreachable_not_in_used():
    for mid in R["tree_shaking"]["unreachable_modules"]:
        assert mid not in R["tree_shaking"]["used_exports"]


def test_ts_unreachable_not_in_unused():
    for mid in R["tree_shaking"]["unreachable_modules"]:
        assert mid not in R["tree_shaking"]["unused_exports"]


def test_ts_used_exports_sorted():
    for mid, exports in R["tree_shaking"]["used_exports"].items():
        assert exports == sorted(exports), f"{mid} used_exports not sorted"


def test_ts_unused_exports_sorted():
    for mid, exports in R["tree_shaking"]["unused_exports"].items():
        assert exports == sorted(exports), f"{mid} unused_exports not sorted"


# ─── Source size consistency ─────────────────────────────────────────────────

def test_source_sizes_positive():
    for m in R["modules"]:
        assert m["source_size"] > 0, f"{m['module_id']} has zero source size"


def test_source_sizes_sum():
    total = sum(m["source_size"] for m in R["modules"])
    assert total == R["tree_shaking"]["original_size"]


# ─── Input integrity ─────────────────────────────────────────────────────────

EXPECTED_HASHES = {
    "data/project_config.json": "d09ee727cc96956d2f5e184412844a4487ed3f2d74c21b3d7c661cf353cb36f8",
    "data/modules/index.js": "13beb8b69186fa713cd5823cf75af23dcba8da3ae8d154826f4b1827e9fbdd83",
    "data/modules/app.js": "88794c66f05842a263006fcd88b977843082d772a304e516b78be90b9aa144cb",
    "data/modules/router.js": "b026e91e6ccc86fd7947439431f71b0ef21f051d647c327985d7503f5107898d",
    "data/modules/utils.js": "7292503ed609e9b931148aff016af5128d9bdd3bc54ab2bb7b9b771b647b0958",
    "data/modules/helpers.js": "fa6b41ed639fa8151070fef58c7726017d056ef7f4d456e14885840a1a3cdfdf",
    "data/modules/config.js": "9ec43e9a7590c5f41d5a5cb3185aa391732a3fb501a12195efdc1592e41d2469",
    "data/modules/logger.js": "6047e03cfcdc96ae4ebb433d0557d5537712add43b07768ecba935fde0726f29",
    "data/modules/middleware.js": "a491e9072b0c140e7f36c727452d8e724f681ef9e630c8a63833cf8a26a510c5",
    "data/modules/auth.js": "3685da9b0aa26bb2561d63ee0522da6346fe9b9736848afaaddbc604565904aa",
    "data/modules/db.js": "99af1a780a895a191584341cb9088407b51997c8af2fc58659fdd33323b62c46",
    "data/modules/models.js": "26b83df07c7edd6df7763e2a6e178004604853083c44f890132753fa6b314182",
    "data/modules/validators.js": "f6a881047bd6cc38d8231338c6d047fb97a9a8d8ff7861eb0a53ea83e0a058a7",
    "data/modules/constants.js": "142069218c6b50ff42e08851bcc7a7832bc52a48fbe27e31721bfad663c91513",
    "data/modules/errors.js": "ff246ec8fdb4c67c0f9620d06b8e0089b5766164617644c8867399a0faf746fb",
    "data/modules/events.js": "b99e5d092a66ee627bb01e66f24ef6a818d81bca6d0c99ea71607ee2eb55d0eb",
    "data/modules/polyfill.js": "4967902cdecc96f4091c41e4b73f07fa88ab6a8d3d9bcfe03245eb970b6394cf",
    "data/modules/admin.js": "e526b735129e757f06a9f419f6f37c19bb757302338142946eba2e1878216e67",
}


def test_input_files_exist():
    for rel_path in EXPECTED_HASHES:
        p = ROOT / rel_path
        assert p.is_file(), f"Missing input file: {p}"


def test_input_file_count():
    modules_dir = ROOT / "data" / "modules"
    js_files = list(modules_dir.glob("*.js"))
    assert len(js_files) == 17


def test_input_files_not_modified():
    for rel_path, expected_hash in EXPECTED_HASHES.items():
        p = ROOT / rel_path
        assert p.is_file(), f"Missing input file: {p}"
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == expected_hash, (
            f"{rel_path} was modified: expected sha256={expected_hash}, "
            f"got {actual}"
        )
