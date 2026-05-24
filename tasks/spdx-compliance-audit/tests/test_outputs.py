"""Tests for dependency-license-audit-hard."""
import json
import math
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

FLOAT_TOL = 1e-3


def load_report():
    """Load and return the main output JSON report."""
    p = OUT_DIR / "audit_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


def _find_project(project_id):
    """Find a project entry in the report."""
    for p in R["projects"]:
        if p["project_id"] == project_id:
            return p
    pytest.fail(f"Missing project: {project_id}")


def _find_dep(project_id, package_name):
    """Find a dependency entry within a project."""
    proj = _find_project(project_id)
    for d in proj["dependencies"]:
        if d["package_name"] == package_name:
            return d
    pytest.fail(f"Missing dep {package_name} in {project_id}")


def _find_violation(project_id, package_name, violation_type=None):
    """Find a violation entry within a project."""
    proj = _find_project(project_id)
    for v in proj["violations"]:
        if v["package_name"] == package_name:
            if violation_type is None or v["violation_type"] == violation_type:
                return v
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Structure tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_output_file_exists():
    """Verify the main output file was created."""
    assert (OUT_DIR / "audit_report.json").is_file()


def test_top_level_keys():
    """Verify the output contains all required top-level keys."""
    required = {"metadata", "projects", "summary"}
    assert set(R.keys()) == required


def test_metadata_total_projects():
    """Verify metadata reports 3 projects."""
    assert R["metadata"]["total_projects"] == 3


def test_metadata_total_packages():
    """Verify metadata reports 23 packages."""
    assert R["metadata"]["total_packages"] == 23


def test_metadata_policy_version():
    """Verify metadata reports policy version 1.0."""
    assert R["metadata"]["policy_version"] == "1.0"


def test_projects_count():
    """Verify there are 3 project entries."""
    assert len(R["projects"]) == 3


def test_project_entry_keys():
    """Verify each project has all required keys."""
    required = {"project_id", "project_license", "dependency_count",
                "direct_dependency_count", "max_depth", "dependencies",
                "violations", "risk_score"}
    for p in R["projects"]:
        assert set(p.keys()) == required, f"{p['project_id']}: missing keys"


def test_dependency_entry_keys():
    """Verify each dependency entry has all required keys."""
    required = {"package_name", "version", "declared_license",
                "effective_license", "license_category", "depth"}
    for p in R["projects"]:
        for d in p["dependencies"]:
            assert set(d.keys()) == required, f"{d['package_name']}: missing keys"


def test_summary_keys():
    """Verify summary has all required keys."""
    required = {"total_violations", "total_waived", "projects_at_risk",
                "highest_risk_project", "most_common_violation_license"}
    assert set(R["summary"].keys()) == required


# ═══════════════════════════════════════════════════════════════════════════════
# Sorting tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_projects_sorted_by_id():
    """Verify projects are sorted by project_id ascending."""
    ids = [p["project_id"] for p in R["projects"]]
    assert ids == sorted(ids)


def test_dependencies_sorted_by_depth_then_name():
    """Verify dependencies within each project are sorted by (depth, name)."""
    for p in R["projects"]:
        keys = [(d["depth"], d["package_name"]) for d in p["dependencies"]]
        assert keys == sorted(keys), f"{p['project_id']}: deps not sorted"


def test_violations_sorted_by_severity_desc_depth_asc_name_asc():
    """Verify violations are sorted by (severity DESC, depth ASC, name ASC)."""
    for p in R["projects"]:
        keys = [(-v["severity"], v["depth"], v["package_name"]) for v in p["violations"]]
        assert keys == sorted(keys), f"{p['project_id']}: violations not sorted"


# ═══════════════════════════════════════════════════════════════════════════════
# web-api project tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_webapi_dependency_count():
    """Verify web-api has 13 total dependencies."""
    p = _find_project("web-api")
    assert p["dependency_count"] == 13


def test_webapi_direct_count():
    """Verify web-api has 7 direct dependencies."""
    p = _find_project("web-api")
    assert p["direct_dependency_count"] == 7


def test_webapi_max_depth():
    """Verify web-api max depth is 1."""
    p = _find_project("web-api")
    assert p["max_depth"] == 1


def test_webapi_risk_score_zero():
    """Verify web-api risk is 0 because only violation is waived."""
    p = _find_project("web-api")
    assert p["risk_score"] == 0.0


def test_webapi_violation_count():
    """Verify web-api has exactly 1 violation (libvips, waived)."""
    p = _find_project("web-api")
    assert len(p["violations"]) == 1


def test_webapi_libvips_waived():
    """Verify libvips violation in web-api is waived."""
    v = _find_violation("web-api", "libvips", "restricted_license")
    assert v is not None
    assert v["waived"] is True


def test_webapi_libvips_severity():
    """Verify libvips restricted violation has severity 5."""
    v = _find_violation("web-api", "libvips")
    assert v["severity"] == 5


def test_webapi_libvips_depth():
    """Verify libvips is at depth 1 in web-api."""
    d = _find_dep("web-api", "libvips")
    assert d["depth"] == 1


def test_webapi_libvips_dependency_path():
    """Verify libvips dependency path goes through sharp."""
    v = _find_violation("web-api", "libvips")
    assert v["dependency_path"] == ["web-api", "sharp", "libvips"]


def test_webapi_no_copyleft_propagation():
    """Verify LGPL with dynamic linking does NOT propagate to sharp."""
    v = _find_violation("web-api", "sharp", "copyleft_propagation")
    assert v is None, "sharp should NOT have copyleft_propagation (LGPL dynamic exempt)"


# ═══════════════════════════════════════════════════════════════════════════════
# video-svc project tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_videosvc_dependency_count():
    """Verify video-svc has 9 total dependencies."""
    p = _find_project("video-svc")
    assert p["dependency_count"] == 9


def test_videosvc_direct_count():
    """Verify video-svc has 4 direct dependencies."""
    p = _find_project("video-svc")
    assert p["direct_dependency_count"] == 4


def test_videosvc_max_depth():
    """Verify video-svc max depth is 2 (media-codec through ffmpeg-node)."""
    p = _find_project("video-svc")
    assert p["max_depth"] == 2


def test_videosvc_risk_score():
    """Verify video-svc risk = 10/2 + 8/1 + 5/3 = 14.6667."""
    p = _find_project("video-svc")
    expected = 10.0 / 2 + 8.0 / 1 + 5.0 / 3
    assert math.isclose(p["risk_score"], round(expected, 4), abs_tol=FLOAT_TOL)


def test_videosvc_violation_count():
    """Verify video-svc has exactly 3 violations."""
    p = _find_project("video-svc")
    assert len(p["violations"]) == 3


def test_videosvc_ffmpeg_banned():
    """Verify ffmpeg-node has banned_license violation."""
    v = _find_violation("video-svc", "ffmpeg-node", "banned_license")
    assert v is not None
    assert v["severity"] == 10
    assert v["depth"] == 1


def test_videosvc_videoutil_copyleft():
    """Verify video-utils has copyleft_propagation from ffmpeg-node."""
    v = _find_violation("video-svc", "video-utils", "copyleft_propagation")
    assert v is not None
    assert v["severity"] == 8
    assert v["depth"] == 0
    assert v["propagated_from"] == "ffmpeg-node"
    assert v["source_license"] == "GPL-3.0-only"


def test_videosvc_mediacodec_restricted():
    """Verify media-codec has restricted_license violation."""
    v = _find_violation("video-svc", "media-codec", "restricted_license")
    assert v is not None
    assert v["severity"] == 5
    assert v["depth"] == 2


def test_videosvc_mediacodec_path():
    """Verify media-codec dependency path goes through video-utils and ffmpeg-node."""
    v = _find_violation("video-svc", "media-codec")
    assert v["dependency_path"] == ["video-svc", "video-utils", "ffmpeg-node", "media-codec"]


def test_videosvc_no_waived():
    """Verify no violations are waived in video-svc."""
    p = _find_project("video-svc")
    assert all(not v["waived"] for v in p["violations"])


# ═══════════════════════════════════════════════════════════════════════════════
# data-pipe project tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_datapipe_dependency_count():
    """Verify data-pipe has 7 total dependencies."""
    p = _find_project("data-pipe")
    assert p["dependency_count"] == 7


def test_datapipe_direct_count():
    """Verify data-pipe has 4 direct dependencies."""
    p = _find_project("data-pipe")
    assert p["direct_dependency_count"] == 4


def test_datapipe_risk_score():
    """Verify data-pipe risk = 10/2 + 8/1 = 13.0."""
    p = _find_project("data-pipe")
    assert p["risk_score"] == 13.0


def test_datapipe_violation_count():
    """Verify data-pipe has exactly 2 violations."""
    p = _find_project("data-pipe")
    assert len(p["violations"]) == 2


def test_datapipe_xmlparser_banned():
    """Verify xml-parser has banned_license violation."""
    v = _find_violation("data-pipe", "xml-parser", "banned_license")
    assert v is not None
    assert v["severity"] == 10
    assert v["dependency_path"] == ["data-pipe", "config-reader", "xml-parser"]


def test_datapipe_configreader_copyleft():
    """Verify config-reader has copyleft_propagation from xml-parser."""
    v = _find_violation("data-pipe", "config-reader", "copyleft_propagation")
    assert v is not None
    assert v["propagated_from"] == "xml-parser"
    assert v["source_license"] == "GPL-2.0-only"


# ═══════════════════════════════════════════════════════════════════════════════
# SPDX OR resolution — key gotcha
# ═══════════════════════════════════════════════════════════════════════════════


def test_spdx_or_chartlib_resolved_to_mit():
    """Verify (MIT OR GPL-3.0-only) resolves to MIT (most permissive)."""
    d = _find_dep("data-pipe", "chart-lib")
    assert d["declared_license"] == "(MIT OR GPL-3.0-only)"
    assert d["effective_license"] == "MIT"
    assert d["license_category"] == "allowed"


def test_spdx_or_no_violation_for_chartlib():
    """Verify chart-lib has no violation despite GPL-3.0-only in OR expression."""
    v = _find_violation("data-pipe", "chart-lib")
    assert v is None, "chart-lib should have no violation (OR resolves to MIT)"


# ═══════════════════════════════════════════════════════════════════════════════
# SPDX AND handling — key gotcha
# ═══════════════════════════════════════════════════════════════════════════════


def test_spdx_and_pg_effective_license():
    """Verify (MIT AND BSD-2-Clause) keeps combined effective_license string."""
    d = _find_dep("web-api", "pg")
    assert d["declared_license"] == "(MIT AND BSD-2-Clause)"
    assert d["effective_license"] == "MIT AND BSD-2-Clause"


def test_spdx_and_pg_category():
    """Verify AND expression takes most restrictive: both allowed → allowed."""
    d = _find_dep("web-api", "pg")
    assert d["license_category"] == "allowed"


def test_spdx_and_pg_no_violation():
    """Verify pg has no violation (both MIT and BSD-2-Clause are allowed)."""
    v = _find_violation("web-api", "pg")
    assert v is None


# ═══════════════════════════════════════════════════════════════════════════════
# Copyleft propagation — key gotcha
# ═══════════════════════════════════════════════════════════════════════════════


def test_copyleft_propagation_has_source_fields():
    """Verify copyleft_propagation violations include propagated_from and source_license."""
    v = _find_violation("video-svc", "video-utils", "copyleft_propagation")
    assert "propagated_from" in v
    assert "source_license" in v


def test_copyleft_propagation_severity():
    """Verify copyleft propagation uses the configured severity (8)."""
    v = _find_violation("video-svc", "video-utils", "copyleft_propagation")
    assert v["severity"] == 8


def test_lgpl_dynamic_does_not_propagate():
    """Verify LGPL-2.1-or-later with dynamic linking does not cause copyleft propagation.

    libvips is LGPL with linking_type=dynamic. The policy has lgpl_dynamic_linking_exempt=true.
    Therefore sharp (which depends on libvips) should NOT get a copyleft_propagation violation.
    """
    v = _find_violation("web-api", "sharp", "copyleft_propagation")
    assert v is None


def test_lgpl_still_generates_own_violation():
    """Verify LGPL package itself still gets a restricted_license violation."""
    v = _find_violation("web-api", "libvips", "restricted_license")
    assert v is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Waiver handling — key gotcha
# ═══════════════════════════════════════════════════════════════════════════════


def test_waived_violation_still_listed():
    """Verify waived violations appear in the violations list (not omitted)."""
    p = _find_project("web-api")
    assert len(p["violations"]) == 1
    assert p["violations"][0]["waived"] is True


def test_waived_does_not_affect_risk():
    """Verify waived violations do not contribute to risk_score."""
    p = _find_project("web-api")
    assert p["risk_score"] == 0.0


def test_waiver_project_specific():
    """Verify waiver for libvips only applies to web-api, not other projects."""
    v_webapi = _find_violation("web-api", "libvips")
    assert v_webapi is not None and v_webapi["waived"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Risk scoring — key gotcha: depth + 1
# ═══════════════════════════════════════════════════════════════════════════════


def test_risk_score_formula_videosvc():
    """Verify risk uses severity/(depth+1), not severity/depth or severity*depth."""
    p = _find_project("video-svc")
    expected = 10.0 / (1 + 1) + 8.0 / (0 + 1) + 5.0 / (2 + 1)
    assert math.isclose(p["risk_score"], round(expected, 4), abs_tol=FLOAT_TOL)


def test_risk_score_depth_zero_divides_by_one():
    """Verify depth=0 violation contributes severity/1 to risk, not division by zero."""
    p = _find_project("video-svc")
    assert p["risk_score"] >= 8.0, "Depth-0 copyleft (severity 8) should contribute 8.0"


def test_risk_excludes_waived():
    """Verify risk computation excludes waived violations."""
    p = _find_project("web-api")
    assert p["risk_score"] == 0.0, "All violations waived, risk should be 0"


# ═══════════════════════════════════════════════════════════════════════════════
# Deduplication — key gotcha: shallowest depth
# ═══════════════════════════════════════════════════════════════════════════════


def test_lodash_deduplicated_at_shallowest():
    """Verify lodash appears once at depth 0 in data-pipe (direct dep + transitive via data-viz)."""
    p = _find_project("data-pipe")
    lodash_entries = [d for d in p["dependencies"] if d["package_name"] == "lodash"]
    assert len(lodash_entries) == 1, "lodash should appear exactly once"
    assert lodash_entries[0]["depth"] == 0, "lodash should be at depth 0 (direct dep)"


def test_no_duplicate_packages_in_deps():
    """Verify no package appears more than once in any project's dependencies."""
    for p in R["projects"]:
        names = [d["package_name"] for d in p["dependencies"]]
        assert len(names) == len(set(names)), f"{p['project_id']}: duplicate deps found"


# ═══════════════════════════════════════════════════════════════════════════════
# Summary tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_summary_total_violations():
    """Verify total violations across all projects is 6."""
    assert R["summary"]["total_violations"] == 6


def test_summary_total_waived():
    """Verify total waived violations is 1."""
    assert R["summary"]["total_waived"] == 1


def test_summary_projects_at_risk():
    """Verify 2 projects have risk_score > 0."""
    assert R["summary"]["projects_at_risk"] == 2


def test_summary_highest_risk_project():
    """Verify highest risk project is video-svc (14.6667 > 13.0)."""
    assert R["summary"]["highest_risk_project"] == "video-svc"


def test_summary_most_common_violation_license():
    """Verify most common violation license is GPL-2.0-only (tied with GPL-3.0, alphabetic first)."""
    assert R["summary"]["most_common_violation_license"] == "GPL-2.0-only"


def test_summary_violations_match_project_sum():
    """Verify total_violations equals sum of per-project violation counts."""
    total = sum(len(p["violations"]) for p in R["projects"])
    assert R["summary"]["total_violations"] == total


def test_summary_waived_match():
    """Verify total_waived matches count of waived=true across all projects."""
    total = sum(1 for p in R["projects"] for v in p["violations"] if v["waived"])
    assert R["summary"]["total_waived"] == total


# ═══════════════════════════════════════════════════════════════════════════════
# Depth and path consistency
# ═══════════════════════════════════════════════════════════════════════════════


def test_direct_deps_at_depth_zero():
    """Verify all direct dependencies are at depth 0."""
    projects_raw = {}
    for fp in sorted((DATA_DIR / "projects").glob("*.json")):
        proj = json.loads(fp.read_text(encoding="utf-8"))
        projects_raw[proj["project_id"]] = proj["direct_dependencies"]

    for p in R["projects"]:
        direct = set(projects_raw.get(p["project_id"], []))
        for d in p["dependencies"]:
            if d["package_name"] in direct:
                assert d["depth"] == 0, (
                    f"{p['project_id']}/{d['package_name']}: direct dep should be depth 0"
                )


def test_transitive_deps_positive_depth():
    """Verify non-direct dependencies have depth > 0."""
    projects_raw = {}
    for fp in sorted((DATA_DIR / "projects").glob("*.json")):
        proj = json.loads(fp.read_text(encoding="utf-8"))
        projects_raw[proj["project_id"]] = set(proj["direct_dependencies"])

    for p in R["projects"]:
        direct = projects_raw.get(p["project_id"], set())
        for d in p["dependencies"]:
            if d["package_name"] not in direct:
                assert d["depth"] > 0, (
                    f"{p['project_id']}/{d['package_name']}: transitive dep should have depth > 0"
                )


def test_violation_depth_matches_dep_depth():
    """Verify violation depth matches the dependency depth for non-propagation violations."""
    for p in R["projects"]:
        dep_map = {d["package_name"]: d["depth"] for d in p["dependencies"]}
        for v in p["violations"]:
            if v["package_name"] in dep_map:
                assert v["depth"] == dep_map[v["package_name"]], (
                    f"{p['project_id']}/{v['package_name']}: violation depth != dep depth"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# JSON formatting
# ═══════════════════════════════════════════════════════════════════════════════


def test_json_trailing_newline():
    """Verify the output JSON file ends with a trailing newline."""
    content = (OUT_DIR / "audit_report.json").read_text(encoding="utf-8")
    assert content.endswith("\n")


def test_json_two_space_indent():
    """Verify the output JSON uses 2-space indentation."""
    content = (OUT_DIR / "audit_report.json").read_text(encoding="utf-8")
    parsed = json.loads(content)
    expected = json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
    assert content == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Input integrity
# ═══════════════════════════════════════════════════════════════════════════════


def test_input_packages_exist():
    """Verify all 23 package files exist."""
    pkg_dir = DATA_DIR / "packages"
    assert pkg_dir.is_dir()
    files = list(pkg_dir.glob("*.json"))
    assert len(files) == 23


def test_input_projects_exist():
    """Verify all 3 project files exist."""
    proj_dir = DATA_DIR / "projects"
    assert proj_dir.is_dir()
    files = list(proj_dir.glob("*.json"))
    assert len(files) == 3


def test_input_policy_exists():
    """Verify policy.json exists."""
    assert (ROOT / "config" / "policy.json").is_file()


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-project consistency
# ═══════════════════════════════════════════════════════════════════════════════


def test_express_same_version_across_projects():
    """Verify express has the same version in all projects that use it."""
    versions = set()
    for p in R["projects"]:
        for d in p["dependencies"]:
            if d["package_name"] == "express":
                versions.add(d["version"])
    assert len(versions) <= 1


def test_all_license_categories_valid():
    """Verify all license_category values are one of the three valid categories."""
    valid = {"allowed", "restricted", "banned"}
    for p in R["projects"]:
        for d in p["dependencies"]:
            assert d["license_category"] in valid, (
                f"{d['package_name']}: invalid category {d['license_category']}"
            )


def test_all_violation_types_valid():
    """Verify all violation_type values are one of the three valid types."""
    valid = {"banned_license", "restricted_license", "copyleft_propagation"}
    for p in R["projects"]:
        for v in p["violations"]:
            assert v["violation_type"] in valid
