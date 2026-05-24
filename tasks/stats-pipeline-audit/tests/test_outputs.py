"""Tests for the JavaScript statistical pipeline audit."""
import json
import math
import pathlib

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

FLOAT_TOL = 5e-7


def load_report():
    """Load and return the main output JSON report."""
    p = OUT_DIR / "stats_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


def exp(eid):
    """Look up an experiment result by experiment_id."""
    for e in R["experiments"]:
        if e["experiment_id"] == eid:
            return e
    raise AssertionError(f"Experiment {eid} not found")


def grp(eid, gname):
    """Look up a group within an experiment."""
    return exp(eid)["groups"][gname]


def cmp(eid, ga, gb):
    """Look up a comparison within an experiment."""
    for c in exp(eid)["comparisons"]:
        if c["group_a"] == ga and c["group_b"] == gb:
            return c
    raise AssertionError(f"Comparison {ga}-{gb} not found in {eid}")


# ─── Output file and structure ───────────────────────────────────────────────


def test_output_file_exists():
    """Verify the output file was created."""
    assert (OUT_DIR / "stats_report.json").is_file()


def test_top_level_keys():
    """Verify the report has all required top-level keys."""
    assert set(R.keys()) == {"config", "experiments", "summary"}


def test_config_fields():
    """Verify config contains all expected fields."""
    cfg = R["config"]
    assert cfg["trim_fraction"] == 0.1
    assert cfg["outlier_threshold"] == 3.5
    assert cfg["bootstrap_seed"] == 42
    assert cfg["rounding_decimals"] == 6


def test_experiments_is_list():
    """Verify experiments is a list."""
    assert isinstance(R["experiments"], list)


def test_experiments_count():
    """Verify all 8 experiments were processed."""
    assert len(R["experiments"]) == 8


def test_experiments_sorted():
    """Verify experiments are sorted by experiment_id."""
    ids = [e["experiment_id"] for e in R["experiments"]]
    assert ids == sorted(ids)


def test_experiment_ids_complete():
    """Verify all expected experiment IDs are present."""
    ids = {e["experiment_id"] for e in R["experiments"]}
    expected = {f"exp_{i:02d}" for i in range(1, 9)}
    assert ids == expected


def test_group_required_keys():
    """Verify each group has all required keys."""
    required = {"n", "mean", "trimmed_mean", "median", "variance", "sd",
                "mad", "mad_scaled", "skewness", "min", "max",
                "outlier_indices", "outlier_modified_z"}
    for e in R["experiments"]:
        for gn, g in e["groups"].items():
            assert set(g.keys()) == required, f"{e['experiment_id']}/{gn}"


def test_comparison_required_keys():
    """Verify each comparison has all required keys."""
    required = {"group_a", "group_b", "t_statistic", "welch_df", "p_value",
                "significant", "hedges_g", "ci_lower", "ci_upper"}
    for e in R["experiments"]:
        for c in e["comparisons"]:
            assert set(c.keys()) == required


def test_summary_keys():
    """Verify summary has all required keys."""
    required = {"total_experiments", "total_groups", "total_comparisons",
                "total_outliers_detected", "significant_comparisons"}
    assert set(R["summary"].keys()) == required


def test_json_trailing_newline():
    """Verify JSON file ends with a trailing newline."""
    raw = (OUT_DIR / "stats_report.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")


def test_json_two_space_indent():
    """Verify JSON uses two-space indentation."""
    raw = (OUT_DIR / "stats_report.json").read_text(encoding="utf-8")
    json.loads(raw)
    lines = raw.rstrip("\n").split("\n")
    assert len(lines) > 1
    for i, line in enumerate(lines):
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        assert "\t" not in line, f"Line {i+1} uses tab"
        if stripped and indent > 0:
            assert indent % 2 == 0


def test_correlation_matrix_keys():
    """Verify correlation matrix has group_names and matrix keys."""
    for e in R["experiments"]:
        cm = e["correlation_matrix"]
        assert "group_names" in cm
        assert "matrix" in cm
        assert isinstance(cm["group_names"], list)
        assert isinstance(cm["matrix"], list)


# ─── Summary tests ──────────────────────────────────────────────────────────


def test_summary_total_experiments():
    """Verify summary total_experiments."""
    assert R["summary"]["total_experiments"] == 8


def test_summary_total_groups():
    """Verify summary total_groups matches sum across experiments."""
    total = sum(len(e["groups"]) for e in R["experiments"])
    assert R["summary"]["total_groups"] == total
    assert R["summary"]["total_groups"] == 19


def test_summary_total_comparisons():
    """Verify summary total_comparisons matches sum across experiments."""
    total = sum(len(e["comparisons"]) for e in R["experiments"])
    assert R["summary"]["total_comparisons"] == total
    assert R["summary"]["total_comparisons"] == 15


def test_summary_total_outliers():
    """Verify summary total_outliers_detected."""
    total = sum(
        len(g["outlier_indices"])
        for e in R["experiments"] for g in e["groups"].values()
    )
    assert R["summary"]["total_outliers_detected"] == total
    assert R["summary"]["total_outliers_detected"] == 2


def test_summary_significant():
    """Verify summary significant_comparisons."""
    count = sum(
        1 for e in R["experiments"] for c in e["comparisons"]
        if c["significant"] is True
    )
    assert R["summary"]["significant_comparisons"] == count
    assert R["summary"]["significant_comparisons"] == 12


# ─── Exp 01: Basic two-group ────────────────────────────────────────────────


def test_e01_control_n():
    """exp_01: control group has 20 observations."""
    assert grp("exp_01", "control")["n"] == 20


def test_e01_control_mean():
    """exp_01: control mean."""
    assert math.isclose(grp("exp_01", "control")["mean"], 50.33, abs_tol=FLOAT_TOL)


def test_e01_control_trimmed_mean():
    """exp_01: control trimmed mean."""
    assert math.isclose(grp("exp_01", "control")["trimmed_mean"], 50.33125, abs_tol=FLOAT_TOL)


def test_e01_control_variance():
    """exp_01: control sample variance (Bessel's correction)."""
    assert math.isclose(grp("exp_01", "control")["variance"], 3.852737, abs_tol=FLOAT_TOL)


def test_e01_control_mad():
    """exp_01: control MAD (raw, unscaled)."""
    assert math.isclose(grp("exp_01", "control")["mad"], 1.65, abs_tol=FLOAT_TOL)


def test_e01_control_mad_scaled():
    """exp_01: control MAD scaled by 1.4826."""
    assert math.isclose(grp("exp_01", "control")["mad_scaled"], 2.44629, abs_tol=FLOAT_TOL)


def test_e01_treatment_mean():
    """exp_01: treatment mean."""
    assert math.isclose(grp("exp_01", "treatment")["mean"], 55.45, abs_tol=FLOAT_TOL)


def test_e01_comparison_t():
    """exp_01: Welch t-statistic for control vs treatment."""
    assert math.isclose(cmp("exp_01", "control", "treatment")["t_statistic"],
                         -9.170448, abs_tol=FLOAT_TOL)


def test_e01_comparison_df():
    """exp_01: Welch df is fractional, not rounded."""
    assert math.isclose(cmp("exp_01", "control", "treatment")["welch_df"],
                         35.995574, abs_tol=FLOAT_TOL)


def test_e01_comparison_significant():
    """exp_01: comparison is significant."""
    assert cmp("exp_01", "control", "treatment")["significant"] is True


def test_e01_hedges_g():
    """exp_01: Hedges' g with correction factor."""
    assert math.isclose(cmp("exp_01", "control", "treatment")["hedges_g"],
                         -2.842335, abs_tol=FLOAT_TOL)


def test_e01_bootstrap_ci():
    """exp_01: bootstrap CI bounds."""
    c = cmp("exp_01", "control", "treatment")
    assert math.isclose(c["ci_lower"], -6.19, abs_tol=FLOAT_TOL)
    assert math.isclose(c["ci_upper"], -4.045, abs_tol=FLOAT_TOL)


def test_e01_correlation():
    """exp_01: Spearman correlation between control and treatment."""
    m = exp("exp_01")["correlation_matrix"]["matrix"]
    assert math.isclose(m[0][1], -0.141353, abs_tol=FLOAT_TOL)
    assert math.isclose(m[1][0], -0.141353, abs_tol=FLOAT_TOL)


def test_e01_no_outliers():
    """exp_01: no outliers detected."""
    assert grp("exp_01", "control")["outlier_indices"] == []
    assert grp("exp_01", "treatment")["outlier_indices"] == []


# ─── Exp 02: Three-group unequal sizes ──────────────────────────────────────


def test_e02_group_sizes():
    """exp_02: group sizes 15, 20, 25."""
    assert grp("exp_02", "group_a")["n"] == 15
    assert grp("exp_02", "group_b")["n"] == 20
    assert grp("exp_02", "group_c")["n"] == 25


def test_e02_three_comparisons():
    """exp_02: 3 pairwise comparisons."""
    assert len(exp("exp_02")["comparisons"]) == 3


def test_e02_ab_welch_df():
    """exp_02: Welch df for group_a vs group_b."""
    assert math.isclose(cmp("exp_02", "group_a", "group_b")["welch_df"],
                         26.436887, abs_tol=FLOAT_TOL)


def test_e02_ac_p_value():
    """exp_02: p-value for group_a vs group_c."""
    assert math.isclose(cmp("exp_02", "group_a", "group_c")["p_value"],
                         0.005474, abs_tol=FLOAT_TOL)


def test_e02_bc_hedges_g():
    """exp_02: Hedges' g for group_b vs group_c."""
    assert math.isclose(cmp("exp_02", "group_b", "group_c")["hedges_g"],
                         1.676572, abs_tol=FLOAT_TOL)


def test_e02_correlation_null_unequal():
    """exp_02: correlation null for unequal-size groups."""
    m = exp("exp_02")["correlation_matrix"]["matrix"]
    assert m[0][1] is None
    assert m[0][2] is None
    assert m[1][2] is None


def test_e02_trimmed_mean_group_a():
    """exp_02: fractional trimmed mean for group_a (N=15, k=1.5)."""
    assert math.isclose(grp("exp_02", "group_a")["trimmed_mean"],
                         100.825, abs_tol=FLOAT_TOL)


# ─── Exp 03: Outlier detection ──────────────────────────────────────────────


def test_e03_outlier_count():
    """exp_03: sensor_x has 2 outliers (at values 50 and 350)."""
    assert len(grp("exp_03", "sensor_x")["outlier_indices"]) == 2


def test_e03_outlier_indices():
    """exp_03: outlier indices are 3 and 10 (0-based)."""
    assert grp("exp_03", "sensor_x")["outlier_indices"] == [3, 10]


def test_e03_outlier_modified_z():
    """exp_03: modified Z-scores for outliers."""
    zs = grp("exp_03", "sensor_x")["outlier_modified_z"]
    assert math.isclose(zs[0], -53.32027, abs_tol=FLOAT_TOL)
    assert math.isclose(zs[1], 53.178271, abs_tol=FLOAT_TOL)


def test_e03_sensor_y_no_outliers():
    """exp_03: sensor_y has no outliers."""
    assert grp("exp_03", "sensor_y")["outlier_indices"] == []


def test_e03_mad_sensor_x():
    """exp_03: sensor_x MAD (unscaled)."""
    assert math.isclose(grp("exp_03", "sensor_x")["mad"], 1.9, abs_tol=FLOAT_TOL)


def test_e03_mad_scaled_sensor_x():
    """exp_03: sensor_x MAD scaled by 1.4826."""
    assert math.isclose(grp("exp_03", "sensor_x")["mad_scaled"], 2.81694, abs_tol=FLOAT_TOL)


def test_e03_not_significant():
    """exp_03: comparison is not significant (high variance from outliers)."""
    assert cmp("exp_03", "sensor_x", "sensor_y")["significant"] is False


def test_e03_p_value():
    """exp_03: p-value for sensor_x vs sensor_y."""
    assert math.isclose(cmp("exp_03", "sensor_x", "sensor_y")["p_value"],
                         0.506087, abs_tol=FLOAT_TOL)


# ─── Exp 04: Small samples ──────────────────────────────────────────────────


def test_e04_small_n():
    """exp_04: each group has exactly 5 observations."""
    assert grp("exp_04", "micro_a")["n"] == 5
    assert grp("exp_04", "micro_b")["n"] == 5


def test_e04_variance():
    """exp_04: variance for evenly spaced values [10,20,30,40,50]."""
    assert math.isclose(grp("exp_04", "micro_a")["variance"], 250.0, abs_tol=FLOAT_TOL)


def test_e04_welch_df():
    """exp_04: Welch df for equal-variance small samples."""
    assert math.isclose(cmp("exp_04", "micro_a", "micro_b")["welch_df"],
                         8.0, abs_tol=FLOAT_TOL)


def test_e04_t_statistic():
    """exp_04: t-statistic for micro_a vs micro_b."""
    assert math.isclose(cmp("exp_04", "micro_a", "micro_b")["t_statistic"],
                         -0.5, abs_tol=FLOAT_TOL)


def test_e04_hedges_g():
    """exp_04: Hedges' g with small-sample correction."""
    assert math.isclose(cmp("exp_04", "micro_a", "micro_b")["hedges_g"],
                         -0.285625, abs_tol=FLOAT_TOL)


def test_e04_perfect_correlation():
    """exp_04: perfectly correlated groups (r=1.0)."""
    m = exp("exp_04")["correlation_matrix"]["matrix"]
    assert math.isclose(m[0][1], 1.0, abs_tol=FLOAT_TOL)


def test_e04_skewness_zero():
    """exp_04: skewness of symmetric data is 0."""
    assert math.isclose(grp("exp_04", "micro_a")["skewness"], 0.0, abs_tol=FLOAT_TOL)


# ─── Exp 05: Tied values ────────────────────────────────────────────────────


def test_e05_tied_variance():
    """exp_05: variance for tied values group."""
    assert math.isclose(grp("exp_05", "tied_a")["variance"], 3.181818, abs_tol=FLOAT_TOL)


def test_e05_tied_correlation():
    """exp_05: Spearman correlation with ties using Pearson-on-ranks."""
    m = exp("exp_05")["correlation_matrix"]["matrix"]
    assert math.isclose(m[0][1], 1.0, abs_tol=FLOAT_TOL)


def test_e05_welch_df():
    """exp_05: Welch df for equal-variance groups."""
    assert math.isclose(cmp("exp_05", "tied_a", "tied_b")["welch_df"],
                         22.0, abs_tol=FLOAT_TOL)


def test_e05_p_value():
    """exp_05: p-value for tied groups."""
    assert math.isclose(cmp("exp_05", "tied_a", "tied_b")["p_value"],
                         0.183521, abs_tol=FLOAT_TOL)


def test_e05_hedges_g():
    """exp_05: Hedges' g for tied groups."""
    assert math.isclose(cmp("exp_05", "tied_a", "tied_b")["hedges_g"],
                         -0.54128, abs_tol=FLOAT_TOL)


def test_e05_not_significant():
    """exp_05: comparison is not significant."""
    assert cmp("exp_05", "tied_a", "tied_b")["significant"] is False


# ─── Exp 06: Zero variance ──────────────────────────────────────────────────


def test_e06_constant_variance_zero():
    """exp_06: constant group has variance 0."""
    assert grp("exp_06", "constant")["variance"] == 0.0


def test_e06_constant_sd_zero():
    """exp_06: constant group has sd 0."""
    assert grp("exp_06", "constant")["sd"] == 0.0


def test_e06_constant_mad_zero():
    """exp_06: constant group has MAD 0."""
    assert grp("exp_06", "constant")["mad"] == 0.0


def test_e06_constant_skewness_null():
    """exp_06: skewness is null when sd is 0."""
    assert grp("exp_06", "constant")["skewness"] is None


def test_e06_correlation_null_constant():
    """exp_06: correlation with constant group is null."""
    m = exp("exp_06")["correlation_matrix"]["matrix"]
    assert m[0][1] is None
    assert m[1][0] is None


def test_e06_welch_df():
    """exp_06: Welch df when one group has zero variance."""
    assert math.isclose(cmp("exp_06", "constant", "varied")["welch_df"],
                         9.0, abs_tol=FLOAT_TOL)


def test_e06_hedges_g():
    """exp_06: Hedges' g when one group has zero variance."""
    assert math.isclose(cmp("exp_06", "constant", "varied")["hedges_g"],
                         -1.118407, abs_tol=FLOAT_TOL)


def test_e06_significant():
    """exp_06: comparison is significant."""
    assert cmp("exp_06", "constant", "varied")["significant"] is True


# ─── Exp 07: Fractional trimming ────────────────────────────────────────────


def test_e07_trimmed_mean_m():
    """exp_07: fractional trimmed mean for method_m (N=15, 10% trim = 1.5)."""
    assert math.isclose(grp("exp_07", "method_m")["trimmed_mean"],
                         14.029167, abs_tol=FLOAT_TOL)


def test_e07_trimmed_mean_n():
    """exp_07: fractional trimmed mean for method_n (N=15, 10% trim = 1.5)."""
    assert math.isclose(grp("exp_07", "method_n")["trimmed_mean"],
                         19.808333, abs_tol=FLOAT_TOL)


def test_e07_welch_df_near_integer():
    """exp_07: Welch df is near 28 but not exactly integer."""
    assert math.isclose(cmp("exp_07", "method_m", "method_n")["welch_df"],
                         27.999772, abs_tol=FLOAT_TOL)


def test_e07_hedges_g():
    """exp_07: Hedges' g for method_m vs method_n."""
    assert math.isclose(cmp("exp_07", "method_m", "method_n")["hedges_g"],
                         -2.796832, abs_tol=FLOAT_TOL)


def test_e07_perfect_correlation():
    """exp_07: perfectly correlated methods (r=1.0)."""
    m = exp("exp_07")["correlation_matrix"]["matrix"]
    assert math.isclose(m[0][1], 1.0, abs_tol=FLOAT_TOL)


# ─── Exp 08: Four-group stress test ─────────────────────────────────────────


def test_e08_six_comparisons():
    """exp_08: 4 groups produce 6 pairwise comparisons."""
    assert len(exp("exp_08")["comparisons"]) == 6


def test_e08_all_significant():
    """exp_08: all 6 comparisons are significant."""
    for c in exp("exp_08")["comparisons"]:
        assert c["significant"] is True


def test_e08_dose0_mean():
    """exp_08: dose_0 mean."""
    assert math.isclose(grp("exp_08", "dose_0")["mean"], 5.55, abs_tol=FLOAT_TOL)


def test_e08_dose0_dose1_t():
    """exp_08: t-statistic for dose_0 vs dose_1."""
    assert math.isclose(cmp("exp_08", "dose_0", "dose_1")["t_statistic"],
                         -13.122181, abs_tol=FLOAT_TOL)


def test_e08_dose0_dose2_hedges():
    """exp_08: Hedges' g for dose_0 vs dose_2."""
    assert math.isclose(cmp("exp_08", "dose_0", "dose_2")["hedges_g"],
                         -7.685037, abs_tol=FLOAT_TOL)


def test_e08_correlation_dose0_dose2():
    """exp_08: Spearman correlation between dose_0 and dose_2."""
    m = exp("exp_08")["correlation_matrix"]["matrix"]
    assert math.isclose(m[0][2], 0.983459, abs_tol=FLOAT_TOL)


def test_e08_correlation_dose1_dose3():
    """exp_08: Spearman correlation between dose_1 and dose_3."""
    m = exp("exp_08")["correlation_matrix"]["matrix"]
    assert math.isclose(m[1][3], 0.378947, abs_tol=FLOAT_TOL)


def test_e08_4x4_correlation():
    """exp_08: correlation matrix is 4x4 with diagonal 1.0."""
    cm = exp("exp_08")["correlation_matrix"]
    assert len(cm["group_names"]) == 4
    assert len(cm["matrix"]) == 4
    for i in range(4):
        assert cm["matrix"][i][i] == 1.0


# ─── Cross-consistency tests ────────────────────────────────────────────────


def test_comparisons_sorted_lex():
    """Verify all comparisons are sorted by (group_a, group_b) lexicographically."""
    for e in R["experiments"]:
        pairs = [(c["group_a"], c["group_b"]) for c in e["comparisons"]]
        assert pairs == sorted(pairs), f"{e['experiment_id']} comparisons not sorted"


def test_groups_sorted_alpha():
    """Verify group names within experiments are sorted alphabetically."""
    for e in R["experiments"]:
        gnames = list(e["groups"].keys())
        assert gnames == sorted(gnames), f"{e['experiment_id']} groups not sorted"


def test_correlation_diagonal_ones():
    """Verify all correlation matrix diagonals are 1.0."""
    for e in R["experiments"]:
        m = e["correlation_matrix"]["matrix"]
        for i in range(len(m)):
            assert m[i][i] == 1.0, f"{e['experiment_id']} diagonal [{i}][{i}]"


def test_correlation_symmetric():
    """Verify correlation matrices are symmetric."""
    for e in R["experiments"]:
        m = e["correlation_matrix"]["matrix"]
        n = len(m)
        for i in range(n):
            for j in range(i + 1, n):
                assert m[i][j] == m[j][i], (
                    f"{e['experiment_id']} not symmetric at [{i}][{j}]")


def test_p_value_range():
    """Verify all p-values are between 0 and 1."""
    for e in R["experiments"]:
        for c in e["comparisons"]:
            if c["p_value"] is not None:
                assert 0 <= c["p_value"] <= 1, (
                    f"{e['experiment_id']}: p={c['p_value']}")


def test_significance_consistency():
    """Verify significant matches p_value < alpha."""
    alpha = R["config"]["significance_alpha"]
    for e in R["experiments"]:
        for c in e["comparisons"]:
            if c["p_value"] is not None:
                assert c["significant"] == (c["p_value"] < alpha)


def test_welch_df_not_integer_when_fractional():
    """Verify Welch df is reported as float, not rounded to integer."""
    df = cmp("exp_01", "control", "treatment")["welch_df"]
    assert not float(df).is_integer() or df == 8.0


def test_mad_scaled_is_1_4826_times_mad():
    """Verify mad_scaled = 1.4826 * mad for all groups."""
    for e in R["experiments"]:
        for gn, g in e["groups"].items():
            expected = 1.4826 * g["mad"]
            if g["mad"] > 0:
                assert math.isclose(g["mad_scaled"], 1.4826 * g["mad"],
                                     rel_tol=1e-4), (
                    f"{e['experiment_id']}/{gn}: "
                    f"scaled={g['mad_scaled']} vs 1.4826*{g['mad']}={expected}")


# ─── Trap-specific tests ────────────────────────────────────────────────────


def test_trap_mad_scaling_constant():
    """Trap #1: MAD uses 1.4826 scaling constant.
    Without it, mad_scaled would equal mad (no scaling)."""
    g = grp("exp_01", "control")
    assert g["mad_scaled"] != g["mad"]
    assert math.isclose(g["mad_scaled"] / g["mad"], 1.4826, rel_tol=1e-4)


def test_trap_welch_df_fractional():
    """Trap #2: Welch df must be fractional, not pooled df.
    Pooled df for exp_01 would be 38, not ~36."""
    df = cmp("exp_01", "control", "treatment")["welch_df"]
    assert math.isclose(df, 35.995574, abs_tol=FLOAT_TOL)
    assert not math.isclose(df, 38.0, abs_tol=0.5)


def test_trap_hedges_g_correction():
    """Trap #3: Hedges' g uses J correction factor, not raw Cohen's d.
    Cohen's d for exp_01 would be approximately -2.90, Hedges' g is -2.84."""
    g_val = cmp("exp_01", "control", "treatment")["hedges_g"]
    assert math.isclose(g_val, -2.842335, abs_tol=FLOAT_TOL)
    assert not math.isclose(g_val, -2.9, abs_tol=0.02)


def test_trap_fractional_trim():
    """Trap #4: fractional trimming for N=15, 10% = 1.5 items.
    Floor-based (k=1) would give a different trimmed mean."""
    tm = grp("exp_07", "method_m")["trimmed_mean"]
    assert math.isclose(tm, 14.029167, abs_tol=FLOAT_TOL)


def test_trap_spearman_pearson_on_ranks():
    """Trap #5: Spearman with ties must use Pearson formula on ranks.
    The simplified d-squared formula gives incorrect results with ties."""
    m = exp("exp_05")["correlation_matrix"]["matrix"]
    assert math.isclose(m[0][1], 1.0, abs_tol=FLOAT_TOL)


def test_trap_bootstrap_deterministic():
    """Trap #6: Bootstrap CI must use deterministic LCG PRNG.
    Non-deterministic PRNG would produce different CI bounds each run."""
    c = cmp("exp_01", "control", "treatment")
    assert math.isclose(c["ci_lower"], -6.19, abs_tol=FLOAT_TOL)
    assert math.isclose(c["ci_upper"], -4.045, abs_tol=FLOAT_TOL)


def test_trap_p_value_incomplete_beta():
    """Trap #7: p-value uses regularized incomplete beta function.
    Normal approximation would give different values for small df."""
    p = cmp("exp_04", "micro_a", "micro_b")["p_value"]
    assert math.isclose(p, 0.630536, abs_tol=FLOAT_TOL)


# ─── Input integrity ────────────────────────────────────────────────────────


def test_input_config_exists():
    """Verify pipeline_config.json exists."""
    assert (DATA_DIR / "pipeline_config.json").is_file()


def test_input_datasets_exist():
    """Verify all 8 experiment files exist."""
    ds = DATA_DIR / "datasets"
    for i in range(1, 9):
        assert (ds / f"experiment_{i:02d}.json").is_file()


# ─── Additional descriptive stats tests ──────────────────────────────────────


def test_e01_control_sd():
    """exp_01: control standard deviation."""
    assert math.isclose(grp("exp_01", "control")["sd"], 1.962839, abs_tol=FLOAT_TOL)


def test_e01_control_median():
    """exp_01: control median."""
    assert math.isclose(grp("exp_01", "control")["median"], 50.15, abs_tol=FLOAT_TOL)


def test_e01_control_skewness():
    """exp_01: control skewness (adjusted Fisher-Pearson)."""
    assert math.isclose(grp("exp_01", "control")["skewness"], 0.02324, abs_tol=FLOAT_TOL)


def test_e01_control_min_max():
    """exp_01: control min and max values."""
    assert grp("exp_01", "control")["min"] == 47.1
    assert grp("exp_01", "control")["max"] == 53.4


def test_e01_treatment_sd():
    """exp_01: treatment standard deviation."""
    assert math.isclose(grp("exp_01", "treatment")["sd"], 1.543237, abs_tol=FLOAT_TOL)


def test_e01_treatment_variance():
    """exp_01: treatment sample variance."""
    assert math.isclose(grp("exp_01", "treatment")["variance"], 2.381579, abs_tol=FLOAT_TOL)


def test_e01_treatment_trimmed_mean():
    """exp_01: treatment trimmed mean."""
    assert math.isclose(grp("exp_01", "treatment")["trimmed_mean"], 55.4375, abs_tol=FLOAT_TOL)


def test_e02_group_b_mean():
    """exp_02: group_b mean."""
    assert math.isclose(grp("exp_02", "group_b")["mean"], 111.595, abs_tol=FLOAT_TOL)


def test_e02_group_c_variance():
    """exp_02: group_c variance."""
    assert math.isclose(grp("exp_02", "group_c")["variance"], 22.8, abs_tol=FLOAT_TOL)


def test_e02_group_a_skewness():
    """exp_02: group_a skewness."""
    assert math.isclose(grp("exp_02", "group_a")["skewness"], 0.165798, abs_tol=FLOAT_TOL)


def test_e03_sensor_x_mean():
    """exp_03: sensor_x mean (affected by outliers)."""
    assert math.isclose(grp("exp_03", "sensor_x")["mean"], 200.113333, abs_tol=FLOAT_TOL)


def test_e03_sensor_x_variance():
    """exp_03: sensor_x variance (very large due to outliers)."""
    assert math.isclose(grp("exp_03", "sensor_x")["variance"], 3218.356952, abs_tol=FLOAT_TOL)


def test_e03_sensor_y_mean():
    """exp_03: sensor_y mean."""
    assert math.isclose(grp("exp_03", "sensor_y")["mean"], 210.113333, abs_tol=FLOAT_TOL)


def test_e06_varied_mean():
    """exp_06: varied group mean."""
    assert math.isclose(grp("exp_06", "varied")["mean"], 44.5, abs_tol=FLOAT_TOL)


def test_e06_varied_variance():
    """exp_06: varied group variance."""
    assert math.isclose(grp("exp_06", "varied")["variance"], 9.166667, abs_tol=FLOAT_TOL)


def test_e06_varied_skewness():
    """exp_06: varied group skewness (symmetric uniform data)."""
    assert math.isclose(grp("exp_06", "varied")["skewness"], 0.0, abs_tol=1e-4)


# ─── Additional comparison tests ────────────────────────────────────────────


def test_e02_ab_t_statistic():
    """exp_02: t-statistic for group_a vs group_b."""
    assert math.isclose(cmp("exp_02", "group_a", "group_b")["t_statistic"],
                         -9.888615, abs_tol=FLOAT_TOL)


def test_e02_ab_hedges_g():
    """exp_02: Hedges' g for group_a vs group_b."""
    assert math.isclose(cmp("exp_02", "group_a", "group_b")["hedges_g"],
                         -3.403118, abs_tol=FLOAT_TOL)


def test_e02_ac_hedges_g():
    """exp_02: Hedges' g for group_a vs group_c."""
    assert math.isclose(cmp("exp_02", "group_a", "group_c")["hedges_g"],
                         -0.870939, abs_tol=FLOAT_TOL)


def test_e02_bc_t_statistic():
    """exp_02: t-statistic for group_b vs group_c."""
    assert math.isclose(cmp("exp_02", "group_b", "group_c")["t_statistic"],
                         6.017049, abs_tol=FLOAT_TOL)


def test_e03_comparison_hedges_g():
    """exp_03: Hedges' g for sensor_x vs sensor_y."""
    assert math.isclose(cmp("exp_03", "sensor_x", "sensor_y")["hedges_g"],
                         -0.242452, abs_tol=FLOAT_TOL)


def test_e06_p_value():
    """exp_06: p-value for constant vs varied."""
    assert math.isclose(cmp("exp_06", "constant", "varied")["p_value"],
                         0.028217, abs_tol=FLOAT_TOL)


def test_e08_dose2_dose3_t():
    """exp_08: t-statistic for dose_2 vs dose_3."""
    assert math.isclose(cmp("exp_08", "dose_2", "dose_3")["t_statistic"],
                         -8.87245, abs_tol=FLOAT_TOL)


def test_e08_dose1_dose2_hedges():
    """exp_08: Hedges' g for dose_1 vs dose_2."""
    assert math.isclose(cmp("exp_08", "dose_1", "dose_2")["hedges_g"],
                         -3.663927, abs_tol=FLOAT_TOL)


def test_e08_dose0_dose3_hedges():
    """exp_08: Hedges' g for dose_0 vs dose_3."""
    assert math.isclose(cmp("exp_08", "dose_0", "dose_3")["hedges_g"],
                         -9.861754, abs_tol=FLOAT_TOL)


# ─── Bootstrap CI additional tests ──────────────────────────────────────────


def test_e02_ab_bootstrap_ci():
    """exp_02: bootstrap CI for group_a vs group_b."""
    c = cmp("exp_02", "group_a", "group_b")
    assert math.isclose(c["ci_lower"], -12.748375, abs_tol=FLOAT_TOL)
    assert math.isclose(c["ci_upper"], -8.65, abs_tol=FLOAT_TOL)


def test_e05_bootstrap_ci():
    """exp_05: bootstrap CI for tied_a vs tied_b."""
    c = cmp("exp_05", "tied_a", "tied_b")
    assert math.isclose(c["ci_lower"], -2.333333, abs_tol=FLOAT_TOL)
    assert math.isclose(c["ci_upper"], 0.333333, abs_tol=FLOAT_TOL)


def test_e06_bootstrap_ci():
    """exp_06: bootstrap CI for constant vs varied."""
    c = cmp("exp_06", "constant", "varied")
    assert math.isclose(c["ci_lower"], -4.3, abs_tol=FLOAT_TOL)
    assert math.isclose(c["ci_upper"], -0.8, abs_tol=FLOAT_TOL)


def test_e07_bootstrap_ci():
    """exp_07: bootstrap CI for method_m vs method_n."""
    c = cmp("exp_07", "method_m", "method_n")
    assert math.isclose(c["ci_lower"], -7.173333, abs_tol=FLOAT_TOL)
    assert math.isclose(c["ci_upper"], -4.413333, abs_tol=FLOAT_TOL)


def test_e08_dose0_dose1_ci():
    """exp_08: bootstrap CI for dose_0 vs dose_1."""
    c = cmp("exp_08", "dose_0", "dose_1")
    assert math.isclose(c["ci_lower"], -2.925, abs_tol=FLOAT_TOL)
    assert math.isclose(c["ci_upper"], -2.18, abs_tol=FLOAT_TOL)


# ─── Correlation additional tests ────────────────────────────────────────────


def test_e03_correlation():
    """exp_03: Spearman correlation between sensor_x and sensor_y."""
    m = exp("exp_03")["correlation_matrix"]["matrix"]
    assert math.isclose(m[0][1], 0.053571, abs_tol=FLOAT_TOL)


def test_e08_corr_dose0_dose1():
    """exp_08: Spearman correlation between dose_0 and dose_1."""
    m = exp("exp_08")["correlation_matrix"]["matrix"]
    assert math.isclose(m[0][1], 0.407519, abs_tol=FLOAT_TOL)


def test_e08_corr_dose2_dose3():
    """exp_08: Spearman correlation between dose_2 and dose_3."""
    m = exp("exp_08")["correlation_matrix"]["matrix"]
    assert math.isclose(m[2][3], 0.965414, abs_tol=FLOAT_TOL)


def test_e08_corr_dose0_dose3():
    """exp_08: Spearman correlation between dose_0 and dose_3."""
    m = exp("exp_08")["correlation_matrix"]["matrix"]
    assert math.isclose(m[0][3], 0.954887, abs_tol=FLOAT_TOL)


def test_e04_p_value():
    """exp_04: p-value for small samples (not significant)."""
    assert cmp("exp_04", "micro_a", "micro_b")["significant"] is False


def test_corr_group_names_sorted():
    """Verify correlation matrix group_names match sorted group names."""
    for e in R["experiments"]:
        cm = e["correlation_matrix"]
        assert cm["group_names"] == sorted(e["groups"].keys())
