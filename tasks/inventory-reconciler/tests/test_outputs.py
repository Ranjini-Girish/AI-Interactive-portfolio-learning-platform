"""Tests for js-inventory-reconciler task."""
import json
import math
from pathlib import Path

REPORT_PATH = Path("/app/output/report.json")


def load_report():
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    with open(REPORT_PATH) as f:
        return json.load(f)


# ── Structure tests ──────────────────────────────────────────────────


def test_report_exists():
    assert REPORT_PATH.exists()


def test_report_valid_json():
    load_report()


def test_report_has_summary():
    r = load_report()
    assert "summary" in r


def test_report_has_warehouse_values():
    r = load_report()
    assert "warehouse_values" in r


def test_report_has_category_totals():
    r = load_report()
    assert "category_totals" in r


def test_report_has_supplier_stats():
    r = load_report()
    assert "supplier_stats" in r


def test_report_has_anomalies():
    r = load_report()
    assert "anomalies" in r


def test_report_has_validation():
    r = load_report()
    assert "validation" in r


def test_report_has_product_ranking():
    r = load_report()
    assert "product_ranking" in r


# ── Summary tests ────────────────────────────────────────────────────


def test_total_products():
    s = load_report()["summary"]
    assert s["total_products"] == 12


def test_total_transactions():
    s = load_report()["summary"]
    assert s["total_transactions"] == 15


def test_matched_products():
    """Bug 1 check: all 15 transactions must match after fixing replace."""
    s = load_report()["summary"]
    assert s["matched_products"] == 15, (
        f"Expected 15 matched, got {s['matched_products']}. "
        "Check that normalizeId removes ALL hyphens, not just the first."
    )


def test_unmatched_products_zero():
    """Bug 1 check: no unmatched transactions."""
    s = load_report()["summary"]
    assert s["unmatched_products"] == 0, (
        f"Expected 0 unmatched, got {s['unmatched_products']}."
    )


def test_total_sale_revenue():
    """Bug 1 impacts revenue — all sales must be counted."""
    s = load_report()["summary"]
    assert math.isclose(s["total_sale_revenue"], 3294.30, rel_tol=1e-3), (
        f"Expected ~3294.30, got {s['total_sale_revenue']}"
    )


def test_total_purchase_cost():
    s = load_report()["summary"]
    assert math.isclose(s["total_purchase_cost"], 2665.0, rel_tol=1e-3), (
        f"Expected ~2665.0, got {s['total_purchase_cost']}"
    )


def test_median_transaction_amount():
    """Bug 2 check: must use numeric sort, not lexicographic."""
    s = load_report()["summary"]
    assert math.isclose(s["median_transaction_amount"], 299.88, rel_tol=1e-3), (
        f"Expected 299.88 (numeric median), got {s['median_transaction_amount']}. "
        "If 299.7, sort() is using default lexicographic comparison."
    )


def test_median_not_lexicographic():
    """Explicit check that median is NOT the lexicographic value."""
    s = load_report()["summary"]
    assert s["median_transaction_amount"] != 299.7, (
        "Median 299.7 indicates lexicographic sort — must use numeric comparator."
    )


# ── Warehouse value tests ───────────────────────────────────────────


def test_warehouse_north_value():
    wv = load_report()["warehouse_values"]
    assert math.isclose(wv["warehouse_north"], 14453.20, rel_tol=1e-3)


def test_warehouse_south_value():
    wv = load_report()["warehouse_values"]
    assert math.isclose(wv["warehouse_south"], 15958.15, rel_tol=1e-3)


def test_warehouse_count():
    wv = load_report()["warehouse_values"]
    assert len(wv) == 2


# ── Category totals tests ───────────────────────────────────────────


def test_electronics_sale_count():
    ct = load_report()["category_totals"]
    assert ct["electronics"]["sale_count"] == 6, (
        f"Expected 6 electronics sales, got {ct['electronics']['sale_count']}. "
        "Board Epsilon (EXT-COMP-005) sale must be included."
    )


def test_electronics_sale_revenue():
    ct = load_report()["category_totals"]
    assert math.isclose(ct["electronics"]["sale_revenue"], 1898.62, rel_tol=1e-3)


def test_hardware_sale_count():
    ct = load_report()["category_totals"]
    assert ct["hardware"]["sale_count"] == 3


def test_hardware_sale_revenue():
    ct = load_report()["category_totals"]
    assert math.isclose(ct["hardware"]["sale_revenue"], 726.38, rel_tol=1e-3)


def test_hardware_purchase_count():
    ct = load_report()["category_totals"]
    assert ct["hardware"]["purchase_count"] == 3


def test_hardware_purchase_cost():
    ct = load_report()["category_totals"]
    assert math.isclose(ct["hardware"]["purchase_cost"], 2665.0, rel_tol=1e-3)


def test_accessories_sale_count():
    ct = load_report()["category_totals"]
    assert ct["accessories"]["sale_count"] == 3, (
        f"Expected 3 accessories sales, got {ct['accessories']['sale_count']}. "
        "Adapter Theta (SUP-ITEM-008) must be included."
    )


def test_accessories_sale_revenue():
    ct = load_report()["category_totals"]
    assert math.isclose(ct["accessories"]["sale_revenue"], 669.30, rel_tol=1e-3)


def test_category_count():
    ct = load_report()["category_totals"]
    assert len(ct) == 3


def test_total_sale_count_across_categories():
    ct = load_report()["category_totals"]
    total = sum(ct[c]["sale_count"] for c in ct)
    assert total == 12


# ── Supplier stats tests ────────────────────────────────────────────


def test_supplier_total():
    ss = load_report()["supplier_stats"]
    assert ss["total_suppliers"] == 9


def test_supplier_avg_rating():
    ss = load_report()["supplier_stats"]
    assert math.isclose(ss["avg_rating"], 4.14, abs_tol=0.02)


def test_supplier_avg_lead_days():
    ss = load_report()["supplier_stats"]
    assert math.isclose(ss["avg_lead_days"], 12.67, abs_tol=0.02)


def test_supplier_null_count():
    ss = load_report()["supplier_stats"]
    assert ss["products_without_supplier"] == 3


# ── Anomaly tests ────────────────────────────────────────────────────


def test_anomaly_count():
    """Bugs 3+4: exactly 3 no_supplier anomalies, 0 low_stock."""
    a = load_report()["anomalies"]
    assert len(a) == 3, (
        f"Expected 3 anomalies, got {len(a)}. "
        "3 null-supplier products should produce no_supplier anomalies."
    )


def test_anomaly_types_all_no_supplier():
    """Bug 3 check: typeof null must not pass object check."""
    a = load_report()["anomalies"]
    types = [x["type"] for x in a]
    assert all(t == "no_supplier" for t in types), (
        f"All anomalies should be no_supplier, got {types}"
    )


def test_anomaly_product_ids():
    a = load_report()["anomalies"]
    ids = sorted(x["product_id"] for x in a)
    assert ids == ["MFG-PART-003", "PROD-007", "PROD-012"]


def test_no_false_low_stock():
    """Bug 4 check: shallow copy must not inflate lowStockMultiplier."""
    a = load_report()["anomalies"]
    low_stock = [x for x in a if x["type"] == "low_stock"]
    assert len(low_stock) == 0, (
        f"Found {len(low_stock)} low_stock anomalies. "
        "If PROD-009 is flagged, config.thresholds is being mutated via shallow copy."
    )


def test_no_prod009_anomaly():
    """Bug 4 specific: PROD-009 (qty=15, min=10) should NOT be low_stock."""
    a = load_report()["anomalies"]
    prod009 = [x for x in a if x["product_id"] == "PROD-009"]
    assert len(prod009) == 0, (
        "PROD-009 flagged as anomaly — lowStockMultiplier was mutated."
    )


def test_anomalies_sorted_by_product_id():
    a = load_report()["anomalies"]
    ids = [x["product_id"] for x in a]
    assert ids == sorted(ids)


# ── Validation tests ────────────────────────────────────────────────


def test_validation_total_checked():
    v = load_report()["validation"]
    assert v["total_checked"] == 12


def test_validation_all_valid():
    """Bug 6 check: RegExp /g flag must be removed so all IDs validate."""
    v = load_report()["validation"]
    assert v["valid_count"] == 12, (
        f"Expected 12 valid, got {v['valid_count']}. "
        "If 6, the RegExp /g flag is causing lastIndex state leak."
    )


def test_validation_none_invalid():
    v = load_report()["validation"]
    assert v["invalid_count"] == 0, (
        f"Expected 0 invalid, got {v['invalid_count']}."
    )


def test_validation_invalid_ids_empty():
    v = load_report()["validation"]
    assert v["invalid_ids"] == []


def test_validation_not_alternating():
    """Bug 6 specific: check that validation isn't alternating valid/invalid."""
    v = load_report()["validation"]
    assert v["valid_count"] != 6, (
        "Exactly 6 valid IDs indicates alternating lastIndex leak from /g flag."
    )


# ── Product ranking tests ───────────────────────────────────────────


def test_product_ranking_count():
    """Bug 1 impact: all 10 sold products should appear in ranking."""
    pr = load_report()["product_ranking"]
    assert len(pr) == 10, (
        f"Expected 10 products in ranking, got {len(pr)}. "
        "Products with multi-hyphen IDs must match after fixing normalizeId."
    )


def test_product_ranking_sorted_alphabetically():
    """Bug 5 check: sort comparator must return number, not boolean."""
    pr = load_report()["product_ranking"]
    names = [p["name"] for p in pr]
    assert names == sorted(names), (
        f"product_ranking not sorted alphabetically: {names}. "
        "Sort comparator (a, b) => a.name > b.name returns boolean, not number."
    )


def test_product_ranking_first_item():
    pr = load_report()["product_ranking"]
    assert pr[0]["name"] == "Adapter Theta"


def test_product_ranking_last_item():
    pr = load_report()["product_ranking"]
    assert pr[-1]["name"] == "Widget Beta"


def test_product_ranking_relay_lambda_quantity():
    pr = load_report()["product_ranking"]
    rl = [p for p in pr if p["name"] == "Relay Lambda"]
    assert len(rl) == 1
    assert rl[0]["total_sold"] == 100


def test_product_ranking_cable_delta_quantity():
    pr = load_report()["product_ranking"]
    cd = [p for p in pr if p["name"] == "Cable Delta"]
    assert len(cd) == 1
    assert cd[0]["total_sold"] == 55


def test_product_ranking_widget_alpha_quantity():
    pr = load_report()["product_ranking"]
    wa = [p for p in pr if p["name"] == "Widget Alpha"]
    assert len(wa) == 1
    assert wa[0]["total_sold"] == 30


def test_product_ranking_adapter_theta_present():
    """Bug 1 impact: SUP-ITEM-008 must be in ranking after fix."""
    pr = load_report()["product_ranking"]
    at = [p for p in pr if p["name"] == "Adapter Theta"]
    assert len(at) == 1
    assert at[0]["total_sold"] == 15


def test_product_ranking_fan_kappa_present():
    """Bug 1 impact: WH-BULK-010 must be in ranking after fix."""
    pr = load_report()["product_ranking"]
    fk = [p for p in pr if p["name"] == "Fan Kappa"]
    assert len(fk) == 1
    assert fk[0]["total_sold"] == 12


def test_product_ranking_gadget_gamma_present():
    """Bug 1 impact: MFG-PART-003 must be in ranking after fix."""
    pr = load_report()["product_ranking"]
    gg = [p for p in pr if p["name"] == "Gadget Gamma"]
    assert len(gg) == 1
    assert gg[0]["total_sold"] == 3


def test_product_ranking_board_epsilon_present():
    """Bug 1 impact: EXT-COMP-005 must be in ranking after fix."""
    pr = load_report()["product_ranking"]
    be = [p for p in pr if p["name"] == "Board Epsilon"]
    assert len(be) == 1
    assert be[0]["total_sold"] == 2


# ── Cross-validation tests ──────────────────────────────────────────


def test_sale_revenue_matches_category_sum():
    r = load_report()
    cat_revenue = sum(
        r["category_totals"][c]["sale_revenue"]
        for c in r["category_totals"]
    )
    assert math.isclose(r["summary"]["total_sale_revenue"], cat_revenue, rel_tol=1e-3)


def test_purchase_cost_matches_category_sum():
    r = load_report()
    cat_cost = sum(
        r["category_totals"][c]["purchase_cost"]
        for c in r["category_totals"]
    )
    assert math.isclose(r["summary"]["total_purchase_cost"], cat_cost, rel_tol=1e-3)


def test_ranking_total_matches_sale_transactions():
    r = load_report()
    ranking_total = sum(p["total_sold"] for p in r["product_ranking"])
    txn_sale_qty = 10 + 5 + 3 + 25 + 2 + 8 + 15 + 1 + 12 + 100 + 20 + 30
    assert ranking_total == txn_sale_qty


def test_warehouse_total_value():
    wv = load_report()["warehouse_values"]
    total = sum(wv.values())
    assert math.isclose(total, 30411.35, rel_tol=1e-3)


def test_anomaly_ids_are_null_suppliers():
    """Cross-check anomaly IDs against known null suppliers."""
    r = load_report()
    anomaly_ids = {a["product_id"] for a in r["anomalies"]}
    null_suppliers = {"MFG-PART-003", "PROD-007", "PROD-012"}
    assert anomaly_ids == null_suppliers
