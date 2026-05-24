"""Tests for rust-fsm-transition-audit-hard — FSM transition replay auditor."""
import hashlib
import json
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
REPORT_PATH = OUT_DIR / "fsm_audit_report.json"
BINARY = ROOT / "build" / "fsm-transition-audit"
FLOAT_TOL = 1e-6

EXPECTED_RAW_HASHES = {
    "data/workflows/w01_pr_linear.json": "bdde9afa26e1d376241e9297dafc744dba0ca749250e6346b2a90106f5577473",
    "data/workflows/w02_pr_dedup.json": "1dd19999effb893d33ff7cea876d25b635b2afcd310b779f08fa18ae15996bcd",
    "data/workflows/w03_pr_timestamp.json": "114984517a9c01fc9423a2f357800b60fa99f46cebf7d75021156211da614f63",
    "data/workflows/w04_pr_illegal.json": "aa9b75dcc927c228bc6722c22a13b849aa04ab12a0ca5143a926b8dc6d8f53a5",
    "data/workflows/w05_pr_mismatch.json": "37b910514e2e87c76dcec1c8674aab1df0679b551eed56ee406ba3a4eacbe4eb",
    "data/workflows/w06_deploy_stuck.json": "097b8dd27f865edd59ab8e346484eddacf7a0470f4b6b30326ee1d50b55b1c5d",
    "data/workflows/w07_deploy_terminal.json": "3ac630768ec36633f70c6e39b0ac7b9b76c424bfa4c68fd012daa1a4adb91ce6",
    "data/workflows/w08_incident_mix.json": "8c0c8e1204532a8578140ada518cf0253e73b5430a01ce3c0da63f0ff01e7b36",
}

EXPECTED_SOURCE_HASHES = {
    "data/fsm_defs/deploy.json": "409c603c71ec954655a2c1d0447bac653e8f6d41067569c36e6968b67c6b2426",
    "data/fsm_defs/incident.json": "7b716c2d402a859f1fbe32af165940d6ee8905fa8cad455ecec85d7a11e7a452",
    "data/fsm_defs/pull_request.json": "32c6c8bacb85c054a3211d088feb9e494cee0911657e4798c3c4349c28c2f213",
    "data/workflows/w01_pr_linear.json": "903ea33992fc942fb8c992ad8a37c242ca09b4f151d5e5752055dbce355435e2",
    "data/workflows/w02_pr_dedup.json": "34a846255401584b51b4fcf68f012c12e037f7e687ac274d9932396dda04445b",
    "data/workflows/w03_pr_timestamp.json": "d5918397f15c11688678c02a987424bbc32ee60ce473aa5c7a21e1c1ad2a33aa",
    "data/workflows/w04_pr_illegal.json": "bc89fbba1c5d11fcce84351ef5e59b81392fe0dc746270878806e400f23a9bdd",
    "data/workflows/w05_pr_mismatch.json": "804316d1a1320f3243d440df273f559237c02f1d9483196396edc7589b1c98f9",
    "data/workflows/w06_deploy_stuck.json": "f9d8248d6eb3fb3e4fa776a089aec923287987e4a9a7481f65630be0fb2922f3",
    "data/workflows/w07_deploy_terminal.json": "d19fdabb66ca711a12fbe16b51c1f6c03031b6fb755b0ee39c8a890769a7dc4b",
    "data/workflows/w08_incident_mix.json": "ea258bbb91e6b5fe8c7df6cb70020c1c21d594d61cde24a1d0a4187f36ec86c8",
}

EXPECTED_INTEGRITY = "88403b54be5f81b39c7bb172d6e9a35a16308f0f81e371e6520b63cf06a1ad20"


@pytest.fixture(scope="session")
def report():
    """Load the FSM audit report produced by the agent binary."""
    assert REPORT_PATH.is_file(), f"Missing report at {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def _wf(report, workflow_id):
    for a in report["workflow_audits"]:
        if a["workflow_id"] == workflow_id:
            return a
    pytest.fail(f"workflow audit missing: {workflow_id}")


def _findings(report, finding_type=None, workflow_id=None):
    fs = report["findings"]
    if finding_type:
        fs = [f for f in fs if f["finding_type"] == finding_type]
    if workflow_id:
        fs = [f for f in fs if f["workflow_id"] == workflow_id]
    return fs


def test_rust_binary_exists():
    """Verify compiled binary exists at /app/build/fsm-transition-audit."""
    alt = ROOT / "target" / "release" / "fsm-transition-audit"
    assert BINARY.is_file() or alt.is_file()


def test_rust_binary_is_elf():
    """Verify the auditor binary is a valid ELF executable."""
    path = BINARY if BINARY.is_file() else ROOT / "target" / "release" / "fsm-transition-audit"
    with open(path, "rb") as f:
        assert f.read(4) == b"\x7fELF"


def test_input_files_not_modified():
    """Verify workflow input JSON files were not tampered with."""
    for rel, expected in EXPECTED_RAW_HASHES.items():
        fp = ROOT / rel
        assert fp.is_file(), rel
        got = hashlib.sha256(fp.read_bytes()).hexdigest()
        assert got == expected, f"{rel} tampered"


def test_output_file_exists():
    """Verify fsm_audit_report.json was created."""
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
        "workflow_audits",
        "findings",
        "summary",
    }


def test_schema_version(report):
    """Verify schema_version is 1."""
    assert report["schema_version"] == 1


def test_source_hash_keys(report):
    """Verify source_hashes covers all workflow and FSM definition files."""
    assert set(report["source_hashes"].keys()) == set(EXPECTED_SOURCE_HASHES.keys())


@pytest.mark.parametrize("rel,expected", sorted(EXPECTED_SOURCE_HASHES.items()))
def test_source_hash_value(report, rel, expected):
    """Verify canonical source hash for each input file."""
    assert report["source_hashes"][rel] == expected


def test_workflow_audit_count(report):
    """Verify all eight workflows were audited."""
    assert len(report["workflow_audits"]) == 8


def test_workflow_audits_sorted(report):
    """Verify workflow_audits are sorted by workflow_id."""
    ids = [a["workflow_id"] for a in report["workflow_audits"]]
    assert ids == sorted(ids)


def test_pr101_linear_metrics(report):
    """Verify pr-101 clean linear PR workflow metrics."""
    a = _wf(report, "pr-101")
    assert a["transitions_kept"] == 4
    assert a["transitions_skipped"] == 0
    assert a["final_state"] == "merged"
    assert a["avg_dwell_ms"] == pytest.approx(219.178082, abs=FLOAT_TOL)


def test_pr202_dedup(report):
    """Verify pr-202 skips one duplicate transition."""
    a = _wf(report, "pr-202")
    assert a["transitions_kept"] == 4
    assert a["transitions_skipped"] == 1
    assert a["avg_dwell_ms"] == pytest.approx(40.0, abs=FLOAT_TOL)


def test_pr303_harmonic_dwell(report):
    """Verify pr-303 uses harmonic mean for dwell (not arithmetic)."""
    a = _wf(report, "pr-303")
    assert a["avg_dwell_ms"] == pytest.approx(19.2, abs=FLOAT_TOL)


def test_dep601_stuck(report):
    """Verify dep-601 ends in non-terminal staging with stuck finding."""
    a = _wf(report, "dep-601")
    assert a["final_state"] == "staging"
    assert len(_findings(report, "stuck_workflow", "dep-601")) == 1


def test_dep707_terminal_reopened(report):
    """Verify dep-707 detects terminal_reopened after reaching live."""
    fs = _findings(report, "terminal_reopened", "dep-707")
    assert len(fs) == 1
    assert fs[0]["transition_id"] == "d5"
    assert fs[0]["severity"] == "critical"


def test_total_findings(report):
    """Verify total finding count in report and summary."""
    assert len(report["findings"]) == 7
    assert report["summary"]["total_findings"] == 7


def test_findings_sorted(report):
    """Verify findings sort order by severity_rank then type then workflow."""
    keys = [
        (f["severity_rank"], f["finding_type"], f["workflow_id"], f["transition_id"] or "")
        for f in report["findings"]
    ]
    assert keys == sorted(keys)


def test_duplicate_finding(report):
    """Verify duplicate_transition_skipped on pr-202."""
    fs = _findings(report, "duplicate_transition_skipped", "pr-202")
    assert len(fs) == 1
    assert fs[0]["evidence"]["duplicate_sequence"] == 4


def test_timestamp_regression(report):
    """Verify timestamp_regression on pr-303 after sequence-ordered replay."""
    fs = _findings(report, "timestamp_regression", "pr-303")
    assert len(fs) == 1
    assert fs[0]["transition_id"] == "t2"


def test_state_mismatch(report):
    """Verify state_mismatch on pr-505."""
    fs = _findings(report, "state_mismatch", "pr-505")
    assert len(fs) == 1
    assert fs[0]["evidence"]["expected_state"] == "open"


def test_illegal_transition(report):
    """Verify illegal_transition on pr-404 open->merged shortcut."""
    fs = _findings(report, "illegal_transition", "pr-404")
    assert len(fs) == 1


def test_summary_totals(report):
    """Verify summary transition totals."""
    s = report["summary"]
    assert s["workflow_count"] == 8
    assert s["total_transitions_kept"] == 28
    assert s["total_transitions_skipped"] == 1


def test_findings_by_type(report):
    """Verify findings_by_type counts."""
    assert report["summary"]["findings_by_type"] == {
        "duplicate_transition_skipped": 1,
        "illegal_transition": 1,
        "state_mismatch": 1,
        "stuck_workflow": 2,
        "terminal_reopened": 1,
        "timestamp_regression": 1,
    }


def test_findings_by_severity(report):
    """Verify findings_by_severity includes all five keys."""
    fbs = report["summary"]["findings_by_severity"]
    assert set(fbs.keys()) == {"critical", "high", "medium", "low", "info"}
    assert fbs["critical"] == 1
    assert fbs["high"] == 2
    assert fbs["medium"] == 3
    assert fbs["info"] == 1


def test_avg_workflow_dwell_harmonic(report):
    """Verify summary avg_workflow_dwell_ms harmonic mean."""
    assert report["summary"]["avg_workflow_dwell_ms"] == pytest.approx(
        39.659862, abs=FLOAT_TOL
    )


def test_integrity_hash(report):
    """Verify cross-workflow integrity hash."""
    assert report["summary"]["integrity_hash"] == EXPECTED_INTEGRITY


def test_integrity_lines(report):
    """Verify integrity_lines equals transitions_kept per workflow."""
    for a in report["workflow_audits"]:
        assert a["integrity_lines"] == a["transitions_kept"]


def test_inc808_resolved(report):
    """Verify inc-808 incident workflow completes at resolved."""
    a = _wf(report, "inc-808")
    assert a["final_state"] == "resolved"
    assert a["avg_dwell_ms"] == pytest.approx(320.0, abs=FLOAT_TOL)
