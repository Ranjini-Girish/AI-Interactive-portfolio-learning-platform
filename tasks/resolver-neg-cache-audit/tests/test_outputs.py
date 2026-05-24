"""Behavioral tests for the resolver negative cache audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RNCA_DATA_DIR", "/app/resolver_negcache"))
AUDIT_DIR = Path(os.environ.get("RNCA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "incident_journal.json",
    "query_profiles.json",
    "stale_events.json",
    "summary.json",
    "zone_rollups.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "c44196004e6d30472c28736d034b9db494efee08f9b04b61fc65b57ebbd104ba",
    "ancillary/a1.json": "46e38073db261adc8b1abd8cc97d92459ea52662b2d5514c0f802278fc93ccf2",
    "ancillary/a2.json": "4b02b4f9e104e62cdb78d799c2ac22a2a6673832e885fa121ce6a07ea5d7070f",
    "ancillary/a3.json": "476dcf477dafb2494f8bdeccc0f7602b23e2d8b864d10b535bd7209e74b5a3e7",
    "hints/h1.txt": "6c42d07235665bb143e7dc60bb91361fee7acd902dc570abb5739630bf688f4b",
    "hints/h2.txt": "f3c832a3a24619bf3a0d6ed180aa8888cc114ec1fd47efecf52735e159738c68",
    "incident_log.json": "4004a5df83021c87e1da761778488a78a2b8532c8347b60eb7a73b14430fde70",
    "ledger/packaging.json": "322af95e6d368317d5a5ea5b1748272fea35fedb59f04dfe0e0cab511279da5c",
    "ledger/tag.json": "11791e55625de02e8e90cdee1d0a2c4882a734eee7cee4cb87209f8f650ae566",
    "policy.json": "23247c74ac905740f8a668339e5136118d899ed6ebb61f6140911f5e97b422ca",
    "pool_state.json": "d08fc110d88d5fd10ee292e6075d32f5944d4f2ea4b07fd132824a072b52304a",
    "queries/q-01.json": "482cfc2f7bc66bd2700150b56a899c404925c885cf0694aedfec811ae5206873",
    "queries/q-02.json": "276bc42de70b3387c1cc87dc33cdadc77df3589ea4d3c669809bcaa6862f864f",
    "queries/q-03.json": "850d6c44fd390721561bcec2975142fd8d7e5d7cd696783adc738f9785d41da1",
    "queries/q-04.json": "1dba46c5adafb5c61916cac6b52e465428f13b7b8aceb60a12957e82f3562a76",
    "queries/q-05.json": "a343950e28f581ca7f34c2b45e12b42ddc7e431ac848c84f61b45fc85ea208be",
    "queries/q-06.json": "3e6f8ce8d21f7a50560cbb5b0706ad486fc1874d740b64e38f56175f0854d1cc",
    "queries/q-07.json": "08bd58aecda4bf90e5c3f9520e8205fa9aeb659816d054bb445603bd09358db2",
    "queries/q-08.json": "d27b18d5b2ca6890dea2111ffb5d1432df4dd602815f424a77c95999777547d7",
    "queries/q-09.json": "0da8104c47066ccb31a4385b2108e9c1716798f1127c64c4fcf019822ea01f13",
    "queries/q-10.json": "6ba5ead41735cd8bebb7ab49fe1e579f561a54ad3fe479852d8d9d92e2aea849",
    "queries/q-11.json": "51a14be219d432b238f942a6ffe1345bc182057e34602b44e98086ea46d7030c",
    "queries/q-12.json": "dc55ee2e05bba41638f5d4d622a3230ee6b4b614ee18ff61fb561c87d9972134",
    "zones/z-corp.json": "b18d0a7313ea480b04b8e63643157a1247c6e590579bc90eb167b04336db2de7",
    "zones/z-edge.json": "fe64a21f5da0912f339c14957ee431a067523e7f16a9aba1f7f99fb2dae22ed6",
    "zones/z-internal.json": "5d9292452e62ee90014aabb34426be03c8e3f0ffe138a56c814a09ead7f75262",
    "zones/z-legacy.json": "f563586a3685cf341fa34d3c803a1e659b480e48f3d01221b6926b5b6d19b671",
    "zones/z-public.json": "72d375fe04f8e1e88dd37249be51b79b5b71437be78f7ab9c5497b53f0da15d7",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "query_profiles.json": "271b751cf1e0f2c088e1619b9007686fb8f20f24906fb47c782501d71dfeac60",
    "zone_rollups.json": "25490eb482d5dbba41bcfe58df3f35ece91ed7087a10997b6b0413bec32b42b1",
    "stale_events.json": "f8739e7f6f0bfd667b2d226acf6607b0d4384b1a87547addfa1f307e6eb8471b",
    "incident_journal.json": "53fc1f571639dde816310a0be224dd8f9e46ec413a98bc6dfa3836172186a372",
    "summary.json": "16d7e43e80245e5889bb8f7cfdba536fb60f499130ef5f6316c09bf5dc8ae5cf",
}

EXPECTED_FIELD_HASHES = {
    "query_profiles.queries": "b58557c5e13281b75295f19fbc65e7150598b80c12e52598d1398c98e3e09f3b",
    "zone_rollups.zones": "cb2fccec2202a5c5a04d2e885c1ae0066713c3b9417a28ced41c7167f0261f6d",
    "stale_events.events": "d09eb90a64546645566d9bc783db3a59d22c3cbdb45c479bc63c734ddd969a0b",
    "incident_journal.applied_events": "7e11e97b37868145a58467df11ca68f825b36827b8420d27e434fe92e718de19",
    "summary.zones": "7df53f46c648cb5a3f76f02802b08167850d465d08246de957cfa8503ad501c0",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _profile_by_id(outputs: dict[str, object]) -> dict[str, dict[str, object]]:
    qp = outputs["query_profiles.json"]
    assert isinstance(qp, dict)
    rows = qp["queries"]
    assert isinstance(rows, list)
    return {str(r["query_id"]): r for r in rows}


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

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        qp = outputs["query_profiles.json"]
        assert isinstance(qp, dict)
        assert (
            _sha256_bytes(_canonical(qp["queries"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["query_profiles.queries"]
        )

        zr = outputs["zone_rollups.json"]
        assert isinstance(zr, dict)
        assert (
            _sha256_bytes(_canonical(zr["zones"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["zone_rollups.zones"]
        )

        se = outputs["stale_events.json"]
        assert isinstance(se, dict)
        assert (
            _sha256_bytes(_canonical(se["events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["stale_events.events"]
        )

        ij = outputs["incident_journal.json"]
        assert isinstance(ij, dict)
        assert (
            _sha256_bytes(_canonical(ij["applied_events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_journal.applied_events"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["zones"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.zones"]
        )


class TestQueryOrdering:
    """Deterministic ordering rules on query rows."""

    def test_queries_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`queries` must list rows in ascending ASCII `query_id` order."""
        rows = outputs["query_profiles.json"]["queries"]
        assert isinstance(rows, list)
        ids = [str(r["query_id"]) for r in rows]
        assert ids == sorted(ids)


class TestCacheStatusCoverage:
    """Bundled fixtures exercise every documented cache_status value."""

    def _statuses(self, outputs: dict[str, object]) -> set[str]:
        return {str(r["cache_status"]) for r in outputs["query_profiles.json"]["queries"]}

    def test_fresh_status_present(self, outputs: dict[str, object]) -> None:
        """At least one query remains `fresh` after TTL and hint processing."""
        assert "fresh" in self._statuses(outputs)

    def test_stale_grace_status_present(self, outputs: dict[str, object]) -> None:
        """At least one query carries `stale_grace` from TTL math or negative_hold."""
        assert "stale_grace" in self._statuses(outputs)

    def test_expired_status_present(self, outputs: dict[str, object]) -> None:
        """At least one query is `expired` when age exceeds TTL plus grace."""
        assert "expired" in self._statuses(outputs)

    def test_poisoned_status_present(self, outputs: dict[str, object]) -> None:
        """At least one query is `poisoned` from resolver_compromise."""
        assert "poisoned" in self._statuses(outputs)

    def test_flushed_status_present(self, outputs: dict[str, object]) -> None:
        """At least one query is `flushed` from zone_flush on a rebound zone."""
        assert "flushed" in self._statuses(outputs)

    def test_non_negative_status_present(self, outputs: dict[str, object]) -> None:
        """At least one positive response is labeled `non_negative`."""
        assert "non_negative" in self._statuses(outputs)


class TestSuffixRebinding:
    """Longest-suffix zone rebinding overrides file zone_id."""

    def test_corp_suffix_rebinds_q06(self, outputs: dict[str, object]) -> None:
        """`app.corp.example.com` must rebound to `z-corp` even when the file says `z-public`."""
        row = _profile_by_id(outputs)["q-06"]
        assert row["rebound_zone_id"] == "z-corp"


class TestIncidentPrecedence:
    """Cross-cutting incident rules override hints and TTL results."""

    def test_compromise_poisoned_q08(self, outputs: dict[str, object]) -> None:
        """`res-b` compromise poisons eligible queries regardless of TTL freshness."""
        row = _profile_by_id(outputs)["q-08"]
        assert row["cache_status"] == "poisoned"

    def test_zone_flush_q09(self, outputs: dict[str, object]) -> None:
        """`z-corp` flush marks rebound corp queries observed on or after the flush day."""
        row = _profile_by_id(outputs)["q-09"]
        assert row["cache_status"] == "flushed"

    def test_negative_hold_q10(self, outputs: dict[str, object]) -> None:
        """`negative_hold` forces `stale_grace` when no higher-priority incident applies."""
        row = _profile_by_id(outputs)["q-10"]
        assert row["cache_status"] == "stale_grace"


class TestHintOverrides:
    """Hint files override TTL classification for known query ids."""

    def test_hint_fresh_q11(self, outputs: dict[str, object]) -> None:
        """Hint `fresh` on `q-11` wins over TTL `expired` for that query id."""
        row = _profile_by_id(outputs)["q-11"]
        assert row["cache_status"] == "fresh"

    def test_hint_stale_grace_q03(self, outputs: dict[str, object]) -> None:
        """Later hint line for `q-03` sets `stale_grace` after an earlier `expired` hint."""
        row = _profile_by_id(outputs)["q-03"]
        assert row["cache_status"] == "stale_grace"


class TestStaleEvents:
    """Stale event list includes only stale_grace and expired rows."""

    def test_stale_events_query_ids(self, outputs: dict[str, object]) -> None:
        """Events list tracks exactly queries whose final status is stale or expired."""
        profiles = _profile_by_id(outputs)
        expected = sorted(
            qid
            for qid, row in profiles.items()
            if row["cache_status"] in {"stale_grace", "expired"}
        )
        events = outputs["stale_events.json"]["events"]
        assert isinstance(events, list)
        actual = sorted(str(e["query_id"]) for e in events)
        assert actual == expected
