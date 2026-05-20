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
    "SPEC.md": "e8be766794523bc2b91770e984cfbd29c2fbc5bf08b64553007a2213807ae4a9",
    "ancillary/ci_guard.json": "eba1ec125cc5942f93adccde1abea1add7ca5796cbc79a8b3851c97c1f1d1758",
    "ancillary/delivery_tag.json": "ebf9c0a86c94267a6595f5e12eee041940f738de86180414c4ed9560672dfada",
    "ancillary/extra_one.json": "bb52a85cf33ee17d6969543cd02d140ed27e8d223072a82083552bc64076af20",
    "ancillary/extra_two.json": "b1a12699a82a70b7cfd76fd53ff1ccc696a74421825ab5f632e3450a1388486c",
    "ancillary/watermark.txt": "62d6ee1e91ee934b139887c48456e06e96b74bd092c9acedd6032332e41bc980",
    "endpoints/ep-hooks.json": "dd80fe679d1dfb0c3af0cd25d56fa6dee6354a58b74d1cbfdc6b8b1b747fffb5",
    "endpoints/ep-internal.json": "78912f7420f0455c22b053404f1f7e438a999c90d24cf4c7ff7165617f55059a",
    "endpoints/ep-partner.json": "b42f9278915db11cfcf9114dc3753a3c0aa9fb636e20368998d57b494caf77ab",
    "endpoints/ep-public.json": "0db672feb4bc1f3ad48687e80478fcea4a9ae870621e66ba4efb5fe990c8b488",
    "incident_log.json": "9aa05cf804415f6e694cfb77fddfb128c49ffb507653424fde3d462cb130bfb0",
    "policy.json": "9fccfca4346ffa1b5184ca60bfd4e371ce19bf6b5bc0707f420d2996481ed436",
    "pool_state.json": "92066811574abf75489fec47a6d2d8961c1a71ae7b600e20d48cda83b4c03dc3",
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
    "incident_journal.json": "6b2562172e09bb96e89acb70c5ae61ee3378f5ee9edd70e05dd456f7b170ea6f",
    "subscription_verdicts.json": "709de620c089e475040f387abd2e3fade01a99fea3831db0fa5d036633bbdcc6",
    "summary.json": "60fac55c05eec6c434e4f67c224b0e452a4246540269f50df468f3e6e862bff8",
    "tier_retry_budgets.json": "40f0b30b545c4a86f843ee704cf58e294d3333e176985edd495c90e975d2cd76",
}

EXPECTED_FIELD_HASHES = {
    "endpoint_touchpoints.endpoints": "f9759ca57555e70040d358f832ba3c8f1084b36bbc2cf9e6282ae808378095b0",
    "incident_journal.applied_events": "5803ddf42f3c16197029e0a7c50dc0ad20b40d5d444e967f2818d6386dc11ac0",
    "subscription_verdicts.subscriptions": "35b0b6cfcc20fb92d68a5d7936d9d2b4fac2ada958210717fa58b65f86b98f77",
    "summary.applied_incident_events": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "summary.bronze_surge_active": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
    "summary.endpoints_total": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.exhausted_subscriptions": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "summary.gold_subscriptions_with_throttle_penalty": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.ignored_incident_events": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.quarantined_subscriptions": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.subscriptions_total": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "tier_retry_budgets.tiers": "18f4a98f20a22dc1f76116ddb23aa954a3511547b56f7538deaa91f29eb301d1",
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
        """`sub-eta` stays active under gold budget with a single chargeable timeout and zero carryover."""
        r = self._row(outputs, "sub-eta")
        assert r["disposition"] == "active"
        assert r["retries_exhausted"] is False
        assert r["reasons"] == []
        assert r["raw_chargeable"] == 1
        assert r["effective_failures"] == 1
        assert r["carryover_failures"] == 0

    def test_quarantined_endpoint_compromise(self, outputs: dict[str, object]) -> None:
        """`sub-delta` on a compromised endpoint is quarantined with the compromise reason."""
        r = self._row(outputs, "sub-delta")
        assert r["disposition"] == "quarantined"
        assert r["retries_exhausted"] is True
        assert r["reasons"] == ["endpoint_compromise"]

    def test_force_exhausted_without_chargeable_failures(
        self, outputs: dict[str, object]
    ) -> None:
        """`sub-epsilon` is forced exhausted even with zero chargeable deliveries and zero carryover."""
        r = self._row(outputs, "sub-epsilon")
        assert r["disposition"] == "exhausted"
        assert r["raw_chargeable"] == 0
        assert r["effective_failures"] == 0
        assert r["carryover_failures"] == 0
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
        raw tally, while a `failure_day_suppress` event on counted day 109 removes one post-slip
        failure before budgets are compared. A second suppress event also targeting (sub-beta, 109)
        is a silent no-op because the pair is already consumed by the earlier event."""
        r = self._row(outputs, "sub-beta")
        assert r["tier"] == "silver"
        assert r["raw_chargeable"] == 5
        assert r["effective_failures"] == 4
        assert r["adjusted_retry_budget"] == 5
        assert r["disposition"] == "active"
        assert r["retries_exhausted"] is False
        assert r["reasons"] == []
        assert r["carryover_failures"] == 0

    def test_bronze_ignores_rate_limited_outcomes(self, outputs: dict[str, object]) -> None:
        """`sub-gamma` bronze tier excludes rate_limited days from the raw chargeable count."""
        r = self._row(outputs, "sub-gamma")
        assert r["tier"] == "bronze"
        assert r["raw_chargeable"] == 4
        assert r["effective_failures"] == 6


class TestPreviousWindowCarryover:
    """Verify the previous-window carryover rule and its tier-driven suppression."""

    def _row(self, outputs: dict[str, object], sid: str) -> dict[str, object]:
        rows = outputs["subscription_verdicts.json"]["subscriptions"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("subscription_id") == sid:
                return r
        raise AssertionError(f"missing subscription row {sid}")

    def test_carryover_applied_when_tier_delta_sum_non_negative(
        self, outputs: dict[str, object]
    ) -> None:
        """`sub-theta` (silver) inherits a carryover of 3 from the previous window. Silver's net
        tier_retry_delta is positive so the carryover passes through, lifts effective_failures
        from 2 to 5, exhausts the silver budget of 5, and adds the `previous_window_carryover`
        reason next to `retry_budget_exhausted`."""
        r = self._row(outputs, "sub-theta")
        assert r["tier"] == "silver"
        assert r["raw_chargeable"] == 2
        assert r["carryover_failures"] == 3
        assert r["effective_failures"] == 5
        assert r["adjusted_retry_budget"] == 5
        assert r["disposition"] == "exhausted"
        assert r["retries_exhausted"] is True
        assert r["reasons"] == ["previous_window_carryover", "retry_budget_exhausted"]

    def test_carryover_suppressed_when_tier_delta_sum_negative(
        self, outputs: dict[str, object]
    ) -> None:
        """`sub-gamma` (bronze) carries 5 in `pool_state.previous_window_carryover`, but bronze's
        net `tier_retry_delta.delta_sum` is strictly negative for this run, so the carryover is
        suppressed: `carryover_failures` reports 0 and the row's `effective_failures` is computed
        as if the carryover were not present. The `previous_window_carryover` reason is therefore
        absent even though the row is exhausted."""
        r = self._row(outputs, "sub-gamma")
        assert r["tier"] == "bronze"
        assert r["raw_chargeable"] == 4
        assert r["carryover_failures"] == 0
        assert r["effective_failures"] == 6
        assert r["disposition"] == "exhausted"
        assert "previous_window_carryover" not in r["reasons"]

    def test_carryover_zero_when_missing_or_zero_in_pool_state(
        self, outputs: dict[str, object]
    ) -> None:
        """Subscriptions whose `pool_state.previous_window_carryover` value is 0 (or absent)
        report `carryover_failures` 0 regardless of tier delta sign."""
        for sid in (
            "sub-alpha",
            "sub-beta",
            "sub-delta",
            "sub-epsilon",
            "sub-eta",
            "sub-zeta",
        ):
            r = self._row(outputs, sid)
            assert r["carryover_failures"] == 0, f"unexpected carryover for {sid}"


class TestRetryBudgetAdjustments:
    """Verify negative-delta tier_retry_delta events flow through to adjusted_retry_budget."""

    def test_bronze_budget_clamped_at_one(self, outputs: dict[str, object]) -> None:
        """The bronze tier received a strictly negative `tier_retry_delta.delta_sum`. The
        `adjusted_retry_budget` for every bronze subscription is `max(1, 6 + delta_sum)`,
        which equals 3 for the bundled trace, while `tier_retry_budgets.tiers.bronze` exposes
        the same arithmetic at the tier level."""
        rows = outputs["subscription_verdicts.json"]["subscriptions"]
        assert isinstance(rows, list)
        for r in rows:
            if r.get("tier") == "bronze":
                assert r["adjusted_retry_budget"] == 3, (
                    f"unexpected bronze adjusted_retry_budget for {r['subscription_id']}"
                )
        tiers = outputs["tier_retry_budgets.json"]["tiers"]
        bronze = tiers["bronze"]
        assert bronze["base_budget"] == 6
        assert bronze["delta_sum"] == -3
        assert bronze["adjusted_retry_budget"] == 3


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
        """The bundled log applies eight well-formed incidents the spec names, including the
        duplicate failure_day_suppress that exercises cross-event pair deduplication."""
        evs = outputs["incident_journal.json"]["applied_events"]
        ids = {str(e["event_id"]) for e in evs}
        assert ids == {"w01", "w02", "w03", "w04", "w05", "w06", "w08", "w09"}
