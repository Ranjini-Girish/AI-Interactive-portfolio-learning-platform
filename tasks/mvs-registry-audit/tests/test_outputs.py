"""Tests for Go Dependency Graph Audit."""
import json
import math
import pathlib
import hashlib

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

EXACT_TOL = 1e-6


def load_report():
    p = OUT_DIR / "dep_audit.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


def _pkg(name):
    return next(p for p in R["resolved_packages"] if p["package"] == name)


# ─── File structure ───────────────────────────────────────────────────────


def test_output_file_exists():
    assert (OUT_DIR / "dep_audit.json").is_file()


def test_valid_json():
    text = (OUT_DIR / "dep_audit.json").read_text(encoding="utf-8")
    data = json.loads(text)
    assert isinstance(data, dict)


def test_trailing_newline():
    text = (OUT_DIR / "dep_audit.json").read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_two_space_indent():
    """JSON must use 2-space indentation."""
    text = (OUT_DIR / "dep_audit.json").read_text(encoding="utf-8")
    assert "\t" not in text, "Output should not contain tabs"
    assert '\n  "' in text, "Output should use 2-space indentation"


def test_top_level_keys():
    required = {
        "build_order", "cycles", "metadata", "resolved_packages",
        "root_modules", "schema_version", "source_checksum",
        "summary", "vulnerabilities",
    }
    assert set(R.keys()) == required


def test_schema_version():
    assert R["schema_version"] == 1


def test_sorted_keys_all_levels():
    """All JSON objects at every nesting level must have sorted keys."""
    violations = []

    def _check(obj, path="root"):
        if isinstance(obj, dict):
            keys = list(obj.keys())
            if keys != sorted(keys):
                violations.append(f"{path}: {keys}")
            for k, v in obj.items():
                _check(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _check(v, f"{path}[{i}]")

    _check(R)
    assert violations == [], "Unsorted keys found:\n" + "\n".join(violations)


# ─── Source checksum ──────────────────────────────────────────────────────


def test_source_checksum():
    """SHA-256 of registry.json with normalized line endings."""
    p = ROOT / "data" / "registry.json"
    raw = p.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert R["source_checksum"] == expected


# ─── Metadata ─────────────────────────────────────────────────────────────


def test_metadata_strategy():
    assert R["metadata"]["resolution_strategy"] == "mvs"


def test_metadata_prerelease():
    assert R["metadata"]["prerelease_policy"] == "exclude"


def test_metadata_registry_packages():
    assert R["metadata"]["total_registry_packages"] == 17


def test_metadata_registry_versions():
    assert R["metadata"]["total_registry_versions"] == 32


# ─── MVS Resolution (TRAP: minimum version, not maximum) ─────────────────


def test_resolved_count():
    assert len(R["resolved_packages"]) == 12


def test_resolved_sorted():
    names = [p["package"] for p in R["resolved_packages"]]
    assert names == sorted(names)


def test_mvs_logger_version():
    """MVS picks minimum satisfying version: cli-tool needs >=2.1.0, so 2.1.0."""
    assert _pkg("logger")["version"] == "2.1.0"


def test_mvs_config_loader_version():
    """cli-tool needs >=1.1.0, web-server needs >=1.0.0 → max(1.1.0, 1.0.0) = 1.1.0."""
    assert _pkg("config-loader")["version"] == "1.1.0"


def test_mvs_http_router_version():
    """web-server needs >=1.2.0 → minimum is 1.2.0 (NOT 1.3.0 or beta)."""
    assert _pkg("http-router")["version"] == "1.2.0"


def test_mvs_auth_middleware_version():
    """web-server needs >=0.9.0 → minimum is 0.9.0."""
    assert _pkg("auth-middleware")["version"] == "0.9.0"


def test_mvs_crypto_utils_version():
    """auth-middleware 0.9.0 needs >=1.0.0 → 1.0.0."""
    assert _pkg("crypto-utils")["version"] == "1.0.0"


def test_mvs_validator_version():
    """config-loader 1.1.0 needs >=0.5.0 → 0.5.0."""
    assert _pkg("validator")["version"] == "0.5.0"


def test_mvs_format_utils_version():
    """Multiple packages need >=1.0.0 → 1.0.0 (not 1.1.0)."""
    assert _pkg("format-utils")["version"] == "1.0.0"


# ─── Pre-release exclusion (TRAP: beta/rc must be excluded) ──────────────


def test_prerelease_excluded_http_router():
    """1.4.0-beta.1 must NOT be selected even though it exists."""
    assert _pkg("http-router")["version"] == "1.2.0"


def test_prerelease_excluded_logger():
    """2.3.0-rc.1 must NOT be selected."""
    assert _pkg("logger")["version"] == "2.1.0"


# ─── Depths ───────────────────────────────────────────────────────────────


def test_depth_direct_dependencies():
    """Direct dependencies of roots have depth 1."""
    assert _pkg("logger")["depth"] == 1
    assert _pkg("config-loader")["depth"] == 1
    assert _pkg("http-router")["depth"] == 1
    assert _pkg("auth-middleware")["depth"] == 1
    assert _pkg("task-runner")["depth"] == 1


def test_depth_transitive():
    """Transitive dependencies have depth > 1."""
    assert _pkg("crypto-utils")["depth"] == 2
    assert _pkg("format-utils")["depth"] == 2
    assert _pkg("middleware-chain")["depth"] == 2
    assert _pkg("session-store")["depth"] == 2
    assert _pkg("validator")["depth"] == 2
    assert _pkg("event-bus")["depth"] == 2
    assert _pkg("cache-driver")["depth"] == 3


# ─── Coupling metrics (TRAP: instability I=0 when denom=0) ───────────────


def test_fan_in_logger():
    """logger is imported by 8 packages (6 resolved + 2 roots)."""
    assert _pkg("logger")["fan_in"] == 8


def test_fan_out_logger():
    """logger 2.1.0 depends on format-utils only."""
    assert _pkg("logger")["fan_out"] == 1


def test_instability_logger():
    """I = 1 / (8 + 1) = 0.111111."""
    assert math.isclose(_pkg("logger")["instability"], 0.111111, abs_tol=EXACT_TOL)


def test_fan_in_crypto_utils():
    assert _pkg("crypto-utils")["fan_in"] == 1


def test_fan_out_crypto_utils():
    """crypto-utils has no dependencies."""
    assert _pkg("crypto-utils")["fan_out"] == 0


def test_instability_crypto_utils():
    """Ca=1, Ce=0 → I = 0.0."""
    assert _pkg("crypto-utils")["instability"] == 0


def test_instability_auth_middleware():
    """Ca=1, Ce=3 → I = 3/(1+3) = 0.75."""
    assert _pkg("auth-middleware")["instability"] == 0.75


def test_instability_http_router():
    """Ca=1, Ce=2 → I = 2/(1+2) = 0.666667."""
    assert math.isclose(
        _pkg("http-router")["instability"], 0.666667, abs_tol=EXACT_TOL
    )


# ─── Required-by arrays ──────────────────────────────────────────────────


def test_required_by_logger_sorted():
    rb = _pkg("logger")["required_by"]
    assert rb == sorted(rb)
    assert len(rb) == 8


def test_required_by_format_utils():
    rb = _pkg("format-utils")["required_by"]
    assert set(rb) == {"config-loader", "logger", "validator"}


# ─── Build order (TRAP: topological, deps before dependents) ──────────────


def test_build_order_count():
    assert len(R["build_order"]) == 12


def test_build_order_is_topological():
    """Every dependency must appear before its dependents."""
    reg = json.loads((ROOT / "data" / "registry.json").read_text(encoding="utf-8"))
    resolved_names = {p["package"] for p in R["resolved_packages"]}

    pos = {name: i for i, name in enumerate(R["build_order"])}
    for p in R["resolved_packages"]:
        pkg = p["package"]
        ver = p["version"]
        pe = reg["packages"].get(pkg, {})
        ve = pe.get("versions", {}).get(ver, {})
        for dep in ve.get("dependencies", {}):
            if dep in resolved_names:
                assert pos[dep] < pos[pkg], (
                    f"{dep} (pos {pos[dep]}) must come before "
                    f"{pkg} (pos {pos[pkg]}) in build order"
                )


def test_build_order_leaf_nodes_first():
    """Packages with no resolved deps should appear early."""
    pos = {name: i for i, name in enumerate(R["build_order"])}
    assert pos["crypto-utils"] < pos["auth-middleware"]
    assert pos["format-utils"] < pos["logger"]


# ─── Cycles ───────────────────────────────────────────────────────────────


def test_no_cycles():
    """This registry has no circular dependencies."""
    assert R["cycles"] == []


# ─── Root modules ────────────────────────────────────────────────────────


def test_root_modules_count():
    assert len(R["root_modules"]) == 2


def test_root_modules_sorted():
    names = [m["module_name"] for m in R["root_modules"]]
    assert names == sorted(names)


def test_root_cli_tool():
    mod = next(m for m in R["root_modules"] if m["module_name"] == "cli-tool")
    assert mod["version"] == "2.1.0"
    assert sorted(mod["dependencies"]) == [
        "config-loader", "logger", "task-runner"
    ]


def test_root_web_server():
    mod = next(m for m in R["root_modules"] if m["module_name"] == "web-server")
    assert mod["version"] == "1.4.0"
    assert sorted(mod["dependencies"]) == [
        "auth-middleware", "config-loader", "http-router", "logger"
    ]


# ─── Vulnerability analysis ──────────────────────────────────────────────


def test_vulnerabilities_count():
    """4 advisories match resolved packages (ADV-004 does NOT match)."""
    assert len(R["vulnerabilities"]) == 4


def test_vulnerability_sorted_by_id():
    ids = [v["advisory_id"] for v in R["vulnerabilities"]]
    assert ids == sorted(ids)


def test_adv_001_crypto_utils():
    """ADV-2024-001: crypto-utils 1.0.0 <= 1.0.0 → matched, critical."""
    v = next(x for x in R["vulnerabilities"] if x["advisory_id"] == "ADV-2024-001")
    assert v["affected_package"] == "crypto-utils"
    assert v["severity"] == "critical"


def test_adv_001_propagation():
    """crypto-utils vuln propagates to auth-middleware at 1 hop."""
    v = next(x for x in R["vulnerabilities"] if x["advisory_id"] == "ADV-2024-001")
    props = {p["package"]: p["score"] for p in v["propagated_to"]}
    assert math.isclose(props["auth-middleware"], 8.5, abs_tol=EXACT_TOL)


def test_adv_004_not_matched():
    """ADV-2024-004: logger <=2.0.0 but resolved 2.1.0 → NOT matched."""
    ids = [v["advisory_id"] for v in R["vulnerabilities"]]
    assert "ADV-2024-004" not in ids


def test_adv_003_propagation_count():
    """format-utils vuln propagates to 10 packages."""
    v = next(x for x in R["vulnerabilities"] if x["advisory_id"] == "ADV-2024-003")
    assert len(v["propagated_to"]) == 10


def test_vuln_score_crypto_utils():
    """Direct critical vuln: max_vuln_score = 10.0."""
    assert _pkg("crypto-utils")["max_vuln_score"] == 10


def test_vuln_score_session_store():
    """session-store has direct high (7.5) and propagated medium."""
    assert math.isclose(
        _pkg("session-store")["max_vuln_score"], 7.5, abs_tol=EXACT_TOL
    )


def test_vuln_propagation_decay():
    """auth-middleware: hop=1 from crypto-utils → 10.0 * 0.85^1 = 8.5."""
    assert math.isclose(
        _pkg("auth-middleware")["max_vuln_score"], 8.5, abs_tol=EXACT_TOL
    )


# ─── Summary ─────────────────────────────────────────────────────────────


def test_summary_total_packages():
    assert R["summary"]["total_packages"] == 12


def test_summary_total_direct():
    assert R["summary"]["total_direct"] == 5


def test_summary_total_transitive():
    assert R["summary"]["total_transitive"] == 7


def test_summary_max_depth():
    assert R["summary"]["max_depth"] == 3


def test_summary_critical_vulns():
    assert R["summary"]["critical_vulns"] == 1


def test_summary_avg_instability():
    assert math.isclose(
        R["summary"]["avg_instability"], 0.43287, abs_tol=EXACT_TOL
    )


def test_summary_vulnerability_score():
    """Geometric mean of all max_vuln_score values."""
    assert math.isclose(
        R["summary"]["vulnerability_score"], 4.934406, abs_tol=EXACT_TOL
    )


def test_summary_vulnerability_score_is_geometric():
    """Verify it's geometric mean, not arithmetic."""
    scores = [
        p["max_vuln_score"]
        for p in R["resolved_packages"]
        if p["max_vuln_score"] > 0
    ]
    if len(scores) > 1:
        arith = sum(scores) / len(scores)
        assert not math.isclose(
            R["summary"]["vulnerability_score"], arith, abs_tol=0.01
        )


# ─── Go language enforcement ─────────────────────────────────────────────


def test_go_binary_exists():
    """Verify the compiled Go binary exists."""
    binary = ROOT / "depaudit"
    assert binary.is_file(), (
        "Go binary not found at /app/depaudit. "
        "The solution must be built with go build."
    )


def test_go_binary_is_native_elf():
    """Verify the Go binary is a real ELF executable."""
    binary = ROOT / "depaudit"
    if not binary.is_file():
        return
    with open(binary, "rb") as f:
        magic = f.read(4)
    assert magic == b'\x7fELF', (
        f"Binary is not an ELF executable (magic: {magic!r}). "
        "Solution must be compiled from Go."
    )


def test_go_binary_produces_report():
    """Delete report and re-run binary to verify it generates output."""
    import subprocess
    binary = ROOT / "depaudit"
    if not binary.is_file():
        return
    report = OUT_DIR / "dep_audit.json"
    if report.exists():
        report.unlink()
    result = subprocess.run(
        [str(binary)],
        cwd=str(ROOT),
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"Binary exited with code {result.returncode}:\n"
        f"stderr: {result.stderr.decode(errors='replace')}"
    )
    assert report.exists(), "Binary did not produce /app/output/dep_audit.json"
    data = json.loads(report.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and "resolved_packages" in data
