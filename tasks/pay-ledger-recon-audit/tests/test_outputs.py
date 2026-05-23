"""Behavioral tests
 for the payments-ledger reconciliation auditor.

Each test that needs a custom fixture builds its own SQLite database from
inline SQL into a tmp directory and runs the bundled CLI against it. The first
test runs against the seeded ``/var/lib/audit/state.db`` shipped with the image
and asserts every section of the report.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest  # noqa: F401


SEEDED_DB = os.environ.get("AUDIT_SEEDED_DB", "/var/lib/audit/state.db")
SEEDED_POLICY = os.environ.get("AUDIT_SEEDED_POLICY", "/app/data/policy.json")
APP_ROOT = os.environ.get("AUDIT_APP_ROOT", "/app")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_audit(db: str, policy: str, out: str) -> dict:
    """Run ``python -m audit`` and return the parsed report."""
    result = subprocess.run(
        [
            "python",
            "-m",
            "audit",
            "--db",
            db,
            "--policy",
            policy,
            "--out",
            out,
        ],
        cwd=APP_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"audit CLI failed (exit={result.returncode}):\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert Path(out).exists(), "audit did not write the requested output file"
    with open(out, encoding="utf-8") as fh:
        return json.load(fh)


def _build_db(db_path: str, schema_sql: str, seed_sql: str = "") -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(db_path).unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        if seed_sql.strip():
            conn.executescript(seed_sql)
        conn.commit()
    finally:
        conn.close()


def _write_policy(path: str, **overrides) -> None:
    base = {
        "current_day": 20000,
        "current_day_end_utc_seconds": 1728086400,
        "chain_resolution_window_days": 30,
        "default_fee_bps": 250,
        "unverified_fee_bps": 350,
        "balance_view_max_staleness_min": 60,
        "severe_floor_breach_minor": 1000000,
        "velocity_threshold_per_day": 5,
    }
    base.update(overrides)
    Path(path).write_text(json.dumps(base, indent=2, sort_keys=True), encoding="utf-8")


_SCHEMA_PATH = Path(APP_ROOT) / "data" / "migrations" / "001_schema.sql"
SCHEMA_SQL = _SCHEMA_PATH.read_text() if _SCHEMA_PATH.exists() else ""


# ---------------------------------------------------------------------------
# 1. Whole-report assertions on the seeded fixture.
# ---------------------------------------------------------------------------


def test_default_fixture_full_report(tmp_path: Path) -> None:
    """Run the auditor against the shipped seeded database and assert every section of the report.

    This is the primary end-to-end correctness test: it checks the full top-level shape,
    all account findings, stuck holds, fee anomalies, chain anomalies, FX findings,
    data quality fields, and the summary section against expected values.
    """
    out = tmp_path / "report.json"
    report = _run_audit(SEEDED_DB, SEEDED_POLICY, str(out))

    # Top-level shape
    assert set(report) == {
        "schema_version",
        "as_of_day",
        "summary",
        "account_findings",
        "stuck_holds",
        "fee_anomalies",
        "chain_anomalies",
        "fx_findings",
        "data_quality",
    }
    assert report["schema_version"] == 1
    assert report["as_of_day"] == 20000

    # Summary
    summary = report["summary"]
    assert summary["as_of_day"] == 20000
    assert summary["non_closed_account_count"] == 12
    assert summary["tenant_count"] == 3
    assert summary["by_severity"] == {"critical": 6, "high": 3, "medium": 4, "low": 0}
    assert summary["by_finding_code"] == {
        "available_below_floor": 2,
        "cycle_in_chain": 1,
        "double_resolution": 1,
        "duplicate_refund": 1,
        "fee_amount_mismatch": 1,
        "fee_missing": 3,
        "fx_drift": 1,
        "fx_missing": 1,
        "negative_open_balance": 4,
        "post_close_chain_activity": 1,
        "velocity_breach": 1,
    }
    # by_finding_code keys are sorted ASCII
    assert list(summary["by_finding_code"]) == sorted(summary["by_finding_code"])
    assert isinstance(summary["audit_run_seconds"], float)
    assert summary["audit_run_seconds"] > 0

    # Account findings: 7 entries, sorted by (severity_rank, finding_code, tenant_id, account_id)
    af = report["account_findings"]
    assert len(af) == 7
    assert [(e["severity"], e["finding_code"], e["tenant_id"], e["account_id"]) for e in af] == [
        ("critical", "negative_open_balance", "T_GBP", "ACC_006"),
        ("critical", "negative_open_balance", "T_USD", "ACC_005"),
        ("critical", "negative_open_balance", "T_USD", "ACC_010"),
        ("critical", "negative_open_balance", "T_USD", "ACC_011"),
        ("high", "available_below_floor", "T_USD", "ACC_012"),
        ("medium", "available_below_floor", "T_GBP", "ACC_006"),
        ("medium", "velocity_breach", "T_GBP", "ACC_006"),
    ]
    by_acc = {(e["account_id"], e["finding_code"]): e for e in af}
    assert by_acc[("ACC_005", "negative_open_balance")]["evidence"] == {"open_balance": -7620}
    assert by_acc[("ACC_006", "negative_open_balance")]["evidence"] == {"open_balance": -612}
    assert by_acc[("ACC_010", "negative_open_balance")]["evidence"] == {"open_balance": -2000}
    assert by_acc[("ACC_011", "negative_open_balance")]["evidence"] == {"open_balance": -1020}
    assert by_acc[("ACC_012", "available_below_floor")]["evidence"] == {
        "available": -1200000,
        "floor": -100000,
        "gap": 1100000,
    }
    assert by_acc[("ACC_006", "available_below_floor")]["evidence"] == {
        "available": -612,
        "floor": 500000,
        "gap": 500612,
    }
    assert by_acc[("ACC_006", "velocity_breach")]["evidence"] == {
        "captures_today": 6,
        "threshold": 5,
    }

    # Stuck holds: 2 entries, sorted by expires_ts then hold_id
    sh = report["stuck_holds"]
    assert len(sh) == 2
    assert [(e["hold_id"], e["account_id"], e["tenant_id"]) for e in sh] == [
        ("H_005", "ACC_PHANTOM", ""),
        ("H_002_a", "ACC_002", "T_USD"),
    ]
    assert sh[0]["amount_minor"] == 1500
    assert sh[0]["expires_ts"] == 1727800000
    assert sh[1]["amount_minor"] == 500
    assert sh[1]["expires_ts"] == 1727900000

    # Fee anomalies: 1 mismatch + 3 missing, sorted by (finding_code, tx_id)
    fa = report["fee_anomalies"]
    assert [(e["finding_code"], e["tx_id"]) for e in fa] == [
        ("fee_amount_mismatch", "TX_007_a"),
        ("fee_missing", "TX_005_b"),
        ("fee_missing", "TX_010_a"),
        ("fee_missing", "TX_010_b"),
    ]
    fa_by_tx = {e["tx_id"]: e for e in fa}
    assert fa_by_tx["TX_007_a"]["expected_fee_minor"] == 40
    assert fa_by_tx["TX_007_a"]["actual_fee_minor"] == 35
    assert fa_by_tx["TX_007_a"]["priority"] == 10
    assert fa_by_tx["TX_007_a"]["merchant_id"] == "M_WEIRD"
    assert fa_by_tx["TX_005_b"]["expected_fee_minor"] == 22  # banker's: 1500*150/10000=22.5 -> 22
    assert fa_by_tx["TX_005_b"]["actual_fee_minor"] is None
    assert fa_by_tx["TX_005_b"]["priority"] == 5
    assert fa_by_tx["TX_010_a"]["expected_fee_minor"] == 20
    assert fa_by_tx["TX_010_a"]["actual_fee_minor"] is None

    # Chain anomalies: 4 entries, sorted by (severity_rank, finding_code, chain_root)
    ca = report["chain_anomalies"]
    assert [(e["severity"], e["finding_code"], e["chain_root"]) for e in ca] == [
        ("critical", "cycle_in_chain", "TX_010_a"),
        ("critical", "double_resolution", "TX_008_root"),
        ("high", "duplicate_refund", "TX_008_root"),
        ("medium", "post_close_chain_activity", "TX_003_root"),
    ]
    ca_by_code = {e["finding_code"]: e for e in ca}
    assert ca_by_code["cycle_in_chain"]["tx_ids"] == ["TX_010_a", "TX_010_b"]
    assert ca_by_code["duplicate_refund"]["tx_ids"] == [
        "TX_008_refund_a",
        "TX_008_refund_b",
    ]
    assert ca_by_code["double_resolution"]["tx_ids"] == [
        "TX_008_chargeback",
        "TX_008_refund_a",
        "TX_008_refund_b",
        "TX_008_root",
        "TX_008_root_fee",
    ]
    assert ca_by_code["post_close_chain_activity"]["tx_ids"] == [
        "TX_003_post",
        "TX_003_root",
        "TX_003_root_fee",
    ]

    # FX findings: fx_missing (high) before fx_drift (medium)
    fx = report["fx_findings"]
    assert len(fx) == 2
    assert fx[0]["finding_code"] == "fx_missing"
    assert fx[0]["tx_id"] == "TX_005_b"
    assert fx[0]["currency"] == "GBP"
    assert fx[0]["base_currency"] == "USD"
    assert fx[0]["expected_day"] == 20000
    assert fx[1]["finding_code"] == "fx_drift"
    assert fx[1]["tx_id"] == "TX_005_c"
    assert fx[1]["expected_micro"] == 1100000
    assert fx[1]["recorded_micro"] == 1095000

    # Data quality
    dq = report["data_quality"]
    assert dq["orphan_tenant_accounts"] == 1
    assert dq["orphan_holds"] == 1
    assert dq["unknown_kind_rows"] == 1
    assert dq["negative_amounts"] == 1
    assert dq["fx_unconvertible_count"] == 1
    assert dq["view_stale"] is True
    assert dq["view_staleness_seconds"] == 6400


def test_db_must_remain_readonly(tmp_path: Path) -> None:
    """Running the audit must not mutate state.db."""
    digest_before = hashlib.sha256(Path(SEEDED_DB).read_bytes()).hexdigest()
    out = tmp_path / "r.json"
    _run_audit(SEEDED_DB, SEEDED_POLICY, str(out))
    digest_after = hashlib.sha256(Path(SEEDED_DB).read_bytes()).hexdigest()
    assert digest_before == digest_after, "state.db was mutated by the audit run"


def test_output_file_is_deterministic(tmp_path: Path) -> None:
    """Two consecutive runs must produce byte-identical reports apart from
    audit_run_seconds, and the keys at every level must be ASCII-sorted."""
    out1 = tmp_path / "r1.json"
    out2 = tmp_path / "r2.json"
    _run_audit(SEEDED_DB, SEEDED_POLICY, str(out1))
    _run_audit(SEEDED_DB, SEEDED_POLICY, str(out2))

    a = json.loads(out1.read_text())
    b = json.loads(out2.read_text())
    a["summary"]["audit_run_seconds"] = 0
    b["summary"]["audit_run_seconds"] = 0
    assert a == b

    text = out1.read_text()
    assert text.endswith("\n")
    # Verify exactly 2-space indentation (not 4 or more)
    lines = text.splitlines()
    indented = [ln for ln in lines if ln.startswith(" ")]
    assert indented, "expected indented lines in JSON output"
    assert indented[0].startswith("  ") and not indented[0].startswith("   "), \
        "JSON must use exactly 2-space indentation"

    def _check_sorted(value):
        if isinstance(value, dict):
            keys = list(value)
            assert keys == sorted(keys), f"unsorted dict keys: {keys}"
            for v in value.values():
                _check_sorted(v)
        elif isinstance(value, list):
            for v in value:
                _check_sorted(v)

    _check_sorted(a)


# ---------------------------------------------------------------------------
# 2. Custom-fixture targeted tests for hidden-trap rules.
# ---------------------------------------------------------------------------


_REF_INSERTS = """
INSERT INTO tenants VALUES ('T_USD', 'US', 'USD', 0, -100000);
INSERT INTO merchants VALUES ('M_AMZ', 'Amazon Inc', '5942', 'verified');
INSERT INTO merchant_category_rules VALUES ('R001', 10, 'amazon', '5942', 200);
"""


def _run_with_custom_db(tmp_path: Path, seed_sql: str, **policy_overrides) -> dict:
    db = tmp_path / "state.db"
    pol = tmp_path / "policy.json"
    out = tmp_path / "report.json"
    _build_db(str(db), SCHEMA_SQL, _REF_INSERTS + seed_sql)
    _write_policy(str(pol), **policy_overrides)
    return _run_audit(str(db), str(pol), str(out))


def test_hold_boundary_is_exclusive(tmp_path: Path) -> None:
    """A hold with expires_ts EQUAL to current_day_end_utc_seconds is NOT stuck."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO holds VALUES ('H_BOUND', 'ACC_X', 100, 1727800000, 1728086400, NULL, 'boundary');
    INSERT INTO holds VALUES ('H_AFTER', 'ACC_X', 200, 1727800000, 1728086401, NULL, 'after');
    INSERT INTO holds VALUES ('H_BEFORE','ACC_X', 300, 1727800000, 1728086399, NULL, 'before');
    """
    report = _run_with_custom_db(tmp_path, seed)
    sh = report["stuck_holds"]
    ids = {e["hold_id"] for e in sh}
    assert ids == {"H_BEFORE"}, f"expected only H_BEFORE stuck, got {ids}"


def test_uncleared_holds_inclusive_at_boundary(tmp_path: Path) -> None:
    """A hold with expires_ts EQUAL to boundary IS uncleared (>=); same hold is not stuck.
    The available balance must reflect this hold."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO transactions VALUES ('TX_FUND', 'ACC_X', 'refund', 100000, 'USD', 1727900000, 1, NULL, 'committed', NULL, NULL);
    INSERT INTO transactions VALUES ('TX_CAP', 'ACC_X', 'capture', 5000, 'USD', 1727950000, 1, NULL, 'committed', 'M_AMZ', NULL);
    INSERT INTO transactions VALUES ('TX_FEE', 'ACC_X', 'fee', 100, 'USD', 1727950100, 1, 'TX_CAP', 'committed', 'M_AMZ', NULL);
    INSERT INTO holds VALUES ('H_BOUND', 'ACC_X', 200000, 1727800000, 1728086400, NULL, 'boundary');
    """
    report = _run_with_custom_db(tmp_path, seed, severe_floor_breach_minor=10**9)
    af = report["account_findings"]
    floor = next((e for e in af if e["finding_code"] == "available_below_floor"), None)
    assert floor is not None, "available_below_floor should fire"
    # open_balance = +100000 - 5000 - 100 = 94900
    # uncleared_holds = 200000 (boundary inclusive)
    # available = 94900 - 200000 = -105100
    # floor = -100000
    assert floor["evidence"]["available"] == -105100
    assert floor["evidence"]["floor"] == -100000
    assert floor["evidence"]["gap"] == -100000 - (-105100)


def test_banker_rounding_at_half_minor(tmp_path: Path) -> None:
    """1500*150/10000 = 22.5 -> 22 (banker's)."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO merchants VALUES ('M_NF', 'Netflix Streaming', '4899', 'verified');
    INSERT INTO merchant_category_rules VALUES ('R003', 5, 'netflix', '4899', 150);
    INSERT INTO transactions VALUES ('TX_FUND', 'ACC_X', 'refund', 100000, 'USD', 1727900000, 1, NULL, 'committed', NULL, NULL);
    INSERT INTO transactions VALUES ('TX_CAP', 'ACC_X', 'capture', 1500, 'USD', 1727950000, 1, NULL, 'committed', 'M_NF', NULL);
    INSERT INTO transactions VALUES ('TX_FEE_22', 'ACC_X', 'fee', 22, 'USD', 1727950100, 1, 'TX_CAP', 'committed', 'M_NF', NULL);
    """
    report = _run_with_custom_db(tmp_path, seed)
    fa = report["fee_anomalies"]
    assert fa == [], f"expected no fee anomaly with banker-correct fee 22, got {fa}"


def test_banker_rounding_round_to_even(tmp_path: Path) -> None:
    """500*150/10000 = 7.5 -> 8 (banker's: 8 is even). Recorded 7 must be a mismatch."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO merchants VALUES ('M_NF', 'Netflix Streaming', '4899', 'verified');
    INSERT INTO merchant_category_rules VALUES ('R003', 5, 'netflix', '4899', 150);
    INSERT INTO transactions VALUES ('TX_FUND', 'ACC_X', 'refund', 100000, 'USD', 1727900000, 1, NULL, 'committed', NULL, NULL);
    INSERT INTO transactions VALUES ('TX_CAP', 'ACC_X', 'capture', 500, 'USD', 1727950000, 1, NULL, 'committed', 'M_NF', NULL);
    INSERT INTO transactions VALUES ('TX_FEE_7', 'ACC_X', 'fee', 7, 'USD', 1727950100, 1, 'TX_CAP', 'committed', 'M_NF', NULL);
    """
    report = _run_with_custom_db(tmp_path, seed)
    fa = report["fee_anomalies"]
    assert len(fa) == 1
    assert fa[0]["finding_code"] == "fee_amount_mismatch"
    assert fa[0]["expected_fee_minor"] == 8
    assert fa[0]["actual_fee_minor"] == 7


def test_fee_priority_tiebreak_on_rule_id(tmp_path: Path) -> None:
    """Two rules with same priority 10 both match; ASCII-smallest rule_id wins."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO merchants VALUES ('M_TEST', 'Amazon Weird Store', '5942', 'verified');
    INSERT INTO merchant_category_rules VALUES ('R002', 10, 'weird',  '5942', 400);
    INSERT INTO transactions VALUES ('TX_FUND', 'ACC_X', 'refund', 100000, 'USD', 1727900000, 1, NULL, 'committed', NULL, NULL);
    INSERT INTO transactions VALUES ('TX_CAP', 'ACC_X', 'capture', 1000, 'USD', 1727950000, 1, NULL, 'committed', 'M_TEST', NULL);
    INSERT INTO transactions VALUES ('TX_FEE', 'ACC_X', 'fee', 20, 'USD', 1727950100, 1, 'TX_CAP', 'committed', 'M_TEST', NULL);
    """
    # R001 (priority 10, "amazon") and R002 (priority 10, "weird") both match "Amazon Weird Store".
    # R001 < R002 ASCII => bps=200 => expected fee 1000*200/10000 = 20. Recorded 20 => no anomaly.
    report = _run_with_custom_db(tmp_path, seed)
    assert report["fee_anomalies"] == []


def test_orphan_tenant_skips_account_findings(tmp_path: Path) -> None:
    """Account whose tenant is missing produces no account/FX findings but is counted."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_O', 'T_GHOST', 'USD', 19000, NULL, 'active');
    INSERT INTO transactions VALUES ('TX_O', 'ACC_O', 'capture', 1000, 'EUR', 1727950000, 1, NULL, 'committed', 'M_AMZ', 1100000);
    """
    report = _run_with_custom_db(tmp_path, seed)
    assert report["data_quality"]["orphan_tenant_accounts"] == 1
    # No account findings for ACC_O even though it has a non-base-currency capture.
    assert all(e["account_id"] != "ACC_O" for e in report["account_findings"])
    # No FX findings because tenant lookup failed.
    assert report["fx_findings"] == []


def test_orphan_hold_uses_blank_tenant(tmp_path: Path) -> None:
    """Assert that a stuck hold referencing a non-existent account is reported with a blank tenant_id.

    Orphan holds (holds whose account_id does not exist in the accounts table) must still
    appear in the stuck_holds output; the tenant_id field should default to an empty string
    rather than being omitted or causing an error.
    """
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO holds VALUES ('H_GHOST', 'ACC_NOEXIST', 999, 1727750000, 1727800000, NULL, 'ghost');
    """
    report = _run_with_custom_db(tmp_path, seed)
    sh = report["stuck_holds"]
    assert len(sh) == 1
    assert sh[0]["hold_id"] == "H_GHOST"
    assert sh[0]["tenant_id"] == ""
    assert report["data_quality"]["orphan_holds"] == 1


def test_chain_cycle_three_nodes(tmp_path: Path) -> None:
    """A 3-node cycle is reported as one cycle_in_chain anomaly with sorted members."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO transactions VALUES ('TX_FUND', 'ACC_X', 'refund', 100000, 'USD', 1727800000, 1, NULL, 'committed', NULL, NULL);
    INSERT INTO transactions VALUES ('TX_C1', 'ACC_X', 'capture', 100, 'USD', 1727850000, 1, 'TX_C3', 'committed', 'M_AMZ', NULL);
    INSERT INTO transactions VALUES ('TX_C2', 'ACC_X', 'capture', 100, 'USD', 1727851000, 1, 'TX_C1', 'committed', 'M_AMZ', NULL);
    INSERT INTO transactions VALUES ('TX_C3', 'ACC_X', 'capture', 100, 'USD', 1727852000, 1, 'TX_C2', 'committed', 'M_AMZ', NULL);
    """
    report = _run_with_custom_db(tmp_path, seed)
    cycles = [e for e in report["chain_anomalies"] if e["finding_code"] == "cycle_in_chain"]
    assert len(cycles) == 1
    assert cycles[0]["chain_root"] == "TX_C1"
    assert cycles[0]["tx_ids"] == ["TX_C1", "TX_C2", "TX_C3"]


def test_double_resolution_skipped_when_chargeback_voided(tmp_path: Path) -> None:
    """A voided chargeback does NOT trigger double_resolution."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO transactions VALUES ('TX_R',  'ACC_X', 'capture',  5000, 'USD', 1727900000, 1, NULL,    'committed', 'M_AMZ', NULL);
    INSERT INTO transactions VALUES ('TX_RF', 'ACC_X', 'fee',       100, 'USD', 1727900100, 1, 'TX_R', 'committed', 'M_AMZ', NULL);
    INSERT INTO transactions VALUES ('TX_REF', 'ACC_X', 'refund',  5000, 'USD', 1727950000, 1, 'TX_R', 'committed', 'M_AMZ', NULL);
    INSERT INTO transactions VALUES ('TX_CB', 'ACC_X', 'chargeback', 5000, 'USD', 1727960000, 1, 'TX_R', 'voided',    'M_AMZ', NULL);
    """
    report = _run_with_custom_db(tmp_path, seed)
    codes = {e["finding_code"] for e in report["chain_anomalies"]}
    assert "double_resolution" not in codes


def test_post_close_excludes_pre_close_only_chains(tmp_path: Path) -> None:
    """A chain entirely before closed_day must NOT fire post_close_chain_activity."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, 19990, 'closed');
    INSERT INTO transactions VALUES ('TX_PRE',  'ACC_X', 'capture', 1000, 'USD', 1726300000, 1, NULL,        'committed', 'M_AMZ', NULL);
    INSERT INTO transactions VALUES ('TX_PREF', 'ACC_X', 'fee',       20, 'USD', 1726300100, 1, 'TX_PRE',   'committed', 'M_AMZ', NULL);
    """
    # day = 1726300000 // 86400 = 19980 < 19990 closed_day -> no anomaly
    report = _run_with_custom_db(tmp_path, seed)
    assert report["chain_anomalies"] == []


def test_fx_per_tenant_offset_shifts_expected_day(tmp_path: Path) -> None:
    """T_GBP has audit_day_offset_min=60. expected_day = floor((ts - 3600)/86400).
    A transaction at ts=1728001000 has effective ts=1727997400 -> day 19999 (not 20000)."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_OFF', 'GBP', 19000, NULL, 'active');
    INSERT INTO tenants VALUES ('T_OFF', 'UK', 'GBP', 60, 0);
    INSERT INTO fx_rates VALUES (19999, 'USD', 'GBP', 750000);
    INSERT INTO transactions VALUES ('TX_FUND', 'ACC_X', 'refund', 100000, 'GBP', 1727800000, 1, NULL, 'committed', NULL, NULL);
    INSERT INTO transactions VALUES ('TX_OFF',  'ACC_X', 'capture', 1000, 'USD', 1728001000, 1, NULL, 'committed', 'M_AMZ', 750000);
    INSERT INTO transactions VALUES ('TX_OFF_FEE', 'ACC_X', 'fee', 20, 'USD', 1728001100, 1, 'TX_OFF', 'committed', 'M_AMZ', 750000);
    """
    report = _run_with_custom_db(tmp_path, seed)
    # Without offset, expected_day would be 20000 -> no rate -> fx_missing.
    # With offset, expected_day = 19999 -> rate exists with same micro -> NO fx finding.
    assert report["fx_findings"] == []


def test_null_status_treated_as_non_voided(tmp_path: Path) -> None:
    """A transaction with status NULL must be treated as non-voided (kept in balance)."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO transactions VALUES ('TX_FUND', 'ACC_X', 'refund', 50000, 'USD', 1727800000, 1, NULL, 'committed', NULL, NULL);
    INSERT INTO transactions VALUES ('TX_NULL', 'ACC_X', 'capture', 70000, 'USD', 1727900000, 1, NULL, NULL, 'M_AMZ', NULL);
    """
    # Without NULL handling: capture excluded, balance = +50000 (no neg).
    # With NULL handling (correct): capture included, balance = 50000 - 70000 = -20000 -> negative_open_balance.
    report = _run_with_custom_db(tmp_path, seed)
    codes = [e["finding_code"] for e in report["account_findings"]]
    assert "negative_open_balance" in codes


def test_velocity_threshold_uses_current_day_only(tmp_path: Path) -> None:
    """Velocity counts only captures whose floor(ts/86400) == current_day."""
    # 4 captures on current_day + 3 on yesterday => total 7, but only 4 today => no breach (threshold 5).
    seed_lines = [
        "INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');",
        "INSERT INTO transactions VALUES ('TX_FUND', 'ACC_X', 'refund', 100000, 'USD', 1727800000, 1, NULL, 'committed', NULL, NULL);",
    ]
    for i in range(4):
        ts = 1728001000 + i * 1000  # day 20000
        seed_lines.append(
            f"INSERT INTO transactions VALUES ('TX_T{i}', 'ACC_X', 'capture', 100, 'USD', {ts}, 1, NULL, 'committed', 'M_AMZ', NULL);"
        )
        seed_lines.append(
            f"INSERT INTO transactions VALUES ('TX_T{i}_F', 'ACC_X', 'fee', 2, 'USD', {ts + 100}, 1, 'TX_T{i}', 'committed', 'M_AMZ', NULL);"
        )
    for i in range(3):
        ts = 1727950000 + i * 1000  # day 19999
        seed_lines.append(
            f"INSERT INTO transactions VALUES ('TX_Y{i}', 'ACC_X', 'capture', 100, 'USD', {ts}, 1, NULL, 'committed', 'M_AMZ', NULL);"
        )
        seed_lines.append(
            f"INSERT INTO transactions VALUES ('TX_Y{i}_F', 'ACC_X', 'fee', 2, 'USD', {ts + 100}, 1, 'TX_Y{i}', 'committed', 'M_AMZ', NULL);"
        )
    report = _run_with_custom_db(tmp_path, "\n".join(seed_lines))
    codes = [e["finding_code"] for e in report["account_findings"]]
    assert "velocity_breach" not in codes


def test_voided_capture_does_not_require_fee(tmp_path: Path) -> None:
    """A voided capture must not produce fee_missing or fee_amount_mismatch."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO transactions VALUES ('TX_FUND', 'ACC_X', 'refund', 100000, 'USD', 1727800000, 1, NULL, 'committed', NULL, NULL);
    INSERT INTO transactions VALUES ('TX_VOID', 'ACC_X', 'capture', 5000, 'USD', 1727900000, 1, NULL, 'voided', 'M_AMZ', NULL);
    """
    report = _run_with_custom_db(tmp_path, seed)
    assert report["fee_anomalies"] == []


def test_data_quality_view_stale_threshold(tmp_path: Path) -> None:
    """Staleness > balance_view_max_staleness_min*60 => view_stale True."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO mv_daily_balances VALUES ('ACC_X', 19999, 0, 1728082400);
    """
    # boundary 1728086400 - 1728082400 = 4000 sec; threshold 60*60=3600 -> stale.
    report = _run_with_custom_db(tmp_path, seed)
    assert report["data_quality"]["view_stale"] is True
    assert report["data_quality"]["view_staleness_seconds"] == 4000


def test_data_quality_view_fresh(tmp_path: Path) -> None:
    """Staleness <= balance_view_max_staleness_min*60 => view_stale False."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO mv_daily_balances VALUES ('ACC_X', 19999, 0, 1728085000);
    """
    # 1728086400 - 1728085000 = 1400 sec < 3600 -> fresh.
    report = _run_with_custom_db(tmp_path, seed)
    assert report["data_quality"]["view_stale"] is False
    assert report["data_quality"]["view_staleness_seconds"] == 1400


def test_severe_floor_breach_severity(tmp_path: Path) -> None:
    """gap >= severe_floor_breach_minor => severity 'high'."""
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO transactions VALUES ('TX_FUND', 'ACC_X', 'refund', 50000, 'USD', 1727800000, 1, NULL, 'committed', NULL, NULL);
    INSERT INTO holds VALUES ('H_BIG', 'ACC_X', 2000000, 1727800000, 1728172800, NULL, 'reserve');
    """
    # open = 50000, uncleared = 2000000, available = -1950000, floor = -100000 (T_USD)
    # gap = -100000 - (-1950000) = 1850000 >= severe (1000000) => high severity
    report = _run_with_custom_db(tmp_path, seed, severe_floor_breach_minor=1000000)
    floor = next(
        e for e in report["account_findings"] if e["finding_code"] == "available_below_floor"
    )
    assert floor["severity"] == "high"
    assert floor["evidence"]["gap"] == 1850000


def test_null_status_capture_still_checked_for_fees(tmp_path: Path) -> None:
    """A capture with status=NULL is non-voided and must be fee-checked.

    If the fee path incorrectly requires status IS NOT NULL before examining a
    capture, this NULL-status capture will be silently skipped and the expected
    fee_missing anomaly will not fire.
    """
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, NULL, 'active');
    INSERT INTO transactions VALUES ('TX_FUND', 'ACC_X', 'refund', 100000, 'USD', 1727800000, 1, NULL, 'committed', NULL, NULL);
    INSERT INTO transactions VALUES ('TX_NULL_CAP', 'ACC_X', 'capture', 2000, 'USD', 1727950000, 1, NULL, NULL, 'M_AMZ', NULL);
    """
    # TX_NULL_CAP has status=NULL -> non-voided -> fee required.
    # No fee transaction exists -> must produce fee_missing.
    report = _run_with_custom_db(tmp_path, seed)
    fa = report["fee_anomalies"]
    matching = [e for e in fa if e["tx_id"] == "TX_NULL_CAP"]
    assert len(matching) == 1, (
        f"expected fee_missing for NULL-status capture TX_NULL_CAP, got {fa}"
    )
    assert matching[0]["finding_code"] == "fee_missing"
    # R001 matches M_AMZ (pattern 'amazon' in 'Amazon Inc', mcc '5942') -> bps=200
    # expected = banker_round(2000 * 200 / 10000) = banker_round(40.0) = 40
    assert matching[0]["expected_fee_minor"] == 40


def test_post_close_boundary_equal_day_no_finding(tmp_path: Path) -> None:
    """post_close_chain_activity requires resolution_day > closed_day (strict).

    When resolution_day == closed_day, the finding must NOT fire. An
    implementation using >= would incorrectly flag this chain.
    """
    seed = """
    INSERT INTO accounts VALUES ('ACC_X', 'T_USD', 'USD', 19000, 19995, 'closed');
    INSERT INTO transactions VALUES ('TX_BOUNDARY', 'ACC_X', 'capture', 1000, 'USD', 1727568000, 1, NULL, 'committed', 'M_AMZ', NULL);
    INSERT INTO transactions VALUES ('TX_BOUNDARY_F', 'ACC_X', 'fee', 20, 'USD', 1727568100, 1, 'TX_BOUNDARY', 'committed', 'M_AMZ', NULL);
    """
    # TX_BOUNDARY: ts=1727568000, floor(1727568000/86400) = 19995 == closed_day
    # TX_BOUNDARY_F: ts=1727568100, floor(1727568100/86400) = 19995 == closed_day
    # resolution_day = max(19995, 19995) = 19995 == closed_day -> NO finding (strict >)
    report = _run_with_custom_db(tmp_path, seed)
    post_close = [
        e for e in report["chain_anomalies"]
        if e["finding_code"] == "post_close_chain_activity"
    ]
    assert post_close == [], (
        f"resolution_day == closed_day must NOT fire post_close_chain_activity, "
        f"got {post_close}"
    )
