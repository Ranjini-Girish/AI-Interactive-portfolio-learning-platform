"""Tests for js-rollout-exposure-audit-hard."""
import json
import math
from pathlib import Path

import pytest

REPORT_PATH = Path("/app/output/rollout_audit.json")
FLOAT_TOL = 5e-7


@pytest.fixture(scope="session")
def report():
    """Load rollout audit report after agent/oracle run."""
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def _exp(report, eid):
    for e in report["experiments"]:
        if e["experiment_id"] == eid:
            return e
    raise AssertionError(f"Experiment {eid} not found")


def _var(report, eid, vid):
    for v in _exp(report, eid)["variants"]:
        if v["variant_id"] == vid:
            return v
    raise AssertionError(f"Variant {vid} not in {eid}")


def test_output_file_exists():
    """Verify rollout_audit.json exists."""
    assert REPORT_PATH.is_file()


def test_json_trailing_newline():
    """Verify JSON ends with a single trailing newline."""
    raw = REPORT_PATH.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert not raw.endswith("\n\n")


def test_json_two_space_indent():
    """Verify 2-space indentation."""
    raw = REPORT_PATH.read_text(encoding="utf-8")
    assert '\n  "' in raw


def test_top_level_keys(report):
    """Verify required top-level keys."""
    assert set(report.keys()) == {"metadata", "experiments", "mutex_violations"}


def test_metadata_fields(report):
    """Verify metadata documents attribution and mutex policy."""
    m = report["metadata"]
    assert m["experiments_analyzed"] == 2
    assert m["attribution_rule"] == "last_touch_within_window"
    assert m["mutex_policy"] == "latest_assignment_wins_per_group"


def test_experiments_sorted(report):
    """Verify experiments sorted by experiment_id."""
    ids = [e["experiment_id"] for e in report["experiments"]]
    assert ids == sorted(ids)


def test_mutex_violations_sorted(report):
    """Verify mutex_violations sorted by group_id then user_id."""
    keys = [(v["group_id"], v["user_id"]) for v in report["mutex_violations"]]
    assert keys == sorted(keys)


def test_mutex_violation_count(report):
    """Verify all cross-experiment users are listed."""
    assert len(report["mutex_violations"]) == 10


def test_exp_auth_assigned_split(report):
    """Mutex splits users: exp_auth has 5 eligible assignees."""
    assert _var(report, "exp_auth", "control")["assigned"] == 2
    assert _var(report, "exp_auth", "treatment")["assigned"] == 3


def test_exp_checkout_assigned_split(report):
    """exp_checkout has 5 eligible assignees."""
    assert _var(report, "exp_checkout", "legacy")["assigned"] == 2
    assert _var(report, "exp_checkout", "streamlined")["assigned"] == 3


def test_exp_auth_treatment_converted(report):
    """Treatment variant conversion count on auth experiment."""
    assert _var(report, "exp_auth", "treatment")["converted"] == 3


def test_exp_auth_control_converted(report):
    """Control variant conversion count on auth experiment."""
    assert _var(report, "exp_auth", "control")["converted"] == 1


def test_exp_auth_treatment_rate(report):
    """Treatment conversion rate is 1.0."""
    assert math.isclose(_var(report, "exp_auth", "treatment")["conversion_rate"], 1.0, abs_tol=FLOAT_TOL)


def test_exp_checkout_streamlined_rate(report):
    """Streamlined checkout conversion rate."""
    assert math.isclose(
        _var(report, "exp_checkout", "streamlined")["conversion_rate"], 0.666667, abs_tol=FLOAT_TOL
    )


def test_srm_not_flagged_auth(report):
    """SRM check should not flag exp_auth."""
    assert _exp(report, "exp_auth")["srm"]["flagged"] is False


def test_srm_chi2_auth(report):
    """SRM chi-square on assignment counts (not exposures)."""
    assert math.isclose(_exp(report, "exp_auth")["srm"]["chi2"], 0.2, abs_tol=FLOAT_TOL)


def test_sequential_winner_exp_auth(report):
    """First calendar look should declare treatment winner."""
    winners = _exp(report, "exp_auth")["sequential_winners"]
    assert len(winners) >= 1
    assert winners[0]["analysis_date"] == "2026-01-10"
    assert winners[0]["winner_variant"] == "treatment"
    assert winners[0]["threshold"] == 1.0


def test_outside_window_ignored(report):
    """Late conversion must not inflate attributed counts."""
    assert _var(report, "exp_auth", "control")["attributed_conversions"] == 2


def test_u10_in_checkout_not_auth(report):
    """u10 mutex winner is exp_checkout only."""
    assert _var(report, "exp_auth", "control")["assigned"] == 2
    assert _var(report, "exp_auth", "treatment")["assigned"] == 3


def test_variant_keys(report):
    """Each variant includes required metrics."""
    required = {
        "variant_id",
        "assigned",
        "exposed",
        "attributed_conversions",
        "converted",
        "conversion_rate",
        "cuped_rate",
    }
    for e in report["experiments"]:
        for v in e["variants"]:
            assert set(v.keys()) == required


def test_solution_is_javascript():
    """Solution must live in JavaScript under /app/src."""
    assert list(Path("/app/src").glob("*.js"))


def test_no_python_in_app():
    """Disallow Python shortcuts in /app."""
    assert len(list(Path("/app").rglob("*.py"))) == 0


def test_input_assignments_intact():
    """Anti-cheat: assignments data unchanged."""
    path = Path("/app/data/assignments.json")
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert len(data) == 21


def test_wrong_mutex_all_users_auth(report):
    """Ignoring mutex would assign 9 users to auth — expect 5 total assigned."""
    total = sum(v["assigned"] for v in _exp(report, "exp_auth")["variants"])
    assert total == 5
