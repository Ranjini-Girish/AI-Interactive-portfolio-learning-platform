"""Behavioral tests for the cpp-keytab-rotation-audit task.

These tests assert the agent's outputs against the documented contract in
``instruction.md`` and ``/app/data/SPEC.md``. Hash-locked anti-cheat fixtures
are computed independently from the input data and compared against the
agent's emitted JSON files; an agent cannot pass these tests by writing
arbitrary or hand-tweaked output.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("KRA_DATA_DIR", "/app/data"))
AUDIT_DIR = Path(os.environ.get("KRA_AUDIT_DIR", "/app/audit"))

REQUIRED_OUTPUT_FILES = [
    "kvno_lifecycle.json",
    "rotation_compliance.json",
    "ticket_validity.json",
    "anomalies.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "ac05643a4e724416d8a32311ff681672784339ffc6528157fc8e041858da2387",
    "pool_state.json": "12a2bebaa00b7ff7218f4cada75a3eb48a14425a31e6d2c8aa843e126d4f81ef",
    "policies/rotation_policy.json": "b5dbf59ab591abc16a69546c9d920a25f2d54c5306a7ebd704e42cdc56007b83",
    "policies/enctype_policy.json": "00e31b664712933c6953ca20bd22c3b2539c221eda6fd98b9b1e6d5a723d5d8c",
    "principals/burner.json": "29f0bec58bd5d34d935ed89de23aefa6df3348870f9aaf607e49951fbfdba3f4",
    "principals/cache01.json": "58081b89083daa4b6ddfcf10e95e25cfc03af25a4d8bc22a55dd6b2e5ea898aa",
    "principals/cache02.json": "667ad13c723ee9905fb7b90866742013f80478a75ff2671a6a1685906ac577b4",
    "principals/db-master.json": "abfbaa488bd2938306aed0f033dcd924ac1cd91d3734f28e19537d89eadec21e",
    "principals/legacy.json": "39441f1ddd83d040dde9f5fc92a1bcff306a0a646b174e4ed3177c5967eb8865",
    "principals/mail.json": "519b7ba7a6aa15736f3890021f805d08e8e3bc5dd36dfcf5ea390aefdd6d4694",
    "principals/newhost.json": "1cea6b4e33e1779617a5ce1c4291a292d641368ac3241f7783acd92f55fe3eac",
    "principals/web01.json": "f9b1e3950dd52b415e4238f93656e82ddce6debd77d00b0eaf0e64db7be0e7e4",
    "principals/web02.json": "026768ef5f3a14f0923d9a103ace06245f6a983b746b7a7f52791e884ff03ae5",
    "events/keytab_chunk_01.jsonl": "4495b5019decc60623950f3cbb39450a7d18003dc93d05b95709e1399fa1f289",
    "events/keytab_chunk_02.jsonl": "e686a74c1f4205feed47d76a874481b0c32674f1618cd3e47a2faa995376b51f",
    "events/keytab_chunk_03.jsonl": "52e99707c8432010956804eb42aac0081cc954dd6d358a2f1f1fe2c2ae2d5907",
    "events/keytab_chunk_04.jsonl": "27ca4636825ca545b7813aadc3479e8d236f32894a31df4a865fe2e565603a44",
    "events/keytab_chunk_05.jsonl": "393673846f8795e82d8bd351b53663e506c5d6f425fc4e39dec58f7ec980dae4",
    "events/tgs_chunk_01.jsonl": "cce688de65a8d096a5b83b9df5fc3f7462faf86a5e77c946f4740e8cfb309845",
    "events/tgs_chunk_02.jsonl": "7b11e8af1559cb00ff6f0bb5e024cfad3bbaad171f5ea6d817f5d649d972c62e",
    "events/tgs_chunk_03.jsonl": "3e18993e7ecd782973943e1ec55acce59cac12078754882431423a79e059ac61",
    "events/tgs_chunk_04.jsonl": "f6422d92fc5d91e726c313cc8eb78546402cb25060707e010b58d5853a9e4904",
    "events/tgs_chunk_05.jsonl": "81f96c8d3843619f126487f5c2575dedb0b521ed3ed9409044f659ea655b8105",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "kvno_lifecycle.json": "d74a7e258fcecdb945a40fcf4a85d30d5252d49b4fdb4f7cfe8e063632a2b57d",
    "rotation_compliance.json": "5bb5ba70bbee1b89fc8b0ed7becfd0679015d18eb52dd08615f1a758c29d3fe8",
    "ticket_validity.json": "dc4d2d8c90767981482e8aefbdda3a5acec4272f0c8efabcb41c6c65f4e72edf",
    "anomalies.json": "ddad014ec13b939b8c9064753101131f45861047229e8de323182cfe5537e83a",
    "summary.json": "af36658d63c157d8446f3971f667596d565d86fabd79b8389414c1dc5e55f09b",
}

EXPECTED_FIELD_HASHES = {
    "kvno_lifecycle.principals": "424404d92f2b8ad62fc40eb54f0334b9f19b1ea6d05752b0a84699272505c05d",
    "rotation_compliance.principals": "b8159a673dce96aa5a43b4e628e5cb4cdf995095b7a978fa7b11562afec2ad97",
    "ticket_validity.requests": "a49f4b570563a0e97f15324da1b0922024a48339ec9aaa3f8a8689b1535a1edb",
    "anomalies.anomalies": "54bd1351e216f6eb1b83e59397c264b0d19c903a8055d61ce4808c8637e32118",
    "summary.tickets_per_verdict": "4d6ecd2f50ec4a96c1a620f9ffd590253e6baa1c20715fb6943f798aaa45efa2",
    "summary.anomalies_per_severity": "498efcf8ff8b3210ce2308d53d0e29616e677d9777072079ff6082aea1188919",
    "summary.compromised_principals": "712ec1a6f73344810b418b2bf60d46efe8c909fc9fb8ce17c7f15ee08758e21e",
}

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

ALL_VERDICTS = [
    "valid",
    "valid_cross_fade",
    "invalid_kvno_unknown",
    "invalid_kvno_revoked",
    "invalid_kvno_retired",
    "downgrade_attempt",
    "weak_enctype",
]

ALL_SEVERITIES = ["critical", "high", "medium", "low"]


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


def _walk_keys_sorted(node) -> bool:
    if isinstance(node, dict):
        keys = list(node.keys())
        if keys != sorted(keys):
            return False
        return all(_walk_keys_sorted(v) for v in node.values())
    if isinstance(node, list):
        return all(_walk_keys_sorted(x) for x in node)
    return True


@pytest.fixture(scope="module")
def loaded_outputs():
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: /app/audit/{name}"
        with open(p, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output /app/audit/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


# ---------------------------------------------------------------------------
# Input integrity
# ---------------------------------------------------------------------------


class TestInputIntegrity:
    """Inputs under /app/data must remain byte-identical to the original
    fixtures throughout agent execution."""

    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_file_unchanged(self, rel, expected):
        """Every documented input file's raw bytes hash to the expected SHA-256."""
        p = DATA_DIR / rel
        assert p.is_file(), f"input file vanished: {rel}"
        actual = _sha256_bytes(p.read_bytes())
        assert actual == expected, f"input file mutated: {rel}"


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------


class TestOutputStructure:
    """Each required output file exists, parses as JSON, and follows the
    deterministic on-disk formatting rules."""

    def test_audit_directory_exists(self):
        """The /app/audit directory must exist."""
        assert AUDIT_DIR.is_dir(), "/app/audit does not exist"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_file_exists(self, name):
        """Each required output file must exist as a regular file."""
        assert (AUDIT_DIR / name).is_file(), f"missing /app/audit/{name}"

    def test_no_extra_files_in_audit_dir(self, loaded_outputs):
        """The audit directory contains exactly the five required files."""
        actual = {p.name for p in AUDIT_DIR.iterdir()}
        assert actual == set(REQUIRED_OUTPUT_FILES), (
            f"unexpected files in /app/audit: {actual - set(REQUIRED_OUTPUT_FILES)}; "
            f"missing: {set(REQUIRED_OUTPUT_FILES) - actual}"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_ends_with_single_newline(self, name, loaded_outputs):
        """Each output ends with exactly one trailing newline byte."""
        data = loaded_outputs[name]["bytes"]
        assert data.endswith(b"\n"), f"{name} must end with a newline"
        assert not data.endswith(b"\n\n"), f"{name} must end with EXACTLY one newline"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_object_keys_sorted_at_every_level(self, name, loaded_outputs):
        """Every JSON object's keys are emitted in sorted order at every level."""
        text = loaded_outputs[name]["text"]
        parsed = json.loads(text)
        assert _walk_keys_sorted(parsed), f"{name} has unsorted object keys somewhere"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_matches_two_space_indent(self, name, loaded_outputs):
        """Each output file is formatted with two-space indent and sorted keys."""
        obj = loaded_outputs[name]["obj"]
        expected = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        actual = loaded_outputs[name]["text"]
        assert actual == expected, f"{name} on-disk form differs from canonical pretty form"


# ---------------------------------------------------------------------------
# kvno_lifecycle.json
# ---------------------------------------------------------------------------


class TestKvnoLifecycle:
    """Schema and ordering of /app/audit/kvno_lifecycle.json."""

    def test_top_level_keys(self, loaded_outputs):
        """kvno_lifecycle has exactly the key ``principals``."""
        obj = loaded_outputs["kvno_lifecycle.json"]["obj"]
        assert set(obj.keys()) == {"principals"}

    def test_principals_sorted_alphabetically(self, loaded_outputs):
        """The principals list is sorted by principal name ascending."""
        obj = loaded_outputs["kvno_lifecycle.json"]["obj"]
        names = [e["principal"] for e in obj["principals"]]
        assert names == sorted(names)

    def test_principal_entries_have_required_keys(self, loaded_outputs):
        """Each principal entry has exactly the keys principal/tier/exempt/kvno_events."""
        obj = loaded_outputs["kvno_lifecycle.json"]["obj"]
        required = {"principal", "tier", "exempt", "kvno_events"}
        for e in obj["principals"]:
            assert set(e.keys()) == required, f"unexpected keys in entry {e.get('principal')}"

    def test_kvno_events_sorted_by_kvno(self, loaded_outputs):
        """Within each principal, kvno_events is sorted by kvno ascending."""
        obj = loaded_outputs["kvno_lifecycle.json"]["obj"]
        for e in obj["principals"]:
            kvnos = [k["kvno"] for k in e["kvno_events"]]
            assert kvnos == sorted(kvnos), f"kvno_events not sorted for {e['principal']}"

    def test_kvno_event_entries_have_required_keys(self, loaded_outputs):
        """Each kvno_event entry has the documented keys."""
        obj = loaded_outputs["kvno_lifecycle.json"]["obj"]
        required = {
            "kvno", "added_day", "added_hour", "enctype",
            "revoked_day", "revoked_hour", "revoke_reason",
            "retired_day", "retired_hour", "final_state",
        }
        for e in obj["principals"]:
            for ke in e["kvno_events"]:
                assert set(ke.keys()) == required

    def test_final_state_canonical_values(self, loaded_outputs):
        """final_state is one of active/revoked/retired."""
        obj = loaded_outputs["kvno_lifecycle.json"]["obj"]
        allowed = {"active", "revoked", "retired"}
        for e in obj["principals"]:
            for ke in e["kvno_events"]:
                assert ke["final_state"] in allowed

    def test_revoked_fields_consistent(self, loaded_outputs):
        """revoked_day, revoked_hour, revoke_reason are jointly null or jointly set."""
        obj = loaded_outputs["kvno_lifecycle.json"]["obj"]
        for e in obj["principals"]:
            for ke in e["kvno_events"]:
                triple = (ke["revoked_day"], ke["revoked_hour"], ke["revoke_reason"])
                if any(x is None for x in triple):
                    assert all(x is None for x in triple), f"partial revoked triple in {e['principal']} kvno={ke['kvno']}"
                if ke["final_state"] == "revoked":
                    assert all(x is not None for x in triple)

    def test_retired_fields_consistent(self, loaded_outputs):
        """retired_day and retired_hour are jointly null or jointly set."""
        obj = loaded_outputs["kvno_lifecycle.json"]["obj"]
        for e in obj["principals"]:
            for ke in e["kvno_events"]:
                pair = (ke["retired_day"], ke["retired_hour"])
                if any(x is None for x in pair):
                    assert all(x is None for x in pair)
                if ke["final_state"] == "retired":
                    assert all(x is not None for x in pair)

    def test_no_kvnos_for_newhost(self, loaded_outputs):
        """newhost has no add events and therefore an empty kvno_events list."""
        obj = loaded_outputs["kvno_lifecycle.json"]["obj"]
        nh = [e for e in obj["principals"] if "newhost" in e["principal"]]
        assert len(nh) == 1
        assert nh[0]["kvno_events"] == []

    def test_web01_has_five_kvnos(self, loaded_outputs):
        """web01 received an add for every kvno in {1,2,3,4,5}."""
        obj = loaded_outputs["kvno_lifecycle.json"]["obj"]
        w = next(e for e in obj["principals"] if "web01" in e["principal"])
        assert sorted(k["kvno"] for k in w["kvno_events"]) == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# rotation_compliance.json
# ---------------------------------------------------------------------------


class TestRotationCompliance:
    """Schema and rule enforcement for rotation_compliance.json."""

    def test_top_level_keys(self, loaded_outputs):
        """rotation_compliance has exactly the key ``principals``."""
        obj = loaded_outputs["rotation_compliance.json"]["obj"]
        assert set(obj.keys()) == {"principals"}

    def test_principals_sorted_alphabetically(self, loaded_outputs):
        """The principals list is sorted by principal name ascending."""
        obj = loaded_outputs["rotation_compliance.json"]["obj"]
        names = [e["principal"] for e in obj["principals"]]
        assert names == sorted(names)

    def test_entries_have_required_keys(self, loaded_outputs):
        """Each rotation_compliance entry has the documented keys."""
        obj = loaded_outputs["rotation_compliance.json"]["obj"]
        required = {
            "principal", "tier", "exempt",
            "rotation_window_days", "last_rotation_day", "next_due_day", "status",
        }
        for e in obj["principals"]:
            assert set(e.keys()) == required

    def test_exempt_principal_fields_all_null(self, loaded_outputs):
        """For exempt principals, window/last/next are null and status is exempt."""
        obj = loaded_outputs["rotation_compliance.json"]["obj"]
        for e in obj["principals"]:
            if e["exempt"]:
                assert e["rotation_window_days"] is None
                assert e["last_rotation_day"] is None
                assert e["next_due_day"] is None
                assert e["status"] == "exempt"

    def test_never_rotated_implies_nulls(self, loaded_outputs):
        """When status is never_rotated, last and next day are both null."""
        obj = loaded_outputs["rotation_compliance.json"]["obj"]
        for e in obj["principals"]:
            if e["status"] == "never_rotated":
                assert e["last_rotation_day"] is None
                assert e["next_due_day"] is None
                assert e["exempt"] is False

    def test_overdue_means_next_due_strictly_less_than_current_day(self, loaded_outputs):
        """For overdue principals, next_due_day < current_day."""
        obj = loaded_outputs["rotation_compliance.json"]["obj"]
        cur = loaded_outputs["summary.json"]["obj"]["current_day"]
        for e in obj["principals"]:
            if e["status"] == "overdue":
                assert isinstance(e["next_due_day"], int)
                assert e["next_due_day"] < cur

    def test_status_canonical_values(self, loaded_outputs):
        """status is one of compliant/overdue/exempt/never_rotated."""
        obj = loaded_outputs["rotation_compliance.json"]["obj"]
        allowed = {"compliant", "overdue", "exempt", "never_rotated"}
        for e in obj["principals"]:
            assert e["status"] in allowed

    def test_burner_override_window_is_three(self, loaded_outputs):
        """burner has override_rotation_days=3 and so its window is 3 not 14."""
        obj = loaded_outputs["rotation_compliance.json"]["obj"]
        b = next(e for e in obj["principals"] if "burner" in e["principal"])
        assert b["rotation_window_days"] == 3

    def test_newhost_status_is_never_rotated(self, loaded_outputs):
        """newhost has no add events and therefore status=never_rotated."""
        obj = loaded_outputs["rotation_compliance.json"]["obj"]
        nh = next(e for e in obj["principals"] if "newhost" in e["principal"])
        assert nh["status"] == "never_rotated"

    def test_web02_status_is_overdue(self, loaded_outputs):
        """web02's last add was day 7, current_day 30, window 7, so it is overdue."""
        obj = loaded_outputs["rotation_compliance.json"]["obj"]
        w = next(e for e in obj["principals"] if "web02" in e["principal"])
        assert w["status"] == "overdue"


# ---------------------------------------------------------------------------
# ticket_validity.json
# ---------------------------------------------------------------------------


class TestTicketValidity:
    """Schema and verdict assignment for ticket_validity.json."""

    def test_top_level_keys(self, loaded_outputs):
        """ticket_validity has exactly the key ``requests``."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        assert set(obj.keys()) == {"requests"}

    def test_requests_sorted_temporally(self, loaded_outputs):
        """The requests list is sorted by (day, hour, request_id) ascending."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        keys = [(r["day"], r["hour"], r["request_id"]) for r in obj["requests"]]
        assert keys == sorted(keys)

    def test_request_entries_have_required_keys(self, loaded_outputs):
        """Each request entry has the documented keys."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        required = {"request_id", "principal", "kvno", "day", "hour", "verdict", "policy_version"}
        for r in obj["requests"]:
            assert set(r.keys()) == required

    def test_verdicts_canonical_values(self, loaded_outputs):
        """Every verdict is one of the seven documented values."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        for r in obj["requests"]:
            assert r["verdict"] in ALL_VERDICTS

    def test_invalid_requests_omitted(self, loaded_outputs):
        """Three invalid TGS requests are omitted from ticket_validity."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        rids = {r["request_id"] for r in obj["requests"]}
        for bad in ("tgs_bad001", "tgs_bad002", "tgs_bad003"):
            assert bad not in rids, f"invalid request {bad} should be omitted"

    def test_known_valid_cross_fade_request(self, loaded_outputs):
        """The web01 kvno=1 request at day 7 hour 12 is verdict valid_cross_fade."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        r = next(r for r in obj["requests"] if r["request_id"] == "tgs_002")
        assert r["verdict"] == "valid_cross_fade"

    def test_known_revoked_request(self, loaded_outputs):
        """The db-master kvno=2 request after the compromise revoke is verdict invalid_kvno_revoked."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        r = next(r for r in obj["requests"] if r["request_id"] == "tgs_005")
        assert r["verdict"] == "invalid_kvno_revoked"

    def test_known_retired_request(self, loaded_outputs):
        """The web01 kvno=1 request after retirement is verdict invalid_kvno_retired."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        r = next(r for r in obj["requests"] if r["request_id"] == "tgs_003")
        assert r["verdict"] == "invalid_kvno_retired"

    def test_known_downgrade_request(self, loaded_outputs):
        """The cache01 kvno=1 request past cross-fade under v1 is verdict downgrade_attempt."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        r = next(r for r in obj["requests"] if r["request_id"] == "tgs_008")
        assert r["verdict"] == "downgrade_attempt"

    def test_known_weak_enctype_request(self, loaded_outputs):
        """The cache01 kvno=1 request after policy v2 effective is verdict weak_enctype."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        r = next(r for r in obj["requests"] if r["request_id"] == "tgs_009")
        assert r["verdict"] == "weak_enctype"

    def test_known_unknown_kvno_request(self, loaded_outputs):
        """A request for kvno=99 against web01 (never added) is verdict invalid_kvno_unknown."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        r = next(r for r in obj["requests"] if r["request_id"] == "tgs_012")
        assert r["verdict"] == "invalid_kvno_unknown"

    def test_policy_version_present(self, loaded_outputs):
        """Every request has a non-empty policy_version string."""
        obj = loaded_outputs["ticket_validity.json"]["obj"]
        for r in obj["requests"]:
            assert isinstance(r["policy_version"], str) and r["policy_version"]


# ---------------------------------------------------------------------------
# anomalies.json
# ---------------------------------------------------------------------------


class TestAnomalies:
    """Schema, sort order, and id derivation for anomalies.json."""

    SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def test_top_level_keys(self, loaded_outputs):
        """anomalies has exactly the key ``anomalies``."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        assert set(obj.keys()) == {"anomalies"}

    def test_entries_have_required_keys(self, loaded_outputs):
        """Each anomaly entry has the documented keys."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        required = {"id", "kind", "severity", "principal", "kvno", "day", "hour", "details"}
        for a in obj["anomalies"]:
            assert set(a.keys()) == required

    def test_severity_canonical_values(self, loaded_outputs):
        """severity is one of critical/high/medium/low."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        for a in obj["anomalies"]:
            assert a["severity"] in ALL_SEVERITIES

    def test_id_is_lowercase_hex64(self, loaded_outputs):
        """Each anomaly id is a 64-character lowercase hex string."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        for a in obj["anomalies"]:
            assert HEX64_RE.match(a["id"]), f"bad id format: {a['id']}"

    def test_id_matches_documented_derivation(self, loaded_outputs):
        """Each id equals SHA-256 of the canonical JSON of the documented key set."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        for a in obj["anomalies"]:
            key = {
                "day": a["day"],
                "hour": a["hour"],
                "kind": a["kind"],
                "kvno": a["kvno"],
                "principal": a["principal"],
            }
            expected = _sha256_bytes(
                json.dumps(key, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            )
            assert a["id"] == expected, f"id mismatch for {a['kind']} on {a['principal']}"

    def test_anomalies_sorted_by_documented_order(self, loaded_outputs):
        """anomalies is sorted by (severity-desc, day, hour, kind, principal, kvno) with null kvno last."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        prev = None
        for a in obj["anomalies"]:
            kvno_key = (1, 0) if a["kvno"] is None else (0, a["kvno"])
            key = (self.SEV_RANK[a["severity"]], a["day"], a["hour"], a["kind"], a["principal"], kvno_key)
            if prev is not None:
                assert prev <= key, f"anomaly out of order: prev={prev}, this={key}"
            prev = key

    def test_details_match_canonical_form(self, loaded_outputs):
        """details is "<kind> on <principal>" or "<kind> on <principal> kvno=<kvno>"."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        for a in obj["anomalies"]:
            if a["kvno"] is None:
                expected = f"{a['kind']} on {a['principal']}"
            else:
                expected = f"{a['kind']} on {a['principal']} kvno={a['kvno']}"
            assert a["details"] == expected

    def test_known_compromised_principal_referenced_critical(self, loaded_outputs):
        """At least one compromised_principal_referenced anomaly exists at critical severity."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        matches = [a for a in obj["anomalies"] if a["kind"] == "compromised_principal_referenced"]
        assert matches
        for a in matches:
            assert a["severity"] == "critical"

    def test_known_kvno_non_monotonic_high(self, loaded_outputs):
        """The two cache02 monotonicity violations appear as high-severity anomalies."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        matches = [a for a in obj["anomalies"] if a["kind"] == "kvno_non_monotonic"]
        assert len(matches) >= 2
        for a in matches:
            assert a["severity"] == "high"

    def test_known_never_rotated_anomaly_exists(self, loaded_outputs):
        """newhost has a never_rotated anomaly of severity high."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        matches = [a for a in obj["anomalies"] if a["kind"] == "never_rotated"]
        assert matches
        assert any("newhost" in a["principal"] for a in matches)
        for a in matches:
            assert a["severity"] == "high"

    def test_known_excessive_rotation_low(self, loaded_outputs):
        """excessive_rotation anomalies are recorded at severity low."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        matches = [a for a in obj["anomalies"] if a["kind"] == "excessive_rotation"]
        assert matches
        for a in matches:
            assert a["severity"] == "low"

    def test_known_missed_retirement_medium(self, loaded_outputs):
        """missed_retirement anomalies are recorded at severity medium."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        matches = [a for a in obj["anomalies"] if a["kind"] == "missed_retirement"]
        assert matches
        for a in matches:
            assert a["severity"] == "medium"

    def test_known_forbidden_enctype_active_medium(self, loaded_outputs):
        """forbidden_enctype_active anomalies are recorded at severity medium."""
        obj = loaded_outputs["anomalies.json"]["obj"]
        matches = [a for a in obj["anomalies"] if a["kind"] == "forbidden_enctype_active"]
        assert matches
        for a in matches:
            assert a["severity"] == "medium"


# ---------------------------------------------------------------------------
# summary.json
# ---------------------------------------------------------------------------


class TestSummary:
    """Aggregate counts in summary.json."""

    def test_top_level_keys(self, loaded_outputs):
        """summary has exactly the documented keys."""
        obj = loaded_outputs["summary.json"]["obj"]
        expected = {
            "current_day", "current_hour", "total_principals", "exempt_principals",
            "invalid_principals", "total_keytab_events", "invalid_keytab_events",
            "total_tgs_requests", "invalid_tgs_requests",
            "tickets_per_verdict", "anomalies_per_severity", "compromised_principals",
        }
        assert set(obj.keys()) == expected

    def test_current_day_matches_pool_state(self, loaded_outputs):
        """current_day in summary equals current_day in pool_state.json."""
        pool = json.loads((DATA_DIR / "pool_state.json").read_text(encoding="utf-8"))
        obj = loaded_outputs["summary.json"]["obj"]
        assert obj["current_day"] == pool["current_day"]
        assert obj["current_hour"] == pool["current_hour"]

    def test_tickets_per_verdict_contains_every_verdict(self, loaded_outputs):
        """tickets_per_verdict has every documented verdict key, sorted."""
        obj = loaded_outputs["summary.json"]["obj"]
        assert set(obj["tickets_per_verdict"].keys()) == set(ALL_VERDICTS)
        keys = list(obj["tickets_per_verdict"].keys())
        assert keys == sorted(keys)

    def test_anomalies_per_severity_contains_every_severity(self, loaded_outputs):
        """anomalies_per_severity has all four severity keys, sorted."""
        obj = loaded_outputs["summary.json"]["obj"]
        assert set(obj["anomalies_per_severity"].keys()) == set(ALL_SEVERITIES)
        keys = list(obj["anomalies_per_severity"].keys())
        assert keys == sorted(keys)

    def test_compromised_principals_sorted(self, loaded_outputs):
        """compromised_principals is sorted ascending."""
        obj = loaded_outputs["summary.json"]["obj"]
        names = obj["compromised_principals"]
        assert names == sorted(names)

    def test_tickets_per_verdict_sum_equals_processed_requests(self, loaded_outputs):
        """Sum of tickets_per_verdict equals total_tgs_requests minus invalid_tgs_requests."""
        obj = loaded_outputs["summary.json"]["obj"]
        s = sum(obj["tickets_per_verdict"].values())
        assert s == obj["total_tgs_requests"] - obj["invalid_tgs_requests"]

    def test_anomalies_per_severity_sum_matches_list_length(self, loaded_outputs):
        """Sum of anomalies_per_severity equals len(anomalies.anomalies)."""
        s_sum = sum(loaded_outputs["summary.json"]["obj"]["anomalies_per_severity"].values())
        assert s_sum == len(loaded_outputs["anomalies.json"]["obj"]["anomalies"])

    def test_total_principals_matches_lifecycle_plus_invalid(self, loaded_outputs):
        """total_principals = len(kvno_lifecycle.principals) + invalid_principals."""
        s = loaded_outputs["summary.json"]["obj"]
        k = loaded_outputs["kvno_lifecycle.json"]["obj"]
        assert s["total_principals"] == len(k["principals"]) + s["invalid_principals"]

    def test_db_master_is_only_compromised(self, loaded_outputs):
        """The only compromised principal is db-master."""
        obj = loaded_outputs["summary.json"]["obj"]
        assert len(obj["compromised_principals"]) == 1
        assert "db-master" in obj["compromised_principals"][0]

    def test_one_exempt_principal(self, loaded_outputs):
        """Exactly one principal is exempt (legacy)."""
        obj = loaded_outputs["summary.json"]["obj"]
        assert obj["exempt_principals"] == 1


# ---------------------------------------------------------------------------
# Canonical hashes (value lock)
# ---------------------------------------------------------------------------


class TestCanonicalHashes:
    """The canonical (whitespace-independent) value of each output is locked."""

    @pytest.mark.parametrize("name", sorted(EXPECTED_OUTPUT_CANONICAL_HASHES.keys()))
    def test_canonical_hash(self, name, loaded_outputs):
        """The structurally-canonical SHA-256 of each output matches expected."""
        obj = loaded_outputs[name]["obj"]
        actual = _canonical_sha256(obj)
        assert actual == EXPECTED_OUTPUT_CANONICAL_HASHES[name], (
            f"{name} canonical hash mismatch: {actual} != {EXPECTED_OUTPUT_CANONICAL_HASHES[name]}"
        )


# ---------------------------------------------------------------------------
# Field-level hashes (pinpoint diagnostics)
# ---------------------------------------------------------------------------


class TestFieldHashes:
    """Field-level hashes let us pinpoint which output is wrong on failure."""

    FIELD_PATHS = {
        "kvno_lifecycle.principals": ("kvno_lifecycle.json", ("principals",)),
        "rotation_compliance.principals": ("rotation_compliance.json", ("principals",)),
        "ticket_validity.requests": ("ticket_validity.json", ("requests",)),
        "anomalies.anomalies": ("anomalies.json", ("anomalies",)),
        "summary.tickets_per_verdict": ("summary.json", ("tickets_per_verdict",)),
        "summary.anomalies_per_severity": ("summary.json", ("anomalies_per_severity",)),
        "summary.compromised_principals": ("summary.json", ("compromised_principals",)),
    }

    @pytest.mark.parametrize("key", sorted(EXPECTED_FIELD_HASHES.keys()))
    def test_field_canonical_hash(self, key, loaded_outputs):
        """Each documented field's canonical hash matches expected."""
        fname, path = self.FIELD_PATHS[key]
        obj = loaded_outputs[fname]["obj"]
        for p in path:
            obj = obj[p]
        actual = _canonical_sha256(obj)
        assert actual == EXPECTED_FIELD_HASHES[key], (
            f"{key} field hash mismatch: {actual} != {EXPECTED_FIELD_HASHES[key]}"
        )
