"""Behavioral tests for the CSP merge policy audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CMP_DATA_DIR", "/app/cspmerge"))
AUDIT_DIR = Path(os.environ.get("CMP_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "directive_matrix.json",
    "nonce_collisions.json",
    "enforce_verdicts.json",
    "incident_overrides.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "3dd17f821df2b656f086707e76417d6e48ef773a2f096a0459a83f8d701b1eb8",
    "anchors/anchor_a.txt": "7109c3fc21c88f68132a7bc7dc7e8fafc4cbd4e1a16d793724aeb78858fd21c4",
    "anchors/anchor_b.txt": "48f8e3562eaeb7678d2e66dd0f1a7fc8114be2e5d4dff131fcdcb5bbb929cb3e",
    "anchors/anchor_c.txt": "15ff999a26fd68d193e387b0377f96b60e4adb798814cddc8802fb71238f8c5e",
    "ancillary/ci_guard.json": "c74ea21a29703afa9fe59fa499448407096166c7affa8dc074c252a59db1027d",
    "ancillary/pack_meta.json": "d5096f1952070264aad08db69a9fc40040b236586f8c9d154dd52236d3943315",
    "bundles/a01.json": "929d169480970eeb65ada0ad94d7c179dcce6900d104928feb7a8ff4bbc1dedb",
    "bundles/b99.json": "9cbd992c609723e23e863dd12ded4dd7f53b31e1f2dafeee92cd5f7b7aa5019e",
    "bundles/c50.json": "2ff9380f130a64852b129a5508f3f93a8adee5aa9527904393e29f7b60218fd4",
    "bundles/d99.json": "663e88dd8ba92120838db40af5658f0e736d98c604bfa63ba41692fc8394d809",
    "bundles/g01.json": "1b4fae43d2585a12fcb1d7757a1efa6309886a39431b6f6e346f6b7789d3ea54",
    "bundles/g02.json": "1641bc418a5c5f3595d92bb27e6bf243a66346f316355671810e0aed03e1c911",
    "bundles/h10.json": "b00b472cfbdd30edcb1085a0e902a5b47c38185f140ca3550ceceeb05b42442e",
    "bundles/h20.json": "0054751f87eb4cdc4433f74df58121ed0fb60faeb324ac6cb16b96ba96ede203",
    "bundles/m30.json": "fbbcc5c56de1315627c60efdd88a4874d729f36e79f654457e075ccfe1c56622",
    "bundles/m40.json": "d11e27fc3901bc6fca817e9fac5a7fa1ff1c0b5240364bd8de754ceea76d2c24",
    "bundles/m55.json": "ef625edeee8b9b06bbfaac18f52ff8abd3f3cd19c793e22432b6bb733dc66f20",
    "bundles/n01.json": "957082be8a72f0256bb1f6a05736536828073e4d50c418629907b61c6d1a5f22",
    "bundles/n02.json": "773b550def26dcc852a1edf22fe8030fa375064e6e958a0678d5bf1cc9c13618",
    "bundles/p01.json": "304f0be2dca756c1378c6eabfd5f43f6d2a13724d3d1282cbc6dbafb316fe072",
    "bundles/p02.json": "9f0fbf1121cd6c4212955a142d5e17b697e3b57707771d32f83fb44d38bc2e11",
    "incident_log.json": "950b164650d7660287623b7bd9b2c4656b10bbd1db67f82b0c4b6ea2113ceb79",
    "inheritance.json": "797a2ecaf5f2668e5b68818f9d0954bac5fc18ba7a1f9e394cbadeff87e0f87e",
    "ledger/channel_tag.json": "84660198214629b0298f85929e30f1dc500279111f0008cfa23fa714f2a087c7",
    "ledger/ci_guard.json": "76b7d80143bc3d3b48000754f11f713640ca6e3ba0cda605e222555ea82b8e25",
    "origins/o-alpha.json": "d08d7bba9c50d7204ba927d6bcf5434ad56821520a2216eac3618067419856b7",
    "origins/o-beta.json": "0cd5992c98b74ea4cab6f4b1bc8278f064f2274316f16acdc3ea433129474c48",
    "origins/o-delta.json": "5980d2a3ef40ca4700c6134a4a7cb9e2b2a59db8a172655b0b82dae734ec6534",
    "origins/o-epsilon.json": "459a4b57c47f4373cce42f5df73f7fa269f9036d2412fa368547f46cb9ef2c85",
    "origins/o-eta.json": "006afcba0973f9bbe22a6df23ce920c937d72ec8286cfa6a7cb6a1d7705dbc50",
    "origins/o-gamma.json": "bf53bb4c49e6056398fb6cb0818c20c62d676889302b26940e299d52219fed4c",
    "origins/o-theta.json": "8b11f7db57d043295bd42655244d99e71f6be4393a77607e4d2de2fff7f63d7e",
    "origins/o-zeta.json": "f38375de54d9ab6a17d495ea595275224cd40a2aeedda864916b16f695678697",
    "policy.json": "5bb501b18eda4ef78e051b7f5d8bd7d136dd0eb54546977f78e80ac5b8957a41",
    "pool_state.json": "d08fc110d88d5fd10ee292e6075d32f5944d4f2ea4b07fd132824a072b52304a",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "directive_matrix.json": "22df6fc8af262c02e759aa3e12001860ee458a3ab72d4b81fcb882dc86c1a498",
    "enforce_verdicts.json": "bf75f7ce042e1efdaa667f5f823596898dac71fe1d7c77da48470599cbf42895",
    "incident_overrides.json": "e2068ba3ac133ed233637c0b52bb9b8b54a57f2ab613dc71bdb26f802655954d",
    "nonce_collisions.json": "6f02800b92e25f36ac93d795be7dbbd082eb2ce1f20fe2682b4cf1ed9827c9d2",
    "summary.json": "4f878e45bc69f1a8ff5cb6897ec680169efd64c01676c35c9f02cecdeecf1db2",
}


EXPECTED_FIELD_HASHES = {
    "directive_matrix.origins": "c697652af5d834efe5d7bc2753e0e4b2150a263e4d2ba4c1f7e0af53b9e47744",
    "enforce_verdicts.origins": "803e1b5fb24df7da402fdc6754fade7d8f2c8be944af1a5948ad304497b9b029",
    "summary.ignored_counts": "1e47da0a4a85190e85f0e543e837ba7cf209c6aa1a7eb407af537f1fcdd553a6",
    "summary.quarantined_origins": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
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

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        dm = outputs["directive_matrix.json"]
        assert isinstance(dm, dict)
        assert (
            _sha256_bytes(_canonical(dm["origins"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["directive_matrix.origins"]
        )

        ev = outputs["enforce_verdicts.json"]
        assert isinstance(ev, dict)
        assert (
            _sha256_bytes(_canonical(ev["origins"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["enforce_verdicts.origins"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in ("ignored_counts", "quarantined_origins"):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestOriginOrdering:
    """Deterministic ordering rules on origin rows."""

    def test_matrix_origins_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`origins` in directive_matrix must be sorted by ascending origin_id."""
        rows = outputs["directive_matrix.json"]["origins"]
        assert isinstance(rows, list)
        ids = [str(r["origin_id"]) for r in rows]
        assert ids == sorted(ids)

    def test_verdict_origins_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`origins` in enforce_verdicts must be sorted by ascending origin_id."""
        rows = outputs["enforce_verdicts.json"]["origins"]
        assert isinstance(rows, list)
        ids = [str(r["origin_id"]) for r in rows]
        assert ids == sorted(ids)


class TestPostureSemantics:
    """Spot-check bundled origins that exercise distinct spec branches."""

    def _verdict(self, outputs: dict[str, object], oid: str) -> dict[str, object]:
        rows = outputs["enforce_verdicts.json"]["origins"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("origin_id") == oid:
                return r
        raise AssertionError(f"missing verdict row {oid}")

    def _matrix(self, outputs: dict[str, object], oid: str) -> dict[str, object]:
        rows = outputs["directive_matrix.json"]["origins"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("origin_id") == oid:
                return r
        raise AssertionError(f"missing matrix row {oid}")

    def test_compromise_quarantine_blocks_child(self, outputs: dict[str, object]) -> None:
        """`o-beta` is quarantined through inheritance from a compromised parent."""
        row = self._verdict(outputs, "o-beta")
        assert row["preliminary_posture"] == "blocked_quarantine"
        assert row["delivery_posture"] == "blocked_quarantine"
        matrix = self._matrix(outputs, "o-beta")
        assert matrix["quarantined"] is True
        assert matrix["effective_directives"] == {}

    def test_report_cap_marks_suppressed(self, outputs: dict[str, object]) -> None:
        """`o-gamma` exceeds the bronze report cap and is report_suppressed."""
        row = self._verdict(outputs, "o-gamma")
        assert row["preliminary_posture"] == "report_suppressed"
        assert row["delivery_posture"] == "report_suppressed"

    def test_audit_review_overrides_enforce(self, outputs: dict[str, object]) -> None:
        """`o-eta` preliminary enforce is overridden to report-only by audit_review."""
        row = self._verdict(outputs, "o-eta")
        assert row["preliminary_posture"] == "enforce"
        assert row["delivery_posture"] == "report-only"
        assert row["review_override_applied"] is True

    def test_pinned_script_src_keeps_first_bundle(self, outputs: dict[str, object]) -> None:
        """`o-delta` keeps the first pinned script-src despite a later enforce bundle."""
        matrix = self._matrix(outputs, "o-delta")
        directives = matrix["effective_directives"]
        assert isinstance(directives, dict)
        assert directives["script-src"] == ["'self'", "'unsafe-inline'"]

    def test_hash_strips_unsafe_inline(self, outputs: dict[str, object]) -> None:
        """`o-eta` script-src drops unsafe-inline after a sha256 source is merged."""
        matrix = self._matrix(outputs, "o-eta")
        directives = matrix["effective_directives"]
        assert isinstance(directives, dict)
        assert directives["script-src"] == ["sha256-deadbeef"]

    def test_freeze_skips_later_bundle(self, outputs: dict[str, object]) -> None:
        """`o-theta` ignores bundle m55 after a directive_freeze at m50."""
        matrix = self._matrix(outputs, "o-theta")
        directives = matrix["effective_directives"]
        assert isinstance(directives, dict)
        assert directives["default-src"] == ["'self'"]
        assert "https://blocked.after-freeze.example" not in directives.get("default-src", [])


class TestNonceCollisions:
    """Shared nonce detection across origins."""

    def test_shared_nonce_lists_both_origins(self, outputs: dict[str, object]) -> None:
        """`nonce-shared` appears once with epsilon and zeta origin ids."""
        cols = outputs["nonce_collisions.json"]["collisions"]
        assert isinstance(cols, list)
        assert len(cols) == 1
        row = cols[0]
        assert row["nonce"] == "nonce-shared"
        assert row["origin_ids"] == ["o-epsilon", "o-zeta"]


class TestIncidentTrace:
    """Incident processing order and resolution labels."""

    def test_events_sorted_by_day_then_id(self, outputs: dict[str, object]) -> None:
        """Incident trace preserves day then event_id ordering from the spec."""
        evs = outputs["incident_overrides.json"]["events"]
        assert isinstance(evs, list)
        keys = [(int(e["day"]), str(e["event_id"])) for e in evs]
        assert keys == sorted(keys)

    def test_ignored_resolution_kinds_present(self, outputs: dict[str, object]) -> None:
        """Summary ignored_counts includes each ignored resolution bucket."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        ignored = sm["ignored_counts"]
        assert isinstance(ignored, dict)
        for key in (
            "ignored_future_day",
            "ignored_not_accepted",
            "ignored_unsupported_kind",
        ):
            assert key in ignored
            assert int(ignored[key]) >= 1


class TestSummaryCounts:
    """Summary integers align with posture and collision outputs."""

    def test_summary_matches_posture_tallies(self, outputs: dict[str, object]) -> None:
        """Summary quarantine and enforce counts match verdict rows."""
        sm = outputs["summary.json"]
        ev_rows = outputs["enforce_verdicts.json"]["origins"]
        assert isinstance(sm, dict) and isinstance(ev_rows, list)

        mx_rows = outputs["directive_matrix.json"]["origins"]
        quarantined = sum(
            1 for r in mx_rows if isinstance(r, dict) and r.get("quarantined") is True
        )
        assert int(sm["quarantined_origins"]) == quarantined

        enforce_delivery = sum(
            1
            for r in ev_rows
            if isinstance(r, dict) and r.get("delivery_posture") == "enforce"
        )
        assert int(sm["enforce_posture_origins"]) == enforce_delivery

        cols = outputs["nonce_collisions.json"]["collisions"]
        assert int(sm["collision_count"]) == len(cols)
