"""Tests for java-package-metrics-audit-hard."""
import json
import math
import pathlib

ROOT = pathlib.Path("/app")
if not (ROOT / "src").is_dir():
    ROOT = pathlib.Path("/app")

OUT_DIR = pathlib.pathlib.Path('/app/output')

FLOAT_TOL = 1e-4

EXPECTED_PACKAGES = [
    "com.acme.api",
    "com.acme.config",
    "com.acme.core",
    "com.acme.model",
    "com.acme.notification",
    "com.acme.persistence",
    "com.acme.service",
    "com.acme.util",
]


def load_report():
    """Load and return the main output JSON report."""
    p = OUT_DIR / "report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


def pkg(name):
    """Look up a package entry by name."""
    for p in R["packages"]:
        if p["name"] == name:
            return p
    raise AssertionError(f"Package {name} not found in report")


# ─── Output file existence ──────────────────────────────────────────────────


def test_output_file_exists():
    """Verify the main output file was created."""
    assert (OUT_DIR / "report.json").is_file()


# ─── Top-level structure ────────────────────────────────────────────────────


def test_top_level_keys():
    """Verify the report contains all required top-level keys."""
    required = {"packages", "dependency_edges", "circular_dependencies",
                "sdp_violations", "summary"}
    assert set(R.keys()) == required, f"Keys mismatch: got {sorted(R.keys())}"


def test_top_level_key_order():
    """Verify top-level keys appear in the documented order."""
    keys = list(R.keys())
    expected_order = ["packages", "dependency_edges", "circular_dependencies",
                      "sdp_violations", "summary"]
    assert keys == expected_order, f"Key order mismatch: {keys}"


def test_packages_is_list():
    """Verify packages is a list."""
    assert isinstance(R["packages"], list)


def test_dependency_edges_is_list():
    """Verify dependency_edges is a list."""
    assert isinstance(R["dependency_edges"], list)


def test_circular_dependencies_is_list():
    """Verify circular_dependencies is a list."""
    assert isinstance(R["circular_dependencies"], list)


def test_sdp_violations_is_list():
    """Verify sdp_violations is a list."""
    assert isinstance(R["sdp_violations"], list)


def test_summary_is_dict():
    """Verify summary is a dict."""
    assert isinstance(R["summary"], dict)


# ─── Package count and names ────────────────────────────────────────────────


def test_package_count():
    """Verify the correct number of packages was detected."""
    assert len(R["packages"]) == 8


def test_package_names():
    """Verify all expected package names are present."""
    names = [p["name"] for p in R["packages"]]
    assert names == EXPECTED_PACKAGES


def test_packages_sorted_by_name():
    """Verify packages array is sorted by name."""
    names = [p["name"] for p in R["packages"]]
    assert names == sorted(names)


# ─── Package entry structure ────────────────────────────────────────────────


def test_package_entry_keys():
    """Verify each package has all required keys."""
    required = {"name", "types", "afferent_coupling", "efferent_coupling",
                "instability", "abstractness", "distance", "depends_on",
                "depended_on_by", "layer"}
    for p in R["packages"]:
        assert set(p.keys()) == required, \
            f"Package {p['name']} keys mismatch: {sorted(p.keys())}"


def test_types_subkeys():
    """Verify each package types object has all required subkeys."""
    required = {"total", "abstract_classes", "interfaces", "concrete_classes",
                "enums", "annotations"}
    for p in R["packages"]:
        assert set(p["types"].keys()) == required, \
            f"Package {p['name']} types keys: {sorted(p['types'].keys())}"


# ─── Type classification per package ────────────────────────────────────────


def test_core_types():
    """Verify com.acme.core type classification: 1 abstract, 2 interfaces, 1 concrete."""
    t = pkg("com.acme.core")["types"]
    assert t["total"] == 4
    assert t["abstract_classes"] == 1
    assert t["interfaces"] == 2
    assert t["concrete_classes"] == 1
    assert t["enums"] == 0
    assert t["annotations"] == 0


def test_model_types():
    """Verify com.acme.model: 4 concrete classes and 1 enum."""
    t = pkg("com.acme.model")["types"]
    assert t["total"] == 5
    assert t["concrete_classes"] == 4
    assert t["enums"] == 1
    assert t["abstract_classes"] == 0
    assert t["interfaces"] == 0


def test_util_types():
    """Verify com.acme.util: 4 concrete classes, no abstractions."""
    t = pkg("com.acme.util")["types"]
    assert t["total"] == 4
    assert t["concrete_classes"] == 4
    assert t["abstract_classes"] == 0
    assert t["interfaces"] == 0


def test_persistence_types():
    """Verify com.acme.persistence: 4 concrete classes."""
    t = pkg("com.acme.persistence")["types"]
    assert t["total"] == 4
    assert t["concrete_classes"] == 4


def test_service_types():
    """Verify com.acme.service: 4 concrete and 1 interface (Auditable)."""
    t = pkg("com.acme.service")["types"]
    assert t["total"] == 5
    assert t["concrete_classes"] == 4
    assert t["interfaces"] == 1
    assert t["abstract_classes"] == 0


def test_notification_types():
    """Verify com.acme.notification: 2 concrete and 1 interface (Notifier)."""
    t = pkg("com.acme.notification")["types"]
    assert t["total"] == 3
    assert t["concrete_classes"] == 2
    assert t["interfaces"] == 1


def test_api_annotation_type():
    """Verify com.acme.api correctly classifies ApiVersion as an annotation type."""
    t = pkg("com.acme.api")["types"]
    assert t["annotations"] == 1, "ApiVersion @interface must be classified as annotation"


def test_api_abstract_class():
    """Verify com.acme.api has one abstract class (Controller)."""
    t = pkg("com.acme.api")["types"]
    assert t["abstract_classes"] == 1


def test_api_types_total():
    """Verify com.acme.api total: 5 types (1 abstract + 3 concrete + 1 annotation)."""
    t = pkg("com.acme.api")["types"]
    assert t["total"] == 5
    assert t["concrete_classes"] == 3


def test_config_types():
    """Verify com.acme.config: 2 concrete classes only."""
    t = pkg("com.acme.config")["types"]
    assert t["total"] == 2
    assert t["concrete_classes"] == 2
    assert t["abstract_classes"] == 0
    assert t["interfaces"] == 0


def test_total_types_summary():
    """Verify summary total_types equals sum across all packages."""
    assert R["summary"]["total_types"] == 32


def test_total_types_consistency():
    """Verify summary total_types matches sum of individual package totals."""
    total = sum(p["types"]["total"] for p in R["packages"])
    assert R["summary"]["total_types"] == total


# ─── Dependency graph ───────────────────────────────────────────────────────


def test_core_depends_on_nothing():
    """Verify com.acme.core has no outgoing dependencies."""
    assert pkg("com.acme.core")["depends_on"] == []


def test_util_depends_on_nothing():
    """Verify com.acme.util has no outgoing dependencies."""
    assert pkg("com.acme.util")["depends_on"] == []


def test_model_depends_on_core():
    """Verify com.acme.model depends only on core."""
    assert pkg("com.acme.model")["depends_on"] == ["com.acme.core"]


def test_persistence_dependencies():
    """Verify com.acme.persistence depends on core, model, and util."""
    deps = pkg("com.acme.persistence")["depends_on"]
    assert deps == ["com.acme.core", "com.acme.model", "com.acme.util"]


def test_service_dependencies():
    """Verify com.acme.service depends on core, model, notification, persistence."""
    deps = pkg("com.acme.service")["depends_on"]
    assert deps == ["com.acme.core", "com.acme.model",
                    "com.acme.notification", "com.acme.persistence"]


def test_notification_depends_on_service():
    """Verify com.acme.notification depends only on service (creating a cycle)."""
    assert pkg("com.acme.notification")["depends_on"] == ["com.acme.service"]


def test_api_dependencies():
    """Verify com.acme.api depends on model, service, and util."""
    deps = pkg("com.acme.api")["depends_on"]
    assert deps == ["com.acme.model", "com.acme.service", "com.acme.util"]


def test_config_dependencies():
    """Verify com.acme.config depends on core and service."""
    deps = pkg("com.acme.config")["depends_on"]
    assert deps == ["com.acme.core", "com.acme.service"]


def test_dependency_edges_count():
    """Verify total dependency edge count is 14."""
    assert len(R["dependency_edges"]) == 14
    assert R["summary"]["total_dependency_edges"] == 14


def test_dependency_edges_sorted():
    """Verify dependency_edges are sorted by (source, target)."""
    edges = R["dependency_edges"]
    keys = [(e["source"], e["target"]) for e in edges]
    assert keys == sorted(keys)


def test_depends_on_lists_sorted():
    """Verify every depends_on list is sorted."""
    for p in R["packages"]:
        assert p["depends_on"] == sorted(p["depends_on"]), \
            f"Package {p['name']} depends_on not sorted"


def test_depended_on_by_lists_sorted():
    """Verify every depended_on_by list is sorted."""
    for p in R["packages"]:
        assert p["depended_on_by"] == sorted(p["depended_on_by"]), \
            f"Package {p['name']} depended_on_by not sorted"


# ─── Afferent coupling (Ca) ────────────────────────────────────────────────


def test_core_afferent_coupling():
    """Verify Ca(core) = 4: model, persistence, service, config depend on it."""
    assert pkg("com.acme.core")["afferent_coupling"] == 4


def test_model_afferent_coupling():
    """Verify Ca(model) = 3: persistence, service, api depend on it."""
    assert pkg("com.acme.model")["afferent_coupling"] == 3


def test_util_afferent_coupling():
    """Verify Ca(util) = 2: persistence and api depend on it."""
    assert pkg("com.acme.util")["afferent_coupling"] == 2


def test_persistence_afferent_coupling():
    """Verify Ca(persistence) = 1: only service depends on it."""
    assert pkg("com.acme.persistence")["afferent_coupling"] == 1


def test_service_afferent_coupling():
    """Verify Ca(service) = 3: notification, api, config depend on it."""
    assert pkg("com.acme.service")["afferent_coupling"] == 3


def test_notification_afferent_coupling():
    """Verify Ca(notification) = 1: only service depends on it."""
    assert pkg("com.acme.notification")["afferent_coupling"] == 1


def test_api_afferent_coupling():
    """Verify Ca(api) = 0: nothing depends on it."""
    assert pkg("com.acme.api")["afferent_coupling"] == 0


def test_config_afferent_coupling():
    """Verify Ca(config) = 0: nothing depends on it."""
    assert pkg("com.acme.config")["afferent_coupling"] == 0


# ─── Efferent coupling (Ce) ────────────────────────────────────────────────


def test_core_efferent_coupling():
    """Verify Ce(core) = 0."""
    assert pkg("com.acme.core")["efferent_coupling"] == 0


def test_service_efferent_coupling():
    """Verify Ce(service) = 4: depends on core, model, persistence, notification."""
    assert pkg("com.acme.service")["efferent_coupling"] == 4


def test_api_efferent_coupling():
    """Verify Ce(api) = 3: depends on model, service, util."""
    assert pkg("com.acme.api")["efferent_coupling"] == 3


def test_config_efferent_coupling():
    """Verify Ce(config) = 2: depends on core, service."""
    assert pkg("com.acme.config")["efferent_coupling"] == 2


# ─── Instability ────────────────────────────────────────────────────────────


def test_core_instability():
    """Verify I(core) = 0.0 (fully stable, Ce=0)."""
    assert pkg("com.acme.core")["instability"] == 0.0


def test_util_instability():
    """Verify I(util) = 0.0 (fully stable, Ce=0)."""
    assert pkg("com.acme.util")["instability"] == 0.0


def test_model_instability():
    """Verify I(model) = 1/(3+1) = 0.25."""
    assert math.isclose(pkg("com.acme.model")["instability"], 0.25, abs_tol=FLOAT_TOL)


def test_persistence_instability():
    """Verify I(persistence) = 3/(1+3) = 0.75."""
    assert math.isclose(pkg("com.acme.persistence")["instability"], 0.75, abs_tol=FLOAT_TOL)


def test_service_instability():
    """Verify I(service) = 4/(3+4) = 4/7 ≈ 0.571429."""
    assert math.isclose(pkg("com.acme.service")["instability"], 0.571429, abs_tol=FLOAT_TOL)


def test_notification_instability():
    """Verify I(notification) = 1/(1+1) = 0.5."""
    assert math.isclose(pkg("com.acme.notification")["instability"], 0.5, abs_tol=FLOAT_TOL)


def test_api_instability():
    """Verify I(api) = 3/(0+3) = 1.0 (fully unstable)."""
    assert pkg("com.acme.api")["instability"] == 1.0


def test_config_instability():
    """Verify I(config) = 2/(0+2) = 1.0 (fully unstable)."""
    assert pkg("com.acme.config")["instability"] == 1.0


# ─── Abstractness ───────────────────────────────────────────────────────────


def test_core_abstractness():
    """Verify A(core) = 3/4 = 0.75 (1 abstract + 2 interfaces out of 4 types)."""
    assert math.isclose(pkg("com.acme.core")["abstractness"], 0.75, abs_tol=FLOAT_TOL)


def test_model_abstractness():
    """Verify A(model) = 0.0 (all concrete + enum, no abstractions)."""
    assert pkg("com.acme.model")["abstractness"] == 0.0


def test_util_abstractness():
    """Verify A(util) = 0.0 (all concrete)."""
    assert pkg("com.acme.util")["abstractness"] == 0.0


def test_service_abstractness():
    """Verify A(service) = 1/5 = 0.2 (1 interface out of 5 types)."""
    assert math.isclose(pkg("com.acme.service")["abstractness"], 0.2, abs_tol=FLOAT_TOL)


def test_notification_abstractness():
    """Verify A(notification) = 1/3 ≈ 0.333333."""
    assert math.isclose(pkg("com.acme.notification")["abstractness"], 0.333333, abs_tol=FLOAT_TOL)


def test_api_abstractness_includes_annotation():
    """Verify A(api) = 2/5 = 0.4, counting @interface ApiVersion as abstract."""
    assert math.isclose(pkg("com.acme.api")["abstractness"], 0.4, abs_tol=FLOAT_TOL)


def test_config_abstractness():
    """Verify A(config) = 0.0 (all concrete)."""
    assert pkg("com.acme.config")["abstractness"] == 0.0


# ─── Distance from main sequence ────────────────────────────────────────────


def test_core_distance():
    """Verify D(core) = |0.75 + 0.0 - 1| = 0.25."""
    assert math.isclose(pkg("com.acme.core")["distance"], 0.25, abs_tol=FLOAT_TOL)


def test_util_distance():
    """Verify D(util) = |0.0 + 0.0 - 1| = 1.0 (Zone of Pain)."""
    assert math.isclose(pkg("com.acme.util")["distance"], 1.0, abs_tol=FLOAT_TOL)


def test_model_distance():
    """Verify D(model) = |0.0 + 0.25 - 1| = 0.75."""
    assert math.isclose(pkg("com.acme.model")["distance"], 0.75, abs_tol=FLOAT_TOL)


def test_service_distance():
    """Verify D(service) = |0.2 + 4/7 - 1| ≈ 0.228571."""
    assert math.isclose(pkg("com.acme.service")["distance"], 0.228571, abs_tol=FLOAT_TOL)


def test_config_distance():
    """Verify D(config) = |0.0 + 1.0 - 1| = 0.0 (on the main sequence)."""
    assert math.isclose(pkg("com.acme.config")["distance"], 0.0, abs_tol=FLOAT_TOL)


def test_api_distance():
    """Verify D(api) = |0.4 + 1.0 - 1| = 0.4."""
    assert math.isclose(pkg("com.acme.api")["distance"], 0.4, abs_tol=FLOAT_TOL)


def test_persistence_distance():
    """Verify D(persistence) = |0.0 + 0.75 - 1| = 0.25."""
    assert math.isclose(pkg("com.acme.persistence")["distance"], 0.25, abs_tol=FLOAT_TOL)


def test_notification_distance():
    """Verify D(notification) = |1/3 + 0.5 - 1| ≈ 0.166667."""
    assert math.isclose(pkg("com.acme.notification")["distance"], 0.166667, abs_tol=FLOAT_TOL)


# ─── Circular dependencies ──────────────────────────────────────────────────


def test_circular_dependency_count():
    """Verify exactly one circular dependency (SCC) was detected."""
    assert len(R["circular_dependencies"]) == 1
    assert R["summary"]["circular_dependency_count"] == 1


def test_circular_dependency_packages():
    """Verify the SCC contains notification and service."""
    scc = R["circular_dependencies"][0]
    assert scc["packages"] == ["com.acme.notification", "com.acme.service"]


def test_circular_dependency_representative():
    """Verify SCC representative is the lex-smallest: com.acme.notification."""
    scc = R["circular_dependencies"][0]
    assert scc["representative"] == "com.acme.notification"


def test_circular_dependency_cycle_id():
    """Verify the first (and only) SCC has cycle_id = 1."""
    assert R["circular_dependencies"][0]["cycle_id"] == 1


def test_circular_dependency_packages_sorted():
    """Verify packages within the SCC are in lexicographic order."""
    scc = R["circular_dependencies"][0]
    assert scc["packages"] == sorted(scc["packages"])


# ─── SDP violations ─────────────────────────────────────────────────────────


def test_sdp_violation_count():
    """Verify exactly 2 SDP violations exist."""
    assert len(R["sdp_violations"]) == 2
    assert R["summary"]["sdp_violation_count"] == 2


def test_sdp_violation_service_to_persistence():
    """Verify SDP violation: service depends on persistence (0.75 > 0.571429)."""
    violations = {(v["source"], v["target"]): v for v in R["sdp_violations"]}
    key = ("com.acme.service", "com.acme.persistence")
    assert key in violations, f"Missing SDP violation: {key}"
    v = violations[key]
    assert math.isclose(v["source_instability"], 0.571429, abs_tol=FLOAT_TOL)
    assert math.isclose(v["target_instability"], 0.75, abs_tol=FLOAT_TOL)


def test_sdp_violation_notification_to_service():
    """Verify SDP violation: notification depends on service (0.571429 > 0.5)."""
    violations = {(v["source"], v["target"]): v for v in R["sdp_violations"]}
    key = ("com.acme.notification", "com.acme.service")
    assert key in violations, f"Missing SDP violation: {key}"
    v = violations[key]
    assert math.isclose(v["source_instability"], 0.5, abs_tol=FLOAT_TOL)
    assert math.isclose(v["target_instability"], 0.571429, abs_tol=FLOAT_TOL)


def test_sdp_violations_sorted():
    """Verify SDP violations are sorted by (source, target)."""
    keys = [(v["source"], v["target"]) for v in R["sdp_violations"]]
    assert keys == sorted(keys)


def test_sdp_violation_keys():
    """Verify each SDP violation has the required keys."""
    required = {"source", "target", "source_instability", "target_instability"}
    for v in R["sdp_violations"]:
        assert set(v.keys()) == required


# ─── Layer assignment ────────────────────────────────────────────────────────


def test_core_layer():
    """Verify core is layer 0 (no dependencies)."""
    assert pkg("com.acme.core")["layer"] == 0


def test_util_layer():
    """Verify util is layer 0 (no dependencies)."""
    assert pkg("com.acme.util")["layer"] == 0


def test_model_layer():
    """Verify model is layer 1 (depends on core at layer 0)."""
    assert pkg("com.acme.model")["layer"] == 1


def test_persistence_layer():
    """Verify persistence is layer 2 (depends on model at layer 1)."""
    assert pkg("com.acme.persistence")["layer"] == 2


def test_service_layer():
    """Verify service is layer 3 (SCC depends on persistence at layer 2)."""
    assert pkg("com.acme.service")["layer"] == 3


def test_notification_layer():
    """Verify notification is layer 3 (same SCC as service)."""
    assert pkg("com.acme.notification")["layer"] == 3


def test_scc_packages_same_layer():
    """Verify all packages in an SCC share the same layer."""
    assert pkg("com.acme.service")["layer"] == pkg("com.acme.notification")["layer"]


def test_api_layer():
    """Verify api is layer 4 (depends on service SCC at layer 3)."""
    assert pkg("com.acme.api")["layer"] == 4


def test_config_layer():
    """Verify config is layer 4 (depends on service SCC at layer 3)."""
    assert pkg("com.acme.config")["layer"] == 4


# ─── Zone classification ────────────────────────────────────────────────────


def test_zone_of_pain():
    """Verify Zone of Pain contains model and util (D>0.5, I<0.5, A<0.5)."""
    assert R["summary"]["packages_in_zone_of_pain"] == [
        "com.acme.model", "com.acme.util"
    ]


def test_zone_of_pain_sorted():
    """Verify zone of pain list is sorted."""
    pain = R["summary"]["packages_in_zone_of_pain"]
    assert pain == sorted(pain)


def test_zone_of_uselessness_empty():
    """Verify no packages are in the Zone of Uselessness."""
    assert R["summary"]["packages_in_zone_of_uselessness"] == []


# ─── Summary ────────────────────────────────────────────────────────────────


def test_summary_keys():
    """Verify summary contains all required keys."""
    required = {"total_packages", "total_types", "total_dependency_edges",
                "circular_dependency_count", "sdp_violation_count",
                "packages_in_zone_of_pain", "packages_in_zone_of_uselessness"}
    assert set(R["summary"].keys()) == required


def test_summary_total_packages():
    """Verify summary total_packages is 8."""
    assert R["summary"]["total_packages"] == 8


def test_summary_total_dependency_edges():
    """Verify summary total_dependency_edges matches actual edges count."""
    assert R["summary"]["total_dependency_edges"] == len(R["dependency_edges"])


# ─── Depended-on-by consistency ──────────────────────────────────────────────


def test_core_depended_on_by():
    """Verify depended_on_by for core lists all packages that import from it."""
    assert pkg("com.acme.core")["depended_on_by"] == [
        "com.acme.config", "com.acme.model",
        "com.acme.persistence", "com.acme.service"
    ]


def test_service_depended_on_by():
    """Verify depended_on_by for service lists notification, api, config."""
    assert pkg("com.acme.service")["depended_on_by"] == [
        "com.acme.api", "com.acme.config", "com.acme.notification"
    ]


def test_depended_on_by_consistency():
    """Verify depended_on_by is consistent with depends_on across all packages."""
    for p in R["packages"]:
        for dep in p["depends_on"]:
            dep_pkg = pkg(dep)
            assert p["name"] in dep_pkg["depended_on_by"], \
                f"{p['name']} depends on {dep} but not in depended_on_by"


def test_depends_on_consistency():
    """Verify depends_on is consistent with depended_on_by across all packages."""
    for p in R["packages"]:
        for user in p["depended_on_by"]:
            user_pkg = pkg(user)
            assert p["name"] in user_pkg["depends_on"], \
                f"{user} in depended_on_by of {p['name']} but not in depends_on"


# ─── JSON formatting ────────────────────────────────────────────────────────


def test_json_trailing_newline():
    """Verify the JSON file ends with a trailing newline."""
    raw = (OUT_DIR / "report.json").read_text(encoding="utf-8")
    assert raw.endswith("\n"), "report.json must end with trailing newline"


def test_json_two_space_indent():
    """Verify the JSON uses two-space indentation."""
    raw = (OUT_DIR / "report.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    canonical = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    assert raw == canonical, "JSON formatting does not match 2-space indent"
