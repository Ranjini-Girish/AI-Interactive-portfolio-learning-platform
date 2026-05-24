"""Tests for js-webhook-delivery-audit-hard."""
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_ROOT", "/app"))
REPORT = APP / "output" / "webhook_audit.json"
CKSUM = APP / "output" / "checksum.sha256"
CONFIG = APP / "config"
ENDPOINTS = APP / "endpoints"
DELIVERIES = APP / "deliveries"


@pytest.fixture(scope="session")
def report():
    assert REPORT.exists(), f"Report missing at {REPORT}"
    return json.loads(REPORT.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def policy():
    return json.loads((CONFIG / "policy.json").read_text(encoding="utf-8"))


def normalize_for_hash(raw: bytes) -> bytes:
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    return text.encode("utf-8")


def compute_source_hashes():
    hashes = {}
    for d in ("config", "endpoints", "deliveries"):
        base = APP / d
        for fn in sorted(os.listdir(base)):
            fp = base / fn
            if fp.is_file():
                rel = f"{d}/{fn}"
                hashes[rel] = hashlib.sha256(normalize_for_hash(fp.read_bytes())).hexdigest()
    return dict(sorted(hashes.items()))


def endpoint_audit(report, eid):
    return next(a for a in report["endpoint_audits"] if a["endpoint_id"] == eid)


# --- existence & format ---


def test_report_exists():
    assert REPORT.is_file()


def test_checksum_exists():
    assert CKSUM.is_file()


def test_report_valid_json(report):
    assert isinstance(report, dict)


def test_trailing_newline():
    raw = REPORT.read_bytes()
    assert raw.endswith(b"\n")


def test_two_space_indent():
    lines = REPORT.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if line and line[0] == " ":
            assert line.startswith("  "), "Expected 2-space indentation"


def test_top_level_key_order(report):
    assert list(report.keys()) == [
        "schema_version",
        "summary",
        "source_hashes",
        "endpoint_audits",
        "findings",
    ]


def test_schema_version(report):
    assert report["schema_version"] == 1


# --- summary ---


def test_summary_totals(report):
    s = report["summary"]
    assert s["total_endpoints"] == 8
    assert s["total_deliveries"] == 13
    assert s["total_findings"] == 6


def test_findings_by_severity_keys(report):
    fbs = report["summary"]["findings_by_severity"]
    assert set(fbs.keys()) == {"critical", "high", "medium", "low", "info"}
    assert fbs == {"critical": 2, "high": 2, "medium": 1, "low": 1, "info": 0}


def test_aggregate_risk_geometric_mean(report):
    scores = [f["risk_score"] for f in report["findings"] if f["risk_score"] > 0]
    expected = round(math.exp(sum(math.log(s) for s in scores) / len(scores)), 4)
    assert abs(report["summary"]["aggregate_risk_score"] - expected) < 1e-4


def test_checksum_matches_report():
    raw = REPORT.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    line = CKSUM.read_text(encoding="utf-8").strip()
    assert line == f"{digest}  webhook_audit.json"


# --- source hashes ---


def test_source_hashes_present(report):
    assert len(report["source_hashes"]) == 18


def test_source_hashes_correct(report):
    assert report["source_hashes"] == compute_source_hashes()


def test_source_hashes_sorted(report):
    keys = list(report["source_hashes"].keys())
    assert keys == sorted(keys)


# --- endpoint structure ---


def test_endpoint_audits_sorted(report):
    ids = [a["endpoint_id"] for a in report["endpoint_audits"]]
    assert ids == sorted(ids)
    assert ids[0] == "ep_01" and ids[-1] == "ep_08"


def test_ep01_clean_endpoint(report):
    ep = endpoint_audit(report, "ep_01")
    assert ep["metrics"]["failure_rate"] == 0
    assert ep["metrics"]["invalid_signature_count"] == 0
    assert ep["findings"] == []


def test_ep02_invalid_signature(report):
    types = [f["finding"] for f in report["findings"] if f["endpoint_id"] == "ep_02"]
    assert "invalid_signature" in types
    ep = endpoint_audit(report, "ep_02")
    assert ep["metrics"]["invalid_signature_count"] == 1
    assert ep["metrics"]["failure_rate"] == 0.5


def test_ep03_retry_violation_detail(report):
    f = next(
        x
        for x in report["findings"]
        if x["endpoint_id"] == "ep_03" and x["finding"] == "retry_schedule_violation"
    )
    assert "500ms" in f["detail"]
    assert "1000ms" in f["detail"]


def test_ep04_duplicate_delivery(report):
    assert any(
        f["finding"] == "duplicate_delivery_id" and f["delivery_id"] == "dup_1"
        for f in report["findings"]
    )


def test_ep05_success_after_terminal(report):
    f = next(
        x
        for x in report["findings"]
        if x["endpoint_id"] == "ep_05" and x["finding"] == "success_after_terminal"
    )
    assert "attempt 6" in f["detail"]


def test_ep06_clock_skew(report):
    f = next(
        x
        for x in report["findings"]
        if x["endpoint_id"] == "ep_06" and x["finding"] == "clock_skew_exceeded"
    )
    assert "6500ms" in f["detail"]


def test_ep07_orphan_gap(report):
    assert any(
        f["endpoint_id"] == "ep_07" and f["finding"] == "orphan_attempt_gap"
        for f in report["findings"]
    )


def test_ep08_failure_rate(report):
    ep = endpoint_audit(report, "ep_08")
    assert ep["metrics"]["failure_rate"] == 0.6667
    assert ep["retry_policy"] == "aggressive"


# --- per-delivery / signature ---


def test_del_a_signature_valid(report):
    ep = endpoint_audit(report, "ep_01")
    del_a = next(d for d in ep["deliveries"] if d["delivery_id"] == "del_a")
    assert del_a["signature_valid"] is True
    att = del_a["attempts"][0]
    assert att["expected_signature"] == att["actual_signature"]
    assert att["expected_signature"] == (
        "27cab325f8425c485ee18f1d54e62eae144491274108e22e2fcf2243274364ce"
    )


def test_deliveries_sorted_per_endpoint(report):
    for ep in report["endpoint_audits"]:
        ids = [d["delivery_id"] for d in ep["deliveries"]]
        assert ids == sorted(ids)


def test_attempts_sorted(report):
    for ep in report["endpoint_audits"]:
        for d in ep["deliveries"]:
            nums = [a["attempt_number"] for a in d["attempts"]]
            assert nums == sorted(nums)


def test_global_findings_sort_order(report, policy):
    ranks = policy["severity_ranks"]
    findings = report["findings"]
    for i in range(len(findings) - 1):
        a, b = findings[i], findings[i + 1]
        ra, rb = ranks[a["severity"]], ranks[b["severity"]]
        assert (ra, a["endpoint_id"], a["delivery_id"], a["finding"]) <= (
            rb,
            b["endpoint_id"],
            b["delivery_id"],
            b["finding"],
        )


def test_finding_risk_scores(report, policy):
    import re

    for f in report["findings"]:
        mult = policy["risk_score"]["severity_multiplier"][f["severity"]]
        base = policy["risk_score"]["depth_weight_base"]
        m = re.search(r"attempt_number (\d+)", f["detail"])
        if not m:
            m = re.search(r"attempt (\d+)", f["detail"])
        depth = int(m.group(1)) if m else 1
        expected = round(mult * (base ** depth), 4)
        assert abs(f["risk_score"] - expected) < 1e-3


def test_duplicate_delivery_risk_score(report):
    f = next(x for x in report["findings"] if x["finding"] == "duplicate_delivery_id")
    assert f["risk_score"] == 13.5


def test_total_findings_matches_global_list(report):
    assert report["summary"]["total_findings"] == len(report["findings"])


def test_ep03_harmonic_avg_attempts(report):
    ep = endpoint_audit(report, "ep_03")
    assert ep["metrics"]["avg_attempts_to_success"] == 2


# --- JavaScript implementation checks ---


def test_main_js_not_stub():
    src = (APP / "src" / "main.js").read_text(encoding="utf-8")
    assert "Not implemented" not in src


def test_no_python_solution_in_app():
    py_files = [p for p in APP.glob("*.py") if p.is_file()]
    assert py_files == []


def test_node_rerun_produces_same_report():
    before = REPORT.read_bytes()
    result = subprocess.run(
        ["node", str(APP / "src" / "main.js")],
        cwd=str(APP),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    after = REPORT.read_bytes()
    assert after == before
