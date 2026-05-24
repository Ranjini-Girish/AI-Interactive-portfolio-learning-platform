"""Tests for monte-carlo-estimator-audit-hard."""
import json
import math
import pathlib
import hashlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

FLOAT_TOL = 1e-4
TIGHT_TOL = 1e-6

EXPECTED_INPUT_HASHES = {
    "data/functions/func_01_polynomial.json": "e79e3c79ff8b76a06bab6a4de3f0c9cedc23bf44e1e94fa429e27e3dc8ff5fd2",
    "data/functions/func_10_constant.json": "dc5f5bfbb7d7a4b5a7e3ec1b16ded5f1d3a3fbc6aef01dc5e8d8d4b6c5bfe1a2",
}


def load_report():
    """Load and return the main output JSON report."""
    p = OUT_DIR / "audit_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


def _find_result(func_id, method_id, sample_size):
    """Find a specific result entry."""
    for e in R["results"]:
        if (e["function_id"] == func_id
                and e["method_id"] == method_id
                and e["sample_size"] == sample_size):
            return e
    pytest.fail(f"Missing result: {func_id}/{method_id}/{sample_size}")


def _find_convergence(func_id, method_id, n_small):
    """Find a specific convergence entry."""
    for c in R["convergence"]:
        if (c["function_id"] == func_id
                and c["method_id"] == method_id
                and c["n_small"] == n_small):
            return c
    pytest.fail(f"Missing convergence: {func_id}/{method_id}/{n_small}")


def _find_efficiency(func_id):
    """Find a specific efficiency summary entry."""
    for e in R["efficiency_summary"]:
        if e["function_id"] == func_id:
            return e
    pytest.fail(f"Missing efficiency: {func_id}")


# ═══════════════════════════════════════════════════════════════════════════════
# Structure tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_output_file_exists():
    """Verify the main output file was created."""
    assert (OUT_DIR / "audit_report.json").is_file()


def test_top_level_keys():
    """Verify the output contains all required top-level keys."""
    required = {"metadata", "results", "convergence", "efficiency_summary"}
    assert set(R.keys()) == required, f"Keys mismatch: got {sorted(R.keys())}"


def test_metadata_total_functions():
    """Verify metadata reports 10 functions."""
    assert R["metadata"]["total_functions"] == 10


def test_metadata_total_methods():
    """Verify metadata reports 4 methods."""
    assert R["metadata"]["total_methods"] == 4


def test_metadata_sample_sizes():
    """Verify metadata lists the correct sample sizes."""
    assert R["metadata"]["sample_sizes"] == [100, 500, 1000, 5000]


def test_metadata_seed():
    """Verify metadata reports the seed from the sample files."""
    assert R["metadata"]["seed"] == 314159


def test_results_count():
    """Verify the total number of result entries: 10 funcs * 4 methods * 4 sizes."""
    assert len(R["results"]) == 160


def test_convergence_count():
    """Verify the total number of convergence entries: 10 * 4 * 3 pairs."""
    assert len(R["convergence"]) == 120


def test_efficiency_summary_count():
    """Verify efficiency summary has one entry per function."""
    assert len(R["efficiency_summary"]) == 10


def test_result_entry_keys():
    """Verify each result entry has all required keys."""
    required = {"function_id", "method_id", "sample_size", "estimate",
                "exact_integral", "absolute_error", "relative_error",
                "sample_variance", "standard_error", "cost_adjusted_variance"}
    for i, e in enumerate(R["results"]):
        assert set(e.keys()) == required, f"Result {i}: keys mismatch {set(e.keys())}"


def test_convergence_entry_keys():
    """Verify each convergence entry has all required keys."""
    required = {"function_id", "method_id", "n_small", "n_large",
                "error_small", "error_large", "empirical_order"}
    for i, c in enumerate(R["convergence"]):
        assert set(c.keys()) == required, f"Conv {i}: keys mismatch"


def test_efficiency_entry_keys():
    """Verify each efficiency summary entry has all required keys."""
    required = {"function_id", "best_method", "efficiency_ratios"}
    for e in R["efficiency_summary"]:
        assert set(e.keys()) == required


def test_efficiency_ratios_methods():
    """Verify efficiency_ratios contains all four method keys."""
    for e in R["efficiency_summary"]:
        assert set(e["efficiency_ratios"].keys()) == {
            "crude_mc", "antithetic", "stratified", "control_variate"
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Sorting tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_results_sorted_by_method_function_size():
    """Verify results are sorted by (method_id, function_id, sample_size)."""
    keys = [(e["method_id"], e["function_id"], e["sample_size"]) for e in R["results"]]
    assert keys == sorted(keys)


def test_convergence_sorted_by_method_function_nsmall():
    """Verify convergence is sorted by (method_id, function_id, n_small)."""
    keys = [(c["method_id"], c["function_id"], c["n_small"]) for c in R["convergence"]]
    assert keys == sorted(keys)


def test_efficiency_sorted_by_function_id():
    """Verify efficiency_summary is sorted by function_id."""
    fids = [e["function_id"] for e in R["efficiency_summary"]]
    assert fids == sorted(fids)


# ═══════════════════════════════════════════════════════════════════════════════
# Crude MC numerical precision tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_crude_mc_polynomial_1000_estimate():
    """Verify crude MC estimate for polynomial at N=1000."""
    e = _find_result("func_01_polynomial", "crude_mc", 1000)
    assert math.isclose(e["estimate"], 3.03591477, abs_tol=FLOAT_TOL)


def test_crude_mc_polynomial_1000_variance():
    """Verify crude MC population variance for polynomial at N=1000 uses denominator N."""
    e = _find_result("func_01_polynomial", "crude_mc", 1000)
    assert math.isclose(e["sample_variance"], 2.19175901, abs_tol=FLOAT_TOL)


def test_crude_mc_polynomial_1000_std_error():
    """Verify crude MC standard error = sqrt(var/N)."""
    e = _find_result("func_01_polynomial", "crude_mc", 1000)
    assert math.isclose(e["standard_error"], 0.04681623, abs_tol=FLOAT_TOL)


def test_crude_mc_polynomial_5000_estimate():
    """Verify crude MC estimate for polynomial at N=5000."""
    e = _find_result("func_01_polynomial", "crude_mc", 5000)
    assert math.isclose(e["estimate"], 3.01278225, abs_tol=FLOAT_TOL)


def test_crude_mc_polynomial_5000_cav():
    """Verify cost-adjusted variance equals sample_variance * 1 for crude MC."""
    e = _find_result("func_01_polynomial", "crude_mc", 5000)
    assert math.isclose(e["cost_adjusted_variance"], e["sample_variance"], abs_tol=TIGHT_TOL)


def test_crude_mc_oscillatory_relative_error_null():
    """Verify relative_error is null for oscillatory function (exact_integral=0)."""
    e = _find_result("func_09_oscillatory", "crude_mc", 100)
    assert e["relative_error"] is None


def test_crude_mc_oscillatory_absolute_error():
    """Verify absolute error is computed correctly for oscillatory at N=100."""
    e = _find_result("func_09_oscillatory", "crude_mc", 100)
    assert math.isclose(e["absolute_error"], 0.08169986, abs_tol=FLOAT_TOL)


def test_crude_mc_constant_zero_variance():
    """Verify constant function has zero variance for crude MC."""
    e = _find_result("func_10_constant", "crude_mc", 5000)
    assert e["sample_variance"] == 0.0


def test_crude_mc_constant_exact_estimate():
    """Verify constant function estimate equals the constant value."""
    e = _find_result("func_10_constant", "crude_mc", 5000)
    assert e["estimate"] == 4.5


def test_crude_mc_absolute_value_5000():
    """Verify crude MC for absolute value function at N=5000."""
    e = _find_result("func_06_absolute", "crude_mc", 5000)
    assert math.isclose(e["estimate"], 0.29218781, abs_tol=FLOAT_TOL)
    assert math.isclose(e["sample_variance"], 0.039223, abs_tol=FLOAT_TOL)


# ═══════════════════════════════════════════════════════════════════════════════
# Antithetic variates tests — key gotcha: variance of v_i not of 2N evals
# ═══════════════════════════════════════════════════════════════════════════════


def test_antithetic_step_zero_variance():
    """Verify antithetic variates produces zero variance for step function.

    f(x)=2 if x<0.5 else 1, so f(x)+f(1-x)=3 always, v_i=1.5 always.
    Population variance of constant values is 0.
    """
    e = _find_result("func_08_step", "antithetic", 5000)
    assert e["sample_variance"] == 0.0
    assert e["estimate"] == 1.5
    assert e["absolute_error"] == 0.0


def test_antithetic_step_cav():
    """Verify cost-adjusted variance for antithetic step is 0 * 2 = 0."""
    e = _find_result("func_08_step", "antithetic", 5000)
    assert e["cost_adjusted_variance"] == 0.0


def test_antithetic_polynomial_5000_estimate():
    """Verify antithetic estimate for polynomial at N=5000."""
    e = _find_result("func_01_polynomial", "antithetic", 5000)
    assert math.isclose(e["estimate"], 3.00095054, abs_tol=FLOAT_TOL)


def test_antithetic_polynomial_5000_variance():
    """Verify antithetic variance is computed over yi = (f(xi)+f(1-xi))/2 values."""
    e = _find_result("func_01_polynomial", "antithetic", 5000)
    assert math.isclose(e["sample_variance"], 0.04918205, abs_tol=FLOAT_TOL)


def test_antithetic_polynomial_5000_cav():
    """Verify antithetic CAV = variance * 2 (evaluations_per_sample)."""
    e = _find_result("func_01_polynomial", "antithetic", 5000)
    assert math.isclose(e["cost_adjusted_variance"], 0.0983641, abs_tol=FLOAT_TOL)
    assert math.isclose(e["cost_adjusted_variance"],
                        e["sample_variance"] * 2, abs_tol=TIGHT_TOL)


def test_antithetic_trigonometric_5000():
    """Verify antithetic for trigonometric function at N=5000."""
    e = _find_result("func_02_trigonometric", "antithetic", 5000)
    assert math.isclose(e["estimate"], 0.63493317, abs_tol=FLOAT_TOL)
    assert math.isclose(e["sample_variance"], 0.09334528, abs_tol=FLOAT_TOL)


def test_antithetic_trig_variance_not_halved():
    """Verify antithetic variance for sin(pi*x) is close to crude MC variance.

    For sin(pi*x), f(x)=f(1-x), so antithetic provides no variance reduction.
    The v_i values equal f(x_i), making the variance similar to crude MC.
    """
    e_anti = _find_result("func_02_trigonometric", "antithetic", 5000)
    e_crude = _find_result("func_02_trigonometric", "crude_mc", 5000)
    ratio = e_anti["sample_variance"] / e_crude["sample_variance"]
    assert 0.9 < ratio < 1.1, f"Antithetic variance should be ~same as crude for sin(pi*x), ratio={ratio}"


# ═══════════════════════════════════════════════════════════════════════════════
# Stratified sampling tests — key gotcha: variance formula, sample allocation
# ═══════════════════════════════════════════════════════════════════════════════


def test_stratified_polynomial_5000_estimate():
    """Verify stratified estimate for polynomial at N=5000."""
    e = _find_result("func_01_polynomial", "stratified", 5000)
    assert math.isclose(e["estimate"], 3.0012351, abs_tol=FLOAT_TOL)


def test_stratified_polynomial_5000_variance():
    """Verify stratified variance uses (1/K^2)*sum(sigma_k^2/n_k) formula."""
    e = _find_result("func_01_polynomial", "stratified", 5000)
    assert math.isclose(e["sample_variance"], 4.71e-06, abs_tol=1e-7)


def test_stratified_polynomial_cav_equals_variance():
    """Verify stratified CAV = variance * 1 (1 eval per sample)."""
    e = _find_result("func_01_polynomial", "stratified", 5000)
    assert math.isclose(e["cost_adjusted_variance"], e["sample_variance"], abs_tol=TIGHT_TOL)


def test_stratified_step_zero_variance():
    """Verify stratified sampling produces zero variance for step function.

    With K=10 strata, strata 0-4 are in [0,0.5) where f=2, strata 5-9 in
    [0.5,1] where f=1. Within each stratum f is constant, so variance is 0.
    """
    e = _find_result("func_08_step", "stratified", 5000)
    assert e["sample_variance"] == 0.0
    assert e["estimate"] == 1.5


def test_stratified_step_all_sizes_exact():
    """Verify stratified step function estimate is exact at all sample sizes."""
    for n in [100, 500, 1000, 5000]:
        e = _find_result("func_08_step", "stratified", n)
        assert e["estimate"] == 1.5, f"N={n}: estimate={e['estimate']}"
        assert e["absolute_error"] == 0.0, f"N={n}: error={e['absolute_error']}"


def test_stratified_much_lower_variance_than_crude():
    """Verify stratified variance is orders of magnitude lower than crude MC."""
    e_strat = _find_result("func_01_polynomial", "stratified", 5000)
    e_crude = _find_result("func_01_polynomial", "crude_mc", 5000)
    assert e_strat["sample_variance"] < e_crude["sample_variance"] * 0.001


def test_stratified_rational_500():
    """Verify stratified sampling for rational function at N=500."""
    e = _find_result("func_05_rational", "stratified", 500)
    assert math.isclose(e["exact_integral"], 0.2746801533890032, abs_tol=TIGHT_TOL)


# ═══════════════════════════════════════════════════════════════════════════════
# Control variate tests — key gotcha: population cov/var, analytical E[g]
# ═══════════════════════════════════════════════════════════════════════════════


def test_control_variate_polynomial_1000():
    """Verify control variate for polynomial at N=1000."""
    e = _find_result("func_01_polynomial", "control_variate", 1000)
    assert math.isclose(e["estimate"], 3.00744292, abs_tol=FLOAT_TOL)
    assert math.isclose(e["sample_variance"], 0.0501711, abs_tol=FLOAT_TOL)


def test_control_variate_polynomial_cav():
    """Verify control variate CAV = variance * 2."""
    e = _find_result("func_01_polynomial", "control_variate", 1000)
    assert math.isclose(e["cost_adjusted_variance"], 0.10034219, abs_tol=FLOAT_TOL)
    assert math.isclose(e["cost_adjusted_variance"],
                        e["sample_variance"] * 2, abs_tol=TIGHT_TOL)


def test_control_variate_exponential_5000():
    """Verify control variate for exponential at N=5000."""
    e = _find_result("func_03_exponential", "control_variate", 5000)
    assert math.isclose(e["estimate"], 0.4324932, abs_tol=FLOAT_TOL)
    assert math.isclose(e["sample_variance"], 0.0034621, abs_tol=FLOAT_TOL)


def test_control_variate_constant_zero_variance():
    """Verify control variate for constant function has zero variance."""
    e = _find_result("func_10_constant", "control_variate", 5000)
    assert e["sample_variance"] == 0.0
    assert e["estimate"] == 4.5


def test_control_variate_polynomial_vs_crude_variance():
    """Verify control variate reduces variance for polynomial."""
    e_cv = _find_result("func_01_polynomial", "control_variate", 5000)
    e_crude = _find_result("func_01_polynomial", "crude_mc", 5000)
    assert e_cv["sample_variance"] < e_crude["sample_variance"]


# ═══════════════════════════════════════════════════════════════════════════════
# Exact integral and absolute error consistency
# ═══════════════════════════════════════════════════════════════════════════════


def test_exact_integral_polynomial():
    """Verify exact integral for polynomial 1+2x+3x^2 is 3.0."""
    e = _find_result("func_01_polynomial", "crude_mc", 100)
    assert e["exact_integral"] == 3.0


def test_exact_integral_oscillatory():
    """Verify exact integral for cos(10*pi*x) is 0.0."""
    e = _find_result("func_09_oscillatory", "crude_mc", 100)
    assert e["exact_integral"] == 0.0


def test_exact_integral_step():
    """Verify exact integral for step function is 1.5."""
    e = _find_result("func_08_step", "crude_mc", 100)
    assert e["exact_integral"] == 1.5


def test_exact_integral_constant():
    """Verify exact integral for constant 4.5 is 4.5."""
    e = _find_result("func_10_constant", "crude_mc", 100)
    assert e["exact_integral"] == 4.5


def test_exact_integral_consistent_across_methods():
    """Verify exact_integral is the same for all methods of the same function."""
    by_func = {}
    for e in R["results"]:
        fid = e["function_id"]
        if fid not in by_func:
            by_func[fid] = e["exact_integral"]
        else:
            assert e["exact_integral"] == by_func[fid], (
                f"{fid}: inconsistent exact_integral"
            )


def test_absolute_error_is_abs_diff():
    """Verify absolute_error = |estimate - exact_integral| for all results."""
    for e in R["results"]:
        expected = abs(e["estimate"] - e["exact_integral"])
        assert math.isclose(e["absolute_error"], expected, abs_tol=TIGHT_TOL), (
            f"{e['function_id']}/{e['method_id']}/{e['sample_size']}: "
            f"abs_error={e['absolute_error']} != |{e['estimate']}-{e['exact_integral']}|={expected}"
        )


def test_relative_error_consistency():
    """Verify relative_error = abs_error / |exact| when exact != 0, null otherwise."""
    for e in R["results"]:
        if e["exact_integral"] == 0:
            assert e["relative_error"] is None, (
                f"{e['function_id']}/{e['method_id']}: relative_error should be null"
            )
        else:
            expected = e["absolute_error"] / abs(e["exact_integral"])
            assert math.isclose(e["relative_error"], expected, abs_tol=TIGHT_TOL), (
                f"{e['function_id']}/{e['method_id']}: rel_error mismatch"
            )


def test_standard_error_formula():
    """Verify standard_error = sqrt(sample_variance / N) for all results."""
    for e in R["results"]:
        expected = math.sqrt(e["sample_variance"] / e["sample_size"])
        assert math.isclose(e["standard_error"], expected, abs_tol=TIGHT_TOL), (
            f"{e['function_id']}/{e['method_id']}/{e['sample_size']}: "
            f"se={e['standard_error']} != sqrt({e['sample_variance']}/{e['sample_size']})={expected}"
        )


def test_variance_non_negative():
    """Verify all sample_variance values are non-negative."""
    for e in R["results"]:
        assert e["sample_variance"] >= 0, (
            f"{e['function_id']}/{e['method_id']}/{e['sample_size']}: negative variance"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Convergence tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_convergence_null_for_constant():
    """Verify all convergence orders are null for constant function (zero error)."""
    for c in R["convergence"]:
        if c["function_id"] == "func_10_constant":
            assert c["empirical_order"] is None, (
                f"func_10/{c['method_id']}/{c['n_small']}: order should be null"
            )


def test_convergence_null_when_error_increased():
    """Verify convergence order is null when error_large >= error_small."""
    for c in R["convergence"]:
        if c["error_small"] is not None and c["error_large"] is not None:
            if c["error_large"] >= c["error_small"]:
                assert c["empirical_order"] is None, (
                    f"{c['function_id']}/{c['method_id']}/{c['n_small']}: "
                    f"order should be null when error didn't decrease"
                )


def test_convergence_null_when_either_error_zero():
    """Verify convergence order is null when either error is exactly 0."""
    for c in R["convergence"]:
        if c["error_small"] == 0 or c["error_large"] == 0:
            assert c["empirical_order"] is None, (
                f"{c['function_id']}/{c['method_id']}/{c['n_small']}: "
                f"order should be null when error is 0"
            )


def test_convergence_formula():
    """Verify the convergence order formula: log(e_s/e_l) / log(n_l/n_s)."""
    c = _find_convergence("func_01_polynomial", "crude_mc", 100)
    if c["empirical_order"] is not None:
        expected = math.log(c["error_small"] / c["error_large"]) / math.log(c["n_large"] / c["n_small"])
        assert math.isclose(c["empirical_order"], expected, abs_tol=FLOAT_TOL)


def test_convergence_polynomial_crude_100_500():
    """Verify specific convergence order for polynomial crude MC N=100->500."""
    c = _find_convergence("func_01_polynomial", "crude_mc", 100)
    assert math.isclose(c["empirical_order"], 0.35248698, abs_tol=FLOAT_TOL)


def test_convergence_polynomial_crude_500_1000():
    """Verify specific convergence order for polynomial crude MC N=500->1000."""
    c = _find_convergence("func_01_polynomial", "crude_mc", 500)
    assert math.isclose(c["empirical_order"], 1.21328348, abs_tol=FLOAT_TOL)


def test_convergence_n_pairs():
    """Verify convergence entries cover all consecutive pairs."""
    expected_pairs = [(100, 500), (500, 1000), (1000, 5000)]
    for c in R["convergence"]:
        pair = (c["n_small"], c["n_large"])
        assert pair in expected_pairs, f"Unexpected pair: {pair}"


def test_convergence_errors_match_results():
    """Verify convergence error_small/error_large match the results section."""
    result_idx = {}
    for e in R["results"]:
        result_idx[(e["function_id"], e["method_id"], e["sample_size"])] = e

    for c in R["convergence"]:
        key_s = (c["function_id"], c["method_id"], c["n_small"])
        key_l = (c["function_id"], c["method_id"], c["n_large"])
        assert key_s in result_idx, f"Missing result for {key_s}"
        assert key_l in result_idx, f"Missing result for {key_l}"
        assert math.isclose(c["error_small"], result_idx[key_s]["absolute_error"], abs_tol=TIGHT_TOL)
        assert math.isclose(c["error_large"], result_idx[key_l]["absolute_error"], abs_tol=TIGHT_TOL)


def test_convergence_total_null_count():
    """Verify a significant number of convergence orders are null (edge cases exist)."""
    null_count = sum(1 for c in R["convergence"] if c["empirical_order"] is None)
    assert null_count >= 20, f"Expected at least 20 null orders, got {null_count}"


# ═══════════════════════════════════════════════════════════════════════════════
# Efficiency summary tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_efficiency_crude_always_one():
    """Verify crude_mc efficiency ratio is always 1.0."""
    for e in R["efficiency_summary"]:
        assert e["efficiency_ratios"]["crude_mc"] == 1.0


def test_efficiency_constant_all_null_except_crude():
    """Verify constant function has null ratios for all methods except crude."""
    e = _find_efficiency("func_10_constant")
    assert e["efficiency_ratios"]["crude_mc"] == 1.0
    assert e["efficiency_ratios"]["antithetic"] is None
    assert e["efficiency_ratios"]["stratified"] is None
    assert e["efficiency_ratios"]["control_variate"] is None


def test_efficiency_constant_best_method():
    """Verify constant function best_method is crude_mc (all others null)."""
    e = _find_efficiency("func_10_constant")
    assert e["best_method"] == "crude_mc"


def test_efficiency_polynomial_best_method():
    """Verify polynomial best_method is stratified (highest efficiency ratio)."""
    e = _find_efficiency("func_01_polynomial")
    assert e["best_method"] == "stratified"


def test_efficiency_step_antithetic_null():
    """Verify step function antithetic efficiency is null (zero CAV)."""
    e = _find_efficiency("func_08_step")
    assert e["efficiency_ratios"]["antithetic"] is None


def test_efficiency_step_stratified_null():
    """Verify step function stratified efficiency is null (zero CAV)."""
    e = _find_efficiency("func_08_step")
    assert e["efficiency_ratios"]["stratified"] is None


def test_efficiency_step_best_method():
    """Verify step function best_method is control_variate."""
    e = _find_efficiency("func_08_step")
    assert e["best_method"] == "control_variate"


def test_efficiency_polynomial_stratified_ratio():
    """Verify polynomial stratified efficiency ratio is very high (>1000)."""
    e = _find_efficiency("func_01_polynomial")
    r = e["efficiency_ratios"]["stratified"]
    assert r is not None and r > 1000


def test_efficiency_polynomial_antithetic_ratio():
    """Verify polynomial antithetic efficiency ratio value."""
    e = _find_efficiency("func_01_polynomial")
    assert math.isclose(e["efficiency_ratios"]["antithetic"], 21.83713123, abs_tol=0.01)


def test_efficiency_polynomial_control_ratio():
    """Verify polynomial control variate efficiency ratio value."""
    e = _find_efficiency("func_01_polynomial")
    assert math.isclose(e["efficiency_ratios"]["control_variate"], 21.84027303, abs_tol=0.01)


def test_efficiency_ratio_formula():
    """Verify efficiency ratio = CAV_crude / CAV_method for non-null entries."""
    result_idx = {}
    for e in R["results"]:
        result_idx[(e["function_id"], e["method_id"], e["sample_size"])] = e

    for eff in R["efficiency_summary"]:
        fid = eff["function_id"]
        crude_cav = result_idx[(fid, "crude_mc", 5000)]["cost_adjusted_variance"]
        for mid, ratio in eff["efficiency_ratios"].items():
            if mid == "crude_mc":
                continue
            method_cav = result_idx[(fid, mid, 5000)]["cost_adjusted_variance"]
            if ratio is not None:
                assert method_cav > 0
                expected = crude_cav / method_cav
                assert math.isclose(ratio, expected, abs_tol=0.01), (
                    f"{fid}/{mid}: ratio={ratio} != {expected}"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# Cost-adjusted variance tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_cav_crude_equals_variance():
    """Verify crude MC CAV = variance (evals_per_sample = 1)."""
    for e in R["results"]:
        if e["method_id"] == "crude_mc":
            assert math.isclose(e["cost_adjusted_variance"], e["sample_variance"], abs_tol=TIGHT_TOL), (
                f"{e['function_id']}/{e['sample_size']}: CAV != variance for crude"
            )


def test_cav_antithetic_double_variance():
    """Verify antithetic CAV = 2 * variance (evals_per_sample = 2)."""
    for e in R["results"]:
        if e["method_id"] == "antithetic":
            assert math.isclose(e["cost_adjusted_variance"], 2 * e["sample_variance"], abs_tol=TIGHT_TOL), (
                f"{e['function_id']}/{e['sample_size']}: CAV != 2*variance for antithetic"
            )


def test_cav_stratified_equals_variance():
    """Verify stratified CAV = variance (evals_per_sample = 1)."""
    for e in R["results"]:
        if e["method_id"] == "stratified":
            assert math.isclose(e["cost_adjusted_variance"], e["sample_variance"], abs_tol=TIGHT_TOL), (
                f"{e['function_id']}/{e['sample_size']}: CAV != variance for stratified"
            )


def test_cav_control_double_variance():
    """Verify control variate CAV = 2 * variance (evals_per_sample = 2)."""
    for e in R["results"]:
        if e["method_id"] == "control_variate":
            assert math.isclose(e["cost_adjusted_variance"], 2 * e["sample_variance"], abs_tol=TIGHT_TOL), (
                f"{e['function_id']}/{e['sample_size']}: CAV != 2*variance for control"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Population variance vs sample variance gotcha tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_variance_is_population_not_sample():
    """Verify variance uses denominator N, not N-1.

    For crude MC polynomial at N=1000, population var ~2.19 vs sample var ~2.19*1000/999~2.194.
    Checking the value is closer to population formula.
    """
    e = _find_result("func_01_polynomial", "crude_mc", 1000)
    pop_var = 2.19175901
    bessel_var = pop_var * 1000 / 999
    assert abs(e["sample_variance"] - pop_var) < abs(e["sample_variance"] - bessel_var)


def test_variance_population_crude_5000():
    """Verify population variance for crude MC at large N."""
    e = _find_result("func_01_polynomial", "crude_mc", 5000)
    assert math.isclose(e["sample_variance"], 2.14798976, abs_tol=FLOAT_TOL)


# ═══════════════════════════════════════════════════════════════════════════════
# All oscillatory results have null relative_error
# ═══════════════════════════════════════════════════════════════════════════════


def test_oscillatory_all_relative_errors_null():
    """Verify all oscillatory function results have null relative_error."""
    for e in R["results"]:
        if e["function_id"] == "func_09_oscillatory":
            assert e["relative_error"] is None, (
                f"oscillatory/{e['method_id']}/{e['sample_size']}: relative_error should be null"
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
    assert content == expected, "JSON formatting does not match 2-space indent with trailing newline"


# ═══════════════════════════════════════════════════════════════════════════════
# Input integrity
# ═══════════════════════════════════════════════════════════════════════════════


def test_input_functions_exist():
    """Verify all 10 function definition files exist."""
    func_dir = DATA_DIR / "functions"
    assert func_dir.is_dir()
    files = sorted(func_dir.glob("*.json"))
    assert len(files) == 10


def test_input_samples_exist():
    """Verify all 4 sample files exist."""
    samp_dir = DATA_DIR / "samples"
    assert samp_dir.is_dir()
    files = sorted(samp_dir.glob("*.json"))
    assert len(files) == 4


def test_input_func_01_not_tampered():
    """Verify func_01_polynomial.json has not been modified."""
    p = DATA_DIR / "functions" / "func_01_polynomial.json"
    assert p.is_file()
    actual_hash = hashlib.sha256(p.read_bytes()).hexdigest()
    assert len(actual_hash) == 64, "Hash length mismatch"
    content = json.loads(p.read_text(encoding="utf-8"))
    assert content["id"] == "func_01_polynomial"
    assert content["exact_integral"] == 3.0


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-method consistency tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_all_methods_present_for_each_function():
    """Verify each function has results for all 4 methods at all 4 sizes."""
    expected_methods = {"crude_mc", "antithetic", "stratified", "control_variate"}
    expected_sizes = {100, 500, 1000, 5000}
    by_func = {}
    for e in R["results"]:
        fid = e["function_id"]
        if fid not in by_func:
            by_func[fid] = set()
        by_func[fid].add((e["method_id"], e["sample_size"]))

    for fid, combos in by_func.items():
        for mid in expected_methods:
            for n in expected_sizes:
                assert (mid, n) in combos, f"Missing {fid}/{mid}/{n}"


def test_all_functions_present():
    """Verify all 10 function IDs appear in results."""
    fids = {e["function_id"] for e in R["results"]}
    expected = {f"func_{i:02d}_{n}" for i, n in enumerate([
        "polynomial", "trigonometric", "exponential", "logarithmic",
        "rational", "absolute", "gaussian", "step", "oscillatory", "constant"
    ], 1)}
    assert fids == expected, f"Missing functions: {expected - fids}"


def test_exact_integral_trigonometric():
    """Verify exact integral for sin(pi*x) is 2/pi."""
    e = _find_result("func_02_trigonometric", "crude_mc", 100)
    assert math.isclose(e["exact_integral"], 2.0 / math.pi, abs_tol=TIGHT_TOL)


def test_exact_integral_exponential():
    """Verify exact integral for exp(-2x) is (1-e^-2)/2."""
    e = _find_result("func_03_exponential", "crude_mc", 100)
    expected = (1.0 - math.exp(-2.0)) / 2.0
    assert math.isclose(e["exact_integral"], expected, abs_tol=TIGHT_TOL)
