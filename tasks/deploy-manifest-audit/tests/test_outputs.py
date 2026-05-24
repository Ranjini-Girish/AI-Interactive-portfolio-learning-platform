"""Tests for bash-deploy-manifest-audit-hard."""
import json
import math
from pathlib import Path

import pytest

REPORT_PATH = Path("/app/output/audit_report.json")

GOLDEN_SUMMARY = {
    "manifest_count": 5,
    "artifact_count": 8,
    "matched_deployments": 9,
    "unmatched_deployments": 1,
    "checksum_failures": 1,
    "total_bytes_declared": 6560688,
    "median_deploy_duration_sec": 123.0,
}

GOLDEN_CHECKSUM = {
    "verified": 8,
    "failed": 1,
    "failed_ids": ["dep-theta-08"],
}

GOLDEN_OVERLAY = {
    "conflicts": 3,
    "conflict_keys": ["feature_x", "log_level", "replicas"],
}

GOLDEN_CHAIN = {
    "chain_hash": "ce0b599063a3494e5bfaf9babde918081a5c641a5a5ee54b97b338b1d2e05bc3",
    "link_count": 8,
}

GOLDEN_DEPLOYMENTS = {
    "dep-ALPHA-01": {
        "environment": "production",
        "artifact_sha256": "8d14d7c1308aa55a561c452cad760a051851faf527bc80cdad79c855a10b1c47",
        "declared_size_bytes": 524288,
        "effective_duration_sec": 135.0,
        "risk_level": "low",
    },
    "dep-beta-02": {
        "environment": "staging",
        "artifact_sha256": "fcd1dbc48db9d9acd4b318eb44f835854691722697dd1faf187ecaa05f341ada",
        "declared_size_bytes": 1100000,
        "effective_duration_sec": 165.0,
        "risk_level": "medium",
    },
    "dep-delta-04": {
        "environment": "staging",
        "artifact_sha256": "4be1d2d718f73c319a3a28c2cd9eef5ee65ee0a89b562b827df7e6405fc0e100",
        "declared_size_bytes": 250000,
        "effective_duration_sec": 85.0,
        "risk_level": "medium",
    },
    "dep-epsilon-05": {
        "environment": "production",
        "artifact_sha256": "383791a94b065c451d0116a4e29daa4b09e18ddbaebcf5ca3143d4d31b9aff94",
        "declared_size_bytes": 1310720,
        "effective_duration_sec": 210.0,
        "risk_level": "low",
    },
    "dep-eta-07": {
        "environment": "production",
        "artifact_sha256": "8200276e0ca040c0c820a9662ffe41ed14da003dd3af1fc968d0c0c6849c21e5",
        "declared_size_bytes": 900000,
        "effective_duration_sec": 145.0,
        "risk_level": "low",
    },
    "dep-gamma-03": {
        "environment": "production",
        "artifact_sha256": "888a5aa3f4267a77460d09f1225a5fed96d247875dbe5c4a5f0bea59ea857c48",
        "declared_size_bytes": 786432,
        "effective_duration_sec": 115.0,
        "risk_level": "low",
    },
    "dep-kappa-10": {
        "environment": "staging",
        "artifact_sha256": "8d14d7c1308aa55a561c452cad760a051851faf527bc80cdad79c855a10b1c47",
        "declared_size_bytes": 524288,
        "effective_duration_sec": 123.0,
        "risk_level": "low",
    },
    "dep-theta-08": {
        "environment": "staging",
        "artifact_sha256": "c279855570a67d6e3a59794034f321e4c7ff9dc59b36c75512725c03191b069a",
        "declared_size_bytes": 409600,
        "effective_duration_sec": 70.0,
        "risk_level": "low",
    },
    "dep-zeta-06": {
        "environment": "staging",
        "artifact_sha256": "9ff25e2b897f532290e92252ee62eae3ec3eac22c635813edd2b2350c667ed27",
        "declared_size_bytes": 655360,
        "effective_duration_sec": 105.0,
        "risk_level": "low",
    },
}


@pytest.fixture(scope="session")
def report():
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def test_report_exists():
    assert REPORT_PATH.exists()


def test_report_valid_json(report):
    assert isinstance(report, dict)


def test_report_trailing_newline():
    raw = REPORT_PATH.read_text(encoding="utf-8")
    assert raw.endswith("\n")


def test_top_level_keys(report):
    assert set(report.keys()) == {
        "summary",
        "deployments",
        "checksum_audit",
        "environment_overlay",
        "integrity_chain",
    }


def test_summary_fields(report):
    assert set(report["summary"].keys()) == set(GOLDEN_SUMMARY.keys())


def test_manifest_count(report):
    assert report["summary"]["manifest_count"] == GOLDEN_SUMMARY["manifest_count"]


def test_artifact_count(report):
    assert report["summary"]["artifact_count"] == GOLDEN_SUMMARY["artifact_count"]


def test_matched_deployments(report):
    assert report["summary"]["matched_deployments"] == GOLDEN_SUMMARY["matched_deployments"]


def test_unmatched_deployments(report):
    assert report["summary"]["unmatched_deployments"] == GOLDEN_SUMMARY["unmatched_deployments"]


def test_checksum_failures_summary(report):
    assert report["summary"]["checksum_failures"] == GOLDEN_SUMMARY["checksum_failures"]


def test_total_bytes_declared(report):
    assert report["summary"]["total_bytes_declared"] == GOLDEN_SUMMARY["total_bytes_declared"]


def test_median_deploy_duration(report):
    assert math.isclose(
        report["summary"]["median_deploy_duration_sec"],
        GOLDEN_SUMMARY["median_deploy_duration_sec"],
        rel_tol=0,
        abs_tol=0.05,
    )


def test_deployment_count(report):
    assert len(report["deployments"]) == len(GOLDEN_DEPLOYMENTS)


def test_deployments_sorted_ascending(report):
    ids = [d["deployment_id"] for d in report["deployments"]]
    assert ids == sorted(ids)


def test_deployment_first_id(report):
    assert report["deployments"][0]["deployment_id"] == "dep-ALPHA-01"


def test_deployment_last_id(report):
    assert report["deployments"][-1]["deployment_id"] == "dep-zeta-06"


@pytest.mark.parametrize("dep_id,expected", list(GOLDEN_DEPLOYMENTS.items()))
def test_deployment_row(report, dep_id, expected):
    row = next(d for d in report["deployments"] if d["deployment_id"] == dep_id)
    for key, val in expected.items():
        if isinstance(val, float):
            assert math.isclose(row[key], val, rel_tol=0, abs_tol=0.05), key
        else:
            assert row[key] == val, key


def test_checksum_audit_verified(report):
    assert report["checksum_audit"]["verified"] == GOLDEN_CHECKSUM["verified"]


def test_checksum_audit_failed(report):
    assert report["checksum_audit"]["failed"] == GOLDEN_CHECKSUM["failed"]


def test_checksum_failed_ids(report):
    assert report["checksum_audit"]["failed_ids"] == GOLDEN_CHECKSUM["failed_ids"]


def test_overlay_conflicts(report):
    assert report["environment_overlay"]["conflicts"] == GOLDEN_OVERLAY["conflicts"]


def test_overlay_conflict_keys(report):
    assert report["environment_overlay"]["conflict_keys"] == GOLDEN_OVERLAY["conflict_keys"]


def test_integrity_chain_hash(report):
    assert report["integrity_chain"]["chain_hash"] == GOLDEN_CHAIN["chain_hash"]


def test_integrity_link_count(report):
    assert report["integrity_chain"]["link_count"] == GOLDEN_CHAIN["link_count"]


def test_checksum_failures_match_audit(report):
    assert report["summary"]["checksum_failures"] == report["checksum_audit"]["failed"]


def test_failed_ids_sorted(report):
    assert report["checksum_audit"]["failed_ids"] == sorted(
        report["checksum_audit"]["failed_ids"]
    )


def test_high_risk_count(report):
    high = [d for d in report["deployments"] if d["risk_level"] == "high"]
    assert len(high) == 0


def test_medium_risk_deployments(report):
    medium = {d["deployment_id"] for d in report["deployments"] if d["risk_level"] == "medium"}
    assert medium == {"dep-beta-02", "dep-delta-04"}


def test_unmatched_not_in_deployments(report):
    ids = {d["deployment_id"] for d in report["deployments"]}
    assert "dep-iota-09" not in ids


def test_theta_listed_with_failed_checksum(report):
    assert "dep-theta-08" in report["checksum_audit"]["failed_ids"]


def test_run_audit_script_exists():
    assert Path("/app/run_audit.sh").is_file()


def test_lib_shell_modules_present():
    lib = Path("/app/lib")
    scripts = sorted(p.name for p in lib.glob("*.sh"))
    assert len(scripts) >= 8
    assert "common.sh" in scripts
    assert "emit_json.sh" in scripts


def test_no_python_solution_under_app():
    py_files = [p for p in Path("/app").rglob("*.py") if "output" not in p.parts]
    assert py_files == []


def test_bash_pipeline_not_replaced_by_jq_only():
    text = Path("/app/run_audit.sh").read_text(encoding="utf-8")
    assert "lib/" in text
