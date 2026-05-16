"""Behavioral tests for the webhook retry ledger audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("WRLA_DATA_DIR", "/app/webhooks"))
AUDIT_DIR = Path(os.environ.get("WRLA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "subscription_verdicts.json",
    "tier_retry_budgets.json",
    "incident_journal.json",
    "endpoint_touchpoints.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "097bf84a2d0086c0fc85e264fdae51b32767caf4e5683f391142dccaeb6fd4e5",
    "ancillary/ci_guard.json": "eba1ec125cc5942f93adccde1abea1add7ca5796cbc79a8b3851c97c1f1d1758",
    "ancillary/delivery_tag.json": "ebf9c0a86c94267a6595f5e12eee041940f738de86180414c4ed9560672dfada",
    "ancillary/extra_one.json": "bb52a85cf33ee17d6969543cd02d140ed27e8d223072a82083552bc64076af20",
    "ancillary/extra_two.json": "b1a12699a82a70b7cfd76fd53ff1ccc696a74421825ab5f632e3450a1388486c",
    "ancillary/watermark.txt": "62d6ee1e91ee934b139887c48456e06e96b74bd092c9acedd6032332e41bc980",
    "endpoints/ep-hooks.json": "dd80fe679d1dfb0c3af0cd25d56fa6dee6354a58b74d1cbfdc6b8b1b747fffb5",
    "endpoints/ep-internal.json": "78912f7420f0455c22b053404f1f7e438a999c90d24cf4c7ff7165617f55059a",
    "endpoints/ep-partner.json": "b42f9278915db11cfcf9114dc3753a3c0aa9fb636e20368998d57b494caf77ab",
    "endpoints/ep-public.json": "0db672feb4bc1f3ad48687e80478fcea4a9ae870621e66ba4efb5fe990c8b488",
    "incident_log.json": "948218f6b8ca8fe5f3c88e7823caaefc09054ff53144f36f705368aa76986640",
    "policy.json": "9fccfca4346ffa1b5184ca60bfd4e371ce19bf6b5bc0707f420d2996481ed436",
    "pool_state.json": "bc383d68e9727a5442852b4f4b55c1302361c4e1666ecd6ffd26fb181095b1c7",
    "signing_profiles/sp-hooks.json": "2fd4b3793eafce27e3f5d20f65cf226f29f288d082a421c478660dec2fac9cb4",
    "signing_profiles/sp-internal.json": "74c59c8a912a1a5b4cf1a9b99729b9b98dc0bc1a80ce59832826b29f187a7a2d",
    "signing_profiles/sp-partner.json": "3c4b36c595107fdb5fcdd384679a1b313422b65c818a3a68fb5b56e923e63210",
    "signing_profiles/sp-public.json": "8f6480b9bf238b35098f96a98a20c202e602c794d27d83e9ea67ad773886f46d",
    "subscriptions/sub-alpha.json": "54dbbf6c35f626c37d7f772d2e550bc57c0fe7e3ab8ee2afabfb8d483aa336dc",
    "subscriptions/sub-beta.json": "e605d0331fcb7b1f02c0d5666c755a937e8b37f2dd37296b672e31018e9b1908",
    "subscriptions/sub-delta.json": "985803385ddb348710dde98b5f3e11c1952b15c12a9d5d1081800aadece9bccc",
    "subscriptions/sub-epsilon.json": "0f37576e435173ac9cc824f0324f976b2afd488cf95ce0581783d9404566a750",
    "subscriptions/sub-eta.json": "b85fbe0a212fff862d113346b18fc9f2b4e0c01a63b2f210db66a41b18620052",
    "subscriptions/sub-gamma.json": "035dae94d48a2e0ba845304e6cadfd6c57d5f32cc769be1f3afa115d4daf476c",
    "subscriptions/sub-theta.json": "7c135000746685abd5c59e43d4918a047ab55587c2bd12f58ce2278a2238a879",
    "subscriptions/sub-zeta.json": "2a64ef442838e134fa72fdb0d78dbad868670fda6a9b236af12258f4778cff92",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "endpoint_touchpoints.json": "267b6cecd5ed6d7de72ef498873712feafc00e4dc65656bba99cabd8ba81e4a9",
    "incident_journal.json": "1d8e847e20ece0e2ac0b2373ba7791912b88cd6497f7505fd18111f3bd6eec41",
    "subscription_verdicts.json": "2eb4aaff43233ff4bd4b2e8dc51e821cb373f1ac58bd4804fb439253708b715d",
    "summary.json": "27b2c71f097dcf7be564cb261e3eab7cde2caa7b884feea7bfbe6f1d1601c29e",
    "tier_retry_budgets.json": "58dd87a8e7cd827c7ce5fdd8d051b63ba9cf2e4380d782b48c302604b51b58ec",
}

EXPECTED_FIELD_HASHES = {
    "endpoint_touchpoints.endpoints": "f9759ca57555e70040d358f832ba3c8f1084b36bbc2cf9e6282ae808378095b0",
    "incident_journal.applied_events": "1532b39edc7b7e3802deac2cf5b5e1756300fbdffeed046db8e870e9d04dd277",
    "subscription_verdicts.subscriptions": "4c8145eb01d3be8eb8715fbf5350cb13ce29b0a4a47bf67a7dc64881d8757948",
    "summary.applied_incident_events": "e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683",
    "summary.bronze_surge_active": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
    "summary.endpoints_total": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.exhausted_subscriptions": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.gold_subscriptions_with_throttle_penalty": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.ignored_incident_events": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.quarantined_subscriptions": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.subscriptions_total": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "tier_retry_budgets.tiers": "d9e40b90cdcd1c5b3f5d83a80dc940f24a46725d06a89cdac73ce01e61aab479",
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
        sv = outputs["subscription_verdicts.json"]
        assert isinstance(sv, dict)
        assert (
            _sha256_bytes(_canonical(sv["subscriptions"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["subscription_verdicts.subscriptions"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in (
            "applied_incident_events",
            "bronze_surge_active",
            "endpoints_total",
            "exhausted_subscriptions",
            "gold_subscriptions_with_throttle_penalty",
            "ignored_incident_events",
            "quarantined_subscriptions",
            "subscriptions_total",
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

        et = outputs["endpoint_touchpoints.json"]
        assert isinstance(et, dict)
        assert (
            _sha256_bytes(_canonical(et["endpoints"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["endpoint_touchpoints.endpoints"]
        )

        tr = outputs["tier_retry_budgets.json"]
        assert isinstance(tr, dict)
        assert (
            _sha256_bytes(_canonical(tr["tiers"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["tier_retry_budgets.tiers"]
        )


class TestSubscriptionOrdering:
    """Verify deterministic ordering rules on subscription rows."""

    def test_subscription_rows_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`subscriptions` must list rows in ascending ASCII `subscription_id` order."""
        sv = outputs["subscription_verdicts.json"]
        assert isinstance(sv, dict)
        rows = sv["subscriptions"]
        assert isinstance(rows, list)
        ids = [str(r["subscription_id"]) for r in rows]
        assert ids == sorted(ids)


class TestDispositionSemantics:
    """Spot-check bundled rows that exercise distinct disposition branches."""

    def _row(self, outputs: dict[str, object], sid: str) -> dict[str, object]:
        rows = outputs["subscription_verdicts.json"]["subscriptions"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("subscription_id") == sid:
                return r
        raise AssertionError(f"missing subscription row {sid}")

    def test_active_row_has_empty_reasons(self, outputs: dict[str, object]) -> None:
        """`sub-eta` stays active under gold budget with a single chargeable timeout."""
        r = self._row(outputs, "sub-eta")
        assert r["disposition"] == "active"
        assert r["retries_exhausted"] is False
        assert r["reasons"] == []
        assert r["raw_chargeable"] == 1
        assert r["effective_failures"] == 1

    def test_quarantined_endpoint_compromise(self, outputs: dict[str, object]) -> None:
        """`sub-delta` on a compromised endpoint is quarantined with the compromise reason."""
        r = self._row(outputs, "sub-delta")
        assert r["disposition"] == "quarantined"
        assert r["retries_exhausted"] is True
        assert r["reasons"] == ["endpoint_compromise"]

    def test_force_exhausted_without_chargeable_failures(
        self, outputs: dict[str, object]
    ) -> None:
        """`sub-epsilon` is forced exhausted even with zero chargeable deliveries."""
        r = self._row(outputs, "sub-epsilon")
        assert r["disposition"] == "exhausted"
        assert r["raw_chargeable"] == 0
        assert r["effective_failures"] == 0
        assert r["reasons"] == ["force_exhausted_incident"]

    def test_gold_throttle_penalty_pairs_with_budget_exhaustion(
        self, outputs: dict[str, object]
    ) -> None:
        """`sub-alpha` on a throttled public endpoint picks up throttle and budget reasons."""
        r = self._row(outputs, "sub-alpha")
        assert r["tier"] == "gold"
        assert r["disposition"] == "exhausted"
        assert r["reasons"] == [
            "gold_endpoint_throttle_penalty",
            "retry_budget_exhausted",
        ]
        assert r["raw_chargeable"] == 4
        assert r["effective_failures"] == 5

    def test_bronze_surge_pairs_with_budget_exhaustion(
        self, outputs: dict[str, object]
    ) -> None:
        """`sub-zeta` bronze surge lifts effective failures above the bronze retry budget."""
        r = self._row(outputs, "sub-zeta")
        assert r["tier"] == "bronze"
        assert r["disposition"] == "exhausted"
        assert r["reasons"] == ["bronze_surge_active", "retry_budget_exhausted"]
        assert r["raw_chargeable"] == 6
        assert r["effective_failures"] == 8

    def test_silver_slip_grace_and_failure_day_suppress(
        self, outputs: dict[str, object]
    ) -> None:
        """`sub-beta` uses slip grace on day 106 so that failure stays out of the slip-adjusted
        raw tally, while a `failure_day_suppress` on counted day 109 removes one post-slip
        failure before budgets are compared."""
        r = self._row(outputs, "sub-beta")
        assert r["tier"] == "silver"
        assert r["raw_chargeable"] == 5
        assert r["effective_failures"] == 4
        assert r["adjusted_retry_budget"] == 5
        assert r["disposition"] == "active"
        assert r["retries_exhausted"] is False
        assert r["reasons"] == []

    def test_bronze_ignores_rate_limited_outcomes(self, outputs: dict[str, object]) -> None:
        """`sub-gamma` bronze tier excludes rate_limited days from the raw chargeable count."""
        r = self._row(outputs, "sub-gamma")
        assert r["tier"] == "bronze"
        assert r["raw_chargeable"] == 4
        assert r["effective_failures"] == 6


class TestSigningResolution:
    """Effective signing keys respect rotation lag against bundled profiles."""

    def test_signing_keys_match_rotation_cutoff(self, outputs: dict[str, object]) -> None:
        """Each subscription row resolves the lexicographically greatest eligible key id."""
        rows = outputs["subscription_verdicts.json"]["subscriptions"]
        assert isinstance(rows, list)
        by_id = {str(r["subscription_id"]): str(r["effective_signing_key_id"]) for r in rows}
        assert by_id["sub-alpha"] == "pk-a"
        assert by_id["sub-beta"] == "hk-v3"
        assert by_id["sub-delta"] == "ptk-old"
        assert by_id["sub-gamma"] == "ik-02"


class TestEndpointTouchpoints:
    """Referrer lists stay sorted and aligned with inputs."""

    def test_referencing_subscriptions_sorted(self, outputs: dict[str, object]) -> None:
        """Each endpoint block lists referencing subscriptions in ascending ASCII order."""
        eps = outputs["endpoint_touchpoints.json"]["endpoints"]
        assert isinstance(eps, dict)
        for _eid, body in eps.items():
            assert isinstance(body, dict)
            refs = body["referencing_subscriptions"]
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
        """The bundled log applies the six well-formed incidents the spec names."""
        evs = outputs["incident_journal.json"]["applied_events"]
        ids = {str(e["event_id"]) for e in evs}
        assert ids == {"w01", "w02", "w03", "w04", "w05", "w06"}
