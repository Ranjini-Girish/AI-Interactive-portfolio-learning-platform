"""Tests for csv-reconciliation-audit task."""
import json
import math
import pathlib

import pytest  # noqa: F401

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
FLOAT_TOL = 0.005


def load_report():
    """Load and return the reconciliation report JSON."""
    p = OUT_DIR / "reconciliation_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


# ─── Output file existence ────────────────────────────────────────────────────


def test_output_file_exists():
    """Verify the reconciliation report file was created."""
    assert (OUT_DIR / "reconciliation_report.json").is_file()


def test_valid_json():
    """Verify the output is valid JSON with all top-level keys."""
    required = {
        "summary", "unsettled_transactions", "orphan_settlements",
        "amount_mismatches", "ledger_imbalances", "duplicate_pairs",
        "volume_by_currency",
    }
    assert required.issubset(set(R.keys())), f"Missing keys: {required - set(R.keys())}"


# ─── Summary counts ──────────────────────────────────────────────────────────


def test_total_transactions():
    """Verify total transaction count is 20."""
    assert R["summary"]["total_transactions"] == 20


def test_settled_count():
    """Verify 18 out of 20 transactions have matching settlements."""
    assert R["summary"]["settled_count"] == 18


def test_unsettled_count():
    """Verify 2 transactions have no settlement."""
    assert R["summary"]["unsettled_count"] == 2


def test_orphan_count():
    """Verify 1 orphan settlement exists."""
    assert R["summary"]["orphan_count"] == 1


def test_mismatch_count():
    """Verify 1 amount mismatch between transaction and settlement."""
    assert R["summary"]["mismatch_count"] == 1


def test_imbalance_count():
    """Verify 2 ledger imbalances detected."""
    assert R["summary"]["imbalance_count"] == 2


def test_duplicate_pair_count():
    """Verify 1 duplicate pair detected."""
    assert R["summary"]["duplicate_pair_count"] == 1


# ─── Volume and fee aggregation ───────────────────────────────────────────────


def test_total_volume_usd():
    """Verify total volume in USD includes EUR conversion at configured rate."""
    assert math.isclose(R["summary"]["total_volume_usd"], 15696.74, abs_tol=FLOAT_TOL)


def test_total_fees():
    """Verify total fees sum from matched settlements only, excluding orphans."""
    assert math.isclose(R["summary"]["total_fees_usd"], 30.75, abs_tol=FLOAT_TOL)


def test_fee_rate_percent():
    """Verify fee rate is fees/volume*100 rounded to 2 decimal places."""
    assert math.isclose(R["summary"]["fee_rate_percent"], 0.20, abs_tol=FLOAT_TOL)


# ─── Unsettled transactions ──────────────────────────────────────────────────


def test_unsettled_list():
    """Verify T007 and T018 are the unsettled transactions."""
    assert sorted(R["unsettled_transactions"]) == ["T007", "T018"]


def test_unsettled_excludes_settled():
    """Verify settled transactions do not appear in unsettled list."""
    for tid in ["T001", "T005", "T008", "T020"]:
        assert tid not in R["unsettled_transactions"]


# ─── Orphan settlements ──────────────────────────────────────────────────────


def test_orphan_settlement_s099():
    """Verify S099 is detected as orphan referencing nonexistent T999."""
    orphans = R["orphan_settlements"]
    assert len(orphans) == 1
    assert orphans[0]["settlement_id"] == "S099"
    assert orphans[0]["txn_id"] == "T999"


def test_orphan_amount():
    """Verify orphan settlement amount is 350.00."""
    assert math.isclose(R["orphan_settlements"][0]["amount"], 350.00, abs_tol=FLOAT_TOL)


# ─── Amount mismatches ───────────────────────────────────────────────────────


def test_mismatch_t005():
    """Verify T005 flagged: txn=1000.00 vs settled=999.50, diff=0.50."""
    mismatches = R["amount_mismatches"]
    assert len(mismatches) == 1
    m = mismatches[0]
    assert m["txn_id"] == "T005"


def test_mismatch_t005_amounts():
    """Verify T005 mismatch amounts are precisely reported."""
    m = R["amount_mismatches"][0]
    assert math.isclose(m["txn_amount"], 1000.00, abs_tol=FLOAT_TOL)
    assert math.isclose(m["settled_amount"], 999.50, abs_tol=FLOAT_TOL)
    assert math.isclose(m["difference"], 0.50, abs_tol=FLOAT_TOL)


def test_no_false_mismatch():
    """Verify transactions with matching amounts are not flagged."""
    tids = [m["txn_id"] for m in R["amount_mismatches"]]
    assert "T001" not in tids
    assert "T008" not in tids


# ─── Ledger imbalances ───────────────────────────────────────────────────────


def test_imbalance_count_is_two():
    """Verify exactly two ledger imbalances are detected."""
    assert len(R["ledger_imbalances"]) == 2


def test_imbalance_t005():
    """Verify T005 ledger imbalance: debit=1000.00, credit=999.50."""
    imbs = {x["txn_id"]: x for x in R["ledger_imbalances"]}
    assert "T005" in imbs
    assert math.isclose(imbs["T005"]["total_debit"], 1000.00, abs_tol=FLOAT_TOL)
    assert math.isclose(imbs["T005"]["total_credit"], 999.50, abs_tol=FLOAT_TOL)
    assert math.isclose(imbs["T005"]["imbalance"], 0.50, abs_tol=FLOAT_TOL)


def test_imbalance_t013():
    """Verify T013 ledger imbalance: debit=600.00, credit=599.20."""
    imbs = {x["txn_id"]: x for x in R["ledger_imbalances"]}
    assert "T013" in imbs
    assert math.isclose(imbs["T013"]["total_debit"], 600.00, abs_tol=FLOAT_TOL)
    assert math.isclose(imbs["T013"]["total_credit"], 599.20, abs_tol=FLOAT_TOL)
    assert math.isclose(imbs["T013"]["imbalance"], 0.80, abs_tol=FLOAT_TOL)


def test_no_false_imbalance():
    """Verify balanced transactions are not flagged as imbalances."""
    tids = [x["txn_id"] for x in R["ledger_imbalances"]]
    assert "T001" not in tids
    assert "T008" not in tids


# ─── Duplicate detection ─────────────────────────────────────────────────────


def test_duplicate_pair_detected():
    """Verify T001 and T014 detected as duplicates (same acct, amount, desc within 7 days)."""
    dups = R["duplicate_pairs"]
    assert len(dups) == 1


def test_duplicate_pair_ids():
    """Verify the duplicate pair contains T001 and T014 sorted."""
    pair = R["duplicate_pairs"][0]
    assert sorted(pair["txn_ids"]) == ["T001", "T014"]


def test_duplicate_pair_details():
    """Verify duplicate pair metadata: account A10, amount 100.00."""
    pair = R["duplicate_pairs"][0]
    assert pair["account_id"] == "A10"
    assert math.isclose(pair["amount"], 100.00, abs_tol=FLOAT_TOL)


def test_t020_not_duplicate():
    """Verify T020 (different account A12) is not flagged as duplicate of T001/T014."""
    all_dup_ids = []
    for dp in R["duplicate_pairs"]:
        all_dup_ids.extend(dp["txn_ids"])
    assert "T020" not in all_dup_ids


# ─── Volume by currency ──────────────────────────────────────────────────────


def test_usd_count():
    """Verify 16 USD transactions counted."""
    assert R["volume_by_currency"]["USD"]["count"] == 16


def test_usd_total():
    """Verify USD total is 12712.99."""
    assert math.isclose(R["volume_by_currency"]["USD"]["total"], 12712.99, abs_tol=FLOAT_TOL)


def test_eur_count():
    """Verify 4 EUR transactions counted."""
    assert R["volume_by_currency"]["EUR"]["count"] == 4


def test_eur_total_eur():
    """Verify EUR total in native currency is 2750.00."""
    assert math.isclose(R["volume_by_currency"]["EUR"]["total_eur"], 2750.00, abs_tol=FLOAT_TOL)


def test_eur_total_usd():
    """Verify EUR total converted to USD is 2983.75 (2750.00 * 1.085)."""
    assert math.isclose(R["volume_by_currency"]["EUR"]["total_usd"], 2983.75, abs_tol=FLOAT_TOL)


def test_volume_sum_consistency():
    """Verify total_volume_usd equals USD total + EUR total in USD."""
    usd = R["volume_by_currency"]["USD"]["total"]
    eur_usd = R["volume_by_currency"]["EUR"]["total_usd"]
    assert math.isclose(R["summary"]["total_volume_usd"], usd + eur_usd, abs_tol=FLOAT_TOL)


# ─── Cross-field consistency ─────────────────────────────────────────────────


def test_settled_plus_unsettled_equals_total():
    """Verify settled + unsettled = total transactions."""
    s = R["summary"]
    assert s["settled_count"] + s["unsettled_count"] == s["total_transactions"]


def test_unsettled_list_matches_count():
    """Verify unsettled list length matches unsettled_count."""
    assert len(R["unsettled_transactions"]) == R["summary"]["unsettled_count"]


def test_mismatch_list_matches_count():
    """Verify mismatch list length matches mismatch_count."""
    assert len(R["amount_mismatches"]) == R["summary"]["mismatch_count"]


def test_imbalance_list_matches_count():
    """Verify imbalance list length matches imbalance_count."""
    assert len(R["ledger_imbalances"]) == R["summary"]["imbalance_count"]


def test_orphan_list_matches_count():
    """Verify orphan list length matches orphan_count."""
    assert len(R["orphan_settlements"]) == R["summary"]["orphan_count"]


def test_duplicate_list_matches_count():
    """Verify duplicate pairs list length matches duplicate_pair_count."""
    assert len(R["duplicate_pairs"]) == R["summary"]["duplicate_pair_count"]


def test_currency_counts_sum():
    """Verify USD count + EUR count equals total transactions."""
    usd_c = R["volume_by_currency"]["USD"]["count"]
    eur_c = R["volume_by_currency"]["EUR"]["count"]
    assert usd_c + eur_c == R["summary"]["total_transactions"]


def test_fee_rate_computation():
    """Verify fee_rate_percent is correctly computed from fees and volume."""
    fees = R["summary"]["total_fees_usd"]
    vol = R["summary"]["total_volume_usd"]
    expected = round(fees / vol * 100, 2)
    assert math.isclose(R["summary"]["fee_rate_percent"], expected, abs_tol=FLOAT_TOL)


# ─── JSON type checks ────────────────────────────────────────────────────────


def test_monetary_values_are_numbers():
    """Verify monetary fields are JSON numbers, not strings."""
    assert isinstance(R["summary"]["total_volume_usd"], (int, float))
    assert isinstance(R["summary"]["total_fees_usd"], (int, float))
    if R["amount_mismatches"]:
        assert isinstance(R["amount_mismatches"][0]["difference"], (int, float))


def test_counts_are_integers():
    """Verify count fields are integers."""
    for k in ["total_transactions", "settled_count", "unsettled_count",
              "orphan_count", "mismatch_count", "imbalance_count"]:
        assert isinstance(R["summary"][k], int), f"{k} should be int"


def test_txn_ids_are_strings():
    """Verify transaction IDs in lists are strings."""
    for tid in R["unsettled_transactions"]:
        assert isinstance(tid, str)
