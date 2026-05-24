"""Tests for rust-raii-scope-audit-hard — RAII scope-guard replay auditor."""
import hashlib
import json
import math
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
REPORT_PATH = OUT_DIR / "scope_audit_report.json"
BINARY = ROOT / "build" / "scope-guard-audit"
FLOAT_TOL = 1e-6

EXPECTED_RAW_HASHES = {
    "data/workloads/w01_linear.json": "7be8c5c531791db23ae4c8ce2a49c59323ef045b701b26abcef1c560617e2326",
    "data/workloads/w02_dup.json": "01d3e1f57926981acf3bb71f123f4954ddb23a118e7cc5bb3d3d132ec4923436",
    "data/workloads/w03_mismatch.json": "9c45f45b04e2bfe8e19b39f42174efcb00035ad8ae0922df006ed2993443332c",
    "data/workloads/w04_leak.json": "93e4abb5ab6c395edcc06d574454e56d0dd581f78cf640bbf85fc8513b0cb6aa",
    "data/workloads/w05_reenter.json": "2fdaac0bce16d4dffeb3737874f57a07beb65bdc0d4408d4a8312e00016b83d1",
    "data/workloads/w06_timestamp.json": "a42f23d14f0ee4621c8ec3e280c38f96fc6444ea55f582b93a07f05a0a1de6c7",
    "data/workloads/w07_panic_unwind.json": "c9c7c9475ecbea66a4d3e901e42d13c56a65124fb049a501356d7c775213ba4b",
    "data/workloads/w08_empty_exit.json": "770753bc94c8756b77646feb60e85a4c558463d182d5af414fa759f792bce7dc",
}

EXPECTED_SOURCE_HASHES = {
    "data/workloads/w01_linear.json": "2bb4c6a059ba59924e44165df711bd8dac02f895546d45ab0b3cd12b6382b929",
    "data/workloads/w02_dup.json": "4a12d12f8c0971302da354dc6c3269bd03d9e136aa9270ea64b3b841bf49e48d",
    "data/workloads/w03_mismatch.json": "eda0aeb93b30bbd8c2e907d903c5ef5ff33b92dee4d70ac841172748d8915841",
    "data/workloads/w04_leak.json": "296f691ac38a988c532f923fd497e9f5031151a024899160800a07a544217960",
    "data/workloads/w05_reenter.json": "e826f885e32be85c51abfc9ee2e6f0156131a51958b41d252bd1abd1163710fb",
    "data/workloads/w06_timestamp.json": "b6b18f2e52852dec9a15cbda80183cacd12cad41706c047c5d801c4527d791f6",
    "data/workloads/w07_panic_unwind.json": "4853319878d1777c6cc0c28d6545e182caf6fe429d6c3076190d64ccf5476858",
    "data/workloads/w08_empty_exit.json": "764707d20543e9a53767bf474a9ebace5c816b5fba8ac3d23966e18adaafc898",
}

EXPECTED_INTEGRITY = "89faa3093bcd099702df3f478148cbaedccbce5ffa70f289aca145ea9c3489a3"


@pytest.fixture(scope="session")
def report():
    """Load scope audit report produced by the Rust binary."""
    assert REPORT_PATH.is_file(), f"Missing report at {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def _wl(report, workload_id):
    for a in report["workload_audits"]:
        if a["workload_id"] == workload_id:
            return a
    pytest.fail(f"workload audit missing: {workload_id}")


def _findings(report, finding_type=None, workload_id=None):
    fs = report["findings"]
    if finding_type:
        fs = [f for f in fs if f["finding_type"] == finding_type]
    if workload_id:
        fs = [f for f in fs if f["workload_id"] == workload_id]
    return fs


def test_rust_binary_exists():
    """Verify compiled binary exists at /app/build/scope-guard-audit."""
    alt = ROOT / "target" / "release" / "scope-guard-audit"
    assert BINARY.is_file() or alt.is_file()


def test_rust_binary_is_elf():
    """Verify the auditor binary is a valid ELF executable."""
    path = BINARY if BINARY.is_file() else ROOT / "target" / "release" / "scope-guard-audit"
    with open(path, "rb") as f:
        assert f.read(4) == b"\x7fELF"


def test_input_files_not_modified():
    """Verify workload JSON inputs were not tampered with."""
    for rel, expected in EXPECTED_RAW_HASHES.items():
        fp = ROOT / rel
        assert fp.is_file(), rel
        got = hashlib.sha256(fp.read_bytes()).hexdigest()
        assert got == expected, f"{rel} tampered"


def test_output_file_exists():
    """Verify scope_audit_report.json was created."""
    assert REPORT_PATH.is_file()


def test_trailing_newline():
    """Verify report ends with a single trailing newline."""
    raw = REPORT_PATH.read_text(encoding="utf-8")
    assert raw.endswith("\n") and not raw.endswith("\n\n")


def test_two_space_indent(report):
    """Verify JSON uses 2-space indentation."""
    raw = REPORT_PATH.read_text(encoding="utf-8")
    assert "\t" not in raw
    assert '\n  "' in raw


def test_top_level_keys(report):
    """Verify required top-level report keys."""
    assert set(report.keys()) == {
        "schema_version",
        "source_hashes",
        "workload_audits",
        "findings",
        "summary",
    }


def test_schema_version(report):
    """Verify schema_version is 1."""
    assert report["schema_version"] == 1


def test_source_hashes(report):
    """Verify normalized source hashes for workload files."""
    for rel, expected in EXPECTED_SOURCE_HASHES.items():
        assert report["source_hashes"][rel] == expected


def test_integrity_hash(report):
    """Verify global integrity hash over replay lines."""
    assert report["summary"]["integrity_hash"] == EXPECTED_INTEGRITY


def test_workload_count(report):
    """Verify all eight workloads were audited."""
    assert report["summary"]["workload_count"] == 8


def test_w01_linear_clean(report):
    """Linear enter/exit workload has no leaks."""
    w = _wl(report, "w01_linear")
    assert w["events_kept"] == 4
    assert w["scopes_leaked"] == 0
    assert math.isclose(w["avg_hold_ms"], 133.333333, abs_tol=FLOAT_TOL)


def test_w02_duplicate_skipped(report):
    """Duplicate event_id increments skipped counter."""
    w = _wl(report, "w02_dup")
    assert w["events_skipped"] == 1
    assert len(_findings(report, "duplicate_event_skipped", "w02_dup")) == 1


def test_w03_exit_mismatch(report):
    """Wrong-scope exit emits scope_exit_mismatch."""
    assert len(_findings(report, "scope_exit_mismatch", "w03_mismatch")) >= 1


def test_w04_scope_leaks(report):
    """Unclosed scopes produce scope_leak findings."""
    w = _wl(report, "w04_leak")
    assert w["scopes_leaked"] == 2
    assert len(_findings(report, "scope_leak", "w04_leak")) == 2


def test_w07_unwind_violation(report):
    """Panic unwind emits unwind_order_violation."""
    assert len(_findings(report, "unwind_order_violation", "w07_panic_unwind")) >= 1


def test_w08_exit_without_enter(report):
    """Exit on empty stack is flagged."""
    assert len(_findings(report, "exit_without_enter", "w08_empty_exit")) >= 1


def test_summary_avg_hold(report):
    """Verify summary harmonic mean across workloads."""
    assert math.isclose(
        report["summary"]["avg_workload_hold_ms"], 46.601942, abs_tol=FLOAT_TOL
    )


def test_findings_sorted(report):
    """Verify findings sort order."""
    keys = [
        (f["severity_rank"], f["finding_type"], f["workload_id"], f["event_id"] or "")
        for f in report["findings"]
    ]
    assert keys == sorted(keys)


def test_findings_by_severity_keys(report):
    """Verify all severity buckets exist in summary."""
    assert set(report["summary"]["findings_by_severity"].keys()) == {
        "info",
        "low",
        "medium",
        "high",
        "critical",
    }


def test_no_python_solution():
    """Disallow Python implementation files under /app."""
    py = [f for f in ROOT.rglob("*.py") if "pytest" not in str(f)]
    assert len(py) == 0
