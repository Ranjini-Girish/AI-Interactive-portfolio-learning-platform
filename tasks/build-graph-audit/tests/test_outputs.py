"""Behavioral tests for js-build-graph-audit-hard.

Each test has a docstring explaining which behavior it checks so that
failures are self-documenting.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

REPORT_FILE = Path("/app/output/build_graph_report.json")
DATA_DIR = Path("/app/data")

_here = Path(__file__).resolve().parent
_local_report = _here.parent / "environment" / "output" / "build_graph_report.json"
_local_data = _here.parent / "environment" / "data"

if not REPORT_FILE.exists() and _local_report.exists():
    REPORT_FILE = _local_report
    DATA_DIR = _local_data


def _load_report():
    assert REPORT_FILE.is_file(), f"Missing report: {REPORT_FILE}"
    return json.loads(REPORT_FILE.read_text("utf-8"))


R = None


def _r():
    global R
    if R is None:
        R = _load_report()
    return R


def _mod(name):
    for m in _r()["modules"]:
        if m["name"] == name:
            return m
    raise KeyError(f"Module {name!r} not found")


def _finding(finding_type, module=None):
    for f in _r()["quality_findings"]:
        if f["finding_type"] == finding_type:
            if module is None or f["module"] == module:
                return f
    return None


# ── file format ─────────────────────────────────────────────────────

def test_output_file_exists():
    """The report JSON file must exist."""
    assert REPORT_FILE.is_file()


def test_report_is_valid_json():
    """The report must parse as valid JSON."""
    _r()


def test_json_trailing_newline():
    """Report must end with a trailing newline."""
    raw = REPORT_FILE.read_text("utf-8")
    assert raw.endswith("\n")


def test_json_two_space_indent():
    """Report must use two-space indentation, no tabs."""
    raw = REPORT_FILE.read_text("utf-8")
    assert "\t" not in raw
    for line in raw.split("\n"):
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if indent > 0:
            assert indent % 2 == 0, f"Odd indent: {line!r}"


# ── top-level keys ──────────────────────────────────────────────────

def test_top_level_keys():
    """Report must contain exactly the required top-level keys."""
    expected = {
        "schema_version", "project_name", "summary", "modules",
        "dependency_edges", "cycles", "build_order", "size_analysis",
        "quality_findings",
    }
    assert set(_r().keys()) == expected


def test_schema_version():
    """schema_version must be 1."""
    assert _r()["schema_version"] == 1


def test_project_name():
    """project_name must match project.json."""
    assert _r()["project_name"] == "acme-webapp"


# ── summary ─────────────────────────────────────────────────────────

def test_summary_total_modules():
    """19 modules defined in the data directory."""
    assert _r()["summary"]["total_modules"] == 19


def test_summary_reachable_modules():
    """18 modules are reachable from the entry point."""
    assert _r()["summary"]["reachable_modules"] == 18


def test_summary_unreachable_modules():
    """1 module (legacy-polyfill) is unreachable."""
    assert _r()["summary"]["unreachable_modules"] == 1


def test_summary_entry_points():
    """1 entry point (app)."""
    assert _r()["summary"]["entry_points"] == 1


def test_summary_total_edges():
    """30 resolved dependency edges in the graph."""
    assert _r()["summary"]["total_edges"] == 30


def test_summary_cycle_count():
    """Exactly 1 cycle detected (api-client <-> auth-service)."""
    assert _r()["summary"]["cycle_count"] == 1


def test_summary_total_findings():
    """8 quality findings total."""
    assert _r()["summary"]["total_findings"] == 8


def test_summary_by_severity_all_keys():
    """All five severity buckets must be present."""
    keys = set(_r()["summary"]["by_severity"].keys())
    assert keys == {"critical", "high", "medium", "low", "info"}


def test_summary_by_severity_values():
    """Severity counts: 1 critical, 2 high, 3 medium, 1 low, 1 info."""
    sev = _r()["summary"]["by_severity"]
    assert sev == {"critical": 1, "high": 2, "medium": 3, "low": 1, "info": 1}


# ── modules sorted ─────────────────────────────────────────────────

def test_modules_sorted_by_name():
    """Modules array must be sorted alphabetically by name."""
    names = [m["name"] for m in _r()["modules"]]
    assert names == sorted(names)


def test_modules_count():
    """19 module entries in the array."""
    assert len(_r()["modules"]) == 19


# ── re-export resolution trap ──────────────────────────────────────

def test_dashboard_depends_on_route_config():
    """dashboard imports navigateTo from router, but router re-exports it
    from route-config. The resolved dependency must be dashboard -> route-config."""
    edges = _r()["dependency_edges"]
    assert {"source": "dashboard", "target": "route-config"} in edges


def test_dashboard_also_depends_on_router():
    """dashboard imports BOTH navigateTo (re-exported) and Router (own export)
    from router. Since Router is router's own export, dashboard -> router must
    exist as a separate edge alongside dashboard -> route-config."""
    edges = _r()["dependency_edges"]
    assert {"source": "dashboard", "target": "router"} in edges


def test_dashboard_fan_out_is_four():
    """dashboard depends on chart-engine, data-service, route-config, and router
    (4 edges total from mixed-source resolution)."""
    assert _mod("dashboard")["fan_out"] == 4


def test_router_fan_in_is_two():
    """router is depended on by app AND dashboard (since dashboard imports
    Router as an own-export)."""
    assert _mod("router")["fan_in"] == 2


# ── multi-hop re-export trap ───────────────────────────────────────

def test_analytics_depends_on_logger_via_reexport():
    """analytics imports 'warn' from event-bus. event-bus re-exports 'warn'
    from logger. The resolved dependency is analytics -> logger (multi-hop)."""
    edges = _r()["dependency_edges"]
    assert {"source": "analytics", "target": "logger"} in edges


def test_analytics_also_depends_on_event_bus():
    """analytics imports 'emit' from event-bus (own export of event-bus).
    So analytics -> event-bus must also exist (mixed-source)."""
    edges = _r()["dependency_edges"]
    assert {"source": "analytics", "target": "event-bus"} in edges


def test_analytics_fan_out_is_two():
    """analytics has 2 resolved deps: event-bus (for emit) and logger (for warn)."""
    assert _mod("analytics")["fan_out"] == 2


def test_logger_fan_in_is_five():
    """logger is depended on by http-utils, token-store, cache-manager,
    analytics (via multi-hop re-export of warn), and event-bus."""
    assert _mod("logger")["fan_in"] == 5


# ── depth = longest path trap ──────────────────────────────────────

def test_depth_app_entry():
    """Entry point app has depth 0."""
    assert _mod("app")["depth"] == 0


def test_depth_router_is_two():
    """router depth = 2 because dashboard(1) -> router gives longer path than
    app(0) -> router = 1. max(1, 2) = 2."""
    assert _mod("router")["depth"] == 2


def test_depth_route_config_is_three():
    """route-config depth = 3 because router(2) -> route-config = 3 is longer
    than dashboard(1) -> route-config = 2."""
    assert _mod("route-config")["depth"] == 3


def test_depth_auth_guard_is_three():
    """auth-guard depth = 3 because router(2) -> auth-guard = 3."""
    assert _mod("auth-guard")["depth"] == 3


def test_depth_event_bus_is_two():
    """event-bus depth = max(app->event-bus=1, app->analytics->event-bus=2) = 2."""
    assert _mod("event-bus")["depth"] == 2


def test_depth_logger_longest_path():
    """logger depth must be 6 (longest path), not 2 (shortest via event-bus).
    Longest: app->dashboard->chart-engine->data-service->api-client(SCC=4)->
    http-utils(5)->logger(6)."""
    assert _mod("logger")["depth"] == 6


def test_depth_utils_longest_path():
    """utils depth must be 6 (longest path via token-store)."""
    assert _mod("utils")["depth"] == 6


def test_depth_http_utils():
    """http-utils depth must be 5 (api-client(4) -> http-utils)."""
    assert _mod("http-utils")["depth"] == 5


def test_depth_token_store():
    """token-store depth must be 5 (auth-service(4) -> token-store)."""
    assert _mod("token-store")["depth"] == 5


def test_depth_data_service():
    """data-service depth must be 3 (chart-engine(2) -> data-service)."""
    assert _mod("data-service")["depth"] == 3


def test_depth_cache_manager():
    """cache-manager depth must be 4 (data-service(3) -> cache-manager)."""
    assert _mod("cache-manager")["depth"] == 4


# ── cycle detection (SCC) ──────────────────────────────────────────

def test_cycle_count():
    """Exactly 1 cycle detected."""
    assert len(_r()["cycles"]) == 1


def test_cycle_members():
    """The cycle contains api-client and auth-service."""
    cyc = _r()["cycles"][0]
    assert sorted(cyc["members"]) == ["api-client", "auth-service"]


def test_scc_same_depth():
    """Both SCC members must have the same depth (4)."""
    assert _mod("api-client")["depth"] == _mod("auth-service")["depth"] == 4


def test_api_client_in_cycle():
    """api-client must be marked as in_cycle=true."""
    assert _mod("api-client")["in_cycle"] is True


def test_auth_service_in_cycle():
    """auth-service must be marked as in_cycle=true."""
    assert _mod("auth-service")["in_cycle"] is True


# ── instability null trap ──────────────────────────────────────────

def test_legacy_polyfill_instability_null():
    """legacy-polyfill has Ca=0 and Ce=0, so instability must be null (not 0)."""
    assert _mod("legacy-polyfill")["instability"] is None


def test_legacy_polyfill_depth_null():
    """legacy-polyfill is unreachable, so depth must be null."""
    assert _mod("legacy-polyfill")["depth"] is None


def test_legacy_polyfill_layer():
    """legacy-polyfill layer must be 'unreachable'."""
    assert _mod("legacy-polyfill")["layer"] == "unreachable"


# ── instability values ─────────────────────────────────────────────

def test_app_instability():
    """app: Ca=0, Ce=5. I = 5/5 = 1.0."""
    assert math.isclose(_mod("app")["instability"], 1.0, abs_tol=1e-6)


def test_app_fan_out_five():
    """app depends on 5 modules: router, dashboard, settings, analytics, event-bus."""
    assert _mod("app")["fan_out"] == 5


def test_dashboard_instability_exactly_threshold():
    """dashboard: Ca=1, Ce=4. I = 4/5 = 0.8. This equals the threshold 0.8
    exactly, so high_instability must NOT be triggered (strictly exceeds)."""
    assert math.isclose(_mod("dashboard")["instability"], 0.8, abs_tol=1e-6)


def test_auth_service_instability():
    """auth-service: Ca=3, Ce=2. I = 2/5 = 0.4."""
    assert math.isclose(_mod("auth-service")["instability"], 0.4, abs_tol=1e-6)


def test_event_bus_instability():
    """event-bus: Ca=2 (app, analytics), Ce=1 (logger). I = 1/3 = 0.333333."""
    assert math.isclose(_mod("event-bus")["instability"], 1/3, abs_tol=1e-6)


# ── layer classification ───────────────────────────────────────────

def test_app_layer_entry():
    """app is an entry point."""
    assert _mod("app")["layer"] == "entry"


def test_logger_layer_leaf():
    """logger has fan_out=0 and is reachable -> leaf."""
    assert _mod("logger")["layer"] == "leaf"


def test_route_config_layer_leaf():
    """route-config has fan_out=0 and is reachable -> leaf."""
    assert _mod("route-config")["layer"] == "leaf"


# ── size transforms (multiplicative trap) ───────────────────────────

def test_overall_compression_ratio():
    """overall_compression_ratio = 0.65 * 0.30 = 0.195 (multiplicative)."""
    assert math.isclose(
        _r()["size_analysis"]["overall_compression_ratio"], 0.195, abs_tol=1e-6)


def test_total_raw_bytes():
    """Sum of all module raw sizes."""
    assert _r()["size_analysis"]["total_raw_bytes"] == 21190


def test_total_potential_savings():
    """Sum of all potential_savings_bytes across modules."""
    assert math.isclose(
        _r()["size_analysis"]["total_potential_savings_bytes"], 4360.0, abs_tol=1e-4)


# ── used-export analysis (key trap) ────────────────────────────────

def test_logger_used_exports_includes_warn():
    """logger has 2 used exports: 'log' (directly imported) and 'warn'
    (imported by analytics through event-bus multi-hop re-export).
    This is a critical trap: warn counts as used for logger because
    analytics resolves warn through event-bus's re-export chain."""
    assert _mod("logger")["used_exports"] == 2


def test_logger_used_export_ratio():
    """logger: 2 used / 3 total = 0.666667."""
    assert math.isclose(_mod("logger")["used_export_ratio"], 2/3, abs_tol=1e-6)


def test_logger_potential_savings():
    """logger: eligible, 380 * (1 - 2/3) = 380 * 1/3 = 126.666667."""
    assert math.isclose(
        _mod("logger")["potential_savings_bytes"], 380 * (1/3), abs_tol=1e-4)


def test_chart_engine_used_exports():
    """chart-engine: only ChartPanel used (1/2 exports), renderChart unused."""
    assert _mod("chart-engine")["used_exports"] == 1
    assert _mod("chart-engine")["total_exports"] == 2
    assert math.isclose(_mod("chart-engine")["used_export_ratio"], 0.5, abs_tol=1e-6)


def test_chart_engine_savings():
    """chart-engine: 3200 * (1 - 0.5) = 1600."""
    assert math.isclose(_mod("chart-engine")["potential_savings_bytes"], 1600.0, abs_tol=1e-4)


def test_token_store_used_export_ratio():
    """token-store: 1/3 used (only loadToken). Ratio = 0.333333."""
    assert _mod("token-store")["used_exports"] == 1
    assert math.isclose(_mod("token-store")["used_export_ratio"], 1/3, abs_tol=1e-6)


def test_token_store_savings():
    """token-store: 620 * (1 - 1/3) = 620 * 2/3 = 413.333333."""
    assert math.isclose(
        _mod("token-store")["potential_savings_bytes"], 620 * (2/3), abs_tol=1e-4)


def test_utils_used_exports():
    """utils: formatNumber and sanitize used (2/4). hash and debounce unused."""
    assert _mod("utils")["used_exports"] == 2
    assert _mod("utils")["total_exports"] == 4
    assert math.isclose(_mod("utils")["used_export_ratio"], 0.5, abs_tol=1e-6)


def test_api_client_used_exports():
    """api-client: apiGet and apiRequest used (2/3). apiPost unused."""
    assert _mod("api-client")["used_exports"] == 2
    assert math.isclose(_mod("api-client")["used_export_ratio"], 2/3, abs_tol=1e-6)


def test_event_bus_all_exports_used():
    """event-bus: EventBus used by app, emit used by analytics. 2/2 = 1.0."""
    assert _mod("event-bus")["used_exports"] == 2
    assert math.isclose(_mod("event-bus")["used_export_ratio"], 1.0, abs_tol=1e-6)


def test_app_entry_all_exports_used():
    """Entry point app: all exports considered used. Ratio = 1.0."""
    assert _mod("app")["used_export_ratio"] == 1.0


def test_analytics_no_exports_used():
    """analytics: trackEvent not imported by anyone. used_exports = 0."""
    assert _mod("analytics")["used_exports"] == 0
    assert math.isclose(_mod("analytics")["used_export_ratio"], 0.0, abs_tol=1e-6)


# ── tree-shaking eligibility ──────────────────────────────────────

def test_analytics_not_tree_shakeable():
    """analytics has side_effects=true, so NOT tree-shake eligible."""
    assert _mod("analytics")["tree_shake_eligible"] is False


def test_analytics_zero_savings():
    """analytics is not eligible, so potential_savings = 0."""
    assert _mod("analytics")["potential_savings_bytes"] == 0.0


def test_api_client_not_tree_shakeable():
    """api-client is in a cycle, so NOT tree-shake eligible."""
    assert _mod("api-client")["tree_shake_eligible"] is False
    assert _mod("api-client")["potential_savings_bytes"] == 0.0


def test_auth_service_not_tree_shakeable():
    """auth-service is in a cycle, so NOT tree-shake eligible."""
    assert _mod("auth-service")["tree_shake_eligible"] is False


def test_logger_tree_shakeable():
    """logger: no side effects, not in cycle -> eligible."""
    assert _mod("logger")["tree_shake_eligible"] is True


def test_legacy_polyfill_savings():
    """legacy-polyfill: eligible, 0/1 used, savings = 350 * 1.0 = 350."""
    assert math.isclose(_mod("legacy-polyfill")["potential_savings_bytes"], 350.0, abs_tol=1e-4)


# ── dependency edges ────────────────────────────────────────────────

def test_edges_count():
    """30 resolved dependency edges."""
    assert len(_r()["dependency_edges"]) == 30


def test_edges_sorted():
    """Edges must be sorted by (source, target)."""
    edges = _r()["dependency_edges"]
    pairs = [(e["source"], e["target"]) for e in edges]
    assert pairs == sorted(pairs)


def test_side_effect_import_edge():
    """app imports analytics with empty specifiers (side-effect import).
    Edge app -> analytics must exist."""
    edges = _r()["dependency_edges"]
    assert {"source": "app", "target": "analytics"} in edges


def test_app_to_event_bus_edge():
    """app imports EventBus from event-bus (own export). Edge must exist."""
    edges = _r()["dependency_edges"]
    assert {"source": "app", "target": "event-bus"} in edges


def test_event_bus_to_logger_edge():
    """event-bus imports log from logger. Direct edge must exist."""
    edges = _r()["dependency_edges"]
    assert {"source": "event-bus", "target": "logger"} in edges


# ── build order ─────────────────────────────────────────────────────

def test_build_order_length():
    """Build order must include all 19 modules."""
    assert len(_r()["build_order"]) == 19


def test_build_order_all_modules():
    """Build order must contain every module exactly once."""
    order = _r()["build_order"]
    assert sorted(order) == sorted(m["name"] for m in _r()["modules"])


def test_build_order_deps_before_dependents():
    """Every dependency of a module must appear before it in build order."""
    order = _r()["build_order"]
    pos = {name: i for i, name in enumerate(order)}
    edges = _r()["dependency_edges"]
    scc_members = set()
    for cyc in _r()["cycles"]:
        scc_members.update(cyc["members"])
    for e in edges:
        s, t = e["source"], e["target"]
        if s in scc_members and t in scc_members:
            continue
        assert pos[t] < pos[s], f"{t} must appear before {s}"


def test_build_order_app_last():
    """Entry point app must be last in build order."""
    assert _r()["build_order"][-1] == "app"


def test_build_order_scc_members_adjacent():
    """SCC members (api-client, auth-service) must be adjacent and alphabetical."""
    order = _r()["build_order"]
    idx_a = order.index("api-client")
    idx_b = order.index("auth-service")
    assert idx_b == idx_a + 1


# ── quality findings ────────────────────────────────────────────────

def test_findings_count():
    """8 findings total."""
    assert len(_r()["quality_findings"]) == 8


def test_findings_sorted():
    """Findings sorted by severity_rank desc, finding_type asc, module asc."""
    findings = _r()["quality_findings"]
    keys = [
        (-f["severity_rank"], f["finding_type"], f["module"] or "")
        for f in findings
    ]
    assert keys == sorted(keys)


def test_finding_dependency_cycle():
    """dependency_cycle finding with module=null, severity=critical."""
    f = _finding("dependency_cycle")
    assert f is not None
    assert f["module"] is None
    assert f["severity"] == "critical"
    assert f["severity_rank"] == 4


def test_finding_deep_logger():
    """deep_module finding for logger (depth 6 > threshold 5)."""
    f = _finding("deep_module", "logger")
    assert f is not None
    assert f["evidence"]["depth"] == 6


def test_finding_deep_utils():
    """deep_module finding for utils (depth 6 > threshold 5)."""
    f = _finding("deep_module", "utils")
    assert f is not None


def test_finding_excessive_fan_out_app():
    """excessive_fan_out for app (Ce=5 > threshold 3)."""
    f = _finding("excessive_fan_out", "app")
    assert f is not None
    assert f["evidence"]["fan_out"] == 5


def test_finding_excessive_fan_out_dashboard():
    """excessive_fan_out for dashboard (Ce=4 > threshold 3)."""
    f = _finding("excessive_fan_out", "dashboard")
    assert f is not None
    assert f["evidence"]["fan_out"] == 4


def test_finding_oversized_chart_engine():
    """oversized_module for chart-engine (3200 > 2500)."""
    f = _finding("oversized_module", "chart-engine")
    assert f is not None
    assert f["evidence"]["size_bytes"] == 3200


def test_finding_high_instability_app():
    """high_instability for app (I=1.0 > threshold 0.8)."""
    f = _finding("high_instability", "app")
    assert f is not None


def test_finding_unreachable_legacy_polyfill():
    """unreachable_module for legacy-polyfill."""
    f = _finding("unreachable_module", "legacy-polyfill")
    assert f is not None


def test_finding_cycle_null_module_sorts_first():
    """dependency_cycle has module=null which sorts as '' (before any name)."""
    findings = _r()["quality_findings"]
    assert findings[0]["finding_type"] == "dependency_cycle"
    assert findings[0]["module"] is None


# ── no false positives ──────────────────────────────────────────────

def test_no_deep_finding_for_depth_5():
    """http-utils and token-store have depth 5 (== threshold), must NOT trigger."""
    assert _finding("deep_module", "http-utils") is None
    assert _finding("deep_module", "token-store") is None


def test_no_instability_finding_for_dashboard():
    """dashboard instability is 0.8 (== threshold 0.8). Must not trigger
    (strictly exceeds required)."""
    assert _finding("high_instability", "dashboard") is None


def test_no_fan_out_finding_for_analytics():
    """analytics fan_out=2 <= threshold 3. Must not trigger."""
    assert _finding("excessive_fan_out", "analytics") is None


# ── module field completeness ───────────────────────────────────────

def test_module_has_all_required_keys():
    """Each module entry must have all required keys."""
    required = {
        "name", "path", "depth", "fan_in", "fan_out", "instability",
        "raw_size_bytes", "minified_bytes", "compressed_bytes",
        "in_cycle", "reachable", "layer",
        "used_exports", "total_exports", "used_export_ratio",
        "tree_shake_eligible", "potential_savings_bytes",
    }
    for m in _r()["modules"]:
        assert required.issubset(set(m.keys())), f"{m['name']} missing keys"


# ── input integrity ─────────────────────────────────────────────────

def test_input_module_count():
    """Verify 19 module files exist in data/modules/."""
    mods = list((DATA_DIR / "modules").glob("*.json"))
    assert len(mods) == 19


def test_input_project_entry_point():
    """project.json must list app as the sole entry point."""
    proj = json.loads((DATA_DIR / "project.json").read_text("utf-8"))
    assert proj["entry_points"] == ["app"]


def test_input_config_checksums():
    """Verify config.json has not been modified by computing checksum."""
    cfg = json.loads((DATA_DIR / "config.json").read_text("utf-8"))
    assert cfg["transforms"]["minify_ratio"] == 0.65
    assert cfg["transforms"]["compress_ratio"] == 0.30
    assert cfg["thresholds"]["max_depth"] == 5
    assert cfg["thresholds"]["max_fan_out"] == 3
    assert cfg["thresholds"]["max_instability"] == 0.8
