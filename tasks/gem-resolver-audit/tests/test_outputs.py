"""Tests for Ruby Gem Dependency Resolver Audit."""
import json
import math
import pathlib
import hashlib


ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')


def load_report():
    """Load and return the main output JSON report."""
    p = OUT_DIR / "gem_audit.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()

TOL = 1e-4
EXACT_TOL = 1e-6


def _proj(pid):
    """Return the project audit for the given project_id."""
    return next(a for a in R["project_audits"] if a["project_id"] == pid)


def _resolved(pid, gem):
    """Return a specific resolved dependency from a project."""
    audit = _proj(pid)
    return next(d for d in audit["resolved_dependencies"] if d["gem_name"] == gem)


# ─── File existence and structure ──────────────────────────────────────────


def test_output_file_exists():
    """Verify the main output file was created."""
    assert (OUT_DIR / "gem_audit.json").is_file()


def test_valid_json():
    """Verify the output is valid JSON."""
    text = (OUT_DIR / "gem_audit.json").read_text(encoding="utf-8")
    data = json.loads(text)
    assert isinstance(data, dict)


def test_trailing_newline():
    """Verify the output file ends with a trailing newline."""
    text = (OUT_DIR / "gem_audit.json").read_text(encoding="utf-8")
    assert text.endswith("\n")


def test_two_space_indent():
    """Verify the output uses 2-space indentation."""
    text = (OUT_DIR / "gem_audit.json").read_text(encoding="utf-8")
    lines = text.split("\n")
    indented = [line for line in lines if line.startswith("  ") and not line.startswith("   ")]
    assert len(indented) > 0


def test_top_level_keys():
    """Verify all required top-level keys are present."""
    required = {"findings", "project_audits", "schema_version", "source_hashes", "summary"}
    assert set(R.keys()) == required


def test_schema_version():
    """Verify schema version is 1."""
    assert R["schema_version"] == 1


# ─── Summary tests ────────────────────────────────────────────────────────


def test_summary_total_projects():
    """Verify total project count."""
    assert R["summary"]["total_projects"] == 4


def test_summary_total_findings():
    """Verify total findings count."""
    assert R["summary"]["total_findings"] == 3


def test_summary_total_gems_resolved():
    """Verify total gems resolved across all projects."""
    assert R["summary"]["total_gems_resolved"] == 30


def test_summary_total_conflicts():
    """Verify total version conflicts count."""
    assert R["summary"]["total_conflicts"] == 0


def test_summary_findings_by_severity_all_present():
    """Verify all five severity levels are present in findings_by_severity."""
    fbs = R["summary"]["findings_by_severity"]
    assert set(fbs.keys()) == {"critical", "high", "info", "low", "medium"}


def test_summary_findings_by_severity_values():
    """Verify findings_by_severity counts match the actual findings."""
    fbs = R["summary"]["findings_by_severity"]
    assert fbs["critical"] == 0
    assert fbs["high"] == 1
    assert fbs["medium"] == 2
    assert fbs["low"] == 0
    assert fbs["info"] == 0


def test_summary_findings_by_type():
    """Verify findings_by_type breakdown."""
    fbt = R["summary"]["findings_by_type"]
    assert fbt["copyleft_in_permissive"] == 2
    assert fbt["vulnerability"] == 1


def test_summary_aggregate_risk_geometric_mean():
    """Verify aggregate risk is geometric mean, not arithmetic."""
    agg = R["summary"]["aggregate_risk_score"]
    scores = [f["risk_score"] for f in R["findings"] if f["risk_score"] > 0]
    if scores:
        log_sum = sum(math.log(s) for s in scores)
        expected = round(math.exp(log_sum / len(scores)), 6)
        assert math.isclose(agg, expected, abs_tol=EXACT_TOL), (
            f"aggregate_risk_score={agg}, expected geometric mean={expected}"
        )


def test_summary_aggregate_risk_not_arithmetic():
    """Verify aggregate risk is NOT the arithmetic mean."""
    agg = R["summary"]["aggregate_risk_score"]
    scores = [f["risk_score"] for f in R["findings"] if f["risk_score"] > 0]
    if len(scores) > 1:
        arith = sum(scores) / len(scores)
        assert not math.isclose(agg, arith, abs_tol=0.01), (
            "aggregate_risk_score appears to be arithmetic mean — must be geometric"
        )


def test_summary_aggregate_risk_exact():
    """Verify exact aggregate risk score value."""
    assert math.isclose(R["summary"]["aggregate_risk_score"], 4.608494, abs_tol=EXACT_TOL)


# ─── Project audit structure ──────────────────────────────────────────────


def test_project_audit_count():
    """Verify there are exactly 4 project audits."""
    assert len(R["project_audits"]) == 4


def test_project_audits_sorted():
    """Verify project audits are sorted by project_id."""
    pids = [a["project_id"] for a in R["project_audits"]]
    assert pids == sorted(pids)


def test_audit_keys():
    """Verify each project audit has all required keys."""
    required = {"findings", "metrics", "project_id", "project_license",
                "resolved_dependencies", "version_conflicts"}
    for a in R["project_audits"]:
        assert set(a.keys()) == required, f"Wrong keys in {a['project_id']}"


# ─── api_service resolution (TRAP: ~> 2.1 two-segment form) ──────────────


def test_api_resolved_count():
    """api_service resolves 7 runtime gems."""
    assert _proj("api_service")["metrics"]["total_resolved"] == 7


def test_api_rack_version():
    """api_service resolves rack 2.2.3 — ~> 2.1 allows up to < 3.0.0."""
    assert _resolved("api_service", "rack")["version"] == "2.2.3"


def test_api_sinatra_version():
    """api_service resolves sinatra 3.0.0 — ~> 3.0.0 allows >= 3.0.0, < 3.1.0."""
    assert _resolved("api_service", "sinatra")["version"] == "3.0.0"


def test_api_puma_version():
    """api_service resolves puma 5.0.0 — ~> 5.0 allows >= 5.0.0, < 6.0.0."""
    assert _resolved("api_service", "puma")["version"] == "5.0.0"


def test_api_faraday_version():
    """api_service resolves faraday 2.9.0 — ~> 2.7 allows >= 2.7.0, < 3.0.0."""
    assert _resolved("api_service", "faraday")["version"] == "2.9.0"


def test_api_nokogiri_version():
    """api_service resolves nokogiri 1.16.0 — ~> 1.14 allows >= 1.14.0, < 2.0.0."""
    assert _resolved("api_service", "nokogiri")["version"] == "1.16.0"


def test_api_rack_depth():
    """rack is a transitive dep (via sinatra and puma) at depth 2."""
    assert _resolved("api_service", "rack")["depth"] == 2


def test_api_rack_constraint_sources():
    """rack in api_service is constrained by puma and sinatra."""
    sources = sorted(_resolved("api_service", "rack")["constraint_sources"])
    assert sources == ["puma", "sinatra"]


def test_api_no_findings():
    """api_service has no license or security findings."""
    assert len(_proj("api_service")["findings"]) == 0


def test_api_no_conflicts():
    """api_service has no version conflicts."""
    assert len(_proj("api_service")["version_conflicts"]) == 0


def test_api_dev_deps_excluded():
    """Development dependencies (rspec, webrick) are excluded from resolution."""
    gems = [d["gem_name"] for d in _proj("api_service")["resolved_dependencies"]]
    assert "rspec" not in gems
    assert "webrick" not in gems


def test_api_multi_json_transitive():
    """multi_json is a transitive dep via sinatra and faraday."""
    rd = _resolved("api_service", "multi_json")
    assert rd["depth"] == 2
    assert sorted(rd["constraint_sources"]) == ["faraday", "sinatra"]


def test_api_avg_depth_harmonic():
    """api_service avg_depth uses harmonic mean of depths."""
    m = _proj("api_service")["metrics"]
    depths = [d["depth"] for d in _proj("api_service")["resolved_dependencies"]]
    n = len(depths)
    harmonic = n / sum(1.0 / d for d in depths)
    assert math.isclose(m["avg_depth"], round(harmonic, 6), abs_tol=EXACT_TOL)


def test_api_avg_depth_not_arithmetic():
    """api_service avg_depth is NOT arithmetic mean."""
    m = _proj("api_service")["metrics"]
    depths = [d["depth"] for d in _proj("api_service")["resolved_dependencies"]]
    arith = sum(depths) / len(depths)
    if len(set(depths)) > 1:
        assert not math.isclose(m["avg_depth"], arith, abs_tol=0.01)


def test_api_metrics():
    """Verify api_service metrics values."""
    m = _proj("api_service")["metrics"]
    assert m["direct_count"] == 5
    assert m["transitive_count"] == 2
    assert m["max_depth"] == 2


# ─── auth_lib resolution (TRAP: ~> 2.7.0 three-segment form) ─────────────


def test_auth_resolved_count():
    """auth_lib resolves 4 runtime gems."""
    assert _proj("auth_lib")["metrics"]["total_resolved"] == 4


def test_auth_jwt_version():
    """auth_lib resolves jwt 2.7.0 — ~> 2.7.0 means >= 2.7.0, < 2.8.0."""
    assert _resolved("auth_lib", "jwt")["version"] == "2.7.0"


def test_auth_jwt_not_280():
    """jwt 2.8.0 does NOT satisfy ~> 2.7.0 (upper bound is < 2.8.0)."""
    assert _resolved("auth_lib", "jwt")["version"] != "2.8.0"


def test_auth_rack_version():
    """auth_lib resolves rack 3.1.0 — ~> 3.0 means >= 3.0.0, < 4.0.0."""
    assert _resolved("auth_lib", "rack")["version"] == "3.1.0"


def test_auth_bcrypt_version():
    """auth_lib resolves bcrypt 3.1.20 — ~> 3.1 means >= 3.1.0, < 4.0.0."""
    assert _resolved("auth_lib", "bcrypt")["version"] == "3.1.20"


def test_auth_avg_depth():
    """auth_lib has all direct deps, avg_depth = 1.0."""
    assert _proj("auth_lib")["metrics"]["avg_depth"] == 1.0


def test_auth_no_findings():
    """auth_lib (BSD-2-Clause) has no findings."""
    assert len(_proj("auth_lib")["findings"]) == 0


# ─── web_app resolution (TRAP: prerelease exclusion, ~> two-segment) ─────


def test_web_resolved_count():
    """web_app resolves 11 runtime gems."""
    assert _proj("web_app")["metrics"]["total_resolved"] == 11


def test_web_sidekiq_version():
    """web_app resolves sidekiq 7.2.0 — ~> 7.0 means >= 7.0.0, < 8.0.0."""
    assert _resolved("web_app", "sidekiq")["version"] == "7.2.0"


def test_web_graphql_version():
    """web_app resolves graphql 2.2.0 (stable), not 2.2.0.alpha."""
    assert _resolved("web_app", "graphql")["version"] == "2.2.0"


def test_web_graphql_excludes_prerelease():
    """Pre-release 2.2.0.alpha is excluded even though it satisfies >= 2.1.0."""
    assert _resolved("web_app", "graphql")["version"] != "2.2.0.alpha"


def test_web_activerecord_version():
    """web_app resolves activerecord 7.1.0 — ~> 7.0 means >= 7.0.0, < 8.0.0."""
    assert _resolved("web_app", "activerecord")["version"] == "7.1.0"


def test_web_activesupport_version():
    """activesupport resolves to 7.1.0 via activerecord ~> 7.0."""
    assert _resolved("web_app", "activesupport")["version"] == "7.1.0"


def test_web_devise_version():
    """web_app resolves devise 4.9.3 — ~> 4.9.0 means >= 4.9.0, < 4.10.0."""
    assert _resolved("web_app", "devise")["version"] == "4.9.3"


def test_web_rack_version():
    """web_app resolves rack 2.2.3 — direct ~> 2.2.0 means >= 2.2.0, < 2.3.0."""
    assert _resolved("web_app", "rack")["version"] == "2.2.3"


def test_web_bcrypt_transitive():
    """bcrypt is transitive via devise at depth 2."""
    rd = _resolved("web_app", "bcrypt")
    assert rd["depth"] == 2
    assert rd["constraint_sources"] == ["devise"]


def test_web_warden_transitive():
    """warden is transitive via devise at depth 2."""
    rd = _resolved("web_app", "warden")
    assert rd["depth"] == 2
    assert rd["constraint_sources"] == ["devise"]


def test_web_redis_transitive():
    """redis is transitive via sidekiq at depth 2."""
    rd = _resolved("web_app", "redis")
    assert rd["depth"] == 2


def test_web_copyleft_finding():
    """sidekiq (LGPL-3.0) in MIT project triggers copyleft_in_permissive."""
    findings = _proj("web_app")["findings"]
    copyleft = [f for f in findings if f["finding_type"] == "copyleft_in_permissive"]
    assert len(copyleft) == 1
    assert copyleft[0]["gem_name"] == "sidekiq"


def test_web_metrics():
    """Verify web_app metrics."""
    m = _proj("web_app")["metrics"]
    assert m["direct_count"] == 6
    assert m["transitive_count"] == 5
    assert m["max_depth"] == 3


def test_web_avg_depth_harmonic():
    """web_app avg_depth uses harmonic mean."""
    m = _proj("web_app")["metrics"]
    assert math.isclose(m["avg_depth"], 1.32, abs_tol=TOL)


# ─── worker resolution (TRAP: vulnerability detection) ────────────────────


def test_worker_resolved_count():
    """worker resolves 8 runtime gems."""
    assert _proj("worker")["metrics"]["total_resolved"] == 8


def test_worker_sidekiq_version():
    """worker resolves sidekiq 6.0.0 — ~> 6.0.0 means >= 6.0.0, < 6.1.0."""
    assert _resolved("worker", "sidekiq")["version"] == "6.0.0"


def test_worker_redis_version():
    """worker resolves redis 4.8.0 via sidekiq ~> 4.0."""
    assert _resolved("worker", "redis")["version"] == "4.8.0"


def test_worker_geocoder_version():
    """worker resolves geocoder 1.8.2, excluding pre-release 1.8.3.pre.beta."""
    assert _resolved("worker", "geocoder")["version"] == "1.8.2"


def test_worker_geocoder_no_prerelease():
    """Pre-release 1.8.3.pre.beta is excluded from geocoder resolution."""
    assert _resolved("worker", "geocoder")["version"] != "1.8.3.pre.beta"


def test_worker_activerecord_version():
    """worker resolves activerecord 6.1.0 — ~> 6.1.0 means >= 6.1.0, < 6.2.0."""
    assert _resolved("worker", "activerecord")["version"] == "6.1.0"


def test_worker_activesupport_version():
    """activesupport resolves to 6.1.7 (highest matching ~> 6.1.0)."""
    assert _resolved("worker", "activesupport")["version"] == "6.1.7"


def test_worker_redis_vulnerability():
    """redis 4.8.0 is affected by CVE-2024-1003 (< 5.0.0)."""
    findings = _proj("worker")["findings"]
    vuln = [f for f in findings if f["finding_type"] == "vulnerability"]
    assert len(vuln) == 1
    assert vuln[0]["gem_name"] == "redis"
    assert vuln[0]["version"] == "4.8.0"


def test_worker_vulnerability_risk_score():
    """Vulnerability risk score for redis at depth 2."""
    findings = _proj("worker")["findings"]
    vuln = next(f for f in findings if f["finding_type"] == "vulnerability")
    expected = round(7.5 * (0.85 ** 2), 6)
    assert math.isclose(vuln["risk_score"], expected, abs_tol=EXACT_TOL)


def test_worker_copyleft_finding():
    """sidekiq (LGPL-3.0) in MIT project triggers copyleft_in_permissive."""
    findings = _proj("worker")["findings"]
    copyleft = [f for f in findings if f["finding_type"] == "copyleft_in_permissive"]
    assert len(copyleft) == 1
    assert copyleft[0]["gem_name"] == "sidekiq"


def test_worker_copyleft_risk_score():
    """Copyleft risk for sidekiq at depth 1."""
    findings = _proj("worker")["findings"]
    cop = next(f for f in findings if f["finding_type"] == "copyleft_in_permissive")
    expected = round(5.0 * (0.85 ** 1), 6)
    assert math.isclose(cop["risk_score"], expected, abs_tol=EXACT_TOL)


def test_worker_finding_count():
    """worker has exactly 2 findings (vulnerability + copyleft)."""
    assert len(_proj("worker")["findings"]) == 2


def test_worker_metrics():
    """Verify worker metrics."""
    m = _proj("worker")["metrics"]
    assert m["direct_count"] == 4
    assert m["transitive_count"] == 4
    assert m["max_depth"] == 2
    assert m["vulnerability_count"] == 1


def test_worker_avg_depth_harmonic():
    """worker avg_depth uses harmonic mean."""
    m = _proj("worker")["metrics"]
    assert math.isclose(m["avg_depth"], 1.333333, abs_tol=EXACT_TOL)


# ─── Global findings ──────────────────────────────────────────────────────


def test_global_findings_count():
    """Verify total global findings."""
    assert len(R["findings"]) == 3


def test_global_findings_sort_severity_first():
    """Global findings sorted by severity rank ASC first."""
    ranks = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
    sev_ranks = [ranks[f["severity"]] for f in R["findings"]]
    assert sev_ranks == sorted(sev_ranks)


def test_global_findings_risk_desc_within_severity():
    """Within same severity, findings sorted by risk_score DESC."""
    by_sev = {}
    for f in R["findings"]:
        by_sev.setdefault(f["severity"], []).append(f["risk_score"])
    for sev, scores in by_sev.items():
        assert scores == sorted(scores, reverse=True), (
            f"Risk scores not DESC within {sev}: {scores}"
        )


def test_global_finding_has_project_id():
    """Every global finding has a project_id field."""
    for f in R["findings"]:
        assert "project_id" in f


def test_total_findings_matches_per_project():
    """Sum of per-project findings equals global total."""
    per_proj = sum(len(a["findings"]) for a in R["project_audits"])
    assert per_proj == len(R["findings"])


# ─── Source hashes ────────────────────────────────────────────────────────


def test_source_hashes_present():
    """Source hashes object must be present and non-empty."""
    assert len(R["source_hashes"]) > 0


def test_source_hashes_count():
    """Verify correct number of source hash entries."""
    assert len(R["source_hashes"]) == 24


def test_source_hashes_sorted():
    """Source hash keys must be sorted alphabetically."""
    keys = list(R["source_hashes"].keys())
    assert keys == sorted(keys)


def test_source_hash_rack():
    """Verify SHA-256 hash of rack.json registry file."""
    p = ROOT / "data" / "registry" / "rack.json"
    raw = p.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert R["source_hashes"]["data/registry/rack.json"] == expected


def test_source_hash_policy():
    """Verify SHA-256 hash of policy.json."""
    p = ROOT / "data" / "config" / "policy.json"
    raw = p.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert R["source_hashes"]["data/config/policy.json"] == expected


# ─── Resolved dependencies sorting ───────────────────────────────────────


def test_resolved_sorted_by_gem_name():
    """Resolved dependencies in each project sorted by gem_name."""
    for a in R["project_audits"]:
        names = [d["gem_name"] for d in a["resolved_dependencies"]]
        assert names == sorted(names), (
            f"Not sorted in {a['project_id']}: {names}"
        )


# ─── Path and depth consistency ──────────────────────────────────────────


def test_depth_equals_path_length_minus_one():
    """Depth must equal len(path) - 1 for all resolved deps."""
    for a in R["project_audits"]:
        for d in a["resolved_dependencies"]:
            assert d["depth"] == len(d["path"]) - 1, (
                f"{a['project_id']}/{d['gem_name']}: depth={d['depth']} "
                f"but path has {len(d['path'])} elements"
            )


def test_paths_start_with_project():
    """Every resolved dependency path starts with the project_id."""
    for a in R["project_audits"]:
        for d in a["resolved_dependencies"]:
            assert d["path"][0] == a["project_id"]


# ─── Risk score formula ──────────────────────────────────────────────────


def test_risk_score_formula():
    """Verify risk_score = severity_multiplier * depth_decay ^ depth."""
    mults = {"critical": 10.0, "high": 7.5, "medium": 5.0, "low": 2.5, "info": 1.0}
    base = 0.85
    for f in R["findings"]:
        sev = f["severity"]
        gem = f["gem_name"]
        pid = f["project_id"]
        audit = _proj(pid)
        deps = {d["gem_name"]: d for d in audit["resolved_dependencies"]}
        if gem in deps:
            depth = deps[gem]["depth"]
            expected = round(mults[sev] * (base ** depth), 6)
            assert math.isclose(f["risk_score"], expected, abs_tol=EXACT_TOL), (
                f"{pid}/{gem}: risk={f['risk_score']}, expected={expected}"
            )


# ─── JSON formatting ─────────────────────────────────────────────────────


def test_json_sorted_keys():
    """Verify top-level keys are sorted alphabetically."""
    text = (OUT_DIR / "gem_audit.json").read_text(encoding="utf-8")
    data = json.loads(text)
    keys = list(data.keys())
    assert keys == sorted(keys)
