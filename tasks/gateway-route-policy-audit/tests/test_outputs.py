"""Behavioral tests for the gateway route policy audit task."""

import hashlib
import json
import os
from pathlib import Path


DOMAIN = Path(os.environ.get("GRA_DATA_DIR", "/app/gateway"))
OUT_PATH = Path(os.environ.get("GRA_AUDIT_PATH", "/app/out/gateway_audit.json"))


EXPECTED_INPUT_FINGERPRINT = "8c16180c01e8f2259908657630f21628542c407e4373971e1e3349babbb90a6a"

# SHA-256 of the entire on-disk report bytes (UTF-8, two-space `encoding/json` layout, no trailing newline).
EXPECTED_FULL_REPORT_SHA256 = (
    "68da322a8615fc920ffd07812b0397057a5258c40d604eb1c404d2f5249046a4"
)

EXPECTED_FIELD_HASHES = {
    "evaluations": "58a4f763319814ea544c104f5c77c55d55bdc8cfc01d7c9c03628d3cf86ab547",
    "group_resolution": "253bc6748bd5abf98a886bfd865448a483530f625920e846b3b024d9063e14ba",
    "overrides": "8c01c0e09de70bab7b6ed9988dc29cc2a8eca1943e272424ce54e99e06a297c3",
    "summary": "fec3859989a3172678669ef5de21a63591588fe650696ab03a2d23e07e195256",
    "violations": "11e40697ad43e7b172ee8d9fcc3113ecf814e525e8eb24ee3f92bc7afb2b9fc9",
}


def _iter_files(root: Path):
    files = [p for p in root.rglob("*") if p.is_file()]
    return sorted(files, key=lambda p: p.as_posix())


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workspace_fingerprint(root: Path) -> str:
    h = hashlib.sha256()
    for p in _iter_files(root):
        rel = p.relative_to(root).as_posix()
        h.update(rel.encode())
        h.update(b"\n")
        h.update(_file_sha256(p).encode())
        h.update(b"\n")
    return h.hexdigest()


def _stable_hash(value) -> str:
    s = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _load_report():
    raw = OUT_PATH.read_bytes()
    _assert_raw_report_bytes(raw)
    obj = json.loads(raw.decode("utf-8"))
    return obj


def _assert_raw_report_bytes(raw: bytes) -> None:
    """Enforces on-disk UTF-8, LF-only, no trailing newline, and two-space indent steps."""
    if raw.endswith(b"\n"):
        raise AssertionError("Output must not have a trailing newline.")
    text = raw.decode("utf-8")
    if "\r" in text:
        raise AssertionError("Output must use LF newlines only.")
    for line in text.split("\n"):
        if not line:
            continue
        lead = len(line) - len(line.lstrip(" "))
        if lead % 2 != 0:
            raise AssertionError("Every output line must use a multiple of two leading spaces.")
        if line[:lead].replace(" ", "") != "":
            raise AssertionError("Indentation must be spaces only (no tabs).")


def _eval_by_id(report):
    return {row["request_id"]: row for row in report["evaluations"]}


def _violation_codes(report):
    return {v["code"] for v in report["violations"]}


class TestInputIntegrity:
    def test_input_fingerprint_matches_fixture(self):
        """Verifies the input workspace matches the expected fixture contents."""
        fp = _workspace_fingerprint(DOMAIN)
        assert fp == EXPECTED_INPUT_FINGERPRINT


class TestReportStructure:
    def test_report_file_exists(self):
        """Ensures the report file is created at the required absolute path."""
        assert OUT_PATH.exists()

    def test_full_report_raw_bytes_sha256(self):
        """Locks the exact serialized bytes; parsing and re-serializing JSON is not equivalent."""
        raw = OUT_PATH.read_bytes()
        _assert_raw_report_bytes(raw)
        got = hashlib.sha256(raw).hexdigest()
        assert got == EXPECTED_FULL_REPORT_SHA256

    def test_top_level_keys_exact(self):
        """Ensures the report has exactly the required top-level keys and no others."""
        report = _load_report()
        assert sorted(report.keys()) == [
            "evaluations",
            "group_resolution",
            "overrides",
            "summary",
            "violations",
        ]


class TestEvaluations:
    def test_evaluations_hash(self):
        """Hash-locks the canonical value of the evaluations field."""
        report = _load_report()
        assert _stable_hash(report["evaluations"]) == EXPECTED_FIELD_HASHES["evaluations"]


class TestGroupResolution:
    def test_group_resolution_hash(self):
        """Hash-locks the canonical value of the group_resolution field."""
        report = _load_report()
        assert _stable_hash(report["group_resolution"]) == EXPECTED_FIELD_HASHES["group_resolution"]


class TestOverrides:
    def test_overrides_hash(self):
        """Hash-locks the canonical value of the overrides field."""
        report = _load_report()
        assert _stable_hash(report["overrides"]) == EXPECTED_FIELD_HASHES["overrides"]


class TestViolations:
    def test_violations_hash(self):
        """Hash-locks the canonical value of the violations field."""
        report = _load_report()
        assert _stable_hash(report["violations"]) == EXPECTED_FIELD_HASHES["violations"]


class TestSummary:
    def test_summary_hash(self):
        """Hash-locks the canonical value of the summary field."""
        report = _load_report()
        assert _stable_hash(report["summary"]) == EXPECTED_FIELD_HASHES["summary"]

    def test_summary_counts_align_with_evaluations(self):
        """Summary totals must equal counts derived from the evaluations array."""
        report = _load_report()
        ev = report["evaluations"]
        summary = report["summary"]
        assert summary["requests_total"] == len(ev)
        assert summary["allow"] == sum(1 for row in ev if row["decision"] == "allow")
        assert summary["deny"] == sum(1 for row in ev if row["decision"] == "deny")
        assert summary["incident_lock_denies"] == sum(
            1 for row in ev if row["reason"] == "incident_lock"
        )
        assert summary["violations_count"] == len(report["violations"])


class TestIncidentOverrides:
    def test_incident_lock_on_locked_host_without_break_glass(self):
        """A locked host without valid break-glass must deny with reason incident_lock."""
        report = _load_report()
        row = _eval_by_id(report)["q07"]
        assert row["decision"] == "deny"
        assert row["reason"] == "incident_lock"
        assert row["matched_rule_id"] is None

    def test_break_glass_skip_allows_route_match(self):
        """Valid break-glass on a locked host must resume normal route evaluation."""
        report = _load_report()
        row = _eval_by_id(report)["q08"]
        assert row["decision"] == "allow"
        assert row["reason"] == "matched"
        kinds = [o["kind"] for o in report["overrides"] if o["request_id"] == "q08"]
        assert "break_glass_skip" in kinds

    def test_override_kinds_cover_incident_lock_and_break_glass(self):
        """The bundled dataset must emit both override kinds at least once."""
        kinds = {o["kind"] for o in _load_report()["overrides"]}
        assert kinds == {"break_glass_skip", "incident_lock"}


class TestViolationsCoverage:
    def test_group_cycle_violations_for_cyclic_groups(self):
        """Each group on a cycle must emit a group_cycle violation."""
        report = _load_report()
        cyclic = {v["detail"] for v in report["violations"] if v["code"] == "group_cycle"}
        assert cyclic == {
            "group=broken",
            "group=cycle_a",
            "group=cycle_b",
        }

    def test_duplicate_rule_id_violation_present(self):
        """Globally duplicated rule ids must surface duplicate_rule_id once per id."""
        report = _load_report()
        dupes = [v for v in report["violations"] if v["code"] == "duplicate_rule_id"]
        assert len(dupes) == 1
        assert dupes[0]["detail"] == "id=dup-open"

    def test_unknown_group_violation_present(self):
        """Global validation emits unknown_group for any rule with a missing group name, even if no request hits that route."""
        report = _load_report()
        codes = _violation_codes(report)
        assert "unknown_group" in codes
        hits = [
            v["detail"]
            for v in report["violations"]
            if v["code"] == "unknown_group"
        ]
        assert hits == ["pack=epsilon rule=ghost group=not-a-real-group"]

    def test_rule_uses_cyclic_group_violation_present(self):
        """Rules bound to cyclic groups must emit rule_uses_cyclic_group."""
        report = _load_report()
        assert "rule_uses_cyclic_group" in _violation_codes(report)


class TestHostAndGroupSemantics:
    def test_suffix_host_match_allows_subdomain(self):
        """Suffix host_type must match a subdomain of the declared base host."""
        report = _load_report()
        row = _eval_by_id(report)["q03"]
        assert row["reason"] == "matched"
        assert row["matched_rule_id"] == "corp-edge"

    def test_partner_group_inherits_base_trace_header(self):
        """Partner group resolution must merge base headers before partner overrides."""
        report = _load_report()
        partner = report["group_resolution"]["partner"]
        assert partner["extends_linearized"] == ["base", "partner"]
        assert partner["required_headers"]["X-Trace"] == "1"
        assert partner["required_headers"]["X-Partner"] == "prefix:corp"
