"""Test suite for robust regression pipeline output.

Verifies that /app/output/analysis.json matches the expected results
from a correct IRLS implementation with Huber M-estimator, sandwich
covariance, and two-sided outlier detection on the sensors.csv dataset.
"""

import json
import math
import subprocess
from pathlib import Path

OUTPUT_PATH = Path("/app/output/analysis.json")
BINARY_PATH = Path("/app/target/release/robust-regression")


def load_report():
    """Load and parse the output JSON."""
    assert OUTPUT_PATH.exists(), f"Output file not found: {OUTPUT_PATH}"
    text = OUTPUT_PATH.read_text()
    return json.loads(text)


# ── Anti-cheating: binary and language verification ──────────


def test_rust_binary_compiled():
    """The Rust binary must have been compiled via cargo build --release."""
    assert BINARY_PATH.exists(), (
        f"Rust binary not found at {BINARY_PATH}. "
        "Run 'cargo build --release' from /app first."
    )


def test_binary_is_elf():
    """The binary must be a compiled ELF executable, not a script."""
    assert BINARY_PATH.exists(), "Binary not found"
    header = BINARY_PATH.read_bytes()[:4]
    assert header == b"\x7fELF", (
        "File at /app/target/release/robust-regression is not an ELF "
        "binary — solution must be compiled Rust, not a wrapper script"
    )


def test_no_python_solution_files():
    """No Python scripts in /app/src/ — solution must be in Rust."""
    src_dir = Path("/app/src")
    if src_dir.exists():
        py_files = list(src_dir.rglob("*.py"))
        assert len(py_files) == 0, (
            f"Found Python files in /app/src/: {[str(f) for f in py_files]}. "
            "The solution must be implemented in Rust."
        )


def test_cargo_toml_exists():
    """Cargo.toml must exist — the project must remain a Rust crate."""
    assert Path("/app/Cargo.toml").exists(), (
        "Cargo.toml not found — the project must be built with cargo"
    )


# ── Output existence and format ──────────────────────────────


def test_output_file_exists():
    """The output JSON file must exist at /app/output/analysis.json."""
    assert OUTPUT_PATH.exists()


def test_output_is_valid_json():
    """The output must be parseable JSON."""
    text = OUTPUT_PATH.read_text()
    data = json.loads(text)
    assert isinstance(data, dict)


def test_json_trailing_newline():
    """JSON output must end with a trailing newline."""
    raw = OUTPUT_PATH.read_bytes()
    assert raw.endswith(b"\n"), "Output file must end with a newline"


def test_json_two_space_indent():
    """JSON must use 2-space indent (serde_json::to_string_pretty default)."""
    text = OUTPUT_PATH.read_text()
    for line in text.split("\n"):
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if indent > 0:
            assert indent % 2 == 0, f"Non-2-space indent: {line!r}"


def test_json_no_nan_or_inf():
    """No NaN or Infinity values should appear in the output."""
    text = OUTPUT_PATH.read_text()
    assert "NaN" not in text, "NaN found in output"
    assert "Infinity" not in text, "Infinity found in output"
    assert "-Infinity" not in text, "-Infinity found in output"


# ── Structure tests ────────────────────────────────────────────


def test_top_level_keys():
    """All required top-level keys must be present."""
    report = load_report()
    for key in ["coefficients", "convergence", "outliers", "diagnostics"]:
        assert key in report, f"Missing top-level key: {key}"


def test_exactly_four_top_level_keys():
    """Only the four required top-level keys should be present."""
    report = load_report()
    assert set(report.keys()) == {
        "coefficients", "convergence", "outliers", "diagnostics"
    }


def test_coefficient_structure():
    """Each coefficient entry has name, value, and std_error."""
    report = load_report()
    for entry in report["coefficients"]:
        assert "name" in entry
        assert "value" in entry
        assert "std_error" in entry
        assert isinstance(entry["name"], str)
        assert isinstance(entry["value"], (int, float))
        assert isinstance(entry["std_error"], (int, float))


def test_convergence_structure():
    """Convergence section has required fields."""
    report = load_report()
    conv = report["convergence"]
    assert "iterations" in conv
    assert "converged" in conv
    assert "final_change" in conv


def test_outlier_structure():
    """Outlier section has required fields."""
    report = load_report()
    out = report["outliers"]
    assert "indices" in out
    assert "count" in out
    assert "threshold" in out


def test_diagnostics_structure():
    """Diagnostics section has required fields."""
    report = load_report()
    diag = report["diagnostics"]
    assert "scale_estimate" in diag
    assert "r_squared_robust" in diag
    assert "degrees_of_freedom" in diag


# ── Coefficient count and names ────────────────────────────────


def test_coefficient_count():
    """Must have 4 coefficients (intercept + 3 predictors)."""
    report = load_report()
    assert len(report["coefficients"]) == 4


def test_coefficient_names():
    """All expected predictor names must appear."""
    report = load_report()
    names = {c["name"] for c in report["coefficients"]}
    assert names == {"intercept", "temp", "pressure", "humidity"}


# ── Coefficient values (approx) ───────────────────────────────


def test_intercept_value():
    """Intercept ≈ 47.783 — sensitive to Huber weight normalization."""
    report = load_report()
    coefs = {c["name"]: c["value"] for c in report["coefficients"]}
    assert math.isclose(coefs["intercept"], 47.783193, abs_tol=0.01), (
        f"intercept={coefs['intercept']}, expected ≈47.783193"
    )


def test_temp_coefficient():
    """Temperature coefficient ≈ 2.553."""
    report = load_report()
    coefs = {c["name"]: c["value"] for c in report["coefficients"]}
    assert math.isclose(coefs["temp"], 2.552695, abs_tol=0.01), (
        f"temp={coefs['temp']}, expected ≈2.552695"
    )


def test_pressure_coefficient():
    """Pressure coefficient ≈ -0.120."""
    report = load_report()
    coefs = {c["name"]: c["value"] for c in report["coefficients"]}
    assert math.isclose(coefs["pressure"], -0.119603, abs_tol=0.01), (
        f"pressure={coefs['pressure']}, expected ≈-0.119603"
    )


def test_humidity_coefficient():
    """Humidity coefficient ≈ 0.815."""
    report = load_report()
    coefs = {c["name"]: c["value"] for c in report["coefficients"]}
    assert math.isclose(coefs["humidity"], 0.815432, abs_tol=0.01), (
        f"humidity={coefs['humidity']}, expected ≈0.815432"
    )


# ── Coefficient values (tight 1e-6 tolerance) ─────────────────


def test_intercept_precise():
    """Intercept to 6 decimal places with tight tolerance."""
    report = load_report()
    coefs = {c["name"]: c["value"] for c in report["coefficients"]}
    assert math.isclose(coefs["intercept"], 47.783193, abs_tol=1e-6), (
        f"intercept={coefs['intercept']}, expected 47.783193 ±1e-6"
    )


def test_temp_precise():
    """Temp coefficient to 6 decimal places with tight tolerance."""
    report = load_report()
    coefs = {c["name"]: c["value"] for c in report["coefficients"]}
    assert math.isclose(coefs["temp"], 2.552695, abs_tol=1e-6), (
        f"temp={coefs['temp']}, expected 2.552695 ±1e-6"
    )


def test_pressure_precise():
    """Pressure coefficient to 6 decimal places with tight tolerance."""
    report = load_report()
    coefs = {c["name"]: c["value"] for c in report["coefficients"]}
    assert math.isclose(coefs["pressure"], -0.119603, abs_tol=1e-6), (
        f"pressure={coefs['pressure']}, expected -0.119603 ±1e-6"
    )


def test_humidity_precise():
    """Humidity coefficient to 6 decimal places with tight tolerance."""
    report = load_report()
    coefs = {c["name"]: c["value"] for c in report["coefficients"]}
    assert math.isclose(coefs["humidity"], 0.815432, abs_tol=1e-6), (
        f"humidity={coefs['humidity']}, expected 0.815432 ±1e-6"
    )


# ── Coefficient ordering ───────────────────────────────────────


def test_coefficients_sorted_by_absolute_value():
    """Coefficients must be sorted by |value| descending."""
    report = load_report()
    vals = [abs(c["value"]) for c in report["coefficients"]]
    assert vals == sorted(vals, reverse=True), (
        f"Coefficient absolute values not in descending order: {vals}"
    )


def test_coefficient_order_names():
    """Expected order: intercept, temp, humidity, pressure."""
    report = load_report()
    names = [c["name"] for c in report["coefficients"]]
    assert names == ["intercept", "temp", "humidity", "pressure"]


# ── Standard errors (approx) ──────────────────────────────────


def test_intercept_std_error():
    """Intercept SE ≈ 29.651 — sensitive to sandwich meat term (w² vs w)."""
    report = load_report()
    coefs = {c["name"]: c for c in report["coefficients"]}
    assert math.isclose(
        coefs["intercept"]["std_error"], 29.651001, abs_tol=0.5
    ), f"intercept SE={coefs['intercept']['std_error']}, expected ≈29.651001"


def test_temp_std_error():
    """Temp SE ≈ 0.052 — requires correct w² in sandwich meat."""
    report = load_report()
    coefs = {c["name"]: c for c in report["coefficients"]}
    assert math.isclose(
        coefs["temp"]["std_error"], 0.052495, abs_tol=0.005
    ), f"temp SE={coefs['temp']['std_error']}, expected ≈0.052495"


def test_pressure_std_error():
    """Pressure SE ≈ 0.030."""
    report = load_report()
    coefs = {c["name"]: c for c in report["coefficients"]}
    assert math.isclose(
        coefs["pressure"]["std_error"], 0.030007, abs_tol=0.005
    ), f"pressure SE={coefs['pressure']['std_error']}, expected ≈0.030007"


def test_humidity_std_error():
    """Humidity SE ≈ 0.023."""
    report = load_report()
    coefs = {c["name"]: c for c in report["coefficients"]}
    assert math.isclose(
        coefs["humidity"]["std_error"], 0.023318, abs_tol=0.005
    ), f"humidity SE={coefs['humidity']['std_error']}, expected ≈0.023318"


# ── Standard errors (tight 1e-6 tolerance) ────────────────────


def test_intercept_std_error_precise():
    """Intercept SE tight to 6 decimal places."""
    report = load_report()
    coefs = {c["name"]: c for c in report["coefficients"]}
    assert math.isclose(
        coefs["intercept"]["std_error"], 29.651001, abs_tol=1e-6
    ), f"intercept SE={coefs['intercept']['std_error']}, expected 29.651001 ±1e-6"


def test_temp_std_error_precise():
    """Temp SE tight to 6 decimal places."""
    report = load_report()
    coefs = {c["name"]: c for c in report["coefficients"]}
    assert math.isclose(
        coefs["temp"]["std_error"], 0.052495, abs_tol=1e-6
    ), f"temp SE={coefs['temp']['std_error']}, expected 0.052495 ±1e-6"


def test_pressure_std_error_precise():
    """Pressure SE tight to 6 decimal places."""
    report = load_report()
    coefs = {c["name"]: c for c in report["coefficients"]}
    assert math.isclose(
        coefs["pressure"]["std_error"], 0.030007, abs_tol=1e-6
    ), f"pressure SE={coefs['pressure']['std_error']}, expected 0.030007 ±1e-6"


def test_humidity_std_error_precise():
    """Humidity SE tight to 6 decimal places."""
    report = load_report()
    coefs = {c["name"]: c for c in report["coefficients"]}
    assert math.isclose(
        coefs["humidity"]["std_error"], 0.023318, abs_tol=1e-6
    ), f"humidity SE={coefs['humidity']['std_error']}, expected 0.023318 ±1e-6"


# ── Convergence ──────────────────────────────────────────────


def test_convergence_flag():
    """The algorithm should converge within max_iterations."""
    report = load_report()
    assert report["convergence"]["converged"] is True


def test_convergence_iterations():
    """Convergence should take exactly 10 iterations with relative
    criterion and correct tolerance (1e-6, not 1e-5)."""
    report = load_report()
    assert report["convergence"]["iterations"] == 10, (
        f"iterations={report['convergence']['iterations']}, expected 10"
    )


def test_convergence_final_change():
    """Final change should be 0.0 (below tolerance after rounding to 6dp)."""
    report = load_report()
    assert report["convergence"]["final_change"] == 0.0


def test_convergence_iterations_range():
    """Iteration count should be between 5 and 20 for well-conditioned data."""
    report = load_report()
    iters = report["convergence"]["iterations"]
    assert 5 <= iters <= 20, f"iterations={iters}, expected 5-20"


def test_convergence_not_immediate():
    """Iteration count must be > 1, confirming IRLS actually iterated."""
    report = load_report()
    assert report["convergence"]["iterations"] > 1


# ── Outlier detection ──────────────────────────────────────────


def test_outlier_count():
    """Exactly 5 outliers should be detected with two-sided |r|/s > 2.5."""
    report = load_report()
    assert report["outliers"]["count"] == 5, (
        f"outlier count={report['outliers']['count']}, expected 5"
    )


def test_outlier_indices():
    """The exact outlier indices (0-based row numbers)."""
    report = load_report()
    assert report["outliers"]["indices"] == [4, 12, 19, 26, 31], (
        f"outlier indices={report['outliers']['indices']}, "
        "expected [4, 12, 19, 26, 31]"
    )


def test_outlier_index_4():
    """Row 4 must be flagged as outlier."""
    report = load_report()
    assert 4 in report["outliers"]["indices"]


def test_outlier_index_12():
    """Row 12 must be flagged as outlier."""
    report = load_report()
    assert 12 in report["outliers"]["indices"]


def test_outlier_index_19():
    """Row 19 must be flagged — requires two-sided detection."""
    report = load_report()
    assert 19 in report["outliers"]["indices"]


def test_outlier_index_26():
    """Row 26 must be flagged as outlier."""
    report = load_report()
    assert 26 in report["outliers"]["indices"]


def test_outlier_index_31():
    """Row 31 must be flagged as outlier."""
    report = load_report()
    assert 31 in report["outliers"]["indices"]


def test_outlier_threshold():
    """Threshold should match config value 2.5."""
    report = load_report()
    assert report["outliers"]["threshold"] == 2.5


def test_outlier_indices_sorted():
    """Outlier indices must be sorted ascending."""
    report = load_report()
    indices = report["outliers"]["indices"]
    assert indices == sorted(indices)


def test_no_false_positive_outliers():
    """No indices outside the expected 5 should be flagged."""
    report = load_report()
    expected = {4, 12, 19, 26, 31}
    actual = set(report["outliers"]["indices"])
    false_positives = actual - expected
    assert len(false_positives) == 0, (
        f"False positive outlier indices: {false_positives}"
    )


# ── Scale estimate ─────────────────────────────────────────────


def test_scale_estimate():
    """MAD scale ≈ 1.582 — requires median (not mean) as center."""
    report = load_report()
    assert math.isclose(
        report["diagnostics"]["scale_estimate"], 1.582166, abs_tol=0.05
    ), (
        f"scale={report['diagnostics']['scale_estimate']}, expected ≈1.582166"
    )


def test_scale_estimate_precise():
    """MAD scale tight to 6 decimal places."""
    report = load_report()
    assert math.isclose(
        report["diagnostics"]["scale_estimate"], 1.582166, abs_tol=1e-6
    ), (
        f"scale={report['diagnostics']['scale_estimate']}, expected 1.582166 ±1e-6"
    )


def test_scale_positive():
    """Scale estimate must be positive."""
    report = load_report()
    assert report["diagnostics"]["scale_estimate"] > 0


def test_scale_not_std_dev():
    """Scale must differ significantly from the sample standard deviation
    (~6.77), confirming MAD is used instead of variance-based estimation."""
    report = load_report()
    assert abs(report["diagnostics"]["scale_estimate"] - 6.77) > 1.0, (
        "Scale too close to std dev — MAD may not be used correctly"
    )


# ── R² diagnostics ────────────────────────────────────────────


def test_r_squared_robust():
    """Robust R² ≈ 0.962 — requires weighted sums."""
    report = load_report()
    assert math.isclose(
        report["diagnostics"]["r_squared_robust"], 0.961652, abs_tol=0.01
    ), (
        f"R²={report['diagnostics']['r_squared_robust']}, expected ≈0.961652"
    )


def test_r_squared_precise():
    """R² tight to 6 decimal places."""
    report = load_report()
    assert math.isclose(
        report["diagnostics"]["r_squared_robust"], 0.961652, abs_tol=1e-6
    ), (
        f"R²={report['diagnostics']['r_squared_robust']}, expected 0.961652 ±1e-6"
    )


def test_r_squared_range():
    """R² should be between 0 and 1 for a reasonable fit."""
    report = load_report()
    r2 = report["diagnostics"]["r_squared_robust"]
    assert 0.0 <= r2 <= 1.0, f"R² out of range: {r2}"


def test_r_squared_above_threshold():
    """For this well-structured data, R² should be > 0.9."""
    report = load_report()
    assert report["diagnostics"]["r_squared_robust"] > 0.9


# ── Degrees of freedom ────────────────────────────────────────


def test_degrees_of_freedom():
    """DoF = n - p = 35 - 4 = 31."""
    report = load_report()
    assert report["diagnostics"]["degrees_of_freedom"] == 31


# ── Type checks ───────────────────────────────────────────────


def test_convergence_type_boolean():
    """The 'converged' field must be a boolean, not an int or string."""
    report = load_report()
    assert isinstance(report["convergence"]["converged"], bool)


def test_iterations_type_integer():
    """The 'iterations' field must be an integer."""
    report = load_report()
    assert isinstance(report["convergence"]["iterations"], int)


def test_degrees_of_freedom_type_integer():
    """The degrees_of_freedom field must be an integer."""
    report = load_report()
    assert isinstance(report["diagnostics"]["degrees_of_freedom"], int)


def test_outlier_count_type_integer():
    """The outlier count field must be an integer."""
    report = load_report()
    assert isinstance(report["outliers"]["count"], int)


# ── Cross-consistency checks ──────────────────────────────────


def test_outlier_count_matches_indices():
    """The count field must match the length of the indices array."""
    report = load_report()
    assert report["outliers"]["count"] == len(report["outliers"]["indices"])


def test_all_std_errors_positive():
    """All standard errors must be positive."""
    report = load_report()
    for c in report["coefficients"]:
        assert c["std_error"] > 0, (
            f"Non-positive SE for {c['name']}: {c['std_error']}"
        )


def test_coefficient_signs():
    """Expected signs: intercept>0, temp>0, pressure<0, humidity>0."""
    report = load_report()
    coefs = {c["name"]: c["value"] for c in report["coefficients"]}
    assert coefs["intercept"] > 0
    assert coefs["temp"] > 0
    assert coefs["pressure"] < 0
    assert coefs["humidity"] > 0


def test_outlier_indices_valid_range():
    """All outlier indices must be valid row numbers (0 to 34)."""
    report = load_report()
    for idx in report["outliers"]["indices"]:
        assert 0 <= idx < 35, f"Invalid outlier index: {idx}"


def test_temp_is_dominant_predictor():
    """Temperature should have the largest |coefficient| (excluding intercept)."""
    report = load_report()
    coefs = {c["name"]: abs(c["value"]) for c in report["coefficients"]}
    predictor_coefs = {k: v for k, v in coefs.items() if k != "intercept"}
    max_pred = max(predictor_coefs, key=predictor_coefs.get)
    assert max_pred == "temp"


def test_intercept_not_ols():
    """Intercept must differ from OLS value (~53.52), confirming IRLS
    weighting is actually working rather than returning the OLS solution."""
    report = load_report()
    coefs = {c["name"]: c["value"] for c in report["coefficients"]}
    assert abs(coefs["intercept"] - 53.52) > 1.0, (
        "Intercept too close to OLS — IRLS weighting may not be working"
    )


def test_final_change_non_negative():
    """Final change must be non-negative."""
    report = load_report()
    assert report["convergence"]["final_change"] >= 0.0


# ── Precision and rounding verification ────────────────────────


def test_precision_six_decimal_places():
    """All coefficient values must have at most 6 decimal places,
    confirming the rounding function uses the correct precision."""
    report = load_report()
    for c in report["coefficients"]:
        val_str = f"{c['value']:.10f}"
        decimals = val_str.split(".")[1]
        trailing = decimals[6:]
        assert all(d == "0" for d in trailing), (
            f"{c['name']} value {c['value']} has more than 6 decimal places"
        )


def test_scale_six_decimal_places():
    """Scale estimate must have at most 6 decimal places."""
    report = load_report()
    scale = report["diagnostics"]["scale_estimate"]
    val_str = f"{scale:.10f}"
    decimals = val_str.split(".")[1]
    trailing = decimals[6:]
    assert all(d == "0" for d in trailing), (
        f"scale_estimate {scale} has more than 6 decimal places"
    )


# ── Dynamic tests (re-run binary with modified config) ────────
# These tests prevent hardcoding the output and verify the binary
# actually implements the algorithm by checking it responds to
# parameter changes.

CONFIG_PATH = Path("/app/config/analysis.toml")


def _modify_config(section, key, new_value):
    """Modify a config value in analysis.toml. Returns original text."""
    original = CONFIG_PATH.read_text()
    lines = original.split("\n")
    new_lines = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"[{section}]"):
            in_section = True
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_section = False
        if in_section and stripped.startswith(f"{key} ="):
            new_lines.append(f"{key} = {new_value}")
        else:
            new_lines.append(line)
    CONFIG_PATH.write_text("\n".join(new_lines))
    return original


def _rerun_binary():
    """Rerun the compiled binary and return the parsed output."""
    subprocess.run(
        [str(BINARY_PATH)], cwd="/app",
        capture_output=True, timeout=30
    )
    return json.loads(OUTPUT_PATH.read_text())


def test_dynamic_threshold_higher():
    """With threshold=20.0, fewer outliers should be detected than at 2.5.
    This verifies the binary reads the config and applies the threshold."""
    assert BINARY_PATH.exists(), "Rust binary required for dynamic tests"
    assert OUTPUT_PATH.exists(), "Output file required for dynamic tests"
    original_output = OUTPUT_PATH.read_text()
    original_config = CONFIG_PATH.read_text()
    try:
        _modify_config("outliers", "threshold", "20.0")
        report = _rerun_binary()
        assert report["outliers"]["count"] < 5, (
            f"With threshold=20.0, expected fewer than 5 outliers, "
            f"got {report['outliers']['count']}"
        )
        assert report["outliers"]["threshold"] == 20.0
    finally:
        CONFIG_PATH.write_text(original_config)
        OUTPUT_PATH.write_text(original_output)


def test_dynamic_single_iteration():
    """With max_iterations=1, the algorithm should not have converged
    fully and iterations must equal 1."""
    assert BINARY_PATH.exists(), "Rust binary required for dynamic tests"
    assert OUTPUT_PATH.exists(), "Output file required for dynamic tests"
    original_output = OUTPUT_PATH.read_text()
    original_config = CONFIG_PATH.read_text()
    try:
        _modify_config("regression", "max_iterations", "1")
        report = _rerun_binary()
        assert report["convergence"]["iterations"] == 1, (
            f"With max_iterations=1, expected 1 iteration, "
            f"got {report['convergence']['iterations']}"
        )
    finally:
        CONFIG_PATH.write_text(original_config)
        OUTPUT_PATH.write_text(original_output)


def test_dynamic_large_k_approaches_ols():
    """With huber_k=1000, all weights ≈ 1 and the result should approach
    the OLS solution, which differs from the IRLS result at k=1.345."""
    assert BINARY_PATH.exists(), "Rust binary required for dynamic tests"
    assert OUTPUT_PATH.exists(), "Output file required for dynamic tests"
    original_output = OUTPUT_PATH.read_text()
    original_config = CONFIG_PATH.read_text()
    irls_report = load_report()
    irls_intercept = next(
        c["value"] for c in irls_report["coefficients"]
        if c["name"] == "intercept"
    )
    try:
        _modify_config("regression", "huber_k", "1000.0")
        report = _rerun_binary()
        ols_intercept = next(
            c["value"] for c in report["coefficients"]
            if c["name"] == "intercept"
        )
        assert not math.isclose(ols_intercept, irls_intercept, abs_tol=0.5), (
            f"With k=1000, intercept ({ols_intercept}) should differ from "
            f"IRLS intercept ({irls_intercept}) by > 0.5"
        )
    finally:
        CONFIG_PATH.write_text(original_config)
        OUTPUT_PATH.write_text(original_output)


def test_dynamic_strict_threshold():
    """With threshold=1.0, more outliers should be detected than at 2.5."""
    assert BINARY_PATH.exists(), "Rust binary required for dynamic tests"
    assert OUTPUT_PATH.exists(), "Output file required for dynamic tests"
    original_output = OUTPUT_PATH.read_text()
    original_config = CONFIG_PATH.read_text()
    try:
        _modify_config("outliers", "threshold", "1.0")
        report = _rerun_binary()
        assert report["outliers"]["count"] > 5, (
            f"With threshold=1.0, expected more than 5 outliers, "
            f"got {report['outliers']['count']}"
        )
    finally:
        CONFIG_PATH.write_text(original_config)
        OUTPUT_PATH.write_text(original_output)


def test_dynamic_precision_change():
    """With precision=3, values should have 3 decimal places, not 6."""
    assert BINARY_PATH.exists(), "Rust binary required for dynamic tests"
    assert OUTPUT_PATH.exists(), "Output file required for dynamic tests"
    original_output = OUTPUT_PATH.read_text()
    original_config = CONFIG_PATH.read_text()
    try:
        _modify_config("output", "precision", "3")
        report = _rerun_binary()
        for c in report["coefficients"]:
            val_str = f"{c['value']:.10f}"
            decimals = val_str.split(".")[1]
            trailing = decimals[3:]
            assert all(d == "0" for d in trailing), (
                f"With precision=3, {c['name']} value {c['value']} "
                f"has more than 3 decimal places"
            )
    finally:
        CONFIG_PATH.write_text(original_config)
        OUTPUT_PATH.write_text(original_output)
