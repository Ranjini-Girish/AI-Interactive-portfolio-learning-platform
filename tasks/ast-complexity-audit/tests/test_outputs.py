"""Tests for JavaScript AST Complexity Audit."""
import json
import math
import pathlib
import hashlib

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

TOL = 1e-4
EXACT_TOL = 1e-6


def load_report():
    p = OUT_DIR / "complexity_audit.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


def _mod(name):
    return next(a for a in R["module_audits"] if a["module_name"] == name)


def _func(mod_name, func_name):
    audit = _mod(mod_name)
    return next(f for f in audit["functions"] if f["function_name"] == func_name)


# ─── File structure ───────────────────────────────────────────────────────


def test_output_file_exists():
    assert (OUT_DIR / "complexity_audit.json").is_file()


def test_valid_json():
    text = (OUT_DIR / "complexity_audit.json").read_text(encoding="utf-8")
    data = json.loads(text)
    assert isinstance(data, dict)


def test_trailing_newline():
    text = (OUT_DIR / "complexity_audit.json").read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_top_level_keys():
    required = {"findings", "module_audits", "schema_version", "source_hashes", "summary"}
    assert set(R.keys()) == required


def test_schema_version():
    assert R["schema_version"] == 1


def test_sorted_keys_top_level():
    keys = list(R.keys())
    assert keys == sorted(keys)


# ─── Summary tests ───────────────────────────────────────────────────────


def test_summary_total_modules():
    assert R["summary"]["total_modules"] == 8


def test_summary_total_functions():
    assert R["summary"]["total_functions"] == 19


def test_summary_total_findings():
    assert R["summary"]["total_findings"] == 16


def test_summary_findings_by_severity_all_present():
    fbs = R["summary"]["findings_by_severity"]
    assert set(fbs.keys()) == {"critical", "high", "medium", "low", "info"}


def test_summary_findings_by_severity_values():
    fbs = R["summary"]["findings_by_severity"]
    assert fbs["critical"] == 0
    assert fbs["high"] == 0
    assert fbs["medium"] == 16
    assert fbs["low"] == 0
    assert fbs["info"] == 0


def test_summary_avg_cyclomatic_harmonic():
    """avg_cyclomatic must be harmonic mean, not arithmetic."""
    assert math.isclose(R["summary"]["avg_cyclomatic"], 4.563939, abs_tol=EXACT_TOL)


def test_summary_avg_cognitive_harmonic():
    """avg_cognitive must be harmonic mean with zeros excluded."""
    assert math.isclose(R["summary"]["avg_cognitive"], 3.748932, abs_tol=EXACT_TOL)


def test_summary_avg_maintainability():
    assert math.isclose(R["summary"]["avg_maintainability"], 56.181627, abs_tol=EXACT_TOL)


def test_summary_aggregate_risk_geometric():
    """aggregate_risk_score must be geometric mean, not arithmetic."""
    assert math.isclose(R["summary"]["aggregate_risk_score"], 0.021798, abs_tol=EXACT_TOL)


def test_summary_aggregate_risk_not_arithmetic():
    scores = [f["risk_score"] for f in R["findings"] if f["risk_score"] > 0]
    if len(scores) > 1:
        arith = sum(scores) / len(scores)
        assert not math.isclose(R["summary"]["aggregate_risk_score"], arith, abs_tol=0.01)


# ─── Module audit structure ──────────────────────────────────────────────


def test_module_audit_count():
    assert len(R["module_audits"]) == 8


def test_module_audits_sorted():
    names = [a["module_name"] for a in R["module_audits"]]
    assert names == sorted(names)


def test_audit_keys():
    required = {"coupling", "findings", "functions", "halstead",
                "maintainability_index", "module_name", "path", "summary"}
    for a in R["module_audits"]:
        assert set(a.keys()) == required, f"Wrong keys in {a['module_name']}"


# ─── Cyclomatic complexity (TRAP: switch vs case counting) ───────────────


def test_cc_authenticate():
    """if + && + try(if + ternary + catch(if + ||)) → CC = 1+6 = 7"""
    assert _func("auth_handler", "authenticate")["cyclomatic_complexity"] == 7


def test_cc_authorize():
    """if + for + if + &&x2 + else_if = CC 7"""
    assert _func("auth_handler", "authorize")["cyclomatic_complexity"] == 7


def test_cc_logout():
    """try + if + catch(no node) → CC = 1+1 = 2"""
    assert _func("auth_handler", "logout")["cyclomatic_complexity"] == 2


def test_cc_processRecords():
    """TRAP: switch NOT counted, but each case IS → CC = 12"""
    assert _func("data_processor", "processRecords")["cyclomatic_complexity"] == 12


def test_cc_validateSchema():
    """Multiple logical operators each counted individually → CC = 11"""
    assert _func("validator", "validateSchema")["cyclomatic_complexity"] == 11


def test_cc_matchRoute():
    """Nested switch+cases+logical → CC = 13"""
    assert _func("router", "matchRoute")["cyclomatic_complexity"] == 13


def test_cc_withRetry():
    """Nested try/catch with else_if chain → CC = 6"""
    assert _func("http_client", "withRetry")["cyclomatic_complexity"] == 6


# ─── Cognitive complexity (TRAP: nesting, else_if, logical sequences) ────


def test_cogc_authenticate():
    """Nesting bonus on if, catch + logical operators → CogC = 10"""
    assert _func("auth_handler", "authenticate")["cognitive_complexity"] == 10


def test_cogc_processRecords():
    """TRAP: switch counts for cognitive (+1+nesting), case does NOT → CogC = 18"""
    assert _func("data_processor", "processRecords")["cognitive_complexity"] == 18


def test_cogc_matchRoute():
    """Deeply nested with logical operator sequences → CogC = 22"""
    assert _func("router", "matchRoute")["cognitive_complexity"] == 22


def test_cogc_validateSchema():
    """TRAP: else_if gets +1 but NO nesting bonus; else gets +1 → CogC = 15"""
    assert _func("validator", "validateSchema")["cognitive_complexity"] == 15


def test_cogc_authorize():
    """else_if adds +1 with no nesting increase → CogC = 8"""
    assert _func("auth_handler", "authorize")["cognitive_complexity"] == 8


def test_cogc_createLogger():
    """TRAP: switch adds +1 cognitive, cases add 0 → CogC = 3"""
    assert _func("logger", "createLogger")["cognitive_complexity"] == 3


def test_cogc_emit():
    """Nested if-else inside catch inside for inside if → CogC = 7"""
    assert _func("event_emitter", "emit")["cognitive_complexity"] == 7


def test_cogc_logout():
    """Simple try(if), no nesting from try → CogC = 1"""
    assert _func("auth_handler", "logout")["cognitive_complexity"] == 1


# ─── Halstead metrics (TRAP: log₂ not ln, n2=0 edge case) ───────────────


def test_halstead_volume_uses_log2():
    """Volume = N * log2(eta), NOT natural log."""
    h = _func("auth_handler", "authenticate")["halstead"]
    assert h["vocabulary"] == 20
    assert h["length"] == 20
    expected_vol = 20 * math.log2(20)
    assert math.isclose(h["volume"], expected_vol, abs_tol=EXACT_TOL)


def test_halstead_difficulty():
    h = _func("auth_handler", "authenticate")["halstead"]
    assert math.isclose(h["difficulty"], 5.0, abs_tol=EXACT_TOL)


def test_halstead_effort():
    h = _func("auth_handler", "authenticate")["halstead"]
    expected = h["difficulty"] * h["volume"]
    assert math.isclose(h["effort"], expected, abs_tol=EXACT_TOL)


def test_halstead_bugs():
    h = _func("auth_handler", "authenticate")["halstead"]
    expected = h["volume"] / 3000
    assert math.isclose(h["bugs"], expected, abs_tol=EXACT_TOL)


def test_halstead_time():
    h = _func("auth_handler", "authenticate")["halstead"]
    expected = h["effort"] / 18
    assert math.isclose(h["time"], expected, abs_tol=EXACT_TOL)


# ─── Maintainability Index (TRAP: natural log, max(0,...), 100/171) ──────


def test_mi_authenticate():
    """MI = max(0, (171 - 5.2*ln(V) - 0.23*CC - 16.2*ln(LOC)) * 100/171)"""
    assert math.isclose(
        _func("auth_handler", "authenticate")["maintainability_index"],
        51.036285, abs_tol=EXACT_TOL
    )


def test_mi_processRecords():
    assert math.isclose(
        _func("data_processor", "processRecords")["maintainability_index"],
        45.657983, abs_tol=EXACT_TOL
    )


def test_mi_uses_natural_log():
    """Verify MI uses ln (base e), not log2 or log10."""
    f = _func("auth_handler", "authenticate")
    V = f["halstead"]["volume"]
    cc = f["cyclomatic_complexity"]
    loc = f["lines"]
    expected = max(0, (171 - 5.2 * math.log(V) - 0.23 * cc - 16.2 * math.log(loc)) * 100 / 171)
    assert math.isclose(f["maintainability_index"], round(expected, 6), abs_tol=EXACT_TOL)


def test_module_mi_auth():
    assert math.isclose(_mod("auth_handler")["maintainability_index"], 57.413368, abs_tol=EXACT_TOL)


def test_module_mi_data_processor():
    assert math.isclose(_mod("data_processor")["maintainability_index"], 49.399619, abs_tol=EXACT_TOL)


# ─── Coupling metrics (TRAP: internal only, instability 0 when denom=0) ──


def test_coupling_logger_afferent():
    """logger is imported by 6 other modules."""
    assert _mod("logger")["coupling"]["afferent"] == 6


def test_coupling_logger_efferent():
    """logger imports nothing."""
    assert _mod("logger")["coupling"]["efferent"] == 0


def test_coupling_logger_instability():
    """Ca=6, Ce=0 → I=0/(6+0)=0."""
    assert _mod("logger")["coupling"]["instability"] == 0


def test_coupling_data_processor_instability():
    """Ca=0, Ce=2 → I=2/(0+2)=1.0."""
    assert _mod("data_processor")["coupling"]["instability"] == 1


def test_coupling_cache_manager_instability():
    """Ca=1, Ce=2 → I=2/(1+2)=0.666667."""
    assert math.isclose(_mod("cache_manager")["coupling"]["instability"], 0.666667, abs_tol=EXACT_TOL)


def test_coupling_validator():
    """Ca=2, Ce=1 → I=1/(2+1)=0.333333."""
    assert math.isclose(_mod("validator")["coupling"]["instability"], 0.333333, abs_tol=EXACT_TOL)


def test_coupling_excludes_external():
    """External imports (no ./ prefix) don't count toward coupling."""
    ce = _mod("auth_handler")["coupling"]["efferent"]
    assert ce == 0  # all 3 imports: ./crypto_utils (not a module), ./user_store (not a module), jsonwebtoken (external)


def test_coupling_abstractness_null():
    for a in R["module_audits"]:
        assert a["coupling"]["abstractness"] is None


# ─── Findings ─────────────────────────────────────────────────────────────


def test_findings_count():
    assert len(R["findings"]) == 16


def test_findings_sorted_by_severity():
    ranks = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
    sev_ranks = [ranks[f["severity"]] for f in R["findings"]]
    assert sev_ranks == sorted(sev_ranks)


def test_findings_risk_desc_within_severity():
    by_sev = {}
    for f in R["findings"]:
        by_sev.setdefault(f["severity"], []).append(f["risk_score"])
    for sev, scores in by_sev.items():
        assert scores == sorted(scores, reverse=True), (
            f"Risk scores not DESC within {sev}: {scores}"
        )


def test_moderate_cyclomatic_findings():
    cc_findings = [f for f in R["findings"] if f["finding_type"] == "moderate_cyclomatic"]
    assert len(cc_findings) == 3
    names = [(f["module_name"], f["function_name"]) for f in cc_findings]
    assert ("data_processor", "processRecords") in names
    assert ("router", "matchRoute") in names
    assert ("validator", "validateSchema") in names


def test_moderate_cognitive_findings():
    cog_findings = [f for f in R["findings"] if f["finding_type"] == "moderate_cognitive"]
    assert len(cog_findings) == 2


def test_instability_findings():
    inst = [f for f in R["findings"] if f["finding_type"] == "high_instability"]
    assert len(inst) == 3
    modules = sorted([f["module_name"] for f in inst])
    assert modules == ["data_processor", "http_client", "router"]


def test_maintainability_findings():
    mi = [f for f in R["findings"] if f["finding_type"] == "moderate_maintainability"]
    assert len(mi) == 8


def test_finding_risk_formula():
    """risk = severity_multiplier * decay_base ^ metric_value"""
    f = next(f for f in R["findings"] if f["finding_type"] == "moderate_cyclomatic"
             and f["function_name"] == "processRecords")
    expected = round(5.0 * (0.9 ** 12), 6)
    assert math.isclose(f["risk_score"], expected, abs_tol=EXACT_TOL)


# ─── Source hashes ────────────────────────────────────────────────────────


def test_source_hashes_present():
    assert len(R["source_hashes"]) > 0


def test_source_hashes_count():
    assert len(R["source_hashes"]) == 8


def test_source_hashes_sorted():
    keys = list(R["source_hashes"].keys())
    assert keys == sorted(keys)


def test_source_hash_auth_handler():
    p = ROOT / "data" / "modules" / "auth_handler.json"
    raw = p.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert R["source_hashes"]["data/modules/auth_handler.json"] == expected


# ─── Module summary metrics ──────────────────────────────────────────────


def test_auth_module_summary():
    s = _mod("auth_handler")["summary"]
    assert s["total_functions"] == 3
    assert s["max_cyclomatic"] == 7
    assert s["max_cognitive"] == 10


def test_data_processor_module_summary():
    s = _mod("data_processor")["summary"]
    assert s["total_functions"] == 2
    assert s["max_cyclomatic"] == 12
    assert s["max_cognitive"] == 18


def test_router_max_cognitive():
    assert _mod("router")["summary"]["max_cognitive"] == 22


def test_module_avg_cyclomatic_harmonic():
    """Module avg_cyclomatic uses harmonic mean."""
    s = _mod("auth_handler")["summary"]
    ccs = [7, 7, 2]
    hm = len(ccs) / sum(1.0 / c for c in ccs)
    assert math.isclose(s["avg_cyclomatic"], round(hm, 6), abs_tol=EXACT_TOL)


# ─── Functions sorted ────────────────────────────────────────────────────


def test_functions_sorted_by_name():
    for a in R["module_audits"]:
        names = [f["function_name"] for f in a["functions"]]
        assert names == sorted(names), (
            f"Functions not sorted in {a['module_name']}: {names}"
        )


# ─── Function object keys ────────────────────────────────────────────────


def test_function_keys():
    required = {"cognitive_complexity", "cyclomatic_complexity", "function_name",
                "halstead", "lines", "maintainability_index", "parameters"}
    for a in R["module_audits"]:
        for f in a["functions"]:
            assert set(f.keys()) == required, (
                f"Wrong keys in {a['module_name']}/{f['function_name']}"
            )


# ─── Cross-checks ────────────────────────────────────────────────────────


def test_total_findings_matches_per_module():
    per_mod = sum(len(a["findings"]) for a in R["module_audits"])
    assert per_mod == len(R["findings"])


def test_total_functions_matches():
    total = sum(a["summary"]["total_functions"] for a in R["module_audits"])
    assert total == R["summary"]["total_functions"]


# ─── JavaScript language enforcement ─────────────────────────────────────


def test_js_solution_exists():
    """Verify the solution was implemented in JavaScript."""
    main_js = ROOT / "src" / "main.js"
    assert main_js.is_file(), "src/main.js not found — solution must be in JavaScript"
    content = main_js.read_text(encoding="utf-8")
    assert len(content) > 200, "src/main.js appears to be a stub — must contain implementation"


def test_no_python_solution():
    """Verify no Python files were created as the solution."""
    py_files = list(
        p for p in ROOT.rglob("*.py")
        if not any(part in ("data", "docs", "output", "node_modules") for part in p.parts)
    )
    assert py_files == [], (
        f"Python files found: {py_files} -- solution must be in JavaScript"
    )
