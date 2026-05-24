"""Tests for rust-crate-depgraph-audit-hard."""
import json
import math
import pathlib
import hashlib
import subprocess

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

FLOAT_TOL = 1e-4


R = None


@pytest.fixture(scope="session", autouse=True)
def _load_report():
    global R
    p = OUT_DIR / "resolver_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    R = json.loads(p.read_text(encoding="utf-8"))


def test_output_file_exists():
    """Verify the resolver_report.json output file was created."""
    assert (OUT_DIR / "resolver_report.json").is_file()


def test_top_level_keys():
    """Verify the output contains exactly the required top-level keys."""
    expected = {"checksums", "conflicts", "findings", "metrics", "resolved"}
    assert set(R.keys()) == expected, f"Keys mismatch: got {sorted(R.keys())}"


def test_top_level_keys_sorted():
    """Verify top-level keys are in alphabetical order."""
    keys = list(R.keys())
    assert keys == sorted(keys), f"Top-level keys not sorted: {keys}"


def test_resolved_count():
    """Verify the total number of resolved crates is 15."""
    assert len(R["resolved"]) == 15


def test_resolved_sorted_by_name():
    """Verify resolved array is sorted by crate name."""
    names = [c["name"] for c in R["resolved"]]
    assert names == sorted(names), f"Resolved not sorted: {names}"


def test_no_conflicts():
    """Verify there are no version conflicts in this resolution."""
    assert R["conflicts"] == []


def test_alpha_core_version():
    """Verify alpha-core resolves to 2.0.5 due to tilde constraint from beta-utils."""
    crate = next(c for c in R["resolved"] if c["name"] == "alpha-core")
    assert crate["version"] == "2.0.5", (
        f"alpha-core should be 2.0.5 (constrained by beta-utils ~2.0.5), got {crate['version']}"
    )


def test_alpha_core_depth():
    """Verify alpha-core has depth 1 as a direct dependency."""
    crate = next(c for c in R["resolved"] if c["name"] == "alpha-core")
    assert crate["depth"] == 1


def test_alpha_core_features():
    """Verify alpha-core has default and std features enabled."""
    crate = next(c for c in R["resolved"] if c["name"] == "alpha-core")
    assert crate["features"] == ["default", "std"]


def test_alpha_core_dependents():
    """Verify alpha-core dependents includes all crates that depend on it."""
    crate = next(c for c in R["resolved"] if c["name"] == "alpha-core")
    assert crate["dependents"] == ["beta-utils", "delta-http", "epsilon-json", "my-app"]


def test_beta_utils_version():
    """Verify beta-utils resolves to 1.3.0."""
    crate = next(c for c in R["resolved"] if c["name"] == "beta-utils")
    assert crate["version"] == "1.3.0"


def test_beta_utils_features():
    """Verify beta-utils has default and logging features."""
    crate = next(c for c in R["resolved"] if c["name"] == "beta-utils")
    assert crate["features"] == ["default", "logging"]


def test_beta_utils_depth():
    """Verify beta-utils has depth 1."""
    crate = next(c for c in R["resolved"] if c["name"] == "beta-utils")
    assert crate["depth"] == 1


def test_delta_http_version():
    """Verify delta-http resolves to 0.2.8 due to caret ^0.2.5 constraint."""
    crate = next(c for c in R["resolved"] if c["name"] == "delta-http")
    assert crate["version"] == "0.2.8", (
        f"delta-http should be 0.2.8 (^0.2.5 means <0.3.0), got {crate['version']}"
    )


def test_delta_http_features():
    """Verify delta-http has default and tls features."""
    crate = next(c for c in R["resolved"] if c["name"] == "delta-http")
    assert crate["features"] == ["default", "tls"]


def test_epsilon_json_version():
    """Verify epsilon-json resolves to 2.8.1, not 3.0.0."""
    crate = next(c for c in R["resolved"] if c["name"] == "epsilon-json")
    assert crate["version"] == "2.8.1", (
        f"epsilon-json should be 2.8.1 (^2.8 means <3.0.0), got {crate['version']}"
    )


def test_epsilon_json_features():
    """Verify epsilon-json has default and std features."""
    crate = next(c for c in R["resolved"] if c["name"] == "epsilon-json")
    assert crate["features"] == ["default", "std"]


def test_gamma_log_version():
    """Verify gamma-log resolves to 0.5.3."""
    crate = next(c for c in R["resolved"] if c["name"] == "gamma-log")
    assert crate["version"] == "0.5.3"


def test_gamma_log_features_sorted():
    """Verify gamma-log features are alphabetically sorted (colors before default)."""
    crate = next(c for c in R["resolved"] if c["name"] == "gamma-log")
    assert crate["features"] == ["colors", "default"], (
        f"Features must be alphabetically sorted: got {crate['features']}"
    )


def test_gamma_log_depth():
    """Verify gamma-log has depth 2 (transitive via beta-utils)."""
    crate = next(c for c in R["resolved"] if c["name"] == "gamma-log")
    assert crate["depth"] == 2


def test_gamma_log_dependents():
    """Verify gamma-log is depended on by beta-utils only."""
    crate = next(c for c in R["resolved"] if c["name"] == "gamma-log")
    assert crate["dependents"] == ["beta-utils"]


def test_iota_rand_version():
    """Verify iota-rand resolves to 0.8.5."""
    crate = next(c for c in R["resolved"] if c["name"] == "iota-rand")
    assert crate["version"] == "0.8.5"


def test_iota_rand_depth():
    """Verify iota-rand has depth 2 (via nu-uuid)."""
    crate = next(c for c in R["resolved"] if c["name"] == "iota-rand")
    assert crate["depth"] == 2


def test_iota_rand_features():
    """Verify iota-rand has default and std but NOT getrandom."""
    crate = next(c for c in R["resolved"] if c["name"] == "iota-rand")
    assert crate["features"] == ["default", "std"], (
        f"iota-rand should not have getrandom feature: got {crate['features']}"
    )


def test_iota_rand_core_version():
    """Verify iota-rand-core resolves to 0.6.4."""
    crate = next(c for c in R["resolved"] if c["name"] == "iota-rand-core")
    assert crate["version"] == "0.6.4"


def test_iota_rand_core_depth():
    """Verify iota-rand-core has depth 3 (my-app -> nu-uuid -> iota-rand -> iota-rand-core)."""
    crate = next(c for c in R["resolved"] if c["name"] == "iota-rand-core")
    assert crate["depth"] == 3


def test_kappa_io_version():
    """Verify kappa-io resolves to 1.2.0."""
    crate = next(c for c in R["resolved"] if c["name"] == "kappa-io")
    assert crate["version"] == "1.2.0"


def test_kappa_io_depth():
    """Verify kappa-io has depth 2 (via zeta-async)."""
    crate = next(c for c in R["resolved"] if c["name"] == "kappa-io")
    assert crate["depth"] == 2


def test_kappa_io_features():
    """Verify kappa-io has only default feature (no net/fs enabled)."""
    crate = next(c for c in R["resolved"] if c["name"] == "kappa-io")
    assert crate["features"] == ["default"]


def test_nu_uuid_version():
    """Verify nu-uuid resolves to 1.6.1."""
    crate = next(c for c in R["resolved"] if c["name"] == "nu-uuid")
    assert crate["version"] == "1.6.1"


def test_nu_uuid_features():
    """Verify nu-uuid has default, std, and v4 features."""
    crate = next(c for c in R["resolved"] if c["name"] == "nu-uuid")
    assert crate["features"] == ["default", "std", "v4"]


def test_pi_tracing_version():
    """Verify pi-tracing resolves to 0.1.40 (matches ~0.1.37)."""
    crate = next(c for c in R["resolved"] if c["name"] == "pi-tracing")
    assert crate["version"] == "0.1.40"


def test_pi_tracing_features():
    """Verify pi-tracing has default and std but NOT log feature."""
    crate = next(c for c in R["resolved"] if c["name"] == "pi-tracing")
    assert crate["features"] == ["default", "std"], (
        f"pi-tracing should not have log feature (not requested): got {crate['features']}"
    )


def test_pi_tracing_core_version():
    """Verify pi-tracing-core resolves to 0.1.32."""
    crate = next(c for c in R["resolved"] if c["name"] == "pi-tracing-core")
    assert crate["version"] == "0.1.32"


def test_pi_tracing_core_depth():
    """Verify pi-tracing-core has depth 2."""
    crate = next(c for c in R["resolved"] if c["name"] == "pi-tracing-core")
    assert crate["depth"] == 2


def test_sigma_tls_version():
    """Verify sigma-tls resolves to 0.9.2."""
    crate = next(c for c in R["resolved"] if c["name"] == "sigma-tls")
    assert crate["version"] == "0.9.2"


def test_sigma_tls_depth():
    """Verify sigma-tls has depth 2 (via delta-http)."""
    crate = next(c for c in R["resolved"] if c["name"] == "sigma-tls")
    assert crate["depth"] == 2


def test_sigma_tls_features():
    """Verify sigma-tls has default and native features."""
    crate = next(c for c in R["resolved"] if c["name"] == "sigma-tls")
    assert crate["features"] == ["default", "native"]


def test_theta_cli_version():
    """Verify theta-cli resolves to 4.2.0."""
    crate = next(c for c in R["resolved"] if c["name"] == "theta-cli")
    assert crate["version"] == "4.2.0"


def test_theta_cli_features_sorted():
    """Verify theta-cli features are alphabetically sorted (color, default, derive)."""
    crate = next(c for c in R["resolved"] if c["name"] == "theta-cli")
    assert crate["features"] == ["color", "default", "derive"], (
        f"Features must be sorted alphabetically: got {crate['features']}"
    )


def test_theta_derive_version():
    """Verify theta-derive resolves to 4.2.0."""
    crate = next(c for c in R["resolved"] if c["name"] == "theta-derive")
    assert crate["version"] == "4.2.0"


def test_theta_derive_depth():
    """Verify theta-derive has depth 2 (via theta-cli)."""
    crate = next(c for c in R["resolved"] if c["name"] == "theta-derive")
    assert crate["depth"] == 2


def test_zeta_async_version():
    """Verify zeta-async resolves to 1.0.0."""
    crate = next(c for c in R["resolved"] if c["name"] == "zeta-async")
    assert crate["version"] == "1.0.0"


def test_zeta_async_features():
    """Verify zeta-async has default, full, io, time features."""
    crate = next(c for c in R["resolved"] if c["name"] == "zeta-async")
    assert crate["features"] == ["default", "full", "io", "time"]


def test_metrics_total_crates():
    """Verify metrics.total_crates equals 15."""
    assert R["metrics"]["total_crates"] == 15


def test_metrics_max_depth():
    """Verify metrics.max_depth equals 3."""
    assert R["metrics"]["max_depth"] == 3


def test_metrics_direct_dependencies():
    """Verify metrics.direct_dependencies equals 8."""
    assert R["metrics"]["direct_dependencies"] == 8


def test_metrics_transitive_dependencies():
    """Verify metrics.transitive_dependencies equals 7."""
    assert R["metrics"]["transitive_dependencies"] == 7


def test_metrics_total_features_enabled():
    """Verify metrics.total_features_enabled equals 32."""
    assert R["metrics"]["total_features_enabled"] == 32


def test_metrics_avg_depth():
    """Verify metrics.avg_depth is 1.5333 (rounded to 4 decimal places)."""
    assert math.isclose(R["metrics"]["avg_depth"], 1.5333, abs_tol=FLOAT_TOL)


def test_findings_count():
    """Verify there are exactly 2 advisory findings."""
    assert len(R["findings"]) == 2


def test_finding_iota_rand_core_advisory():
    """Verify iota-rand-core 0.6.4 is flagged by RUSTSEC-2024-0003."""
    finding = next(
        (f for f in R["findings"] if f["crate"] == "iota-rand-core"), None
    )
    assert finding is not None, "Missing advisory finding for iota-rand-core"
    assert finding["advisory_id"] == "RUSTSEC-2024-0003"
    assert finding["severity"] == "medium"
    assert finding["version"] == "0.6.4"
    assert finding["type"] == "advisory"


def test_finding_kappa_io_advisory():
    """Verify kappa-io 1.2.0 is flagged by RUSTSEC-2024-0004 (inclusive upper bound)."""
    finding = next(
        (f for f in R["findings"] if f["crate"] == "kappa-io"), None
    )
    assert finding is not None, "Missing advisory finding for kappa-io"
    assert finding["advisory_id"] == "RUSTSEC-2024-0004"
    assert finding["severity"] == "low"
    assert finding["version"] == "1.2.0"


def test_findings_sorted_by_severity():
    """Verify findings are sorted by severity (medium before low)."""
    severities = [f["severity"] for f in R["findings"]]
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    severity_values = [severity_order[s] for s in severities]
    assert severity_values == sorted(severity_values), (
        f"Findings not sorted by severity: {severities}"
    )


def test_sigma_tls_not_in_findings():
    """Verify sigma-tls 0.9.2 is NOT flagged (advisory only affects <0.9.1)."""
    finding = next(
        (f for f in R["findings"] if f["crate"] == "sigma-tls"), None
    )
    assert finding is None, (
        "sigma-tls 0.9.2 should NOT be flagged — advisory only affects <0.9.1"
    )


def test_eta_crypto_not_in_findings():
    """Verify eta-crypto is NOT in findings (not in resolved set)."""
    finding = next(
        (f for f in R["findings"] if f["crate"] == "eta-crypto"), None
    )
    assert finding is None, "eta-crypto is not in resolved set, should have no finding"


def test_checksums_present():
    """Verify checksums section exists and is non-empty."""
    assert "checksums" in R
    assert len(R["checksums"]) > 0


def test_checksums_count():
    """Verify checksums includes manifest + advisories + all registry files."""
    registry_count = len(list((DATA_DIR / "registry").glob("*.json")))
    expected_count = 2 + registry_count
    assert len(R["checksums"]) == expected_count, (
        f"Expected {expected_count} checksums, got {len(R['checksums'])}"
    )


def test_checksums_manifest():
    """Verify SHA-256 checksum of data/manifest.json is correct."""
    manifest_path = DATA_DIR / "manifest.json"
    expected = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert R["checksums"]["data/manifest.json"] == expected


def test_checksums_advisories():
    """Verify SHA-256 checksum of data/advisories.json is correct."""
    adv_path = DATA_DIR / "advisories.json"
    expected = hashlib.sha256(adv_path.read_bytes()).hexdigest()
    assert R["checksums"]["data/advisories.json"] == expected


def test_checksums_registry_file():
    """Verify SHA-256 checksum of a registry file is correct."""
    reg_path = DATA_DIR / "registry" / "alpha-core.json"
    expected = hashlib.sha256(reg_path.read_bytes()).hexdigest()
    assert R["checksums"]["data/registry/alpha-core.json"] == expected


def test_checksums_keys_sorted():
    """Verify checksum keys are sorted alphabetically."""
    keys = list(R["checksums"].keys())
    assert keys == sorted(keys), f"Checksum keys not sorted: {keys}"


def test_json_sorted_keys():
    """Verify all JSON keys at every level are sorted."""
    raw = (OUT_DIR / "resolver_report.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    _check_sorted_keys(data, "root")


def _check_sorted_keys(obj, path):
    """Recursively verify all dict keys are sorted."""
    if isinstance(obj, dict):
        keys = list(obj.keys())
        assert keys == sorted(keys), f"Keys not sorted at {path}: {keys}"
        for k, v in obj.items():
            _check_sorted_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _check_sorted_keys(item, f"{path}[{i}]")


def test_json_two_space_indent():
    """Verify the output JSON uses 2-space indentation."""
    raw = (OUT_DIR / "resolver_report.json").read_text(encoding="utf-8")
    lines = raw.split("\n")
    indented = [ln for ln in lines if ln.startswith(" ")]
    for line in indented[:20]:
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        assert indent % 2 == 0, f"Non-2-space indent: {repr(line)}"


def test_json_trailing_newline():
    """Verify the output JSON ends with a trailing newline."""
    raw = (OUT_DIR / "resolver_report.json").read_text(encoding="utf-8")
    assert raw.endswith("\n"), "Output JSON must end with trailing newline"


def test_each_resolved_has_required_keys():
    """Verify each resolved entry has all required keys."""
    required = {"name", "version", "depth", "features", "dependents", "license"}
    for crate in R["resolved"]:
        assert set(crate.keys()) == required, (
            f"Crate {crate.get('name', '?')} keys mismatch: {sorted(crate.keys())}"
        )


def test_resolved_entry_keys_sorted():
    """Verify keys within each resolved entry are sorted."""
    for crate in R["resolved"]:
        keys = list(crate.keys())
        assert keys == sorted(keys), (
            f"Keys not sorted in {crate['name']}: {keys}"
        )


def test_features_are_lists():
    """Verify features field is always a list."""
    for crate in R["resolved"]:
        assert isinstance(crate["features"], list), (
            f"{crate['name']}: features should be a list"
        )


def test_dependents_are_lists():
    """Verify dependents field is always a list."""
    for crate in R["resolved"]:
        assert isinstance(crate["dependents"], list), (
            f"{crate['name']}: dependents should be a list"
        )


def test_depth_positive():
    """Verify all depths are positive integers."""
    for crate in R["resolved"]:
        assert isinstance(crate["depth"], int) and crate["depth"] >= 1, (
            f"{crate['name']}: invalid depth {crate['depth']}"
        )


def test_metrics_keys():
    """Verify metrics has exactly the required keys."""
    expected = {
        "avg_depth", "direct_dependencies", "max_depth",
        "total_crates", "total_features_enabled", "transitive_dependencies"
    }
    assert set(R["metrics"].keys()) == expected


def test_kappa_io_not_from_iota_rand():
    """Verify kappa-io is pulled by zeta-async only (getrandom feature not enabled on iota-rand)."""
    crate = next(c for c in R["resolved"] if c["name"] == "kappa-io")
    assert "iota-rand" not in crate["dependents"], (
        "kappa-io should not be depended on by iota-rand (getrandom feature not enabled)"
    )


def test_gamma_log_not_from_pi_tracing():
    """Verify gamma-log is NOT pulled by pi-tracing (log feature not enabled)."""
    crate = next(c for c in R["resolved"] if c["name"] == "gamma-log")
    assert "pi-tracing" not in crate["dependents"], (
        "gamma-log should not be depended on by pi-tracing (log feature not enabled)"
    )


def test_rust_binary_exists():
    """Verify the compiled Rust binary exists."""
    binary = ROOT / "target" / "release" / "crate-audit"
    if not binary.is_file():
        binary = ROOT / "target" / "debug" / "crate-audit"
    assert binary.is_file(), (
        "Rust binary not found. The solution must be built with cargo build."
    )


def test_binary_produces_output():
    """Verify running the Rust binary actually produces the report file."""
    out_file = OUT_DIR / "resolver_report.json"
    out_file.unlink(missing_ok=True)
    binary = ROOT / "target" / "release" / "crate-audit"
    if not binary.is_file():
        binary = ROOT / "target" / "debug" / "crate-audit"
    assert binary.is_file(), "No Rust binary to execute"
    result = subprocess.run(
        [str(binary)], cwd=str(ROOT), capture_output=True, timeout=30
    )
    assert result.returncode == 0, (
        f"Binary exited with code {result.returncode}: {result.stderr.decode()}"
    )
    assert out_file.is_file(), (
        "Binary must produce /app/output/resolver_report.json"
    )


def test_cargo_lock_exists():
    """Verify Rust dependencies were resolved via Cargo."""
    lock = ROOT / "Cargo.lock"
    assert lock.is_file(), (
        "Cargo.lock missing — Rust dependencies were not installed."
    )


def test_rust_build_artifacts():
    """Verify Cargo produced build artifacts in target/."""
    target_dir = ROOT / "target"
    assert target_dir.is_dir(), (
        "target/ directory missing — Rust code was never compiled."
    )


def test_no_python_solution():
    """Verify no Python scripts anywhere in /app that could bypass Rust requirement."""
    py_files = list(ROOT.glob("*.py"))
    py_files += list(ROOT.glob("src/**/*.py"))
    py_files += list(ROOT.glob("**/*.py"))
    py_files = [f for f in py_files if "target" not in f.parts]
    assert len(py_files) == 0, (
        f"Python files found: {[str(f.relative_to(ROOT)) for f in py_files]}. "
        "Solution must be implemented in Rust."
    )


def test_alpha_core_license():
    """Verify alpha-core has license MIT."""
    crate = next(c for c in R["resolved"] if c["name"] == "alpha-core")
    assert crate["license"] == "MIT"


def test_beta_utils_license():
    """Verify beta-utils has license Apache-2.0."""
    crate = next(c for c in R["resolved"] if c["name"] == "beta-utils")
    assert crate["license"] == "Apache-2.0"


def test_nu_uuid_license():
    """Verify nu-uuid has license MIT OR Apache-2.0."""
    crate = next(c for c in R["resolved"] if c["name"] == "nu-uuid")
    assert crate["license"] == "MIT OR Apache-2.0"


def test_kappa_io_license():
    """Verify kappa-io has license MIT."""
    crate = next(c for c in R["resolved"] if c["name"] == "kappa-io")
    assert crate["license"] == "MIT"


def test_gamma_log_license():
    """Verify gamma-log has license MIT."""
    crate = next(c for c in R["resolved"] if c["name"] == "gamma-log")
    assert crate["license"] == "MIT"


def test_finding_iota_rand_core_title():
    """Verify iota-rand-core advisory has the correct title from advisories.json."""
    finding = next(
        (f for f in R["findings"] if f["crate"] == "iota-rand-core"), None
    )
    assert finding is not None
    assert finding["title"] == "Predictable seed generation in default configuration"


def test_finding_kappa_io_title():
    """Verify kappa-io advisory has the correct title from advisories.json."""
    finding = next(
        (f for f in R["findings"] if f["crate"] == "kappa-io"), None
    )
    assert finding is not None
    assert finding["title"] == "File descriptor leak under high concurrency"


def test_features_no_dep_prefix():
    """Verify no feature entry contains dep:X activation directives."""
    for crate in R["resolved"]:
        for feat in crate["features"]:
            assert not feat.startswith("dep:"), (
                f"{crate['name']}: feature list must not contain dep: directives, "
                f"found '{feat}'"
            )
