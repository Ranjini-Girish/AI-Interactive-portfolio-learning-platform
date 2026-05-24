"""Tests for js-workspace-dependency-audit-hard task."""
import json
from pathlib import Path

OUT_DIR = Path("/app/output/workspace_audit.json")


def get_report():
    assert OUT_DIR.exists(), "workspace_audit.json not found"
    return json.loads(OUT_DIR.read_text())


report = None


def setup_module():
    global report
    report = get_report()


# ─── STRUCTURE TESTS ──────────────────────────────────────────────────────────


def test_01_output_exists():
    """Output file must exist."""
    assert OUT_DIR.exists()


def test_02_valid_json():
    """Output must be valid JSON."""
    json.loads(OUT_DIR.read_text())


def test_03_top_level_keys():
    """Must have exactly these top-level keys."""
    expected = {"dependency_graph", "findings", "hoisting", "metadata", "summary"}
    assert set(report.keys()) == expected


def test_04_keys_sorted_top_level():
    """Top-level keys must be sorted alphabetically."""
    keys = list(report.keys())
    assert keys == sorted(keys)


def test_05_two_space_indent():
    """JSON must use 2-space indentation."""
    text = OUT_DIR.read_text()
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped and stripped[0] not in "{}[]":
            indent = len(line) - len(stripped)
            assert indent % 2 == 0, f"Non-2-space indent: {line!r}"


def test_06_trailing_newline():
    """File must end with trailing newline."""
    text = OUT_DIR.read_text()
    assert text.endswith("}\n")


# ─── METADATA TESTS ──────────────────────────────────────────────────────────


def test_07_metadata_evaluation_date():
    """evaluation_date must be 2026-05-14."""
    assert report["metadata"]["evaluation_date"] == "2026-05-14"


def test_08_metadata_scope():
    """scope must be 'dependencies'."""
    assert report["metadata"]["scope"] == "dependencies"


def test_09_metadata_workspace_packages():
    """workspace_packages must list all 5 packages sorted."""
    expected = ["pkg-api", "pkg-auth", "pkg-cli", "pkg-core", "pkg-utils"]
    assert report["metadata"]["workspace_packages"] == expected


def test_10_metadata_source_hash():
    """source_hash must be 64-char hex SHA-256."""
    h = report["metadata"]["source_hash"]
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_11_metadata_source_hash_value():
    """source_hash must match expected value."""
    assert report["metadata"]["source_hash"] == \
        "2a845eb4557caef11fbfbfc413177ee20f19609f1af399c2cef28ef45c5ef978"


# ─── DEPENDENCY GRAPH TESTS ──────────────────────────────────────────────────


def test_12_dep_graph_packages():
    """dependency_graph must have all 5 workspace packages."""
    expected = {"pkg-api", "pkg-auth", "pkg-cli", "pkg-core", "pkg-utils"}
    assert set(report["dependency_graph"].keys()) == expected


def test_13_dep_graph_pkg_core():
    """pkg-core must resolve lodash, uuid, zod correctly."""
    core = report["dependency_graph"]["pkg-core"]
    assert core["lodash"] == {"depth": 1, "version": "4.17.21"}
    assert core["uuid"] == {"depth": 1, "version": "9.0.0"}
    assert core["zod"] == {"depth": 1, "version": "3.22.4"}


def test_14_dep_graph_pkg_core_count():
    """pkg-core should have exactly 3 dependencies."""
    assert len(report["dependency_graph"]["pkg-core"]) == 3


def test_15_caret_zero_axios_utils():
    """^0.21.0 must resolve to 0.21.4 (caret 0.x locks minor)."""
    utils = report["dependency_graph"]["pkg-utils"]
    assert utils["axios"]["version"] == "0.21.4"


def test_16_caret_zero_axios_cli():
    """^0.27.0 must resolve to 0.27.2 (caret 0.x locks minor)."""
    cli = report["dependency_graph"]["pkg-cli"]
    assert cli["axios"]["version"] == "0.27.2"


def test_17_caret_normal_axios_auth():
    """^1.5.0 must resolve to 1.6.0 (caret locks major)."""
    auth = report["dependency_graph"]["pkg-auth"]
    assert auth["axios"]["version"] == "1.6.0"


def test_18_tilde_dotenv_api():
    """~16.3.0 must resolve to 16.3.1 (tilde locks minor)."""
    api = report["dependency_graph"]["pkg-api"]
    assert api["dotenv"]["version"] == "16.3.1"


def test_19_transitive_body_parser():
    """express 4.18.2 pulls body-parser at depth 2."""
    api = report["dependency_graph"]["pkg-api"]
    assert api["body-parser"] == {"depth": 2, "version": "1.20.2"}


def test_20_transitive_raw_body():
    """body-parser 1.20.2 pulls raw-body at depth 3."""
    api = report["dependency_graph"]["pkg-api"]
    assert api["raw-body"] == {"depth": 3, "version": "2.5.2"}


def test_21_transitive_negotiator():
    """accepts 1.3.8 pulls negotiator ^0.6.0 → 0.6.3 at depth 3."""
    api = report["dependency_graph"]["pkg-api"]
    assert api["negotiator"] == {"depth": 3, "version": "0.6.3"}


def test_22_caret_zero_negotiator():
    """^0.6.0 for negotiator must resolve to 0.6.3 (not higher minor)."""
    api = report["dependency_graph"]["pkg-api"]
    assert api["negotiator"]["version"] == "0.6.3"


def test_23_transitive_follow_redirects():
    """axios pulls follow-redirects at depth 2."""
    auth = report["dependency_graph"]["pkg-auth"]
    assert auth["follow-redirects"] == {"depth": 2, "version": "1.15.6"}


def test_24_transitive_jws():
    """jsonwebtoken 9.0.2 pulls jws ^4.0.0 → 4.0.0 at depth 2."""
    auth = report["dependency_graph"]["pkg-auth"]
    assert auth["jws"] == {"depth": 2, "version": "4.0.0"}


def test_25_transitive_ansi_styles():
    """chalk 4.1.2 pulls ansi-styles ^4.1.0 → 4.3.0 at depth 2."""
    cli = report["dependency_graph"]["pkg-cli"]
    assert cli["ansi-styles"] == {"depth": 2, "version": "4.3.0"}


def test_26_transitive_triple_beam():
    """winston 3.11.0 pulls triple-beam at depth 2."""
    api = report["dependency_graph"]["pkg-api"]
    assert api["triple-beam"] == {"depth": 2, "version": "1.4.1"}


def test_27_transitive_logform():
    """winston 3.11.0 pulls logform ^2.5.0 → 2.6.0 at depth 2."""
    api = report["dependency_graph"]["pkg-api"]
    assert api["logform"] == {"depth": 2, "version": "2.6.0"}


def test_28_dep_graph_pkg_api_count():
    """pkg-api should have exactly 13 deps (direct + transitive)."""
    assert len(report["dependency_graph"]["pkg-api"]) == 13


def test_29_dep_graph_pkg_auth_count():
    """pkg-auth should have exactly 5 deps."""
    assert len(report["dependency_graph"]["pkg-auth"]) == 5


def test_30_dep_graph_pkg_cli_count():
    """pkg-cli should have exactly 5 deps."""
    assert len(report["dependency_graph"]["pkg-cli"]) == 5


def test_31_dep_graph_pkg_utils_count():
    """pkg-utils should have exactly 4 deps."""
    assert len(report["dependency_graph"]["pkg-utils"]) == 4


def test_32_workspace_deps_excluded():
    """Workspace deps (workspace:*) must NOT appear in dependency_graph."""
    for pkg, graph in report["dependency_graph"].items():
        for dep in graph:
            assert not dep.startswith("@myorg/"), \
                f"Workspace dep {dep} in {pkg} graph"


# ─── FINDINGS TESTS ──────────────────────────────────────────────────────────


def test_33_findings_count():
    """Must have exactly 9 findings."""
    assert len(report["findings"]) == 9


def test_34_finding_ids_sequential():
    """Finding IDs must be F-001 through F-009."""
    ids = [f["finding_id"] for f in report["findings"]]
    expected = [f"F-{i:03d}" for i in range(1, 10)]
    assert ids == expected


def test_35_finding_keys_sorted():
    """Each finding object must have keys sorted alphabetically."""
    for f in report["findings"]:
        assert list(f.keys()) == sorted(f.keys())


def test_36_workspace_cycle_detected():
    """F-001 must be a workspace cycle between pkg-auth and pkg-utils."""
    f = report["findings"][0]
    assert f["category"] == "workspace_cycle"
    assert f["severity"] == "critical"
    assert "pkg-auth" in f["detail"]
    assert "pkg-utils" in f["detail"]


def test_37_workspace_cycle_risk_score():
    """Workspace cycle risk = 10.0 * 1.5^0 = 10.0."""
    f = report["findings"][0]
    assert f["risk_score"] == 10.0


def test_38_phantom_helmet():
    """F-002: helmet phantom dependency in pkg-api."""
    f = report["findings"][1]
    assert f["category"] == "phantom_dependency"
    assert f["dependency"] == "helmet"
    assert f["package"] == "pkg-api"
    assert "middleware.js" in f["detail"]


def test_39_phantom_ora():
    """F-003: ora phantom dependency in pkg-cli."""
    f = report["findings"][2]
    assert f["category"] == "phantom_dependency"
    assert f["dependency"] == "ora"
    assert f["package"] == "pkg-cli"


def test_40_phantom_chalk():
    """F-004: chalk phantom dependency in pkg-utils."""
    f = report["findings"][3]
    assert f["category"] == "phantom_dependency"
    assert f["dependency"] == "chalk"
    assert f["package"] == "pkg-utils"


def test_41_phantom_risk_scores():
    """Phantom deps at depth 1: 7.5 * 1.5^1 = 11.25."""
    for i in [1, 2, 3]:
        assert report["findings"][i]["risk_score"] == 11.25


def test_42_license_negotiator():
    """F-005: negotiator ISC incompatible with pkg-api Apache-2.0."""
    f = report["findings"][4]
    assert f["category"] == "license_incompatibility"
    assert f["dependency"] == "negotiator"
    assert f["package"] == "pkg-api"
    assert "ISC" in f["detail"]
    assert "Apache-2.0" in f["detail"]


def test_43_license_negotiator_risk():
    """negotiator at depth 3: 7.5 * 1.5^3 = 25.3125."""
    f = report["findings"][4]
    assert f["risk_score"] == 25.3125


def test_44_license_triple_beam():
    """F-006: triple-beam ISC incompatible with pkg-api Apache-2.0."""
    f = report["findings"][5]
    assert f["category"] == "license_incompatibility"
    assert f["dependency"] == "triple-beam"
    assert f["package"] == "pkg-api"


def test_45_license_triple_beam_risk():
    """triple-beam at depth 2: 7.5 * 1.5^2 = 16.875."""
    f = report["findings"][5]
    assert f["risk_score"] == 16.875


def test_46_vuln_axios_cli():
    """F-007: GHSA-2024-001 advisory matches axios 0.27.2 in pkg-cli."""
    f = report["findings"][6]
    assert f["category"] == "vulnerability"
    assert f["dependency"] == "axios"
    assert f["package"] == "pkg-cli"
    assert "GHSA-2024-001" in f["detail"]
    assert "0.27.2" in f["detail"]


def test_47_vuln_axios_utils():
    """F-008: GHSA-2024-001 advisory matches axios 0.21.4 in pkg-utils."""
    f = report["findings"][7]
    assert f["category"] == "vulnerability"
    assert f["dependency"] == "axios"
    assert f["package"] == "pkg-utils"
    assert "0.21.4" in f["detail"]


def test_48_vuln_not_auth():
    """axios 1.6.0 in pkg-auth must NOT match <1.0.0 advisory."""
    for f in report["findings"]:
        if f["category"] == "vulnerability" and f["package"] == "pkg-auth":
            assert False, "pkg-auth axios 1.6.0 should not match <1.0.0"


def test_49_hoisting_conflict():
    """F-009: axios hoisting conflict across 3 packages."""
    f = report["findings"][8]
    assert f["category"] == "hoisting_conflict"
    assert f["dependency"] == "axios"
    assert "pkg-auth needs 1.6.0" in f["detail"]
    assert "pkg-cli needs 0.27.2" in f["detail"]
    assert "pkg-utils needs 0.21.4" in f["detail"]


def test_50_hoisting_conflict_risk():
    """Hoisting conflict: medium (5.0) * 1.5^1 = 7.5."""
    f = report["findings"][8]
    assert f["risk_score"] == 7.5


# ─── HOISTING TESTS ──────────────────────────────────────────────────────────


def test_51_hoisting_conflicts_list():
    """Only axios should be in conflicts list."""
    assert report["hoisting"]["conflicts"] == ["axios"]


def test_52_hoisting_hoistable_count():
    """23 dependencies can be hoisted."""
    assert len(report["hoisting"]["hoistable"]) == 23


def test_53_hoisting_hoistable_sorted():
    """hoistable array must be sorted alphabetically."""
    h = report["hoisting"]["hoistable"]
    assert h == sorted(h)


def test_54_hoisting_conflicts_sorted():
    """conflicts array must be sorted alphabetically."""
    c = report["hoisting"]["conflicts"]
    assert c == sorted(c)


def test_55_hoistable_contains_follow_redirects():
    """follow-redirects resolves to same version everywhere → hoistable."""
    assert "follow-redirects" in report["hoisting"]["hoistable"]


def test_56_hoistable_contains_dotenv():
    """dotenv resolves to 16.3.1 in both pkg-api and pkg-utils → hoistable."""
    assert "dotenv" in report["hoisting"]["hoistable"]


# ─── SUMMARY TESTS ───────────────────────────────────────────────────────────


def test_57_total_dependencies():
    """24 unique external packages across all workspace packages."""
    assert report["summary"]["total_dependencies"] == 24


def test_58_total_findings():
    """9 total findings."""
    assert report["summary"]["total_findings"] == 9


def test_59_conflict_count():
    """1 hoisting conflict (axios)."""
    assert report["summary"]["conflict_count"] == 1


def test_60_hoistable_count():
    """23 hoistable packages."""
    assert report["summary"]["hoistable_count"] == 23


def test_61_avg_depth():
    """avg_depth must be harmonic mean of all dep depths = 1.295."""
    assert abs(report["summary"]["avg_depth"] - 1.295) < 1e-3


def test_62_aggregate_risk_score():
    """aggregate_risk_score must be geometric mean = 12.1507."""
    assert abs(report["summary"]["aggregate_risk_score"] - 12.1507) < 1e-3


# ─── CROSS-VALIDATION TESTS ──────────────────────────────────────────────────


def test_63_no_devdeps_in_graph():
    """devDependencies must NOT be resolved (scope_filter = dependencies)."""
    core = report["dependency_graph"]["pkg-core"]
    assert "chalk" not in core, "chalk is devDep of pkg-core"


def test_64_no_semver_in_api():
    """semver is devDep of pkg-api, must not appear in graph."""
    api = report["dependency_graph"]["pkg-api"]
    assert "semver" not in api


def test_65_express_not_5():
    """^4.18.0 must NOT resolve to 5.0.0 (caret locks major)."""
    api = report["dependency_graph"]["pkg-api"]
    assert api["express"]["version"] == "4.18.2"


def test_66_bcrypt_version():
    """^5.0.0 resolves to 5.1.1 (highest in 5.x)."""
    auth = report["dependency_graph"]["pkg-auth"]
    assert auth["bcrypt"]["version"] == "5.1.1"


def test_67_chalk_not_5_in_cli():
    """^4.1.0 in pkg-cli must resolve to 4.1.2 not 5.3.0."""
    cli = report["dependency_graph"]["pkg-cli"]
    assert cli["chalk"]["version"] == "4.1.2"


def test_68_lodash_same_version():
    """lodash resolves to same version in both pkg-core and pkg-utils."""
    core_v = report["dependency_graph"]["pkg-core"]["lodash"]["version"]
    utils_v = report["dependency_graph"]["pkg-utils"]["lodash"]["version"]
    assert core_v == utils_v == "4.17.21"


def test_69_finding_categories_valid():
    """All findings must have valid categories."""
    valid = {"workspace_cycle", "version_conflict", "phantom_dependency",
             "license_incompatibility", "vulnerability", "hoisting_conflict"}
    for f in report["findings"]:
        assert f["category"] in valid, f"Invalid category: {f['category']}"


def test_70_all_risk_scores_positive():
    """All risk scores must be positive numbers."""
    for f in report["findings"]:
        assert f["risk_score"] > 0


def test_71_dep_graph_keys_sorted():
    """Dependency names within each package graph must be sorted."""
    for pkg, graph in report["dependency_graph"].items():
        keys = list(graph.keys())
        assert keys == sorted(keys), f"Keys not sorted in {pkg}"


def test_72_no_prerelease_versions():
    """No resolved version should contain a hyphen (pre-release)."""
    for pkg, graph in report["dependency_graph"].items():
        for dep, info in graph.items():
            assert "-" not in info["version"], \
                f"Pre-release {dep}@{info['version']} in {pkg}"


def test_73_depths_all_positive():
    """All depths must be >= 1."""
    for pkg, graph in report["dependency_graph"].items():
        for dep, info in graph.items():
            assert info["depth"] >= 1, f"{dep} in {pkg} has depth {info['depth']}"


def test_74_pg_protocol_transitive():
    """pg 8.11.3 pulls pg-protocol ^1.6.0 → 1.6.0 at depth 2."""
    api = report["dependency_graph"]["pkg-api"]
    assert api["pg-protocol"] == {"depth": 2, "version": "1.6.0"}


def test_75_cookie_parser_version():
    """cookie-parser ^1.4.0 resolves to 1.4.6."""
    api = report["dependency_graph"]["pkg-api"]
    assert api["cookie-parser"]["version"] == "1.4.6"


def test_76_accepts_version():
    """accepts ^1.3.0 resolves to 1.3.8."""
    api = report["dependency_graph"]["pkg-api"]
    assert api["accepts"]["version"] == "1.3.8"


def test_77_finding_order_categories():
    """Findings must follow prescribed order: cycle, phantom, license, vuln, hoisting."""
    categories = [f["category"] for f in report["findings"]]
    cat_order = {"workspace_cycle": 0, "version_conflict": 1,
                 "phantom_dependency": 2, "license_incompatibility": 3,
                 "vulnerability": 4, "hoisting_conflict": 5}
    indices = [cat_order[c] for c in categories]
    assert indices == sorted(indices), "Findings not in correct category order"


def test_78_summary_keys():
    """Summary must have exactly these keys."""
    expected = {"aggregate_risk_score", "avg_depth", "conflict_count",
                "hoistable_count", "total_dependencies", "total_findings"}
    assert set(report["summary"].keys()) == expected


def test_79_metadata_keys():
    """Metadata must have exactly these keys."""
    expected = {"evaluation_date", "scope", "source_hash", "workspace_packages"}
    assert set(report["metadata"].keys()) == expected


def test_80_hoisting_keys():
    """Hoisting must have exactly conflicts and hoistable."""
    assert set(report["hoisting"].keys()) == {"conflicts", "hoistable"}
