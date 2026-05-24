"""Tests for go-depgraph-audit-hard — dependency graph auditor."""
import json
import os
import pytest

POSSIBLE_PATHS = [
    "/app/output/dependency_audit.json",
    os.path.join(os.path.dirname(__file__), "..", "environment", "output", "dependency_audit.json"),
]

def _find_output():
    for p in POSSIBLE_PATHS:
        if os.path.isfile(p):
            return p
    return POSSIBLE_PATHS[0]

@pytest.fixture(scope="session")
def audit():
    path = _find_output()
    with open(path) as f:
        return json.load(f)

@pytest.fixture(scope="session")
def qr_map(audit):
    return {q["query_id"]: q for q in audit["query_results"]}


# ────────────────────────────────────────────────────────────────────
# Structural Tests
# ────────────────────────────────────────────────────────────────────

class TestStructure:
    def test_output_file_exists(self):
        assert os.path.isfile(_find_output()), "dependency_audit.json not found"

    def test_valid_json(self):
        with open(_find_output()) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_schema_version(self, audit):
        assert audit["schema_version"] == 1

    def test_top_level_keys(self, audit):
        expected = {"findings", "query_results", "schema_version", "source_sha256", "summary"}
        assert set(audit.keys()) == expected

    def test_top_level_keys_sorted(self, audit):
        keys = list(audit.keys())
        assert keys == sorted(keys), "Top-level keys must be sorted"

    def test_query_results_count(self, audit):
        assert len(audit["query_results"]) == 9

    def test_query_results_sorted(self, audit):
        ids = [q["query_id"] for q in audit["query_results"]]
        assert ids == sorted(ids)

    def test_query_result_keys(self, audit):
        expected = {
            "build_order", "cycles", "dependency_tree", "license_issues",
            "max_depth", "query_id", "resolution_errors", "resolved_modules",
            "retracted_warnings", "total_resolved", "vulnerabilities",
        }
        for qr in audit["query_results"]:
            assert set(qr.keys()) == expected

    def test_source_sha256_has_entries(self, audit):
        assert len(audit["source_sha256"]) > 0

    def test_source_sha256_keys_sorted(self, audit):
        keys = list(audit["source_sha256"].keys())
        assert keys == sorted(keys)

    def test_trailing_newline(self):
        with open(_find_output(), "rb") as f:
            content = f.read()
        assert content.endswith(b"\n"), "Output must end with newline"


# ────────────────────────────────────────────────────────────────────
# Summary Tests
# ────────────────────────────────────────────────────────────────────

class TestSummary:
    def test_total_queries(self, audit):
        assert audit["summary"]["total_queries"] == 9

    def test_total_modules_resolved(self, audit):
        assert audit["summary"]["total_modules_resolved"] == 39

    def test_total_vulnerabilities_found(self, audit):
        assert audit["summary"]["total_vulnerabilities_found"] == 7

    def test_total_license_issues(self, audit):
        assert audit["summary"]["total_license_issues"] == 2

    def test_total_cycles(self, audit):
        assert audit["summary"]["total_cycles"] == 1

    def test_findings_by_severity_all_levels(self, audit):
        fbs = audit["summary"]["findings_by_severity"]
        for level in ["critical", "high", "medium", "low", "info"]:
            assert level in fbs, f"Missing severity level: {level}"

    def test_findings_by_severity_critical(self, audit):
        assert audit["summary"]["findings_by_severity"]["critical"] == 4

    def test_findings_by_severity_high(self, audit):
        assert audit["summary"]["findings_by_severity"]["high"] == 4

    def test_findings_by_severity_medium(self, audit):
        assert audit["summary"]["findings_by_severity"]["medium"] == 4

    def test_findings_by_severity_low(self, audit):
        assert audit["summary"]["findings_by_severity"]["low"] == 0

    def test_findings_by_severity_info(self, audit):
        assert audit["summary"]["findings_by_severity"]["info"] == 1


# ────────────────────────────────────────────────────────────────────
# Source SHA-256 Tests
# ────────────────────────────────────────────────────────────────────

class TestSHA256:
    def test_config_audit_hash(self, audit):
        assert "config/audit.json" in audit["source_sha256"]

    def test_vulnerabilities_hash(self, audit):
        assert "data/vulnerabilities.json" in audit["source_sha256"]

    def test_all_registry_modules(self, audit):
        for i in range(1, 16):
            key = f"data/registry/module_{i:02d}.json"
            assert key in audit["source_sha256"], f"Missing hash for {key}"

    def test_all_query_files(self, audit):
        for i in range(1, 10):
            key = f"data/queries/query_{i:02d}.json"
            assert key in audit["source_sha256"], f"Missing hash for {key}"

    def test_docs_files(self, audit):
        for doc in ["docs/algorithms.md", "docs/edge_cases.md", "docs/output_schema.md"]:
            assert doc in audit["source_sha256"], f"Missing hash for {doc}"

    def test_hash_format(self, audit):
        for key, val in audit["source_sha256"].items():
            assert len(val) == 64, f"Hash for {key} is not 64 hex chars"
            assert all(c in "0123456789abcdef" for c in val)


# ────────────────────────────────────────────────────────────────────
# Query 01 — Basic MVS Resolution (minimum, not latest)
# ────────────────────────────────────────────────────────────────────

class TestQuery01:
    def test_resolved_count(self, qr_map):
        assert qr_map["query_01"]["total_resolved"] == 4

    def test_config_version_is_minimum(self, qr_map):
        """MVS must select 1.2.0 (minimum >= 1.2.0), NOT 1.3.0 (latest)."""
        assert qr_map["query_01"]["resolved_modules"]["example.com/core/config"] == "1.2.0"

    def test_http_version_is_minimum(self, qr_map):
        """MVS must select 1.1.0 (minimum >= 1.1.0), NOT 2.1.0 (latest)."""
        assert qr_map["query_01"]["resolved_modules"]["example.com/net/http"] == "1.1.0"

    def test_logger_version(self, qr_map):
        """Transitive: max(1.1.0, 1.1.0) = 1.1.0, NOT 2.0.0."""
        assert qr_map["query_01"]["resolved_modules"]["example.com/core/logger"] == "1.1.0"

    def test_errors_version(self, qr_map):
        assert qr_map["query_01"]["resolved_modules"]["example.com/core/errors"] == "1.1.0"

    def test_build_order(self, qr_map):
        assert qr_map["query_01"]["build_order"] == [
            "example.com/core/errors",
            "example.com/core/logger",
            "example.com/core/config",
            "example.com/net/http",
        ]

    def test_max_depth(self, qr_map):
        assert qr_map["query_01"]["max_depth"] == 3

    def test_no_cycles(self, qr_map):
        assert qr_map["query_01"]["cycles"] == []

    def test_no_license_issues(self, qr_map):
        assert qr_map["query_01"]["license_issues"] == []

    def test_vuln_count(self, qr_map):
        assert len(qr_map["query_01"]["vulnerabilities"]) == 1

    def test_http_vuln(self, qr_map):
        vulns = qr_map["query_01"]["vulnerabilities"]
        assert vulns[0]["id"] == "VULN-2024-001"
        assert vulns[0]["module"] == "example.com/net/http"

    def test_dep_tree_http(self, qr_map):
        tree = qr_map["query_01"]["dependency_tree"]
        assert "example.com/net/http@1.1.0" in tree
        deps = tree["example.com/net/http@1.1.0"]
        assert "example.com/core/config@1.2.0" in deps
        assert "example.com/core/logger@1.1.0" in deps

    def test_dep_tree_errors_empty(self, qr_map):
        tree = qr_map["query_01"]["dependency_tree"]
        assert tree["example.com/core/errors@1.1.0"] == []


# ────────────────────────────────────────────────────────────────────
# Query 02 — Diamond Dependency with MVS
# ────────────────────────────────────────────────────────────────────

class TestQuery02:
    def test_resolved_count(self, qr_map):
        assert qr_map["query_02"]["total_resolved"] == 7

    def test_api_rest_version(self, qr_map):
        assert qr_map["query_02"]["resolved_modules"]["example.com/api/rest"] == "1.1.0"

    def test_config_version_diamond(self, qr_map):
        """Diamond: net/http needs config >= 1.0.0, auth/jwt needs config >= 1.1.0.
        MVS picks max(1.0.0, 1.1.0) = 1.1.0, NOT 1.3.0."""
        assert qr_map["query_02"]["resolved_modules"]["example.com/core/config"] == "1.1.0"

    def test_errors_version_diamond(self, qr_map):
        """Multiple sources: auth/jwt needs >= 1.0.0, data/json needs >= 1.1.0.
        MVS picks max = 1.1.0."""
        assert qr_map["query_02"]["resolved_modules"]["example.com/core/errors"] == "1.1.0"

    def test_build_order_length(self, qr_map):
        assert len(qr_map["query_02"]["build_order"]) == 7

    def test_build_order_first_is_errors(self, qr_map):
        assert qr_map["query_02"]["build_order"][0] == "example.com/core/errors"

    def test_build_order_last_is_api_rest(self, qr_map):
        assert qr_map["query_02"]["build_order"][-1] == "example.com/api/rest"

    def test_build_order_jwt_before_rest(self, qr_map):
        bo = qr_map["query_02"]["build_order"]
        assert bo.index("example.com/auth/jwt") < bo.index("example.com/api/rest")

    def test_max_depth(self, qr_map):
        assert qr_map["query_02"]["max_depth"] == 4

    def test_vuln_jwt_critical(self, qr_map):
        vulns = qr_map["query_02"]["vulnerabilities"]
        jwt_vulns = [v for v in vulns if v["module"] == "example.com/auth/jwt"]
        assert len(jwt_vulns) == 1
        assert jwt_vulns[0]["id"] == "VULN-2024-002"
        assert jwt_vulns[0]["severity"] == "critical"


# ────────────────────────────────────────────────────────────────────
# Query 03 — Exclude Directive (bumps to next higher)
# ────────────────────────────────────────────────────────────────────

class TestQuery03:
    def test_resolved_count(self, qr_map):
        assert qr_map["query_03"]["total_resolved"] == 3

    def test_json_excluded_bumps(self, qr_map):
        """data/json 1.1.0 is excluded. MVS should pick 1.2.0, not 1.1.0."""
        assert qr_map["query_03"]["resolved_modules"]["example.com/data/json"] == "1.2.0"

    def test_errors_upgraded_by_exclude(self, qr_map):
        """data/json@1.2.0 requires core/errors >= 1.2.0, so errors bumps to 1.2.0."""
        assert qr_map["query_03"]["resolved_modules"]["example.com/core/errors"] == "1.2.0"

    def test_csv_version(self, qr_map):
        assert qr_map["query_03"]["resolved_modules"]["example.com/data/csv"] == "1.1.0"

    def test_no_vulnerabilities(self, qr_map):
        assert qr_map["query_03"]["vulnerabilities"] == []

    def test_max_depth(self, qr_map):
        assert qr_map["query_03"]["max_depth"] == 2

    def test_build_order(self, qr_map):
        assert qr_map["query_03"]["build_order"] == [
            "example.com/core/errors",
            "example.com/data/json",
            "example.com/data/csv",
        ]


# ────────────────────────────────────────────────────────────────────
# Query 04 — Pre-release Handling + Retracted Version
# ────────────────────────────────────────────────────────────────────

class TestQuery04:
    def test_resolved_count(self, qr_map):
        assert qr_map["query_04"]["total_resolved"] == 4

    def test_json_prerelease_selected(self, qr_map):
        """data/json >= 1.1.0-beta.2 → MVS picks exactly 1.1.0-beta.2."""
        assert qr_map["query_04"]["resolved_modules"]["example.com/data/json"] == "1.1.0-beta.2"

    def test_logger_retracted_still_resolved(self, qr_map):
        """cache/lru >= 1.0.0 requires logger >= 1.0.0. MVS picks 1.0.0 (minimum).
        logger 1.0.0 is retracted but still selectable."""
        assert qr_map["query_04"]["resolved_modules"]["example.com/core/logger"] == "1.0.0"

    def test_retracted_warning(self, qr_map):
        rw = qr_map["query_04"]["retracted_warnings"]
        assert len(rw) == 1
        assert rw[0]["module"] == "example.com/core/logger"
        assert rw[0]["version"] == "1.0.0"

    def test_vuln_prerelease_affected(self, qr_map):
        """VULN-2024-003 affects data/json >= 1.0.0 and < 1.1.0.
        1.1.0-beta.2 < 1.1.0 (pre-release), so it IS affected."""
        vulns = qr_map["query_04"]["vulnerabilities"]
        assert len(vulns) == 1
        assert vulns[0]["id"] == "VULN-2024-003"
        assert vulns[0]["version"] == "1.1.0-beta.2"

    def test_max_depth(self, qr_map):
        assert qr_map["query_04"]["max_depth"] == 1

    def test_logger_has_no_deps(self, qr_map):
        """core/logger@1.0.0 has no dependencies."""
        tree = qr_map["query_04"]["dependency_tree"]
        assert tree["example.com/core/logger@1.0.0"] == []


# ────────────────────────────────────────────────────────────────────
# Query 05 — Replace Directive (missing replacement module)
# ────────────────────────────────────────────────────────────────────

class TestQuery05:
    def test_resolved_count(self, qr_map):
        assert qr_map["query_05"]["total_resolved"] == 2

    def test_resolution_error(self, qr_map):
        errors = qr_map["query_05"]["resolution_errors"]
        assert len(errors) == 1
        assert "fork/logger" in errors[0]

    def test_config_still_resolved(self, qr_map):
        """core/config resolves despite logger replacement failure."""
        assert "example.com/core/config" in qr_map["query_05"]["resolved_modules"]

    def test_logger_not_in_resolved(self, qr_map):
        """core/logger is replaced, so it should NOT be in resolved_modules."""
        assert "example.com/core/logger" not in qr_map["query_05"]["resolved_modules"]

    def test_fork_logger_not_in_resolved(self, qr_map):
        """fork/logger doesn't exist, so it's also not in resolved_modules."""
        assert "example.com/fork/logger" not in qr_map["query_05"]["resolved_modules"]

    def test_max_depth(self, qr_map):
        assert qr_map["query_05"]["max_depth"] == 1


# ────────────────────────────────────────────────────────────────────
# Query 06 — License Incompatibility (asymmetric matrix)
# ────────────────────────────────────────────────────────────────────

class TestQuery06:
    def test_resolved_count(self, qr_map):
        assert qr_map["query_06"]["total_resolved"] == 4

    def test_license_issues_count(self, qr_map):
        assert len(qr_map["query_06"]["license_issues"]) == 2

    def test_apache_incompatible_with_mit_project(self, qr_map):
        """MIT project cannot use Apache-2.0 dependency (asymmetric!)."""
        issues = qr_map["query_06"]["license_issues"]
        apache_issue = [i for i in issues if i["dependency_license"] == "Apache-2.0"]
        assert len(apache_issue) == 1
        assert apache_issue[0]["module"] == "example.com/core/config"
        assert apache_issue[0]["project_license"] == "MIT"

    def test_gpl_incompatible_with_mit_project(self, qr_map):
        """MIT project cannot use GPL-3.0 dependency."""
        issues = qr_map["query_06"]["license_issues"]
        gpl_issue = [i for i in issues if i["dependency_license"] == "GPL-3.0"]
        assert len(gpl_issue) == 1
        assert gpl_issue[0]["module"] == "example.com/db/sql"

    def test_sql_vulnerability(self, qr_map):
        vulns = qr_map["query_06"]["vulnerabilities"]
        assert len(vulns) == 1
        assert vulns[0]["id"] == "VULN-2024-005"
        assert vulns[0]["severity"] == "critical"

    def test_db_sql_version(self, qr_map):
        assert qr_map["query_06"]["resolved_modules"]["example.com/db/sql"] == "1.1.0"

    def test_max_depth(self, qr_map):
        assert qr_map["query_06"]["max_depth"] == 3

    def test_build_order(self, qr_map):
        assert qr_map["query_06"]["build_order"] == [
            "example.com/core/errors",
            "example.com/core/logger",
            "example.com/core/config",
            "example.com/db/sql",
        ]


# ────────────────────────────────────────────────────────────────────
# Query 07 — Large Graph + Deep Chain + Vulnerability Boundary
# ────────────────────────────────────────────────────────────────────

class TestQuery07:
    def test_resolved_count(self, qr_map):
        assert qr_map["query_07"]["total_resolved"] == 8

    def test_api_rest_version(self, qr_map):
        assert qr_map["query_07"]["resolved_modules"]["example.com/api/rest"] == "2.0.0"

    def test_auth_jwt_transitive(self, qr_map):
        """api/rest@2.0.0 requires auth/jwt >= 2.0.0; MVS picks 2.0.0."""
        assert qr_map["query_07"]["resolved_modules"]["example.com/auth/jwt"] == "2.0.0"

    def test_auth_oauth_transitive(self, qr_map):
        assert qr_map["query_07"]["resolved_modules"]["example.com/auth/oauth"] == "1.1.0"

    def test_config_transitive_upgrade(self, qr_map):
        """auth/jwt@2.0.0 requires config >= 1.3.0; this is higher than
        net/http@2.0.0's requirement of config >= 1.2.0. MVS picks max = 1.3.0."""
        assert qr_map["query_07"]["resolved_modules"]["example.com/core/config"] == "1.3.0"

    def test_net_http_version(self, qr_map):
        assert qr_map["query_07"]["resolved_modules"]["example.com/net/http"] == "2.0.0"

    def test_max_depth_triggers_deep_chain(self, qr_map):
        """max_depth must be >= 5 (the deep_chain_threshold)."""
        assert qr_map["query_07"]["max_depth"] == 6

    def test_vuln_boundary_exclusive_max(self, qr_map):
        """VULN-2024-006 affects net/http >= 2.0.0 and < 2.1.0.
        net/http@2.0.0 is affected (2.0.0 >= 2.0.0 AND 2.0.0 < 2.1.0)."""
        vulns = qr_map["query_07"]["vulnerabilities"]
        assert len(vulns) == 1
        assert vulns[0]["id"] == "VULN-2024-006"
        assert vulns[0]["version"] == "2.0.0"

    def test_gpl3_project_allows_apache(self, qr_map):
        """GPL-3.0 project CAN use Apache-2.0 dependencies — no license issues."""
        assert qr_map["query_07"]["license_issues"] == []

    def test_build_order_length(self, qr_map):
        assert len(qr_map["query_07"]["build_order"]) == 8

    def test_build_order_first(self, qr_map):
        assert qr_map["query_07"]["build_order"][0] == "example.com/core/errors"

    def test_build_order_last(self, qr_map):
        assert qr_map["query_07"]["build_order"][-1] == "example.com/api/rest"

    def test_dep_tree_api_rest(self, qr_map):
        tree = qr_map["query_07"]["dependency_tree"]
        deps = tree["example.com/api/rest@2.0.0"]
        assert len(deps) == 4
        assert "example.com/auth/jwt@2.0.0" in deps
        assert "example.com/auth/oauth@1.1.0" in deps
        assert "example.com/data/json@1.2.0" in deps
        assert "example.com/net/http@2.0.0" in deps


# ────────────────────────────────────────────────────────────────────
# Query 08 — Exclude + Pre-release Numeric Ordering
# ────────────────────────────────────────────────────────────────────

class TestQuery08:
    def test_resolved_count(self, qr_map):
        assert qr_map["query_08"]["total_resolved"] == 2

    def test_prerelease_numeric_ordering(self, qr_map):
        """Require >= 1.1.0-beta.2, exclude beta.2.
        With NUMERIC ordering: beta.11 > beta.2, so next is beta.11.
        With LEXICOGRAPHIC ordering: '11' < '2', so next would be rc.1.
        Correct answer is 1.1.0-beta.11."""
        assert qr_map["query_08"]["resolved_modules"]["example.com/data/json"] == "1.1.0-beta.11"

    def test_errors_version(self, qr_map):
        """beta.11 requires core/errors >= 1.1.0."""
        assert qr_map["query_08"]["resolved_modules"]["example.com/core/errors"] == "1.1.0"

    def test_vuln_prerelease_boundary(self, qr_map):
        """VULN-2024-003: affected_max is 1.1.0 (exclusive).
        1.1.0-beta.11 < 1.1.0, so it IS affected."""
        vulns = qr_map["query_08"]["vulnerabilities"]
        assert len(vulns) == 1
        assert vulns[0]["version"] == "1.1.0-beta.11"

    def test_build_order(self, qr_map):
        assert qr_map["query_08"]["build_order"] == [
            "example.com/core/errors",
            "example.com/data/json",
        ]

    def test_max_depth(self, qr_map):
        assert qr_map["query_08"]["max_depth"] == 1


# ────────────────────────────────────────────────────────────────────
# Query 09 — Cycle Detection
# ────────────────────────────────────────────────────────────────────

class TestQuery09:
    def test_resolved_count(self, qr_map):
        assert qr_map["query_09"]["total_resolved"] == 5

    def test_cycle_detected(self, qr_map):
        assert len(qr_map["query_09"]["cycles"]) == 1

    def test_cycle_members(self, qr_map):
        cycle = qr_map["query_09"]["cycles"][0]
        assert set(cycle) == {
            "example.com/mesh/client",
            "example.com/mesh/proxy",
            "example.com/mesh/server",
        }

    def test_cycle_sorted_lexicographically(self, qr_map):
        cycle = qr_map["query_09"]["cycles"][0]
        assert cycle == sorted(cycle), "Cycle members must be sorted"

    def test_build_order_excludes_cyclic(self, qr_map):
        """Cyclic modules must be excluded from build_order."""
        bo = qr_map["query_09"]["build_order"]
        for mod in ["example.com/mesh/client", "example.com/mesh/proxy", "example.com/mesh/server"]:
            assert mod not in bo

    def test_build_order_includes_noncyclic(self, qr_map):
        bo = qr_map["query_09"]["build_order"]
        assert "example.com/core/errors" in bo
        assert "example.com/core/logger" in bo

    def test_cyclic_modules_in_resolved(self, qr_map):
        """Cyclic modules still appear in resolved_modules."""
        rm = qr_map["query_09"]["resolved_modules"]
        assert "example.com/mesh/client" in rm
        assert "example.com/mesh/proxy" in rm
        assert "example.com/mesh/server" in rm

    def test_cyclic_modules_in_dep_tree(self, qr_map):
        """Cyclic modules still appear in dependency_tree."""
        tree = qr_map["query_09"]["dependency_tree"]
        assert "example.com/mesh/client@1.0.0" in tree
        assert "example.com/mesh/proxy@1.0.0" in tree
        assert "example.com/mesh/server@1.0.0" in tree

    def test_max_depth(self, qr_map):
        assert qr_map["query_09"]["max_depth"] == 4

    def test_logger_version_transitive(self, qr_map):
        """mesh/server requires logger >= 1.1.0 (highest among mesh modules)."""
        assert qr_map["query_09"]["resolved_modules"]["example.com/core/logger"] == "1.1.0"


# ────────────────────────────────────────────────────────────────────
# Findings Tests
# ────────────────────────────────────────────────────────────────────

class TestFindings:
    def test_findings_count(self, audit):
        assert len(audit["findings"]) == 13

    def test_findings_sorted_by_severity(self, audit):
        ranks = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
        severities = [ranks[f["severity"]] for f in audit["findings"]]
        assert severities == sorted(severities), "Findings must be sorted by severity"

    def test_cycle_finding_exists(self, audit):
        cycle_findings = [f for f in audit["findings"] if f["type"] == "cycle_detected"]
        assert len(cycle_findings) == 1
        assert cycle_findings[0]["query_id"] == "query_09"
        assert cycle_findings[0]["severity"] == "critical"

    def test_resolution_error_finding(self, audit):
        err_findings = [f for f in audit["findings"] if f["type"] == "resolution_error"]
        assert len(err_findings) == 1
        assert err_findings[0]["query_id"] == "query_05"

    def test_license_findings(self, audit):
        lic_findings = [f for f in audit["findings"] if f["type"] == "license_incompatible"]
        assert len(lic_findings) == 2
        assert all(f["query_id"] == "query_06" for f in lic_findings)

    def test_deep_chain_finding(self, audit):
        deep = [f for f in audit["findings"] if f["type"] == "deep_dependency_chain"]
        assert len(deep) == 1
        assert deep[0]["query_id"] == "query_07"
        assert deep[0]["severity"] == "info"

    def test_retracted_finding(self, audit):
        ret = [f for f in audit["findings"] if f["type"] == "retracted_version"]
        assert len(ret) == 1
        assert ret[0]["query_id"] == "query_04"
        assert ret[0]["severity"] == "medium"

    def test_finding_has_required_fields(self, audit):
        for f in audit["findings"]:
            assert "description" in f
            assert "query_id" in f
            assert "severity" in f
            assert "type" in f


# ────────────────────────────────────────────────────────────────────
# MVS Anti-Pattern Tests (explicitly check WRONG answers fail)
# ────────────────────────────────────────────────────────────────────

class TestMVSAntiPatterns:
    def test_q01_config_not_latest(self, qr_map):
        """If a model picks latest (1.3.0) instead of minimum (1.2.0), fail."""
        assert qr_map["query_01"]["resolved_modules"]["example.com/core/config"] != "1.3.0"

    def test_q01_http_not_latest(self, qr_map):
        """If a model picks latest (2.1.0) instead of minimum (1.1.0), fail."""
        assert qr_map["query_01"]["resolved_modules"]["example.com/net/http"] != "2.1.0"
        assert qr_map["query_01"]["resolved_modules"]["example.com/net/http"] != "2.0.0"

    def test_q01_logger_not_latest(self, qr_map):
        """If a model picks 2.0.0 (latest) or 1.2.0 (higher), fail."""
        assert qr_map["query_01"]["resolved_modules"]["example.com/core/logger"] != "2.0.0"
        assert qr_map["query_01"]["resolved_modules"]["example.com/core/logger"] != "1.2.0"

    def test_q02_config_not_latest(self, qr_map):
        """Diamond resolution: config should be 1.1.0, not 1.3.0."""
        assert qr_map["query_02"]["resolved_modules"]["example.com/core/config"] != "1.3.0"

    def test_q08_json_not_rc1(self, qr_map):
        """If model uses lexicographic pre-release ordering,
        it would pick rc.1 instead of beta.11."""
        assert qr_map["query_08"]["resolved_modules"]["example.com/data/json"] != "1.1.0-rc.1"

    def test_q08_json_not_stable(self, qr_map):
        """Must be a pre-release, not the stable 1.1.0."""
        assert qr_map["query_08"]["resolved_modules"]["example.com/data/json"] != "1.1.0"


# ────────────────────────────────────────────────────────────────────
# Dependency Tree Detail Tests
# ────────────────────────────────────────────────────────────────────

class TestDependencyTrees:
    def test_q02_tree_keys_sorted(self, qr_map):
        tree = qr_map["query_02"]["dependency_tree"]
        keys = list(tree.keys())
        assert keys == sorted(keys)

    def test_q02_tree_values_sorted(self, qr_map):
        tree = qr_map["query_02"]["dependency_tree"]
        for key, deps in tree.items():
            assert deps == sorted(deps), f"Deps for {key} not sorted"

    def test_q07_oauth_deps(self, qr_map):
        tree = qr_map["query_07"]["dependency_tree"]
        oauth_deps = tree["example.com/auth/oauth@1.1.0"]
        assert "example.com/auth/jwt@2.0.0" in oauth_deps
        assert "example.com/net/http@2.0.0" in oauth_deps

    def test_q09_mesh_client_deps(self, qr_map):
        tree = qr_map["query_09"]["dependency_tree"]
        deps = tree["example.com/mesh/client@1.0.0"]
        assert "example.com/core/logger@1.1.0" in deps
        assert "example.com/mesh/server@1.0.0" in deps

    def test_q03_tree_json_dep(self, qr_map):
        tree = qr_map["query_03"]["dependency_tree"]
        deps = tree["example.com/data/csv@1.1.0"]
        assert "example.com/data/json@1.2.0" in deps

    def test_q05_tree_missing_logger(self, qr_map):
        """Replace failed: core/config's dep tree should not reference core/logger."""
        tree = qr_map["query_05"]["dependency_tree"]
        config_deps = tree["example.com/core/config@1.1.0"]
        logger_refs = [d for d in config_deps if "logger" in d]
        assert len(logger_refs) == 0


# ────────────────────────────────────────────────────────────────────
# Build Order Tie-Breaking Tests
# ────────────────────────────────────────────────────────────────────

class TestBuildOrderTieBreaking:
    def test_q02_lex_tiebreak(self, qr_map):
        """auth/jwt and data/json both become available after core/config.
        auth/jwt < data/json lexicographically, so jwt comes first."""
        bo = qr_map["query_02"]["build_order"]
        assert bo.index("example.com/auth/jwt") < bo.index("example.com/data/json")

    def test_q07_lex_tiebreak(self, qr_map):
        """data/json and net/http both available at same level.
        data/json < net/http lexicographically."""
        bo = qr_map["query_07"]["build_order"]
        assert bo.index("example.com/data/json") < bo.index("example.com/net/http")


# ────────────────────────────────────────────────────────────────────
# Vulnerability Boundary Tests
# ────────────────────────────────────────────────────────────────────

class TestVulnerabilityBoundaries:
    def test_q07_http_2_0_0_affected(self, qr_map):
        """VULN-2024-006: affected_min=2.0.0, affected_max=2.1.0.
        2.0.0 >= 2.0.0 (inclusive) AND 2.0.0 < 2.1.0 (exclusive). Affected."""
        vulns = qr_map["query_07"]["vulnerabilities"]
        assert any(v["id"] == "VULN-2024-006" for v in vulns)

    def test_q01_http_1_1_0_not_affected_by_vuln006(self, qr_map):
        """VULN-2024-006 only affects >= 2.0.0. net/http@1.1.0 is NOT affected."""
        vulns = qr_map["query_01"]["vulnerabilities"]
        vuln006 = [v for v in vulns if v["id"] == "VULN-2024-006"]
        assert len(vuln006) == 0

    def test_q04_prerelease_affected(self, qr_map):
        """Pre-release 1.1.0-beta.2 < 1.1.0 (release), and affected_max is 1.1.0.
        So 1.1.0-beta.2 < 1.1.0 → it IS affected by VULN-2024-003."""
        vulns = qr_map["query_04"]["vulnerabilities"]
        assert any(v["version"] == "1.1.0-beta.2" for v in vulns)

    def test_q02_jwt_1_1_0_affected(self, qr_map):
        """VULN-2024-002: affects auth/jwt >= 1.0.0 and < 1.2.0.
        jwt@1.1.0 is in range."""
        vulns = qr_map["query_02"]["vulnerabilities"]
        jwt_vulns = [v for v in vulns if v["module"] == "example.com/auth/jwt"]
        assert len(jwt_vulns) == 1

    def test_q07_jwt_2_0_0_not_affected_by_vuln002(self, qr_map):
        """VULN-2024-002: affects auth/jwt < 1.2.0. jwt@2.0.0 is NOT affected."""
        vulns = qr_map["query_07"]["vulnerabilities"]
        jwt_vulns = [v for v in vulns if v["module"] == "example.com/auth/jwt"]
        assert len(jwt_vulns) == 0
