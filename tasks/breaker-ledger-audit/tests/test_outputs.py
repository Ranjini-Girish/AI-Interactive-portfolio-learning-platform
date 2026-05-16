"""Behavioral tests for the breaker ledger audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CBSA_DATA_DIR", "/app/breakers"))
AUDIT_DIR = Path(os.environ.get("CBSA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "service_verdicts.json",
    "tier_thresholds.json",
    "incident_journal.json",
    "upstream_touchpoints.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "dac6140aa507ebd95ee1e6fb5bf348988d383d433e814c0c463aaa2e30e87bf7",
    "ancillary/channel_tag.json": "714c7991eafe678df33b2389961ceec73d4ee8cf9eeaf317a43445039e423ca1",
    "ancillary/ci_guard.json": "d03ef4bd5c68504af2a297e96b7e008a9b3ad2664a58c35f33d658dda1b9bdfd",
    "ancillary/extra_one.json": "bc94718310ce15c6f1e0ca731743d29edc905e77f1af2302a79e931a6f2888e2",
    "ancillary/extra_two.json": "df2511664af628875125b3b4fe90e597a98d5bbd652428e630015d71e6863fc8",
    "ancillary/watermark.txt": "03339154ceed205d0ab585c26c3c7ea7805fff2345e8a9ad0cff596a6a92d2ec",
    "incident_log.json": "34701218362e1a78dd4084804e6b6f3ef5d0a865a87d49e32261d113d83e04e7",
    "policy.json": "f6a64ebfefa7bc51fb99c8cca7bc1e5ba86dfd5a5ae3bae5c81a3c638a1be535",
    "pool_state.json": "c80a28d8b2d84e91fe72d1a4e3943f4a77e22695cf6aeac4dc1474c6ef1d39ce",
    "services/svc-alpha.json": "789fb2a2d56c21f70ebc489fd1088438a9d0567a41d3a9ad648d4bf0ce3a955d",
    "services/svc-beta.json": "50b28c79b275125995afac35fa536ecc41e80ed7375aff66ed674e3f6cfae106",
    "services/svc-delta.json": "ccac7144d2b468460ee36256f70320589f74610eb189d419a8c171a4a45e8d17",
    "services/svc-epsilon.json": "96485d96b6ac73722511976e77f68ab8a4a9e967d0c4c6be6566aa09cbce1c72",
    "services/svc-eta.json": "571100ef7466f16a1d554fb246086caed9ee7d4efe0588d9e87f3df2e2fa87e8",
    "services/svc-gamma.json": "2650d25505f399d1b56e7c664d9109935c4cd80aea3983d4f00b698123881fd2",
    "services/svc-theta.json": "60b59121dd7dc8dc2bd6876da3980dc4824f93aafde4de1c7e815d0012a9b4d5",
    "services/svc-zeta.json": "d48d04f8f67dad1bc92378baf8ab9e93accda97c1baa2e45da9d0346acd338ff",
    "upstreams/up-east.json": "74da9035fbfbfc94a5d56f3c8a7076c517d94ebd2a787bba763198896ab76936",
    "upstreams/up-north.json": "a2daa3050772c094092571ad0676190b04367727be1a55a5813fe4c658138154",
    "upstreams/up-south.json": "9df4676e91f3d328d625ed85766a4c5465fca646871eb03484a80a38bd106697",
    "upstreams/up-west.json": "0fd7dde2fecf9b29e5f8596269b24f6c1619cb7a2698fefad09a89db6fdc5565",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "incident_journal.json": "7920f6e270d79f7b9c91259f09509ee2598c6f7ccbbd183039fe6e3cf72b9270",
    "service_verdicts.json": "68cc01a47e1d946bf477ff152e21dc9d2c7cf607d8a730f85043b90aa039d36a",
    "summary.json": "2bb18ed42ec22e0e44152929a5920ab8ef0d1ed797218907bbc85a03762bc0f1",
    "tier_thresholds.json": "e20f59692b15b671109fd4f141b514e764952ac778d926ad328d0433f7f8dad8",
    "upstream_touchpoints.json": "7aef9826eaf2658d739d60fff9f41f3ce7332a4be09739cc5203ae80ce5dad51",
}


EXPECTED_FIELD_HASHES = {
    "incident_journal.applied_events": "f1305f5402cf82d977499f1188fb369f0f75c4672579d27133d532a69b980837",
    "service_verdicts.services": "6568372e102919596afd889e14dac55e5dcbc63e2b340a65a2179368a31ffd60",
    "summary.applied_incident_events": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "summary.gold_services_with_upstream_penalty": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.ignored_incident_events": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.open_services": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "summary.services_total": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "summary.silver_spike_active": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
    "summary.tripped_services": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "tier_thresholds.tiers": "7d83ad055c64d56e311da0761740adae6f0cd4c81b8171a8ed391a718f4b9bd9",
    "upstream_touchpoints.upstreams": "8767c4cd9117e90c2ee8369e9bdf331d8bf81870f5d4436d1197bd1d9ef6d65b",
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
        sv = outputs["service_verdicts.json"]
        assert isinstance(sv, dict)
        assert (
            _sha256_bytes(_canonical(sv["services"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["service_verdicts.services"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in (
            "applied_incident_events",
            "gold_services_with_upstream_penalty",
            "ignored_incident_events",
            "open_services",
            "services_total",
            "silver_spike_active",
            "tripped_services",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )

        ij = outputs["incident_journal.json"]
        assert isinstance(ij, dict)
        assert (
            _sha256_bytes(_canonical(ij["applied_events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_journal.applied_events"]
        )

        ut = outputs["upstream_touchpoints.json"]
        assert isinstance(ut, dict)
        assert (
            _sha256_bytes(_canonical(ut["upstreams"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["upstream_touchpoints.upstreams"]
        )

        tt = outputs["tier_thresholds.json"]
        assert isinstance(tt, dict)
        assert (
            _sha256_bytes(_canonical(tt["tiers"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["tier_thresholds.tiers"]
        )


class TestServiceOrdering:
    """Verify deterministic ordering rules on service rows."""

    def test_service_rows_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`services` must list rows in ascending ASCII `service_id` order."""
        sv = outputs["service_verdicts.json"]
        assert isinstance(sv, dict)
        rows = sv["services"]
        assert isinstance(rows, list)
        ids = [str(r["service_id"]) for r in rows]
        assert ids == sorted(ids)


class TestVerdictSemantics:
    """Spot-check bundled rows that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], sid: str) -> dict[str, object]:
        rows = outputs["service_verdicts.json"]["services"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("service_id") == sid:
                return r
        raise AssertionError(f"missing service row {sid}")

    def test_force_open_row_reason(self, outputs: dict[str, object]) -> None:
        """`svc-delta` is forced open with only the directive reason when numeric totals stay clean."""
        r = self._row(outputs, "svc-delta")
        assert r["computed_state"] == "open"
        assert r["tripped"] is True
        assert r["reasons"] == ["force_open_incident"]
        assert r["raw_failures"] == 0
        assert r["effective_failures"] == 0

    def test_gold_upstream_penalty_reason(self, outputs: dict[str, object]) -> None:
        """`svc-alpha` is gold on a degraded upstream so penalty and threshold reasons co-occur."""
        r = self._row(outputs, "svc-alpha")
        assert r["tier"] == "gold"
        assert r["upstream_id"] == "up-east"
        assert r["computed_state"] == "open"
        assert r["reasons"] == ["gold_upstream_degraded_penalty", "threshold_exceeded"]
        assert r["raw_failures"] == 3
        assert r["effective_failures"] == 4

    def test_silver_spike_pairs_with_threshold_reason(self, outputs: dict[str, object]) -> None:
        """Silver services under surge pick up both spike and threshold reasons when tripped."""
        r = self._row(outputs, "svc-epsilon")
        assert r["tier"] == "silver"
        assert r["computed_state"] == "open"
        assert r["reasons"] == ["silver_spike_active", "threshold_exceeded"]

    def test_closed_rows_have_empty_reasons(self, outputs: dict[str, object]) -> None:
        """Closed services must emit an empty reasons array rather than diagnostic leftovers."""
        for sid in ("svc-gamma", "svc-eta", "svc-theta"):
            r = self._row(outputs, sid)
            assert r["computed_state"] == "closed"
            assert r["reasons"] == []
            assert r["tripped"] is False

    def test_bronze_threshold_edge_open(self, outputs: dict[str, object]) -> None:
        """`svc-zeta` reaches the bronze adjusted threshold exactly and trips without spike noise."""
        r = self._row(outputs, "svc-zeta")
        assert r["tier"] == "bronze"
        assert r["computed_state"] == "open"
        assert r["reasons"] == ["threshold_exceeded"]
        assert r["raw_failures"] == 6
        assert r["adjusted_threshold"] == 6

    def test_beta_tripped_after_suppress_and_spike(self, outputs: dict[str, object]) -> None:
        """`svc-beta` keeps the full-window raw tally while suppression plus surge rebuild effective counts."""
        r = self._row(outputs, "svc-beta")
        assert r["raw_failures"] == 5
        assert r["effective_failures"] == 5
        assert r["adjusted_threshold"] == 5
        assert r["computed_state"] == "open"

    def test_alpha_raw_lower_than_effective(self, outputs: dict[str, object]) -> None:
        """Gold upstream penalty lifts `svc-alpha` effective failures above the raw window tally."""
        r = self._row(outputs, "svc-alpha")
        assert r["raw_failures"] < r["effective_failures"]


class TestUpstreamTouchpoints:
    """Referrer lists stay sorted and aligned with inputs."""

    def test_referencing_services_sorted(self, outputs: dict[str, object]) -> None:
        """Each upstream block lists referencing services in ascending ASCII order."""
        ups = outputs["upstream_touchpoints.json"]["upstreams"]
        assert isinstance(ups, dict)
        for _uid, body in ups.items():
            assert isinstance(body, dict)
            refs = body["referencing_services"]
            assert isinstance(refs, list)
            srefs = [str(x) for x in refs]
            assert srefs == sorted(srefs)


class TestIncidentJournal:
    """Journal mirrors accepted, in-window, well-formed incidents."""

    def test_journal_sorted_by_day_then_id(self, outputs: dict[str, object]) -> None:
        """Applied events appear in ascending (day, event_id) order."""
        evs = outputs["incident_journal.json"]["applied_events"]
        assert isinstance(evs, list)
        keys = [(int(e["day"]), str(e["event_id"])) for e in evs]
        assert keys == sorted(keys)

    def test_journal_includes_expected_event_ids(self, outputs: dict[str, object]) -> None:
        """The bundled log applies the five well-formed incidents the spec names."""
        evs = outputs["incident_journal.json"]["applied_events"]
        ids = {str(e["event_id"]) for e in evs}
        assert ids == {"e01", "e02", "e03", "e04", "e05"}
