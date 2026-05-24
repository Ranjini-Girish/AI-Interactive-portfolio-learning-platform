"""Tests for rust-saga-replay-audit-hard — saga replay auditor."""
import hashlib
import json
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')
REPORT_PATH = OUT_DIR / "saga_replay_audit.json"
BINARY = ROOT / "build" / "saga-replay-audit"

FLOAT_TOL = 1e-6

EXPECTED_RAW_HASHES = {
    "data/sagas/s01_linear.json": "598c5fb478d678f375791f393d27f753b2c82308c9cf2fa0e0020cb472e68ac1",
    "data/sagas/s02_dedup.json": "dc1874ce5c0feaf3a49623e1e239c3c08aa1384919ade5722964f3507549c0dd",
    "data/sagas/s03_out_of_order.json": "e5e1b6049d344af294aa574a61fab5c4caa1719a1c519a1c7fef1cde24d6b786",
    "data/sagas/s04_compensate.json": "21e953e4edec2a247a7c60de1a068b48d411876e26b4d5aa65f1190d950d7b13",
    "data/sagas/s05_orphan.json": "071a57b046905240167c552523d267b430d4a51c155dc84971aa707c428ef51d",
    "data/sagas/s06_stalled.json": "8e75541779adf31f92edf1c0ce04e17aae04ff0e22e745a12e078ba7956261c1",
}

EXPECTED_SOURCE_HASHES = {
    "data/sagas/s01_linear.json": "d1a09980b5fd431914b5d4c049ad8fe6abe2dc9f9ee710d690ceeba59c16c370",
    "data/sagas/s02_dedup.json": "2964b7e7c333124ef2abfe74fc675e744ad7958631f37fecc67c4fbde1ed98c9",
    "data/sagas/s03_out_of_order.json": "7b29bdda402fbc4c4291407d42d18a17641cd51dbabd2bbe29adb4eab1754391",
    "data/sagas/s04_compensate.json": "e1b45fad83ac56f6a3d9e6bd5ec97b4edbe188b4d93f626918607ea643a8a62d",
    "data/sagas/s05_orphan.json": "ceed81c86c391520201f0570a1b361f47d39e58bafa7b41800f71a953d3fdeda",
    "data/sagas/s06_stalled.json": "2c12de16a3c4b12ee7fd15782308d288bc344fe1e64b52b906ac4d60b5e02aa6",
}

EXPECTED_INTEGRITY = "195e6415b1a9199201ba512f00765db977d003b793a3eec18449fe6ba5fa2ae8"


@pytest.fixture(scope="session")
def report():
    assert REPORT_PATH.is_file(), f"Missing report at {REPORT_PATH}"
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def _audit(report, saga_id):
    for a in report["saga_audits"]:
        if a["saga_id"] == saga_id:
            return a
    pytest.fail(f"Saga audit missing: {saga_id}")


def _findings(report, finding_type=None, saga_id=None):
    fs = report["findings"]
    if finding_type:
        fs = [f for f in fs if f["finding_type"] == finding_type]
    if saga_id:
        fs = [f for f in fs if f["saga_id"] == saga_id]
    return fs


# ── Rust binary ───────────────────────────────────────────────────────


def test_rust_binary_exists():
    alt = ROOT / "target" / "release" / "saga-replay-audit"
    assert BINARY.is_file() or alt.is_file(), (
        "Compiled binary missing at /app/build/saga-replay-audit"
    )


def test_rust_binary_is_elf():
    path = BINARY if BINARY.is_file() else ROOT / "target" / "release" / "saga-replay-audit"
    with open(path, "rb") as f:
        assert f.read(4) == b"\x7fELF"


# ── Input integrity ───────────────────────────────────────────────────


def test_input_files_not_modified():
    for rel, expected in EXPECTED_RAW_HASHES.items():
        fp = ROOT / rel
        assert fp.is_file(), rel
        got = hashlib.sha256(fp.read_bytes()).hexdigest()
        assert got == expected, f"{rel} tampered"


# ── Output file format ────────────────────────────────────────────────


def test_output_file_exists():
    assert REPORT_PATH.is_file()


def test_valid_json(report):
    assert isinstance(report, dict)


def test_trailing_newline():
    raw = REPORT_PATH.read_text(encoding="utf-8")
    assert raw.endswith("\n") and not raw.endswith("\n\n")


def test_two_space_indent():
    raw = REPORT_PATH.read_text(encoding="utf-8")
    assert "\t" not in raw
    assert '\n  "' in raw


def test_top_level_keys(report):
    assert set(report.keys()) == {
        "schema_version",
        "source_hashes",
        "saga_audits",
        "findings",
        "summary",
    }


def test_schema_version(report):
    assert report["schema_version"] == 1


# ── source_hashes ─────────────────────────────────────────────────────


def test_source_hash_keys(report):
    assert set(report["source_hashes"].keys()) == set(EXPECTED_SOURCE_HASHES.keys())


def test_source_hashes_sorted(report):
    assert list(report["source_hashes"].keys()) == sorted(report["source_hashes"].keys())


@pytest.mark.parametrize("rel,expected", sorted(EXPECTED_SOURCE_HASHES.items()))
def test_source_hash_value(report, rel, expected):
    assert report["source_hashes"][rel] == expected


# ── saga_audits structure ─────────────────────────────────────────────


def test_saga_audit_count(report):
    assert len(report["saga_audits"]) == 6


def test_saga_audits_sorted(report):
    ids = [a["saga_id"] for a in report["saga_audits"]]
    assert ids == sorted(ids)


def test_saga_audit_required_fields(report):
    keys = {
        "saga_id",
        "events_kept",
        "events_skipped",
        "steps_completed",
        "steps_compensated",
        "compensation_events",
        "avg_step_latency_ms",
        "integrity_lines",
    }
    for a in report["saga_audits"]:
        assert set(a.keys()) == keys


# ── per-saga metrics ──────────────────────────────────────────────────


def test_pay001_metrics(report):
    a = _audit(report, "pay-001")
    assert a["events_kept"] == 4
    assert a["events_skipped"] == 0
    assert a["steps_completed"] == 4
    assert a["avg_step_latency_ms"] == pytest.approx(32.0, abs=FLOAT_TOL)


def test_inv002_dedup_metrics(report):
    a = _audit(report, "inv-002")
    assert a["events_kept"] == 4
    assert a["events_skipped"] == 1
    assert a["avg_step_latency_ms"] == pytest.approx(9.836066, abs=FLOAT_TOL)


def test_ship003_harmonic_latency(report):
    a = _audit(report, "ship-003")
    assert a["avg_step_latency_ms"] == pytest.approx(18.786852, abs=FLOAT_TOL)


def test_ord004_compensation(report):
    a = _audit(report, "ord-004")
    assert a["steps_compensated"] == 1
    assert a["compensation_events"] == 1
    assert a["steps_completed"] == 2


def test_reg005_orphan_saga(report):
    a = _audit(report, "reg-005")
    assert a["events_kept"] == 3


def test_ful006_stalled_saga(report):
    a = _audit(report, "ful-006")
    assert a["steps_completed"] == 2
    assert a["avg_step_latency_ms"] == pytest.approx(32.941176, abs=FLOAT_TOL)


def test_integrity_lines_match_kept(report):
    for a in report["saga_audits"]:
        assert a["integrity_lines"] == a["events_kept"]


# ── findings ──────────────────────────────────────────────────────────


def test_total_findings(report):
    assert len(report["findings"]) == 4
    assert report["summary"]["total_findings"] == 4


def test_findings_sorted(report):
    fs = report["findings"]
    keys = [
        (
            f["severity_rank"],
            f["finding_type"],
            f["saga_id"],
            f["event_id"] or "",
            f["step"] or "",
        )
        for f in fs
    ]
    assert keys == sorted(keys)


def test_orphan_parent_finding(report):
    fs = _findings(report, "orphan_parent", "reg-005")
    assert len(fs) == 1
    assert fs[0]["severity"] == "high"
    assert fs[0]["evidence"]["parent_event_id"] == "ghost-9"


def test_stalled_step_finding(report):
    fs = _findings(report, "stalled_step", "ful-006")
    assert len(fs) == 1
    assert fs[0]["step"] == "pack"


def test_out_of_order_timestamp(report):
    fs = _findings(report, "out_of_order_timestamp", "ship-003")
    assert len(fs) == 1
    assert fs[0]["event_id"] == "ship-003-e2"
    assert fs[0]["evidence"]["timestamp_ms"] == 90


def test_duplicate_skipped(report):
    fs = _findings(report, "duplicate_event_skipped", "inv-002")
    assert len(fs) == 1
    assert fs[0]["evidence"]["duplicate_sequence"] == 4


def test_no_compensation_violation(report):
    assert _findings(report, "compensation_order_violation") == []


# ── summary ───────────────────────────────────────────────────────────


def test_summary_totals(report):
    s = report["summary"]
    assert s["saga_count"] == 6
    assert s["total_events_kept"] == 23
    assert s["total_events_skipped"] == 1


def test_findings_by_type(report):
    assert report["summary"]["findings_by_type"] == {
        "duplicate_event_skipped": 1,
        "orphan_parent": 1,
        "out_of_order_timestamp": 1,
        "stalled_step": 1,
    }


def test_findings_by_severity_all_keys(report):
    fbs = report["summary"]["findings_by_severity"]
    assert set(fbs.keys()) == {"critical", "high", "medium", "low", "info"}
    assert fbs["high"] == 2
    assert fbs["info"] == 1


def test_avg_saga_latency_harmonic(report):
    assert report["summary"]["avg_saga_latency_ms"] == pytest.approx(
        19.458132, abs=FLOAT_TOL
    )


def test_integrity_hash(report):
    assert report["summary"]["integrity_hash"] == EXPECTED_INTEGRITY


def test_summary_keys_sorted(report):
    assert list(report["summary"]["findings_by_type"].keys()) == sorted(
        report["summary"]["findings_by_type"].keys()
    )


# ── cross-checks ──────────────────────────────────────────────────────


def test_findings_severity_ranks_from_policy(report):
    ranks = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
    for f in report["findings"]:
        assert f["severity_rank"] == ranks[f["severity"]]


def test_finding_types_in_policy(report):
    allowed = {
        "compensation_order_violation",
        "duplicate_event_skipped",
        "orphan_parent",
        "out_of_order_timestamp",
        "stalled_step",
    }
    for f in report["findings"]:
        assert f["finding_type"] in allowed
