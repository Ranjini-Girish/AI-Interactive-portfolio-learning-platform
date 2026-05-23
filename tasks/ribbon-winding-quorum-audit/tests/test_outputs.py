# scaffold-status: oracle-pending
"""Verifier suite for the ribbon winding quorum audit task.

Hash-locks the bundled lab tree and the four emitted audit JSON files, plus a
small set of semantic checks on crisis activation, incident counts, and lane
status tallies.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RWQ_DATA_DIR", "/app/rwq_lab"))
AUDIT_DIR = Path(os.environ.get("RWQ_AUDIT_DIR", "/app/rwq_audit"))

OUTPUT_FILES = (
    "segment_quorum.json",
    "lane_summary.json",
    "incident_effects.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "87c83ad62b0a893bb8ff1aaa94aafcf3aaa8eaf96f4e870b68c25567fd763ca4",
    "anchors/hi.json": "7db81b2f8a23d6de47ced754753c9549d7cd2933f6a4f7e684e37b3bbd48f997",
    "anchors/lo.json": "f545598799764c5a002e44c45835b15f24520ed2bf5e8443c144dafed8b5c994",
    "ancillary/meta.json": "c6c26ca7a631f0b6cc95791832ecaa17bf7018c19c76e887e706ea3e2bd22294",
    "ancillary/notes.json": "bb04de634ffd03e37d037c142238f4b3f00172b3737e5872450dc18c110f6840",
    "ancillary/stub.json": "66f0308c45b8dd46fdd9ce0dbdbf4a3635436d4364128cee9a25602a1a845680",
    "domain_layout.json": "ef59aa51a2f3dc5a28d1f86c7fd40648d6d780e1a3dc227fa4e5c8574e09fc32",
    "incident_log.json": "389db1f6bb5930776ed44c0205a6c2cd5f3f6ffae2b56bbbbb5d22fc94fb99d5",
    "index.json": "4be202dad5cb8fa815fe8fcfb7a0efceaee4483137bded841b803c543e64097e",
    "policy.json": "9dff5dbff4a390da126d692f72f444a9067d3c4f3b9be048c3e54016c63fa805",
    "pool_state.json": "0ebe1e141bbf159aac633f2c318304fc110b365909a197eacc88ed02c305e0e8",
    "segments/s00.json": "63b8e75508ba730b11212bea0aefe04ee0a3514450ef275bf8e4e15fbc54aa48",
    "segments/s01.json": "3beeab80424b116a6a042a38b55f79f97f62d7b20f2adb06855d94272afe8238",
    "segments/s02.json": "1543fe63cce81cd16d22c152f479b7ced657e487331e2b434caf4e6819715c63",
    "segments/s03.json": "430549b8212793bef21bbf0291d21547c67bd24b7e311f6feb826ec5a6b71ea1",
    "segments/s04.json": "92c802deec5b71ba1b7c0596a4b9bcd7fa41502effc607b5aef2ddcbb74c65e7",
    "segments/s05.json": "d9cd5441b51352f161a1449ab12867c22e9aba282f8f9918c2b7609d6f44ba8c",
    "segments/s06.json": "c8296da4a1c110e7e7272fba20b480fd8a9495b631d348426522a677ed22e880",
    "segments/s07.json": "5706ccf945b3f51d0f9af637450e11e8e4910e02c1cadd93eda9da4fc6fbd9d9",
    "segments/s08.json": "9f5c987062bde9997452bb6ecaf96ac7c2f80898d4f4c7cb546ab0fa774ef07f",
    "segments/s09.json": "047ea21d1d25607eed5b8428ef3180a56652b847d2de2b32eed2b0a470f6d4b8",
    "segments/s10.json": "54afc29df2d1ebffeb78bc0baef80247f8c9996ef8b020d11916bd38a1c336ad",
    "segments/s11.json": "cfaea9569a62ff59e31cadc39dfa058ae782a8c31dc2339d4c03989fa72176e3",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "segment_quorum.json": "1019b7d0e07ecf1aced8ad3ea85b0913636021c9cfa54cb7e3d2816b245245fd",
    "lane_summary.json": "e01673e8bda14cd08189cfe163bedecf24c161d9589e499c750414d643f292a4",
    "incident_effects.json": "154de3ae8984a9afc10c5776034749482648a1de76546dc7f84b7e8f033ef27d",
    "summary.json": "64642b50caa471c00f968f46e478a107985f117ea20cb405e9baa921fddee79c",
}


EXPECTED_FIELD_HASHES = {
    "incident_effects.applied": "12964c1dd420c20573db7425f56ce2ee62d8592b0ecdafbc4b75f6bd95e540e8",
    "lane_summary.lanes": "05bd4ef3f421295cc6938008a448ac08a45535b188f270264a8048768a4f1d8c",
    "segment_quorum.segments": "c8d47ceec7df70e71a46031b55190db14529812a2fa0ba479869de276c9b4a48",
}


def _sha256_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 of the given bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize value as canonical minified JSON for digest comparison."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Parse JSON from disk using UTF-8."""
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted audit artifacts once per session."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


class TestInputIntegrity:
    """Verify the mounted workspace matches the frozen reference bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the data directory must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Verify emitted JSON files exist and hash-lock to the canonical contract."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_nested_field_hashes(self, outputs: dict[str, object]) -> None:
        """Nested collections remain stable under canonical serialisation."""
        sq = outputs["segment_quorum.json"]
        assert isinstance(sq, dict)
        seg = _canonical(sq["segments"])
        assert (
            _sha256_bytes(seg.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["segment_quorum.segments"]
        )

        ls = outputs["lane_summary.json"]
        assert isinstance(ls, dict)
        lanes = _canonical(ls["lanes"])
        assert (
            _sha256_bytes(lanes.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["lane_summary.lanes"]
        )

        inc = outputs["incident_effects.json"]
        assert isinstance(inc, dict)
        applied = _canonical(inc["applied"])
        assert (
            _sha256_bytes(applied.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_effects.applied"]
        )


class TestCrisisAndSummary:
    """Crisis latch and summary counters."""

    def test_crisis_latches_on_severity_day(self, outputs: dict[str, object]) -> None:
        """Crisis mode arms on the first eligible incident meeting the floor."""
        sm = outputs["summary.json"]
        assert sm["crisis_triggered"] is True
        assert sm["crisis_trigger_day"] == 2
        assert sm["active_quorum_floor"] == 8

    def test_summary_counts(self, outputs: dict[str, object]) -> None:
        """Summary counters reflect the bundled replay outcome."""
        sm = outputs["summary.json"]
        assert sm["eligible_incidents"] == 5
        assert sm["applied_incidents"] == 5
        assert sm["segments_total"] == 12
        assert sm["satisfied_count"] == 3
        assert sm["lane_frozen_count"] == 4
        assert sm["missing_slot_count"] == 1


class TestSegmentStatuses:
    """Positive coverage for each terminal status string."""

    def test_status_examples_present(self, outputs: dict[str, object]) -> None:
        """Bundled segments include ok, short, lane_frozen, and slot_missing outcomes."""
        segs = outputs["segment_quorum.json"]["segments"]
        by_id = {s["id"]: s for s in segs}
        assert by_id["s01"]["status"] == "ok"
        assert by_id["s00"]["status"] == "short"
        assert by_id["s02"]["status"] == "slot_missing"
        assert by_id["s08"]["status"] == "lane_frozen"


class TestIncidentTrail:
    """Incident application order."""

    def test_applied_follows_day_then_event_id(self, outputs: dict[str, object]) -> None:
        """Applied incidents follow ascending day then event_id."""
        rows = outputs["incident_effects.json"]["applied"]
        keys = [(int(r["day"]), str(r["event_id"])) for r in rows]
        assert keys == sorted(keys)


class TestLaneRollups:
    """Lane-level aggregates."""

    def test_west_lane_ok_and_short_split(self, outputs: dict[str, object]) -> None:
        """West lane records two satisfied and two short segments."""
        lanes = {x["lane"]: x for x in outputs["lane_summary.json"]["lanes"]}
        w = lanes["west"]
        assert w["ok"] == 2
        assert w["short"] == 2

    def test_north_lane_frozen_bucket(self, outputs: dict[str, object]) -> None:
        """North lane ends fully frozen in the bundled snapshot."""
        lanes = {x["lane"]: x for x in outputs["lane_summary.json"]["lanes"]}
        n = lanes["north"]
        assert n["frozen"] == 4
        assert n["ok"] == 0
