"""Verification suite for the reactive dataflow engine."""
import json
import math
import pathlib
from collections import Counter

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')

ATOL = 1e-4
TIGHT = 1e-6


def load_results():
    p = OUT_DIR / "results.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_results()


# ─── Structure ────────────────────────────────────────────────────────────────


def test_struct_01_output_exists():
    assert (OUT_DIR / "results.json").is_file()


def test_struct_02_required_keys():
    required = {
        "initial_snapshot", "updates", "final_values",
        "cycles_detected", "recalc_counts", "errors", "recalculation_order",
    }
    assert set(R.keys()) == required


def test_struct_03_snapshot_populated():
    assert isinstance(R["initial_snapshot"], dict) and len(R["initial_snapshot"]) > 0


def test_struct_04_final_populated():
    assert isinstance(R["final_values"], dict) and len(R["final_values"]) > 0


def test_struct_05_updates_count():
    assert isinstance(R["updates"], list) and len(R["updates"]) == 32


def test_struct_06_recalc_order_type():
    assert isinstance(R["recalculation_order"], list)
    assert all(isinstance(x, str) for x in R["recalculation_order"])


# ─── Initial snapshot values ──────────────────────────────────────────────────


def test_init_01_sum_formula():
    assert R["initial_snapshot"]["A3"] == 30


def test_init_02_multiply_chain():
    assert R["initial_snapshot"]["B2"] == 150


def test_init_03_aggregate_avg():
    assert math.isclose(R["initial_snapshot"]["C1"], 11.666667, abs_tol=ATOL)


def test_init_04_conditional_select():
    assert R["initial_snapshot"]["C2"] == 35


def test_init_05_division_output():
    assert math.isclose(R["initial_snapshot"]["D2"], 0.666667, abs_tol=ATOL)


def test_init_06_division_roundtrip():
    assert R["initial_snapshot"]["D3"] == 2


def test_init_07_chain_product():
    assert R["initial_snapshot"]["E1"] == 15


def test_init_08_chain_depth_2():
    assert R["initial_snapshot"]["E2"] == 30


def test_init_09_chain_depth_3():
    assert R["initial_snapshot"]["E3"] == 40


def test_init_10_division_output_f():
    assert math.isclose(R["initial_snapshot"]["F2"], 14.285714, abs_tol=ATOL)


def test_init_11_division_roundtrip_f():
    assert R["initial_snapshot"]["F3"] == 100


def test_init_12_wide_sum():
    assert R["initial_snapshot"]["G4"] == 6


def test_init_13_compound_expr():
    assert R["initial_snapshot"]["P1"] == 25


def test_init_14_precision_chain_p():
    assert math.isclose(R["initial_snapshot"]["P2"], 4.166667, abs_tol=ATOL)


def test_init_15_product_precision():
    assert math.isclose(R["initial_snapshot"]["P3"], 104.166667, abs_tol=ATOL)


def test_init_16_countif_result():
    assert R["initial_snapshot"]["Q1"] == 2


def test_init_17_conditional_branch():
    assert R["initial_snapshot"]["R1"] == 2


def test_init_18_division_roundtrip_s():
    assert R["initial_snapshot"]["S3"] == 50


def test_init_19_wide_sum_t():
    assert R["initial_snapshot"]["T1"] == 43


def test_init_20_cross_ref_u():
    assert R["initial_snapshot"]["U1"] == 68


def test_init_21_round_function():
    assert math.isclose(R["initial_snapshot"]["U2"], 4.17, abs_tol=TIGHT)


def test_init_22_s2_division():
    assert math.isclose(R["initial_snapshot"]["S2"], 4.545455, abs_tol=ATOL)


# ─── Precision semantics ─────────────────────────────────────────────────────


def test_eval_01_d2_times_3_exact():
    assert R["initial_snapshot"]["D3"] == 2, "D2*3 must equal D1 exactly"


def test_eval_02_f2_times_7_exact():
    assert R["initial_snapshot"]["F3"] == 100, "F2*7 must equal F1 exactly"


def test_eval_03_s2_times_11_exact():
    assert R["initial_snapshot"]["S3"] == 50, "S2*11 must equal S1 exactly"


def test_eval_04_final_d3_exact():
    assert R["final_values"]["D3"] == 7, "D2*3 with D1=7 must equal 7 exactly"


def test_eval_05_final_f3_exact():
    assert R["final_values"]["F3"] == 100


def test_eval_06_d2_output_rounded():
    assert math.isclose(R["final_values"]["D2"], 2.333333, abs_tol=ATOL)


def test_eval_07_f2_output_rounded():
    assert math.isclose(R["final_values"]["F2"], 14.285714, abs_tol=ATOL)


def test_eval_08_precision_not_premature():
    d3_init = R["initial_snapshot"]["D3"]
    assert d3_init == 2, f"Expected 2, got {d3_init} (premature rounding?)"


def test_eval_09_precision_chain_f():
    f3_init = R["initial_snapshot"]["F3"]
    assert f3_init == 100, f"Expected 100, got {f3_init} (premature rounding?)"


def test_eval_10_precision_chain_s():
    s3_init = R["initial_snapshot"]["S3"]
    assert s3_init == 50, f"Expected 50, got {s3_init} (premature rounding?)"


def test_eval_11_final_s3_correct():
    assert R["final_values"]["S3"] == 110


def test_eval_12_p2_precision():
    p2_init = R["initial_snapshot"]["P2"]
    assert math.isclose(p2_init, 4.166667, abs_tol=TIGHT)


# ─── Conditional and error semantics ──────────────────────────────────────────


def test_cond_01_branch_not_null():
    assert R["final_values"]["L1"] is not None


def test_cond_02_correct_branch_value():
    assert R["final_values"]["L1"] == 5


def test_cond_03_not_in_errors():
    assert "L1" not in R["errors"]


def test_cond_04_initial_conditional():
    assert R["initial_snapshot"]["C2"] == 35


def test_cond_05_conditional_r1():
    assert R["initial_snapshot"]["R1"] == 2


def test_cond_06_final_r1():
    assert R["final_values"]["R1"] == 7


# ─── Cycle detection and graph structure ──────────────────────────────────────


def test_graph_01_cycle_count():
    assert len(R["cycles_detected"]) == 1, (
        f"Expected 1 cycle, found {len(R['cycles_detected'])}"
    )


def test_graph_02_cycle_members():
    cycle = R["cycles_detected"][0]
    members = set(cycle)
    assert {"K1", "K2", "K3"} <= members


def test_graph_03_cycle_is_closed():
    cycle = R["cycles_detected"][0]
    assert cycle[0] == cycle[-1], "Cycle path must be closed"


def test_graph_04_diamond_not_cyclic():
    all_cycle_cells = set()
    for cycle in R["cycles_detected"]:
        all_cycle_cells.update(cycle)
    for cid in ["F1", "F4", "F5", "F6"]:
        assert cid not in all_cycle_cells, f"{cid} falsely in cycle"


def test_graph_05_chain_not_cyclic():
    all_cycle_cells = set()
    for cycle in R["cycles_detected"]:
        all_cycle_cells.update(cycle)
    for cid in ["H1", "H2", "H3"]:
        assert cid not in all_cycle_cells, f"{cid} falsely in cycle"


def test_graph_06_no_false_positives():
    all_cycle_cells = set()
    for cycle in R["cycles_detected"]:
        all_cycle_cells.update(cycle)
    for cid in all_cycle_cells:
        assert cid.startswith("K"), f"Non-K cell {cid} reported in cycle"


def test_graph_07_n_chain_not_cyclic():
    all_cycle_cells = set()
    for cycle in R["cycles_detected"]:
        all_cycle_cells.update(cycle)
    for cid in ["N1", "N2", "N3"]:
        assert cid not in all_cycle_cells


def test_graph_08_p_chain_not_cyclic():
    all_cycle_cells = set()
    for cycle in R["cycles_detected"]:
        all_cycle_cells.update(cycle)
    for cid in ["P1", "P2", "P3"]:
        assert cid not in all_cycle_cells


# ─── Dependency isolation (formula update path) ──────────────────────────────


def test_update_01_cascade_excludes_detached():
    recalced = R["updates"][2]["recalculated_cells"]
    assert "A3" not in recalced, "A3 recalculated despite formula change"


def test_update_02_transitive_excluded():
    recalced = R["updates"][2]["recalculated_cells"]
    assert "B2" not in recalced, "B2 recalculated via phantom dependency"


def test_update_03_other_deps_included():
    recalced = set(R["updates"][2]["recalculated_cells"])
    for cid in ["B3", "C1", "E1", "E2", "E3", "P1", "T1"]:
        assert cid in recalced, f"{cid} missing from update 2 cascade"


def test_update_04_formula_change_isolates():
    recalced = R["updates"][25]["recalculated_cells"]
    assert "E1" not in recalced, "E1 should not recalc after formula change"


def test_update_05_transitive_isolation():
    recalced = R["updates"][25]["recalculated_cells"]
    assert "E2" not in recalced, "E2 should not recalc when E1 unchanged"


def test_update_06_direct_dep_still_works():
    recalced = R["updates"][25]["recalculated_cells"]
    assert "E3" in recalced, "E3 depends on A1 directly"


def test_update_07_cascade_includes_new_cells():
    recalced = set(R["updates"][0]["recalculated_cells"])
    for cid in ["A3", "B2", "B3", "C1", "C2", "E1", "E2", "E3"]:
        assert cid in recalced


def test_update_08_new_cells_in_cascade():
    recalced = set(R["updates"][0]["recalculated_cells"])
    for cid in ["P1", "P2", "P3", "T1"]:
        assert cid in recalced


# ─── Batch formula dependency isolation ───────────────────────────────────────


def test_update_09_batch_formula_isolates():
    recalced = R["updates"][27]["recalculated_cells"]
    assert "E3" not in recalced, "E3 recalculated despite batch formula change"


def test_update_10_batch_formula_no_old_chain():
    recalced = R["updates"][27]["recalculated_cells"]
    assert "E2" not in recalced


def test_update_11_batch_formula_no_e1():
    recalced = R["updates"][27]["recalculated_cells"]
    assert "E1" not in recalced


def test_update_12_batch_deps_correct():
    recalced = set(R["updates"][27]["recalculated_cells"])
    for cid in ["B3", "C1", "N1", "N2", "N3", "Q1", "T1"]:
        assert cid in recalced, f"{cid} missing from update 27"


# ─── Type transition dependency isolation ─────────────────────────────────────


def test_update_13_value_transition_p1_gone():
    recalced = R["updates"][27]["recalculated_cells"]
    assert "P1" not in recalced, "P1 (now value) should not recalculate"


def test_update_14_value_transition_p2_gone():
    recalced = R["updates"][27]["recalculated_cells"]
    assert "P2" not in recalced, "P2 should not recalc via stale P1 dep"


def test_update_15_value_transition_p3_gone():
    recalced = R["updates"][27]["recalculated_cells"]
    assert "P3" not in recalced, "P3 should not recalc via stale P1 dep"


def test_update_16_value_transition_u2_gone():
    recalced = R["updates"][27]["recalculated_cells"]
    assert "U2" not in recalced, "U2 depends on P2 which should not recalc"


def test_update_17_single_value_transition():
    recalced = R["updates"][29]["recalculated_cells"]
    assert len(recalced) == 0, f"Expected empty, got {recalced}"


def test_update_18_s2_not_recalculated():
    recalced = R["updates"][29]["recalculated_cells"]
    assert "S2" not in recalced, "S2 (now value) should not recalculate"


def test_update_19_s3_not_recalculated():
    recalced = R["updates"][29]["recalculated_cells"]
    assert "S3" not in recalced, "S3 should not recalc via stale S2 dep"


def test_update_20_transition_then_recalc():
    recalced = R["updates"][28]["recalculated_cells"]
    assert "S3" in recalced, "S3 should recalc when S2 value changes"


def test_update_21_batch_transition_p2_recalc():
    recalced = R["updates"][26]["recalculated_cells"]
    assert "P2" in recalced, "P2 should recalc when P1 value changes in batch"


def test_update_22_batch_transition_e3_recalc():
    recalced = R["updates"][26]["recalculated_cells"]
    assert "E3" in recalced, "E3 should recalc when its formula changes in batch"


# ─── Evaluation ordering ─────────────────────────────────────────────────────


def test_order_01_topo_a3_before_b2():
    recalced = R["updates"][0]["recalculated_cells"]
    assert recalced.index("A3") < recalced.index("B2")


def test_order_02_chain_e1_e2_e3():
    recalced = R["updates"][0]["recalculated_cells"]
    assert recalced.index("E1") < recalced.index("E2") < recalced.index("E3")


def test_order_03_siblings_alphabetical():
    recalced = R["updates"][19]["recalculated_cells"]
    m_cells = [c for c in recalced if c.startswith("M")]
    assert m_cells == ["M1", "M2", "M3"], f"M ordering: {m_cells}"


def test_order_04_parent_before_child():
    recalced = R["updates"][15]["recalculated_cells"]
    if "G4" in recalced and "H1" in recalced:
        assert recalced.index("G4") < recalced.index("H1")


def test_order_05_n_chain_ordered():
    recalced = R["updates"][23]["recalculated_cells"]
    n1 = recalced.index("N1")
    n2 = recalced.index("N2")
    n3 = recalced.index("N3")
    assert n1 < n2 < n3


def test_order_06_batch30_g4_before_deps():
    recalced = R["updates"][30]["recalculated_cells"]
    assert recalced.index("G4") < recalced.index("H1")
    assert recalced.index("G4") < recalced.index("M1")


def test_order_07_batch30_m_alphabetical():
    recalced = R["updates"][30]["recalculated_cells"]
    m_cells = [c for c in recalced if c.startswith("M")]
    assert m_cells == ["M1", "M2", "M3"]


def test_order_08_batch30_h_chain():
    recalced = R["updates"][30]["recalculated_cells"]
    assert recalced.index("H1") < recalced.index("H2") < recalced.index("H3")


def test_order_09_batch30_e_chain():
    recalced = R["updates"][30]["recalculated_cells"]
    assert recalced.index("E1") < recalced.index("E2") < recalced.index("E3")


def test_order_10_update31_d_chain():
    recalced = R["updates"][31]["recalculated_cells"]
    assert recalced.index("D2") < recalced.index("D3")


# ─── Final values ─────────────────────────────────────────────────────────────


def test_final_01_a1():
    assert R["final_values"]["A1"] == 5


def test_final_02_a3():
    assert R["final_values"]["A3"] == 10


def test_final_03_b2():
    assert R["final_values"]["B2"] == 50


def test_final_04_b3():
    assert R["final_values"]["B3"] == 30


def test_final_05_c1():
    assert R["final_values"]["C1"] == 10


def test_final_06_c2():
    assert R["final_values"]["C2"] == 30


def test_final_07_e1():
    assert R["final_values"]["E1"] == 55


def test_final_08_e2():
    assert R["final_values"]["E2"] == 110


def test_final_09_e3():
    assert R["final_values"]["E3"] == 70


def test_final_10_g4():
    assert R["final_values"]["G4"] == 85


def test_final_11_f4():
    assert R["final_values"]["F4"] == 101


def test_final_12_f5():
    assert R["final_values"]["F5"] == 102


def test_final_13_f6():
    assert R["final_values"]["F6"] == 203


def test_final_14_h1():
    assert R["final_values"]["H1"] == 95


def test_final_15_h2():
    assert R["final_values"]["H2"] == 96


def test_final_16_h3():
    assert R["final_values"]["H3"] == 97


def test_final_17_k_null():
    assert R["final_values"]["K1"] is None
    assert R["final_values"]["K2"] is None
    assert R["final_values"]["K3"] is None


def test_final_18_m1():
    assert R["final_values"]["M1"] == 86


def test_final_19_m2():
    assert R["final_values"]["M2"] == 87


def test_final_20_m3():
    assert R["final_values"]["M3"] == 88


def test_final_21_n1():
    assert R["final_values"]["N1"] == 6


def test_final_22_n2():
    assert R["final_values"]["N2"] == 12


def test_final_23_n3():
    assert R["final_values"]["N3"] == 17


def test_final_24_p1():
    assert R["final_values"]["P1"] == 42


def test_final_25_p2():
    assert R["final_values"]["P2"] == 7


def test_final_26_p3():
    assert R["final_values"]["P3"] == 294


def test_final_27_q1():
    assert R["final_values"]["Q1"] == 1


def test_final_28_s1():
    assert R["final_values"]["S1"] == 99


def test_final_29_s2():
    assert R["final_values"]["S2"] == 10


def test_final_30_t1():
    assert R["final_values"]["T1"] == 122


def test_final_31_u1():
    assert R["final_values"]["U1"] == 164


def test_final_32_u2():
    assert R["final_values"]["U2"] == 7


def test_final_33_d1():
    assert R["final_values"]["D1"] == 7


# ─── Error state ──────────────────────────────────────────────────────────────


def test_error_01_k_in_errors():
    for cid in ["K1", "K2", "K3"]:
        assert cid in R["errors"], f"{cid} missing from errors"


def test_error_02_only_cycle_errors():
    for cid in R["errors"]:
        assert cid.startswith("K"), f"Non-cycle cell {cid} in errors"


def test_error_03_null_values():
    for cid in R["errors"]:
        assert R["final_values"][cid] is None


# ─── Recalculation counts ───────────────────────────────────────────────────


def test_audit_01_value_cells_zero():
    for cid in ["A1", "A2", "B1", "D1", "F1", "G1", "G2", "G3", "S1"]:
        assert R["recalc_counts"][cid] == 0, f"{cid} should have 0 recalcs"


def test_audit_02_a3_count():
    assert R["recalc_counts"]["A3"] == 3


def test_audit_03_b2_count():
    assert R["recalc_counts"]["B2"] == 3


def test_audit_04_e3_count():
    assert R["recalc_counts"]["E3"] == 8


def test_audit_05_l1_count():
    assert R["recalc_counts"]["L1"] == 4


def test_audit_06_p1_count():
    assert R["recalc_counts"]["P1"] == 5


def test_audit_07_p2_count():
    assert R["recalc_counts"]["P2"] == 6


def test_audit_08_s2_count():
    assert R["recalc_counts"]["S2"] == 1


def test_audit_09_s3_count():
    assert R["recalc_counts"]["S3"] == 2


def test_audit_10_t1_count():
    assert R["recalc_counts"]["T1"] == 11


def test_audit_11_u1_count():
    assert R["recalc_counts"]["U1"] == 12


def test_audit_12_g4_count():
    assert R["recalc_counts"]["G4"] == 4


def test_audit_13_m_cells_count():
    for cid in ["M1", "M2", "M3"]:
        assert R["recalc_counts"][cid] == 3


def test_audit_14_n_cells_count():
    for cid in ["N1", "N2", "N3"]:
        assert R["recalc_counts"][cid] == 4


def test_audit_15_q1_count():
    assert R["recalc_counts"]["Q1"] == 8


# ─── Cross-field consistency ─────────────────────────────────────────────────


def test_consistency_01_all_initial_in_final():
    for cid in R["initial_snapshot"]:
        assert cid in R["final_values"], f"{cid} missing from final"


def test_consistency_02_error_cells_null():
    for cid in R["errors"]:
        assert R["final_values"][cid] is None


def test_consistency_03_recalc_matches_order():
    order_counts = Counter(R["recalculation_order"])
    for cid, count in R["recalc_counts"].items():
        assert order_counts.get(cid, 0) == count, (
            f"{cid}: count={count}, order={order_counts.get(cid, 0)}"
        )


def test_consistency_04_total_recalc_events():
    total_from_updates = sum(
        len(u["recalculated_cells"]) for u in R["updates"]
    )
    initial_formula_count = sum(
        1 for v in R["initial_snapshot"].values() if v is not None
    ) - sum(1 for k in R["initial_snapshot"] if R["recalc_counts"].get(k, 0) == 0)
    assert len(R["recalculation_order"]) == total_from_updates + initial_formula_count


def test_consistency_05_update_indices():
    for i, u in enumerate(R["updates"]):
        assert u["index"] == i


def test_consistency_06_cell_count():
    assert len(R["final_values"]) == 48
