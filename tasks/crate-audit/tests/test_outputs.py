"""Tests for rust-crate-audit task."""
import json
import hashlib
import math
import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')
BUILD = ROOT / "build"

FLOAT_TOL = 5e-5
SCORE_TOL = 0.005


def load_report():
    p = OUT_DIR / "audit_report.json"
    assert p.is_file(), f"Missing: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = None


@pytest.fixture(scope="session", autouse=True)
def _load_report():
    global R
    R = load_report()


def _pkg(name):
    return next(p for p in R["resolution"]["resolved"] if p["name"] == name)


def _vuln(name):
    return next(
        v for v in R["audit"]["vulnerability_report"]["critical_packages"]
        if v["name"] == name
    )


# ── Binary verification ──────────────────────────────────────────────


def test_binary_exists():
    binary = BUILD / "crate-audit"
    assert binary.is_file(), "Compiled binary not found at /app/build/crate-audit"


def test_binary_is_elf():
    binary = BUILD / "crate-audit"
    if not binary.is_file():
        assert False, "Binary not found"
    with open(binary, "rb") as f:
        magic = f.read(4)
    assert magic == b'\x7fELF', (
        f"Binary is not a native ELF executable (magic={magic!r})"
    )


def test_binary_runs_and_produces_output():
    binary = BUILD / "crate-audit"
    if not binary.is_file():
        assert False, "Binary not found"
    assert os.access(str(binary), os.X_OK), "Binary is not executable"
    backup = None
    report_path = OUT_DIR / "audit_report.json"
    if report_path.exists():
        backup = report_path.read_bytes()
        report_path.unlink()
    try:
        result = subprocess.run(
            [str(binary)], capture_output=True, timeout=60, check=False
        )
        assert report_path.exists(), (
            f"Binary exited with code {result.returncode} but did not produce output"
        )
    finally:
        if backup is not None:
            report_path.write_bytes(backup)


# ── Output format ────────────────────────────────────────────────────


def test_output_file_exists():
    assert (OUT_DIR / "audit_report.json").is_file()


def test_json_trailing_newline():
    raw = (OUT_DIR / "audit_report.json").read_text(encoding="utf-8")
    assert raw.endswith("\n"), "JSON file must end with a trailing newline"


def test_json_two_space_indent():
    raw = (OUT_DIR / "audit_report.json").read_text(encoding="utf-8")
    lines = raw.rstrip("\n").split("\n")
    assert len(lines) > 1, "JSON appears to be minified (single line)"
    for i, line in enumerate(lines):
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        assert "\t" not in line, f"Line {i+1} uses tab indentation"
        if stripped and indent > 0:
            assert indent % 2 == 0, (
                f"Line {i+1}: indent {indent} is not a multiple of 2"
            )


def test_json_round_trip():
    raw = (OUT_DIR / "audit_report.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


def test_schema_version():
    assert R["schema_version"] == 1


def test_top_level_keys():
    assert set(R.keys()) == {"schema_version", "resolution", "build_order", "audit"}


def test_resolution_keys():
    assert set(R["resolution"].keys()) == {"total_packages", "resolved"}


def test_audit_keys():
    assert set(R["audit"].keys()) == {
        "vulnerability_report", "license_report", "statistics", "integrity_hash"
    }


def test_vuln_report_keys():
    assert set(R["audit"]["vulnerability_report"].keys()) == {
        "max_score", "critical_packages", "total_vulnerable"
    }


def test_license_report_keys():
    assert set(R["audit"]["license_report"].keys()) == {
        "conflicts", "total_conflicts"
    }


def test_statistics_keys():
    assert set(R["audit"]["statistics"].keys()) == {
        "total_packages", "max_depth", "avg_depth",
        "total_edges", "max_fan_out", "max_fan_in"
    }


# ── Resolution counts ────────────────────────────────────────────────


def test_total_packages():
    assert R["resolution"]["total_packages"] == 22


def test_resolved_array_length():
    assert len(R["resolution"]["resolved"]) == 22


# ── Package versions ─────────────────────────────────────────────────


def test_core_utils_version():
    assert _pkg("core-utils")["version"] == "1.2.0"


def test_http_client_version():
    assert _pkg("http-client")["version"] == "0.2.5"


def test_json_parser_version():
    assert _pkg("json-parser")["version"] == "1.0.0-rc.10"


def test_auth_service_version():
    assert _pkg("auth-service")["version"] == "2.1.1"


def test_web_framework_version():
    assert _pkg("web-framework")["version"] == "1.0.0"


def test_logger_version():
    assert _pkg("logger")["version"] == "1.2.0"


def test_cache_engine_version():
    assert _pkg("cache-engine")["version"] == "1.1.0"


def test_rate_limiter_version():
    assert _pkg("rate-limiter")["version"] == "0.0.3"


def test_crypto_lib_version():
    assert _pkg("crypto-lib")["version"] == "0.1.5"


def test_db_connector_version():
    assert _pkg("db-connector")["version"] == "3.2.0"


def test_template_engine_version():
    assert _pkg("template-engine")["version"] == "1.1.0"


def test_serializer_version():
    assert _pkg("serializer")["version"] == "2.2.0"


def test_validator_version():
    assert _pkg("validator")["version"] == "0.3.0"


def test_config_reader_version():
    assert _pkg("config-reader")["version"] == "0.5.1"


def test_event_bus_version():
    assert _pkg("event-bus")["version"] == "2.1.0"


def test_signal_handler_version():
    assert _pkg("signal-handler")["version"] == "0.3.1"


def test_tiny_alloc_version():
    assert _pkg("tiny-alloc")["version"] == "0.0.3"


def test_data_mapper_version():
    assert _pkg("data-mapper")["version"] == "0.2.1"


def test_proto_buf_version():
    assert _pkg("proto-buf")["version"] == "2.0.0-alpha.1"


def test_api_gateway_version():
    assert _pkg("api-gateway")["version"] == "1.0.0"


def test_network_stack_version():
    assert _pkg("network-stack")["version"] == "0.5.0"


def test_thread_pool_version():
    assert _pkg("thread-pool")["version"] == "1.1.0-beta.1"


# ── License and license_category in resolved ─────────────────────────


def test_resolved_has_license_field():
    for pkg in R["resolution"]["resolved"]:
        assert "license" in pkg, f"Missing 'license' field in {pkg['name']}"
        assert isinstance(pkg["license"], str)


def test_resolved_has_license_category_field():
    for pkg in R["resolution"]["resolved"]:
        assert "license_category" in pkg, (
            f"Missing 'license_category' field in {pkg['name']}"
        )
        assert pkg["license_category"] in (
            "permissive", "weak_copyleft", "strong_copyleft", "unknown"
        )


def test_crypto_lib_license():
    p = _pkg("crypto-lib")
    assert p["license"] == "GPL-3.0"
    assert p["license_category"] == "strong_copyleft"


def test_signal_handler_license():
    p = _pkg("signal-handler")
    assert p["license"] == "MPL-2.0"
    assert p["license_category"] == "weak_copyleft"


def test_logger_license():
    p = _pkg("logger")
    assert p["license"] == "MIT"
    assert p["license_category"] == "permissive"


def test_config_reader_license():
    p = _pkg("config-reader")
    assert p["license"] == "BSD-3-Clause"
    assert p["license_category"] == "permissive"


def test_validator_license():
    p = _pkg("validator")
    assert p["license"] == "BSD-2-Clause"
    assert p["license_category"] == "permissive"


def test_rate_limiter_license():
    p = _pkg("rate-limiter")
    assert p["license"] == "ISC"
    assert p["license_category"] == "permissive"


def test_api_gateway_license():
    p = _pkg("api-gateway")
    assert p["license"] == "Apache-2.0"
    assert p["license_category"] == "permissive"


def test_thread_pool_license():
    p = _pkg("thread-pool")
    assert p["license"] == "MIT"
    assert p["license_category"] == "permissive"


# ── Trap: ^0.0.x caret pins to exact patch ───────────────────────────


def test_caret_zero_zero_pins_patch():
    """^0.0.3 must resolve to >=0.0.3, <0.0.4 — only 0.0.3, NOT 0.0.4."""
    assert _pkg("tiny-alloc")["version"] == "0.0.3", (
        "^0.0.x caret must pin to exact patch: ^0.0.3 = [0.0.3, 0.0.4)"
    )


def test_caret_zero_zero_not_higher():
    """Verify tiny-alloc did NOT resolve to 0.0.4 (common ^0.0.x mistake)."""
    assert _pkg("tiny-alloc")["version"] != "0.0.4", (
        "Resolved 0.0.4 — ^0.0.3 must not allow 0.0.4"
    )


# ── Trap: yanked version filtering ───────────────────────────────────


def test_yanked_event_bus_excluded():
    """event-bus@2.2.0 is yanked; resolver must pick 2.1.0."""
    assert _pkg("event-bus")["version"] == "2.1.0", (
        "event-bus@2.2.0 is yanked and must be excluded from resolution"
    )


def test_yanked_logger_excluded():
    """logger@1.3.0 is yanked; resolver must still pick 1.2.0."""
    assert _pkg("logger")["version"] == "1.2.0", (
        "logger@1.3.0 is yanked and must be excluded from resolution"
    )


def test_yanked_api_gateway_excluded():
    """api-gateway@1.1.0 is yanked; resolver must pick 1.0.0."""
    assert _pkg("api-gateway")["version"] == "1.0.0", (
        "api-gateway@1.1.0 is yanked and must be excluded from resolution"
    )


# ── Trap: pre-release selected by caret constraint ────────────────────


def test_thread_pool_prerelease_selected():
    """thread-pool@1.1.0 is yanked. 1.1.0-beta.1 is the highest non-yanked
    version satisfying ^1.0.0. Models that filter pre-releases by convention
    will incorrectly select 1.0.0."""
    assert _pkg("thread-pool")["version"] == "1.1.0-beta.1", (
        "thread-pool: ^1.0.0 with yanked 1.1.0 must select 1.1.0-beta.1 "
        "(pre-releases are valid candidates per the spec)"
    )


def test_thread_pool_not_stable_fallback():
    """thread-pool must NOT resolve to 1.0.0 — pre-release 1.1.0-beta.1
    has higher precedence than 1.0.0."""
    assert _pkg("thread-pool")["version"] != "1.0.0", (
        "thread-pool incorrectly fell back to 1.0.0; "
        "1.1.0-beta.1 > 1.0.0 in semver and is not yanked"
    )


# ── Trap: constraint intersection forces version downgrade ────────────


def test_constraint_intersection_validator():
    """serializer requires ^0.3.0 but data-mapper requires =0.3.0.
    The intersection must force validator to exactly 0.3.0, NOT 0.3.1."""
    assert _pkg("validator")["version"] == "0.3.0", (
        "Constraint intersection: =0.3.0 ∩ ^0.3.0 must resolve to 0.3.0"
    )


def test_constraint_intersection_not_higher():
    """validator must NOT be 0.3.1 when data-mapper requires =0.3.0."""
    assert _pkg("validator")["version"] != "0.3.1", (
        "validator resolved to 0.3.1 — the =0.3.0 exact constraint was ignored"
    )


# ── Trap: pre-release ordering with mixed numeric/string identifiers ──


def test_prerelease_mixed_ordering():
    """proto-buf constraint >=2.0.0-1, <2.0.0 must select 2.0.0-alpha.1.
    Numeric pre-release ids (1, 2) sort BEFORE string ids (alpha).
    More identifiers = higher precedence when prefix matches.
    Order: 2.0.0-1 < 2.0.0-2 < 2.0.0-alpha < 2.0.0-alpha.1"""
    assert _pkg("proto-buf")["version"] == "2.0.0-alpha.1", (
        "Pre-release ordering: numeric < string; alpha.1 > alpha"
    )


def test_prerelease_not_numeric_highest():
    """proto-buf must NOT resolve to 2.0.0-2 (numeric ids sort lower)."""
    assert _pkg("proto-buf")["version"] != "2.0.0-2", (
        "Resolved 2.0.0-2 — numeric pre-release ids must sort before strings"
    )


def test_prerelease_not_stable():
    """proto-buf constraint <2.0.0 must exclude the stable 2.0.0 release."""
    assert _pkg("proto-buf")["version"] != "2.0.0", (
        "Resolved 2.0.0 — the <2.0.0 constraint must exclude the stable release"
    )


# ── Depth values ─────────────────────────────────────────────────────


def test_api_gateway_depth():
    assert _pkg("api-gateway")["depth"] == 1


def test_cache_engine_depth():
    assert _pkg("cache-engine")["depth"] == 1


def test_data_mapper_depth():
    assert _pkg("data-mapper")["depth"] == 1


def test_network_stack_depth():
    assert _pkg("network-stack")["depth"] == 1


def test_proto_buf_depth():
    assert _pkg("proto-buf")["depth"] == 1


def test_rate_limiter_depth():
    assert _pkg("rate-limiter")["depth"] == 1


def test_thread_pool_depth():
    assert _pkg("thread-pool")["depth"] == 1


def test_tiny_alloc_depth():
    assert _pkg("tiny-alloc")["depth"] == 1


def test_auth_service_depth():
    """auth-service is direct dep (1) but also via api-gateway (2). Longest=2."""
    assert _pkg("auth-service")["depth"] == 2


def test_event_bus_depth():
    """event-bus is direct dep (1) but also via network-stack (2). Longest=2."""
    assert _pkg("event-bus")["depth"] == 2


def test_json_parser_depth():
    """json-parser is direct dep (1) but also via data-mapper (2). Longest=2."""
    assert _pkg("json-parser")["depth"] == 2


def test_web_framework_depth():
    """web-framework is direct dep (1) but also via api-gateway (2). Longest=2."""
    assert _pkg("web-framework")["depth"] == 2


def test_db_connector_depth():
    assert _pkg("db-connector")["depth"] == 3


def test_http_client_depth():
    """http-client is direct dep (1) but reachable via longer paths (3)."""
    assert _pkg("http-client")["depth"] == 3


def test_serializer_depth():
    assert _pkg("serializer")["depth"] == 3


def test_signal_handler_depth():
    assert _pkg("signal-handler")["depth"] == 3


def test_template_engine_depth():
    assert _pkg("template-engine")["depth"] == 3


def test_config_reader_depth():
    assert _pkg("config-reader")["depth"] == 4


def test_core_utils_depth():
    assert _pkg("core-utils")["depth"] == 4


def test_crypto_lib_depth():
    assert _pkg("crypto-lib")["depth"] == 4


def test_validator_depth():
    assert _pkg("validator")["depth"] == 4


def test_logger_depth():
    """logger is a direct dep (1) but reachable through 5-hop path. Longest=5."""
    assert _pkg("logger")["depth"] == 5


# ── Direct dependencies ──────────────────────────────────────────────


def test_api_gateway_deps():
    assert _pkg("api-gateway")["direct_dependencies"] == [
        "auth-service@2.1.1", "web-framework@1.0.0"
    ]


def test_network_stack_deps():
    assert _pkg("network-stack")["direct_dependencies"] == [
        "event-bus@2.1.0", "http-client@0.2.5"
    ]


def test_thread_pool_deps():
    assert _pkg("thread-pool")["direct_dependencies"] == ["logger@1.2.0"]


def test_web_framework_deps():
    assert _pkg("web-framework")["direct_dependencies"] == [
        "http-client@0.2.5", "serializer@2.2.0", "template-engine@1.1.0"
    ]


def test_http_client_deps():
    assert _pkg("http-client")["direct_dependencies"] == [
        "core-utils@1.2.0", "crypto-lib@0.1.5"
    ]


def test_auth_service_deps():
    assert _pkg("auth-service")["direct_dependencies"] == [
        "crypto-lib@0.1.5", "db-connector@3.2.0"
    ]


def test_cache_engine_deps():
    assert _pkg("cache-engine")["direct_dependencies"] == [
        "core-utils@1.2.0", "serializer@2.2.0"
    ]


def test_core_utils_deps():
    assert _pkg("core-utils")["direct_dependencies"] == ["logger@1.2.0"]


def test_db_connector_deps():
    assert _pkg("db-connector")["direct_dependencies"] == [
        "config-reader@0.5.1", "logger@1.2.0"
    ]


def test_serializer_deps():
    assert _pkg("serializer")["direct_dependencies"] == ["validator@0.3.0"]


def test_template_engine_deps():
    assert _pkg("template-engine")["direct_dependencies"] == ["core-utils@1.2.0"]


def test_event_bus_deps():
    assert _pkg("event-bus")["direct_dependencies"] == [
        "serializer@2.2.0", "signal-handler@0.3.1"
    ]


def test_signal_handler_deps():
    assert _pkg("signal-handler")["direct_dependencies"] == ["crypto-lib@0.1.5"]


def test_tiny_alloc_deps():
    assert _pkg("tiny-alloc")["direct_dependencies"] == ["logger@1.2.0"]


def test_data_mapper_deps():
    assert _pkg("data-mapper")["direct_dependencies"] == [
        "json-parser@1.0.0-rc.10", "validator@0.3.0"
    ]


def test_proto_buf_deps():
    assert _pkg("proto-buf")["direct_dependencies"] == ["serializer@2.2.0"]


def test_logger_no_deps():
    assert _pkg("logger")["direct_dependencies"] == []


def test_validator_no_deps():
    assert _pkg("validator")["direct_dependencies"] == []


def test_rate_limiter_no_deps():
    assert _pkg("rate-limiter")["direct_dependencies"] == []


def test_json_parser_no_deps():
    assert _pkg("json-parser")["direct_dependencies"] == []


def test_config_reader_no_deps():
    assert _pkg("config-reader")["direct_dependencies"] == []


def test_crypto_lib_no_deps():
    assert _pkg("crypto-lib")["direct_dependencies"] == []


# ── Dependents ────────────────────────────────────────────────────────


def test_core_utils_dependents():
    assert _pkg("core-utils")["dependents"] == [
        "cache-engine@1.1.0", "http-client@0.2.5", "template-engine@1.1.0"
    ]


def test_crypto_lib_dependents():
    assert _pkg("crypto-lib")["dependents"] == [
        "auth-service@2.1.1", "http-client@0.2.5", "signal-handler@0.3.1"
    ]


def test_logger_dependents():
    assert _pkg("logger")["dependents"] == [
        "core-utils@1.2.0", "db-connector@3.2.0",
        "thread-pool@1.1.0-beta.1", "tiny-alloc@0.0.3"
    ]


def test_serializer_dependents():
    assert _pkg("serializer")["dependents"] == [
        "cache-engine@1.1.0", "event-bus@2.1.0",
        "proto-buf@2.0.0-alpha.1", "web-framework@1.0.0"
    ]


def test_http_client_dependents():
    assert _pkg("http-client")["dependents"] == [
        "network-stack@0.5.0", "web-framework@1.0.0"
    ]


def test_db_connector_dependents():
    assert _pkg("db-connector")["dependents"] == ["auth-service@2.1.1"]


def test_template_engine_dependents():
    assert _pkg("template-engine")["dependents"] == ["web-framework@1.0.0"]


def test_validator_dependents():
    assert _pkg("validator")["dependents"] == [
        "data-mapper@0.2.1", "serializer@2.2.0"
    ]


def test_config_reader_dependents():
    assert _pkg("config-reader")["dependents"] == ["db-connector@3.2.0"]


def test_signal_handler_dependents():
    assert _pkg("signal-handler")["dependents"] == ["event-bus@2.1.0"]


def test_json_parser_dependents():
    assert _pkg("json-parser")["dependents"] == ["data-mapper@0.2.1"]


def test_auth_service_dependents():
    assert _pkg("auth-service")["dependents"] == ["api-gateway@1.0.0"]


def test_web_framework_dependents():
    assert _pkg("web-framework")["dependents"] == ["api-gateway@1.0.0"]


def test_event_bus_dependents():
    assert _pkg("event-bus")["dependents"] == ["network-stack@0.5.0"]


def test_cache_engine_no_dependents():
    assert _pkg("cache-engine")["dependents"] == []


def test_rate_limiter_no_dependents():
    assert _pkg("rate-limiter")["dependents"] == []


def test_data_mapper_no_dependents():
    assert _pkg("data-mapper")["dependents"] == []


def test_proto_buf_no_dependents():
    assert _pkg("proto-buf")["dependents"] == []


def test_api_gateway_no_dependents():
    assert _pkg("api-gateway")["dependents"] == []


def test_network_stack_no_dependents():
    assert _pkg("network-stack")["dependents"] == []


def test_thread_pool_no_dependents():
    assert _pkg("thread-pool")["dependents"] == []


def test_tiny_alloc_no_dependents():
    assert _pkg("tiny-alloc")["dependents"] == []


# ── Build order ──────────────────────────────────────────────────────


def test_build_order_length():
    assert len(R["build_order"]) == 22


def test_build_order_all_present():
    pkgs = {
        f"{p['name']}@{p['version']}"
        for p in R["resolution"]["resolved"]
    }
    assert set(R["build_order"]) == pkgs


def test_build_order_first_four():
    assert R["build_order"][:4] == [
        "config-reader@0.5.1",
        "crypto-lib@0.1.5",
        "json-parser@1.0.0-rc.10",
        "logger@1.2.0",
    ]


def test_build_order_last():
    assert R["build_order"][-1] == "api-gateway@1.0.0"


def test_build_order_deps_before_dependents():
    order = R["build_order"]
    idx = {pkg: i for i, pkg in enumerate(order)}
    for pkg in R["resolution"]["resolved"]:
        pkey = f"{pkg['name']}@{pkg['version']}"
        for dep in pkg["direct_dependencies"]:
            assert idx[dep] < idx[pkey], (
                f"{dep} must be built before {pkey}"
            )


def test_build_order_data_mapper_after_validator():
    order = R["build_order"]
    idx = {pkg: i for i, pkg in enumerate(order)}
    assert idx["data-mapper@0.2.1"] > idx["validator@0.3.0"]


def test_build_order_proto_buf_after_serializer():
    order = R["build_order"]
    idx = {pkg: i for i, pkg in enumerate(order)}
    assert idx["proto-buf@2.0.0-alpha.1"] > idx["serializer@2.2.0"]


def test_build_order_api_gateway_after_web_framework():
    order = R["build_order"]
    idx = {pkg: i for i, pkg in enumerate(order)}
    assert idx["api-gateway@1.0.0"] > idx["web-framework@1.0.0"]
    assert idx["api-gateway@1.0.0"] > idx["auth-service@2.1.1"]


def test_build_order_network_stack_after_event_bus():
    order = R["build_order"]
    idx = {pkg: i for i, pkg in enumerate(order)}
    assert idx["network-stack@0.5.0"] > idx["event-bus@2.1.0"]
    assert idx["network-stack@0.5.0"] > idx["http-client@0.2.5"]


# ── Vulnerability report ─────────────────────────────────────────────


def test_vuln_max_score():
    assert math.isclose(
        R["audit"]["vulnerability_report"]["max_score"], 7.5, abs_tol=SCORE_TOL
    )


def test_vuln_total_vulnerable():
    assert R["audit"]["vulnerability_report"]["total_vulnerable"] == 12


def test_vuln_critical_count():
    assert len(R["audit"]["vulnerability_report"]["critical_packages"]) == 12


def test_vuln_crypto_lib_base():
    assert math.isclose(_vuln("crypto-lib")["base_score"], 7.5, abs_tol=SCORE_TOL)


def test_vuln_crypto_lib_effective():
    assert math.isclose(
        _vuln("crypto-lib")["effective_score"], 7.5, abs_tol=SCORE_TOL
    )


def test_vuln_auth_service_base():
    assert math.isclose(_vuln("auth-service")["base_score"], 0.0, abs_tol=SCORE_TOL)


def test_vuln_auth_service_effective():
    """SUM formula: 0 + 0.6*(crypto-lib:7.5 + db-connector:3.0) = 6.3."""
    assert math.isclose(
        _vuln("auth-service")["effective_score"], 6.3, abs_tol=SCORE_TOL
    )


def test_vuln_api_gateway_base():
    assert math.isclose(_vuln("api-gateway")["base_score"], 0.0, abs_tol=SCORE_TOL)


def test_vuln_api_gateway_effective():
    """SUM formula: 0 + 0.6*(auth-service:6.3 + web-framework:2.7) = 5.4."""
    assert math.isclose(
        _vuln("api-gateway")["effective_score"], 5.4, abs_tol=SCORE_TOL
    )


def test_vuln_network_stack_base():
    assert math.isclose(
        _vuln("network-stack")["base_score"], 0.0, abs_tol=SCORE_TOL
    )


def test_vuln_network_stack_effective():
    """SUM formula: 0 + 0.6*(http-client:4.5 + event-bus:4.2) = 5.22."""
    assert math.isclose(
        _vuln("network-stack")["effective_score"], 5.22, abs_tol=SCORE_TOL
    )


def test_vuln_http_client_base():
    assert math.isclose(_vuln("http-client")["base_score"], 0.0, abs_tol=SCORE_TOL)


def test_vuln_http_client_effective():
    assert math.isclose(
        _vuln("http-client")["effective_score"], 4.5, abs_tol=SCORE_TOL
    )


def test_vuln_signal_handler_base():
    assert math.isclose(
        _vuln("signal-handler")["base_score"], 0.0, abs_tol=SCORE_TOL
    )


def test_vuln_signal_handler_effective():
    assert math.isclose(
        _vuln("signal-handler")["effective_score"], 4.5, abs_tol=SCORE_TOL
    )


def test_vuln_event_bus_base():
    assert math.isclose(_vuln("event-bus")["base_score"], 1.5, abs_tol=SCORE_TOL)


def test_vuln_event_bus_effective():
    """SUM: 1.5 + 0.6*(serializer:0.0 + signal-handler:4.5) = 4.2."""
    assert math.isclose(
        _vuln("event-bus")["effective_score"], 4.2, abs_tol=SCORE_TOL
    )


def test_vuln_db_connector_base():
    assert math.isclose(_vuln("db-connector")["base_score"], 3.0, abs_tol=SCORE_TOL)


def test_vuln_db_connector_effective():
    assert math.isclose(
        _vuln("db-connector")["effective_score"], 3.0, abs_tol=SCORE_TOL
    )


def test_vuln_web_framework_base():
    assert math.isclose(
        _vuln("web-framework")["base_score"], 0.0, abs_tol=SCORE_TOL
    )


def test_vuln_web_framework_effective():
    """SUM: 0 + 0.6*(http-client:4.5 + serializer:0.0 + template-engine:0.0) = 2.7."""
    assert math.isclose(
        _vuln("web-framework")["effective_score"], 2.7, abs_tol=SCORE_TOL
    )


def test_vuln_tiny_alloc_base():
    assert math.isclose(_vuln("tiny-alloc")["base_score"], 2.0, abs_tol=SCORE_TOL)


def test_vuln_tiny_alloc_effective():
    assert math.isclose(
        _vuln("tiny-alloc")["effective_score"], 2.0, abs_tol=SCORE_TOL
    )


def test_vuln_thread_pool_base():
    assert math.isclose(_vuln("thread-pool")["base_score"], 1.0, abs_tol=SCORE_TOL)


def test_vuln_thread_pool_effective():
    """1.0 + 0.6*(logger:0.0) = 1.0."""
    assert math.isclose(
        _vuln("thread-pool")["effective_score"], 1.0, abs_tol=SCORE_TOL
    )


def test_vuln_proto_buf_base():
    assert math.isclose(_vuln("proto-buf")["base_score"], 0.5, abs_tol=SCORE_TOL)


def test_vuln_proto_buf_effective():
    """0.5 + 0.6*(serializer:0.0) = 0.5."""
    assert math.isclose(
        _vuln("proto-buf")["effective_score"], 0.5, abs_tol=SCORE_TOL
    )


def test_vuln_ordering_desc():
    scores = [
        v["effective_score"]
        for v in R["audit"]["vulnerability_report"]["critical_packages"]
    ]
    assert scores == sorted(scores, reverse=True)


def test_vuln_ordering_tie_break_alpha():
    cps = R["audit"]["vulnerability_report"]["critical_packages"]
    for i in range(len(cps) - 1):
        if math.isclose(cps[i]["effective_score"], cps[i+1]["effective_score"],
                        abs_tol=SCORE_TOL):
            assert cps[i]["name"] <= cps[i+1]["name"], (
                f"Tie-break: {cps[i]['name']} should come before {cps[i+1]['name']}"
            )


# ── Trap: vulnerability uses SUM not MAX ─────────────────────────────


def test_vuln_sum_not_max_auth_service():
    """auth-service has deps crypto-lib(7.5) and db-connector(3.0).
    With MAX: 0 + 0.6*7.5 = 4.5. With SUM: 0 + 0.6*(7.5+3.0) = 6.3.
    The spec says SUM."""
    eff = _vuln("auth-service")["effective_score"]
    assert not math.isclose(eff, 4.5, abs_tol=SCORE_TOL), (
        "auth-service effective is 4.5 — using MAX instead of SUM formula"
    )
    assert math.isclose(eff, 6.3, abs_tol=SCORE_TOL)


def test_vuln_sum_not_max_api_gateway():
    """api-gateway: SUM gives 5.4, MAX gives 2.7 (with MAX-based auth-service=4.5)."""
    eff = _vuln("api-gateway")["effective_score"]
    assert eff > 4.0, (
        f"api-gateway effective is {eff} — likely using MAX instead of SUM formula"
    )


def test_vuln_sum_not_max_network_stack():
    """network-stack: SUM gives 5.22, MAX gives 2.7."""
    eff = _vuln("network-stack")["effective_score"]
    assert eff > 4.0, (
        f"network-stack effective is {eff} — likely using MAX instead of SUM formula"
    )


# ── Trap: multi-level vulnerability propagation ──────────────────────


def test_multilevel_vuln_decay_chain():
    """event-bus → signal-handler → crypto-lib: two levels of decay compounding."""
    sig_eff = _vuln("signal-handler")["effective_score"]
    ev_eff = _vuln("event-bus")["effective_score"]
    assert math.isclose(sig_eff, 4.5, abs_tol=SCORE_TOL)
    assert math.isclose(ev_eff, 1.5 + 0.6 * sig_eff, abs_tol=SCORE_TOL)


def test_threelevel_vuln_decay():
    """api-gateway → auth-service → crypto-lib: 3 levels of decay.
    crypto-lib:7.5 → auth-service: 0+0.6*(7.5+3.0)=6.3 → api-gateway: 0+0.6*(6.3+2.7)=5.4."""
    assert math.isclose(_vuln("api-gateway")["effective_score"], 5.4, abs_tol=SCORE_TOL)


# ── License report ───────────────────────────────────────────────────


def test_license_total_conflicts():
    assert R["audit"]["license_report"]["total_conflicts"] == 4


def test_license_conflict_count():
    assert len(R["audit"]["license_report"]["conflicts"]) == 4


def test_license_conflict_auth_crypto():
    c = R["audit"]["license_report"]["conflicts"][0]
    assert c["package"] == "auth-service@2.1.1"
    assert c["package_license"] == "MIT"
    assert c["dependency"] == "crypto-lib@0.1.5"
    assert c["dependency_license"] == "GPL-3.0"


def test_license_conflict_eventbus_signal():
    c = R["audit"]["license_report"]["conflicts"][1]
    assert c["package"] == "event-bus@2.1.0"
    assert c["package_license"] == "MIT"
    assert c["dependency"] == "signal-handler@0.3.1"
    assert c["dependency_license"] == "MPL-2.0"


def test_license_conflict_http_crypto():
    c = R["audit"]["license_report"]["conflicts"][2]
    assert c["package"] == "http-client@0.2.5"
    assert c["package_license"] == "MIT"
    assert c["dependency"] == "crypto-lib@0.1.5"
    assert c["dependency_license"] == "GPL-3.0"


def test_license_conflict_signal_crypto():
    c = R["audit"]["license_report"]["conflicts"][3]
    assert c["package"] == "signal-handler@0.3.1"
    assert c["package_license"] == "MPL-2.0"
    assert c["dependency"] == "crypto-lib@0.1.5"
    assert c["dependency_license"] == "GPL-3.0"


def test_weak_copyleft_to_strong_is_conflict():
    conflicts = R["audit"]["license_report"]["conflicts"]
    found = any(
        c["package"].startswith("signal-handler@")
        and c["dependency"].startswith("crypto-lib@")
        for c in conflicts
    )
    assert found, "Missing conflict: signal-handler (MPL-2.0) → crypto-lib (GPL-3.0)"


def test_permissive_to_weak_copyleft_is_conflict():
    conflicts = R["audit"]["license_report"]["conflicts"]
    found = any(
        c["package"].startswith("event-bus@")
        and c["dependency"].startswith("signal-handler@")
        for c in conflicts
    )
    assert found, "Missing conflict: event-bus (MIT) → signal-handler (MPL-2.0)"


def test_no_conflict_permissive_to_permissive():
    """api-gateway (Apache-2.0 = permissive) → auth-service (MIT = permissive)
    should NOT be a conflict."""
    conflicts = R["audit"]["license_report"]["conflicts"]
    found = any(
        c["package"].startswith("api-gateway@")
        for c in conflicts
    )
    assert not found, "api-gateway should have no license conflicts (all permissive deps)"


# ── Statistics ────────────────────────────────────────────────────────


def test_stats_total_packages():
    assert R["audit"]["statistics"]["total_packages"] == 22


def test_stats_max_depth():
    assert R["audit"]["statistics"]["max_depth"] == 5


def test_stats_avg_depth():
    assert math.isclose(
        R["audit"]["statistics"]["avg_depth"], 2.3636, abs_tol=FLOAT_TOL
    )


def test_stats_total_edges():
    assert R["audit"]["statistics"]["total_edges"] == 26


def test_stats_max_fan_out():
    assert R["audit"]["statistics"]["max_fan_out"] == 3


def test_stats_max_fan_in():
    assert R["audit"]["statistics"]["max_fan_in"] == 4


# ── Sorting validation ───────────────────────────────────────────────


def test_resolved_sorted_by_depth_then_name():
    resolved = R["resolution"]["resolved"]
    keys = [(p["depth"], p["name"]) for p in resolved]
    assert keys == sorted(keys)


def test_deps_sorted_alphabetically():
    for pkg in R["resolution"]["resolved"]:
        assert pkg["direct_dependencies"] == sorted(pkg["direct_dependencies"])
        assert pkg["dependents"] == sorted(pkg["dependents"])


def test_conflicts_sorted_by_package():
    conflicts = R["audit"]["license_report"]["conflicts"]
    pkgs = [c["package"] for c in conflicts]
    assert pkgs == sorted(pkgs)


# ── Integrity hash ───────────────────────────────────────────────────


def test_integrity_hash_exists():
    assert "integrity_hash" in R["audit"], "Missing integrity_hash in audit section"
    assert isinstance(R["audit"]["integrity_hash"], str)
    assert len(R["audit"]["integrity_hash"]) == 64, "integrity_hash must be 64 hex chars"


def test_integrity_hash_self_consistent():
    """Recompute the hash from the resolution data + build order and verify."""
    resolved = R["resolution"]["resolved"]
    lines = [
        f"{pkg['name']}:{pkg['version']}:{pkg['depth']}:{pkg['license']}"
        for pkg in sorted(resolved, key=lambda p: p["name"])
    ]
    hash_input = "\n".join(lines) + ";" + ";".join(R["build_order"])
    expected = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    assert R["audit"]["integrity_hash"] == expected, (
        f"integrity_hash mismatch: report has {R['audit']['integrity_hash']}, "
        f"recomputed {expected}"
    )


# ── Dynamic verification ─────────────────────────────────────────────


def test_dynamic_avg_depth():
    resolved = R["resolution"]["resolved"]
    depths = [p["depth"] for p in resolved]
    expected = sum(depths) / len(depths)
    assert math.isclose(
        R["audit"]["statistics"]["avg_depth"], expected, abs_tol=FLOAT_TOL
    )


def test_dynamic_total_edges():
    resolved = R["resolution"]["resolved"]
    edges = sum(len(p["direct_dependencies"]) for p in resolved)
    assert R["audit"]["statistics"]["total_edges"] == edges


def test_dynamic_fan_out():
    resolved = R["resolution"]["resolved"]
    max_fo = max(len(p["direct_dependencies"]) for p in resolved)
    assert R["audit"]["statistics"]["max_fan_out"] == max_fo


def test_dynamic_fan_in():
    resolved = R["resolution"]["resolved"]
    max_fi = max(len(p["dependents"]) for p in resolved)
    assert R["audit"]["statistics"]["max_fan_in"] == max_fi


def test_dynamic_vuln_count():
    cps = R["audit"]["vulnerability_report"]["critical_packages"]
    assert R["audit"]["vulnerability_report"]["total_vulnerable"] == len(cps)


def test_dynamic_max_score():
    cps = R["audit"]["vulnerability_report"]["critical_packages"]
    max_eff = max(c["effective_score"] for c in cps)
    assert math.isclose(
        R["audit"]["vulnerability_report"]["max_score"], max_eff, abs_tol=SCORE_TOL
    )


# ── Input integrity ──────────────────────────────────────────────────

EXPECTED_HASHES = {
    "data/config.json": "af4967fe693508cce0dc3e84d80dd7e3f55fcc144569b4c3641b4b5a173129b8",
    "data/project.json": "1b12bfdb694c6c5345433d54d4229d8aa2e28688f7000b6db14eee7cc9a3fd2a",
    "data/registry/api-gateway.json": "69f19f7eabaf029bcf1622c452aa93ca42a959c3ded20bb8004c97d29bee58ca",
    "data/registry/auth-service.json": "164ffa0ab5c5ba4b9bcd2853585064692d6eaf58c45b1e8f41ecbe2660263b08",
    "data/registry/cache-engine.json": "40a61abbda788916fe6936d57fd0a92ee5b8ea114a3267cb39845402040b63ae",
    "data/registry/config-reader.json": "41bd7edb79b326e6e7d3d9e171430bd77a669f97c3d3f2c8420535815e61402f",
    "data/registry/core-utils.json": "94b96270576be2545878bf2b621ab1ed126554403348f92d45f8a11738b7926d",
    "data/registry/crypto-lib.json": "d1a32d9d3429342931624d8358d9c7b065e8006b4da243dce0cb6a861fec9a16",
    "data/registry/data-mapper.json": "732bbf49658577438219c4b6567cb3462dcaf744790cd821d0bbdd3dace977fa",
    "data/registry/db-connector.json": "b6556d2c26cbe06cec977336b91d11e7adedbdaa21b21a9bc8e9cd111b8f902b",
    "data/registry/event-bus.json": "acf3f269aef7cd970c17b0a57758c363eef15fe9d3c079717174be6c7c09c575",
    "data/registry/http-client.json": "9b01f13cff83174c625cd82b0d091d40ded2976564a8bd506486936c911db1ed",
    "data/registry/json-parser.json": "fab0b1ab089dc1082abeef842f41eb4ecc1026ac49db1c31a87a2b91eb6699ff",
    "data/registry/logger.json": "02b297c63c39d9ad5feb6fe166fcad9b7ccae38247394945689da8a43da75870",
    "data/registry/metrics-collector.json": "7cdbaefc3c4318e173ea6b06e385a83184e283db25e7e9b987bbe6a5dfdedea5",
    "data/registry/network-stack.json": "5ba0a5d963586b5c5d907490023f2186de1cef30bec31b035054af04545ec4bc",
    "data/registry/proto-buf.json": "8b07f94a18c79b911bf437a3bfab4b50827c0fb2ea7e4dbe8413e047f0763388",
    "data/registry/rate-limiter.json": "af44fe9b9ef854f841df5effb9fa74d3a31e631438b8a879823679ec7dc99685",
    "data/registry/serializer.json": "a7e3699f65580dc07dd270d16f827a7e17f90beaf8e12dfda4246fda0b8c0120",
    "data/registry/signal-handler.json": "41a0f4d25abbee533637dbd987091ac84790b2d8fd8982be0ff1cf2545a2b041",
    "data/registry/template-engine.json": "05e7c589a7e53e31a020c76beb20889c58b84424f3886e97a177e551afdb1593",
    "data/registry/thread-pool.json": "bc21a2d608492a441f3fe79871a630cab4e98b63c8b72ed5c0d74c0a7154b937",
    "data/registry/tiny-alloc.json": "7cc18c631d70d032c796132ea6a120932ddd65512e5f236655922d1aa955f5d7",
    "data/registry/validator.json": "79a620e515fc492fc2d46dd1f0cd1afa7546019656a9f81f286e7d58fdd5da81",
    "data/registry/web-framework.json": "95d00add4be873f101c6f4f1fa9243771781ef03af4a92da44908e722b400b39",
    "Cargo.toml": "802115856c887e1c2c4c6a98164a7600226a8b583e33026ee31ebc125812f40f",
}


def test_input_file_integrity():
    for rel, expected_hash in EXPECTED_HASHES.items():
        p = ROOT / rel
        assert p.is_file(), f"Missing: {p}"
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == expected_hash, f"Modified: {rel}"
