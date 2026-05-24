"""Tests for rust-capability-policy-audit-hard — capability policy auditor."""
import hashlib
import json
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')
REPORT_PATH = OUT_DIR / "capability_policy_audit.json"
BINARY = ROOT / "build" / "capability-policy-audit"

FLOAT_TOL = 1e-4

EXPECTED_RAW_HASHES = {
    "data/workloads/w01_cache_proxy.json": "adb80ef8e459542b4fe1f1ff400ce895bcc4c0a3d9065ac5b45e7bf43cd74bd4",
    "data/workloads/w02_log_shipper.json": "fad6ca4d87aa5e6308828a3a415103baf11e55dd5226c559142531aebb35c07d",
    "data/workloads/w03_metrics_agent.json": "f52208850dffc92a5040fa5a9a44c5d8f3832a0a2e613202c01d5debfa1e2a5d",
    "data/workloads/w04_batch_worker.json": "7bf0d167c2f167a3b852ff68f047f0fef3f4656809f50cc68d10bc32fe0deb74",
    "data/workloads/w05_api_gateway.json": "d97946a05bd239ebffca1c5766335ec11d9f41bbc5ee0f97f8c7b3d8da767714",
    "data/workloads/w06_web_frontend.json": "beec5f0819c902c7666e2f5ff6f740bd815e81b72ea6064196426fbe4b7e3960",
}

EXPECTED_SOURCE_HASHES = {
    "config/policy.json": "996917ff81bffa952c00369ca0c925a27b772fb1f28a731c57693474ab48e9a9",
    "data/workloads/w01_cache_proxy.json": "bae3834303651cce34f58b69485529ecb8197c75df08335d831ed8a57c3b67ae",
    "data/workloads/w02_log_shipper.json": "3768975c4fae083a02eef8a285e32e524a596dee2158e2b7c8ea294dceacb1cc",
    "data/workloads/w03_metrics_agent.json": "d1f70451878495a8631403c48241e636fca7577476f2d6e22cc1c20e593634f3",
    "data/workloads/w04_batch_worker.json": "614fd605470ecfa149e51dd915b0bab4a0f1bb50e0b5f3d3e7b0003b3037f227",
    "data/workloads/w05_api_gateway.json": "45200777afb73d20198550f39e0467805b5b50258e14838a3fd0fcd4748e73be",
    "data/workloads/w06_web_frontend.json": "cd653774aeb161a8b72f797fca4f732b3e8d6e3268f0706cfcdb8e18b7071c1f",
}

EXPECTED_INTEGRITY = "3c6a2d7b2a72eed3b5b1bce2b55523be1025230cfac285784cb081ae7891274d"
EXPECTED_WORKLOAD_ORDER = [
    "log-shipper",
    "web-frontend",
    "api-gateway",
    "metrics-agent",
    "cache-proxy",
    "batch-worker",
]


@pytest.fixture(scope="session", autouse=True)
def _load_report():
    if not REPORT_PATH.is_file():
        pytest.skip(f"Report not produced yet: {REPORT_PATH}")


@pytest.fixture(scope="session")
def report():
    if not REPORT_PATH.is_file():
        pytest.skip(f"Missing report at {REPORT_PATH}")
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def _audit(report, workload_id):
    for a in report["workload_audits"]:
        if a["workload_id"] == workload_id:
            return a
    pytest.fail(f"Workload audit missing: {workload_id}")


def _findings(report, finding_type=None, workload_id=None):
    fs = report["findings"]
    if finding_type:
        fs = [f for f in fs if f["finding_type"] == finding_type]
    if workload_id:
        fs = [f for f in fs if f["workload_id"] == workload_id]
    return fs


def test_rust_binary_exists():
    """Compiled auditor must exist at /app/build or release target."""
    alt = ROOT / "target" / "release" / "capability-policy-audit"
    assert BINARY.is_file() or alt.is_file(), (
        "Compiled binary missing at /app/build/capability-policy-audit"
    )


def test_rust_binary_is_elf():
    """Auditor binary must be a Linux ELF executable."""
    path = BINARY if BINARY.is_file() else ROOT / "target" / "release" / "capability-policy-audit"
    with open(path, "rb") as f:
        assert f.read(4) == b"\x7fELF"


def test_input_files_not_modified():
    """Workload inputs under /app/data must match pinned raw SHA-256 hashes."""
    for rel, expected in EXPECTED_RAW_HASHES.items():
        fp = ROOT / rel
        assert fp.is_file(), rel
        got = hashlib.sha256(fp.read_bytes()).hexdigest()
        assert got == expected, f"{rel} tampered"


def test_output_file_exists():
    """Report JSON must be written to /app/output/capability_policy_audit.json."""
    assert REPORT_PATH.is_file()


def test_valid_json(report):
    """Report must parse as a JSON object."""
    assert isinstance(report, dict)


def test_trailing_newline():
    """Report file must end with exactly one newline."""
    raw = REPORT_PATH.read_text(encoding="utf-8")
    assert raw.endswith("\n") and not raw.endswith("\n\n")


def test_two_space_indent(report):
    """Report must use 2-space indentation without tabs."""
    raw = REPORT_PATH.read_text(encoding="utf-8")
    assert "\t" not in raw
    assert '\n  "' in raw


def test_top_level_keys(report):
    """Top-level report keys must match the output format spec."""
    assert set(report.keys()) == {
        "schema_version",
        "source_hashes",
        "workload_audits",
        "findings",
        "summary",
    }


def test_schema_version(report):
    """schema_version must be 1."""
    assert report["schema_version"] == 1


def test_source_hash_keys(report):
    """source_hashes must include policy and every workload file."""
    assert set(report["source_hashes"].keys()) == set(EXPECTED_SOURCE_HASHES.keys())


def test_source_hashes_sorted(report):
    """source_hashes keys must be sorted alphabetically."""
    assert list(report["source_hashes"].keys()) == sorted(report["source_hashes"].keys())


@pytest.mark.parametrize("rel,expected", sorted(EXPECTED_SOURCE_HASHES.items()))
def test_source_hash_value(report, rel, expected):
    """Each canonical source hash must match the specification."""
    assert report["source_hashes"][rel] == expected


def test_workload_audit_count(report):
    """Exactly six workload audits must be present."""
    assert len(report["workload_audits"]) == 6


def test_workload_audits_sorted(report):
    """workload_audits must be sorted by risk tier rank then workload_id."""
    audits = report["workload_audits"]
    keys = [(a["risk_tier_rank"], a["workload_id"]) for a in audits]
    assert keys == sorted(keys)
    assert [a["workload_id"] for a in audits] == EXPECTED_WORKLOAD_ORDER


def test_workload_audit_required_fields(report):
    """Each workload audit entry must expose the required fields only."""
    keys = {
        "workload_id",
        "risk_tier",
        "risk_tier_rank",
        "syscall_count",
        "effective_risk_score",
        "integrity_lines",
    }
    for a in report["workload_audits"]:
        assert set(a.keys()) == keys


def test_log_shipper_metrics(report):
    """log-shipper low-tier workload metrics."""
    a = _audit(report, "log-shipper")
    assert a["risk_tier"] == "low"
    assert a["risk_tier_rank"] == 1
    assert a["syscall_count"] == 3
    assert a["effective_risk_score"] == 2
    assert a["integrity_lines"] == 3


def test_web_frontend_metrics(report):
    """web-frontend low-tier syscall count and effective risk."""
    a = _audit(report, "web-frontend")
    assert a["syscall_count"] == 4
    assert a["effective_risk_score"] == 2
    assert a["integrity_lines"] == 4


def test_api_gateway_metrics(report):
    """api-gateway medium-tier effective risk uses max allowlisted weight."""
    a = _audit(report, "api-gateway")
    assert a["risk_tier_rank"] == 2
    assert a["syscall_count"] == 5
    assert a["effective_risk_score"] == 4


def test_metrics_agent_metrics(report):
    """metrics-agent medium-tier audit row."""
    a = _audit(report, "metrics-agent")
    assert a["syscall_count"] == 6
    assert a["effective_risk_score"] == 4


def test_cache_proxy_metrics(report):
    """cache-proxy high-tier includes non-allowlisted ioctl in count but not effective max."""
    a = _audit(report, "cache-proxy")
    assert a["risk_tier"] == "high"
    assert a["risk_tier_rank"] == 3
    assert a["syscall_count"] == 8
    assert a["effective_risk_score"] == 4
    assert a["integrity_lines"] == 8


def test_batch_worker_metrics(report):
    """batch-worker critical-tier max risk score."""
    a = _audit(report, "batch-worker")
    assert a["risk_tier"] == "critical"
    assert a["risk_tier_rank"] == 4
    assert a["effective_risk_score"] == 6
    assert a["integrity_lines"] == 6


def test_integrity_lines_match_syscall_count(report):
    """integrity_lines equals observed syscall count per workload."""
    for a in report["workload_audits"]:
        assert a["integrity_lines"] == a["syscall_count"]


def test_total_findings(report):
    """Global findings list and summary total must match."""
    assert len(report["findings"]) == 4
    assert report["summary"]["total_findings"] == 4


def test_findings_sorted(report):
    """Findings sorted by severity_rank, finding_type, workload_id."""
    fs = report["findings"]
    keys = [(f["severity_rank"], f["finding_type"], f["workload_id"]) for f in fs]
    assert keys == sorted(keys)


def test_forbidden_capability_finding(report):
    """batch-worker must flag CAP_SYS_ADMIN as forbidden."""
    fs = _findings(report, "forbidden_capability_present", "batch-worker")
    assert len(fs) == 1
    assert fs[0]["severity"] == "critical"
    assert fs[0]["evidence"]["capability"] == "CAP_SYS_ADMIN"


def test_missing_capability_finding(report):
    """api-gateway must flag missing CAP_SETFCAP."""
    fs = _findings(report, "missing_required_capability", "api-gateway")
    assert len(fs) == 1
    assert fs[0]["severity"] == "high"
    assert fs[0]["evidence"]["capability"] == "CAP_SETFCAP"


def test_ioctl_not_allowlisted(report):
    """cache-proxy ioctl must be syscall_not_allowlisted on high tier."""
    fs = _findings(report, "syscall_not_allowlisted", "cache-proxy")
    assert len(fs) == 1
    assert fs[0]["evidence"]["syscall"] == "ioctl"


def test_execve_not_allowlisted(report):
    """web-frontend execve must be syscall_not_allowlisted on low tier."""
    fs = _findings(report, "syscall_not_allowlisted", "web-frontend")
    assert len(fs) == 1
    assert fs[0]["evidence"]["syscall"] == "execve"
    assert fs[0]["evidence"]["risk_tier"] == "low"


def test_summary_totals(report):
    """Summary workload_count must equal workload_audits length."""
    s = report["summary"]
    assert s["workload_count"] == 6


def test_findings_by_type(report):
    """findings_by_type counts must match emitted findings."""
    assert report["summary"]["findings_by_type"] == {
        "forbidden_capability_present": 1,
        "missing_required_capability": 1,
        "syscall_not_allowlisted": 2,
    }


def test_findings_by_severity_all_keys(report):
    """findings_by_severity must include all severity buckets."""
    fbs = report["summary"]["findings_by_severity"]
    assert set(fbs.keys()) == {"critical", "high", "medium", "low", "info"}
    assert fbs["critical"] == 1
    assert fbs["high"] == 1
    assert fbs["medium"] == 2


def test_avg_effective_risk_harmonic(report):
    """avg_effective_risk_score is harmonic mean of positive workload scores."""
    assert report["summary"]["avg_effective_risk_score"] == pytest.approx(
        3.1304, abs=FLOAT_TOL
    )


def test_integrity_hash(report):
    """integrity_hash must match policy-ordered integrity lines."""
    assert report["summary"]["integrity_hash"] == EXPECTED_INTEGRITY


def test_summary_keys_sorted(report):
    """findings_by_type keys sorted alphabetically."""
    assert list(report["summary"]["findings_by_type"].keys()) == sorted(
        report["summary"]["findings_by_type"].keys()
    )


def test_findings_severity_ranks_from_policy(report):
    """Each finding severity_rank must match policy severity_ranks."""
    ranks = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
    for f in report["findings"]:
        assert f["severity_rank"] == ranks[f["severity"]]


def test_finding_types_in_policy(report):
    """finding_type values must be known policy finding types."""
    allowed = {
        "syscall_not_allowlisted",
        "missing_required_capability",
        "forbidden_capability_present",
    }
    for f in report["findings"]:
        assert f["finding_type"] in allowed


def test_no_extra_findings_on_clean_workloads(report):
    """log-shipper and metrics-agent must have zero findings."""
    for wid in ("log-shipper", "metrics-agent"):
        assert _findings(report, workload_id=wid) == []


def test_report_not_empty_object(report):
    """Report must contain non-empty workload_audits and summary."""
    assert len(report["workload_audits"]) > 0
    assert report["summary"]["integrity_hash"]
