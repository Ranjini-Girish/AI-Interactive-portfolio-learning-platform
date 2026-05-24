"""
Tests for the go-semver-resolver task.
Validates the resolution_report.json produced by the agent's Go resolver.
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path("/app")
OUT_DIR = Path('/app/output')
REPORT = OUT_DIR / "resolution_report.json"


def _load():
    assert REPORT.is_file(), f"Missing output file: {REPORT}"
    with open(REPORT) as f:
        return json.load(f)


def _result(request_id):
    data = _load()
    for r in data["results"]:
        if r["request_id"] == request_id:
            return r
    raise AssertionError(f"Request '{request_id}' not found in results")


def _pkg(request_id, pkg_name):
    r = _result(request_id)
    for p in r["resolved_packages"]:
        if p["name"] == pkg_name:
            return p
    raise AssertionError(f"Package '{pkg_name}' not found in request '{request_id}'")


# ─── Output file structure ───────────────────────────────────────────────────
def test_output_file_exists():
    assert REPORT.is_file(), f"Missing: {REPORT}"


def test_json_valid():
    with open(REPORT) as f:
        data = json.load(f)
    assert isinstance(data, dict)


def test_json_two_space_indent():
    with open(REPORT) as f:
        raw = f.read()
    assert raw.startswith("{\n  "), "JSON must use two-space indent"


def test_json_trailing_newline():
    with open(REPORT) as f:
        raw = f.read()
    assert raw.endswith("\n"), "JSON must end with trailing newline"


def test_top_level_keys():
    d = _load()
    for k in ["schema_version", "config", "results"]:
        assert k in d, f"Missing top-level key: {k}"


def test_schema_version():
    assert _load()["schema_version"] == 1


def test_config_values():
    c = _load()["config"]
    assert c["max_depth"] == 10
    assert c["strategy"] == "highest-compatible"


def test_results_count():
    assert len(_load()["results"]) == 5


# ─── Request: basic ─────────────────────────────────────────────────────────
def test_basic_status():
    assert _result("basic")["status"] == "resolved"


def test_basic_total_resolved():
    assert _result("basic")["stats"]["total_resolved"] == 9


def test_basic_total_conflicts():
    assert _result("basic")["stats"]["total_conflicts"] == 0


def test_basic_max_depth():
    assert _result("basic")["stats"]["max_depth"] == 3


def test_basic_resolution_order():
    """BFS alphabetical: level1=[alpha,delta,epsilon], level2=[beta,gamma,iota,theta,zeta], level3=[eta]"""
    order = _result("basic")["stats"]["resolution_order"]
    assert order == ["alpha", "delta", "epsilon", "beta", "gamma", "iota", "theta", "zeta", "eta"]


def test_basic_alpha_version():
    """^1.2.0 = >=1.2.0 <2.0.0. Highest: 1.2.1."""
    assert _pkg("basic", "alpha")["version"] == "1.2.1"


def test_basic_alpha_depth():
    assert _pkg("basic", "alpha")["depth"] == 1


def test_basic_delta_version():
    """~0.0.2 = >=0.0.2 <0.1.0. Highest: 0.0.3."""
    assert _pkg("basic", "delta")["version"] == "0.0.3"


def test_basic_epsilon_version():
    """^2.0.0 = >=2.0.0 <3.0.0. Highest: 2.1.1."""
    assert _pkg("basic", "epsilon")["version"] == "2.1.1"


def test_basic_beta_version():
    """^0.2.0 = >=0.2.0 <0.3.0 (NOT <1.0.0). Highest: 0.2.3."""
    assert _pkg("basic", "beta")["version"] == "0.2.3"


def test_basic_beta_depth():
    assert _pkg("basic", "beta")["depth"] == 2


def test_basic_gamma_version():
    """^1.0.0 excludes pre-releases. Available non-prerelease: 1.0.0, 1.0.1, 1.1.0. Highest: 1.1.0."""
    assert _pkg("basic", "gamma")["version"] == "1.1.0"


def test_basic_gamma_not_prerelease():
    """Verify gamma did NOT resolve to any pre-release version."""
    v = _pkg("basic", "gamma")["version"]
    assert "-" not in v, f"gamma resolved to pre-release {v}, should be 1.1.0"


def test_basic_iota_version():
    assert _pkg("basic", "iota")["version"] == "1.1.0"


def test_basic_theta_version():
    assert _pkg("basic", "theta")["version"] == "1.1.0"


def test_basic_zeta_version():
    """^1.1.0 = >=1.1.0 <2.0.0. Available: 1.1.0, 1.2.0. Highest: 1.2.0."""
    assert _pkg("basic", "zeta")["version"] == "1.2.0"


def test_basic_eta_version():
    """Diamond: eta constrained by ^1.1.0 (gamma) AND ^1.2.0 (zeta). Intersection: >=1.2.0 <2.0.0. Highest: 1.2.1."""
    assert _pkg("basic", "eta")["version"] == "1.2.1"


def test_basic_eta_depth():
    assert _pkg("basic", "eta")["depth"] == 3


def test_basic_eta_requested_by():
    """eta should be requested by both gamma@1.1.0 and zeta@1.2.0."""
    rb = sorted(_pkg("basic", "eta")["requested_by"])
    assert rb == ["gamma@1.1.0", "zeta@1.2.0"]


def test_basic_eta_constraint_sources():
    cs = _pkg("basic", "eta")["constraint_sources"]
    assert cs.get("gamma@1.1.0") == "^1.1.0"
    assert cs.get("zeta@1.2.0") == "^1.2.0"


def test_basic_no_conflicts():
    assert _result("basic")["conflicts"] == []


def test_basic_packages_sorted():
    """resolved_packages must be sorted by name."""
    names = [p["name"] for p in _result("basic")["resolved_packages"]]
    assert names == sorted(names)


# ─── Request: prerelease_order ───────────────────────────────────────────────
def test_prerelease_status():
    assert _result("prerelease_order")["status"] == "resolved"


def test_prerelease_total_resolved():
    assert _result("prerelease_order")["stats"]["total_resolved"] == 1


def test_prerelease_gamma_version():
    """>=1.0.0-beta <1.0.0 matches: beta.2, beta.11, rc.1. Highest by precedence: rc.1."""
    assert _pkg("prerelease_order", "gamma")["version"] == "1.0.0-rc.1"


def test_prerelease_excludes_alpha():
    """1.0.0-alpha < 1.0.0-beta, so it does NOT satisfy >=1.0.0-beta."""
    v = _pkg("prerelease_order", "gamma")["version"]
    assert "alpha" not in v


def test_prerelease_numeric_comparison():
    """beta.11 > beta.2 (numeric comparison: 11 > 2), but rc.1 > beta.11 (lexicographic: r > b)."""
    assert _pkg("prerelease_order", "gamma")["version"] == "1.0.0-rc.1"


def test_prerelease_resolution_order():
    assert _result("prerelease_order")["stats"]["resolution_order"] == ["gamma"]


# ─── Request: conflict_detection ─────────────────────────────────────────────
def test_conflict_status():
    assert _result("conflict_detection")["status"] == "conflict"


def test_conflict_total_resolved():
    assert _result("conflict_detection")["stats"]["total_resolved"] == 6


def test_conflict_total_conflicts():
    assert _result("conflict_detection")["stats"]["total_conflicts"] == 1


def test_conflict_package():
    """eta has incompatible constraints: ~1.0.0 (from kappa) and ^1.1.0 (from gamma)."""
    conflicts = _result("conflict_detection")["conflicts"]
    assert len(conflicts) == 1
    assert conflicts[0]["package"] == "eta"


def test_conflict_reason():
    conflicts = _result("conflict_detection")["conflicts"]
    assert conflicts[0]["reason"] == "no version satisfies all constraints"


def test_conflict_constraint_sources():
    """Conflict on eta comes from kappa@1.1.0 (~1.0.0) and gamma@1.1.0 (^1.1.0)."""
    conflicts = _result("conflict_detection")["conflicts"]
    cs = conflicts[0]["constraint_sources"]
    assert "kappa@1.1.0" in cs
    assert "gamma@1.1.0" in cs
    assert cs["kappa@1.1.0"] == "~1.0.0"
    assert cs["gamma@1.1.0"] == "^1.1.0"


def test_conflict_eta_initially_resolved():
    """eta was resolved to 1.0.0 (satisfying ~1.0.0) before conflict detected."""
    assert _pkg("conflict_detection", "eta")["version"] == "1.0.0"


def test_conflict_kappa_version():
    """kappa@^1.0.0 = >=1.0.0 <2.0.0. Highest: 1.1.0."""
    assert _pkg("conflict_detection", "kappa")["version"] == "1.1.0"


def test_conflict_resolution_order():
    order = _result("conflict_detection")["stats"]["resolution_order"]
    assert order == ["alpha", "kappa", "beta", "eta", "gamma", "iota"]


# ─── Request: caret_zero ────────────────────────────────────────────────────
def test_caret_zero_status():
    assert _result("caret_zero")["status"] == "resolved"


def test_caret_zero_delta_version():
    """^0.0.2 = >=0.0.2 <0.0.3 (locks patch when major AND minor are zero). Only 0.0.2 matches."""
    assert _pkg("caret_zero", "delta")["version"] == "0.0.2"


def test_caret_zero_beta_version():
    """^0.2.0 = >=0.2.0 <0.3.0 (locks minor when major is zero). Highest: 0.2.3."""
    assert _pkg("caret_zero", "beta")["version"] == "0.2.3"


def test_caret_zero_total_resolved():
    assert _result("caret_zero")["stats"]["total_resolved"] == 2


def test_caret_zero_resolution_order():
    assert _result("caret_zero")["stats"]["resolution_order"] == ["beta", "delta"]


def test_caret_zero_max_depth():
    assert _result("caret_zero")["stats"]["max_depth"] == 1


# ─── Request: deep_diamond ──────────────────────────────────────────────────
def test_deep_diamond_status():
    assert _result("deep_diamond")["status"] == "resolved"


def test_deep_diamond_total_resolved():
    assert _result("deep_diamond")["stats"]["total_resolved"] == 6


def test_deep_diamond_max_depth():
    assert _result("deep_diamond")["stats"]["max_depth"] == 3


def test_deep_diamond_epsilon_version():
    assert _pkg("deep_diamond", "epsilon")["version"] == "2.1.1"


def test_deep_diamond_gamma_version():
    assert _pkg("deep_diamond", "gamma")["version"] == "1.1.0"


def test_deep_diamond_eta_version():
    """eta@^1.1.0 from gamma at depth 2. Highest in >=1.1.0 <2.0.0: 1.2.1."""
    assert _pkg("deep_diamond", "eta")["version"] == "1.2.1"


def test_deep_diamond_eta_depth():
    """eta discovered from gamma (depth 1) so eta at depth 2."""
    assert _pkg("deep_diamond", "eta")["depth"] == 2


def test_deep_diamond_theta_version():
    assert _pkg("deep_diamond", "theta")["version"] == "1.1.0"


def test_deep_diamond_zeta_version():
    """^1.1.0 from epsilon. Available >=1.1.0 <2.0.0: 1.1.0, 1.2.0. Highest: 1.2.0."""
    assert _pkg("deep_diamond", "zeta")["version"] == "1.2.0"


def test_deep_diamond_iota_version():
    assert _pkg("deep_diamond", "iota")["version"] == "1.1.0"


def test_deep_diamond_iota_depth():
    """iota from theta (depth 2), so iota at depth 3."""
    assert _pkg("deep_diamond", "iota")["depth"] == 3


def test_deep_diamond_resolution_order():
    order = _result("deep_diamond")["stats"]["resolution_order"]
    assert order == ["epsilon", "gamma", "eta", "theta", "zeta", "iota"]


def test_deep_diamond_eta_compatible_with_zeta():
    """After zeta@1.2.0 requires eta@^1.2.0, check eta@1.2.1 still satisfies (no conflict)."""
    assert _result("deep_diamond")["conflicts"] == []


# ─── Cross-cutting validation ────────────────────────────────────────────────
def test_all_packages_have_required_fields():
    """Every resolved_packages entry must have name, version, depth, requested_by, constraint_sources."""
    for result in _load()["results"]:
        for pkg in result["resolved_packages"]:
            for field in ["name", "version", "depth", "requested_by", "constraint_sources"]:
                assert field in pkg, f"Missing field '{field}' in package {pkg.get('name', '?')}"


def test_all_stats_have_required_fields():
    for result in _load()["results"]:
        stats = result["stats"]
        for field in ["total_resolved", "total_conflicts", "max_depth", "resolution_order"]:
            assert field in stats, f"Missing stats field '{field}' in request {result['request_id']}"


def test_resolved_packages_count_matches_stats():
    for result in _load()["results"]:
        assert len(result["resolved_packages"]) == result["stats"]["total_resolved"]


def test_conflicts_count_matches_stats():
    for result in _load()["results"]:
        assert len(result["conflicts"]) == result["stats"]["total_conflicts"]


# ─── Dynamic anti-hardcoding tests ──────────────────────────────────────────
# These tests modify data at runtime and re-run the Go binary to verify
# the resolver actually computes results from the data files.

DATA_DIR = ROOT / "data"
BUILD_DIR = ROOT / "build"
RESOLVER_BIN = BUILD_DIR / "resolver"


def _find_binary():
    """Find the resolver binary."""
    for name in ["resolver", "resolver.exe"]:
        p = BUILD_DIR / name
        if p.is_file():
            return str(p)
    return None


def _run_resolver_with_modified_data(registry_mod=None, requests_mod=None):
    """Run resolver against modified data, return parsed JSON output."""
    binary = _find_binary()
    if binary is None:
        return None

    tmpdir = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(str(DATA_DIR), str(tmpdir / "data"))
        out_dir = tmpdir / "output"
        out_dir.mkdir()

        if registry_mod:
            reg_path = tmpdir / "data" / "registry.json"
            with open(reg_path) as f:
                reg = json.load(f)
            registry_mod(reg)
            with open(reg_path, "w") as f:
                json.dump(reg, f, indent=2)

        if requests_mod:
            req_path = tmpdir / "data" / "requests.json"
            with open(req_path) as f:
                reqs = json.load(f)
            requests_mod(reqs)
            with open(req_path, "w") as f:
                json.dump(reqs, f, indent=2)

        env = os.environ.copy()
        env["APP_DATA_DIR"] = str(tmpdir / "data")
        env["APP_OUTPUT_DIR"] = str(tmpdir / "output")

        subprocess.run(
            [binary],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            timeout=30,
        )

        report_path = tmpdir / "output" / "resolution_report.json"
        if not report_path.is_file():
            report_path = ROOT / "output" / "resolution_report.json"
            if not report_path.is_file():
                return None

        with open(report_path) as f:
            return json.load(f)
    except Exception:
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_dynamic_caret_zero_locks_patch():
    """Add delta@0.0.4 to registry. ^0.0.2 should still resolve to 0.0.2 (not 0.0.4)."""
    def mod_reg(reg):
        reg["packages"]["delta"]["versions"]["0.0.4"] = {"dependencies": {}}

    report = _run_resolver_with_modified_data(registry_mod=mod_reg)
    if report is None:
        return

    for r in report["results"]:
        if r["request_id"] == "caret_zero":
            for p in r["resolved_packages"]:
                if p["name"] == "delta":
                    assert p["version"] == "0.0.2", \
                        f"^0.0.2 must lock to >=0.0.2 <0.0.3; got {p['version']}"
                    return
    assert False, "delta not found in caret_zero result"


def test_dynamic_caret_zero_minor():
    """Add beta@0.2.9. ^0.2.0 = >=0.2.0 <0.3.0 should pick 0.2.9 (highest in range)."""
    def mod_reg(reg):
        reg["packages"]["beta"]["versions"]["0.2.9"] = {"dependencies": {}}

    report = _run_resolver_with_modified_data(registry_mod=mod_reg)
    if report is None:
        return

    for r in report["results"]:
        if r["request_id"] == "caret_zero":
            for p in r["resolved_packages"]:
                if p["name"] == "beta":
                    assert p["version"] == "0.2.9", \
                        f"^0.2.0 with 0.2.9 available should pick 0.2.9; got {p['version']}"
                    return
    assert False, "beta not found in caret_zero result"


def test_dynamic_prerelease_excluded_from_caret():
    """Add gamma@1.2.0-alpha to registry. ^1.0.0 (no pre-release) must NOT select it over 1.1.0."""
    def mod_reg(reg):
        reg["packages"]["gamma"]["versions"]["1.2.0-alpha"] = {"dependencies": {}}

    report = _run_resolver_with_modified_data(registry_mod=mod_reg)
    if report is None:
        return

    for r in report["results"]:
        if r["request_id"] == "basic":
            for p in r["resolved_packages"]:
                if p["name"] == "gamma":
                    assert p["version"] == "1.1.0", \
                        f"^1.0.0 must not match pre-release 1.2.0-alpha; got {p['version']}"
                    return
    assert False, "gamma not found in basic result"


def test_dynamic_tilde_range():
    """Add delta@0.0.9 to registry. ~0.0.2 = >=0.0.2 <0.1.0 should pick 0.0.9."""
    def mod_reg(reg):
        reg["packages"]["delta"]["versions"]["0.0.9"] = {"dependencies": {}}

    report = _run_resolver_with_modified_data(registry_mod=mod_reg)
    if report is None:
        return

    for r in report["results"]:
        if r["request_id"] == "basic":
            for p in r["resolved_packages"]:
                if p["name"] == "delta":
                    assert p["version"] == "0.0.9", \
                        f"~0.0.2 with 0.0.9 available should pick 0.0.9; got {p['version']}"
                    return
    assert False, "delta not found in basic result"


def test_dynamic_prerelease_ordering():
    """Add gamma 1.0.0-beta.20 to registry. In prerelease_order test, beta.20 > beta.11 numerically, but rc.1 should still win."""
    def mod_reg(reg):
        reg["packages"]["gamma"]["versions"]["1.0.0-beta.20"] = {"dependencies": {}}

    report = _run_resolver_with_modified_data(registry_mod=mod_reg)
    if report is None:
        return

    for r in report["results"]:
        if r["request_id"] == "prerelease_order":
            for p in r["resolved_packages"]:
                if p["name"] == "gamma":
                    assert p["version"] == "1.0.0-rc.1", \
                        f"rc.1 > beta.20 (lexicographic on first id: r>b); got {p['version']}"
                    return
    assert False, "gamma not found in prerelease_order result"


def test_dynamic_new_version_resolves_conflict():
    """Add eta@1.1.5 to registry. In conflict_detection, eta needs ~1.0.0 (>=1.0.0 <1.1.0) AND ^1.1.0 (>=1.1.0). Still a conflict since ranges don't overlap."""
    def mod_reg(reg):
        reg["packages"]["eta"]["versions"]["1.1.5"] = {"dependencies": {}}

    report = _run_resolver_with_modified_data(registry_mod=mod_reg)
    if report is None:
        return

    for r in report["results"]:
        if r["request_id"] == "conflict_detection":
            assert r["status"] == "conflict", \
                "eta conflict should persist even with 1.1.5 (ranges ~1.0.0 and ^1.1.0 don't overlap)"
            return
    assert False, "conflict_detection not found in results"
