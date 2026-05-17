"""Behavioral tests for the lease slot coordinator audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("LSCA_DATA_DIR", "/app/leases"))
AUDIT_DIR = Path(os.environ.get("LSCA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "lease_verdicts.json",
    "tier_policy.json",
    "incident_journal.json",
    "slot_contention.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "8a0814aa96dcf74c0efc3630a3a800b54789e93017d96931b8a9aeb43ea3c87c",
    "ancillary/channel_tag.json": "e126bc42853253544ba41531f545b9ec37571c52e130c59a2a341fedcaf9e257",
    "ancillary/ci_guard.json": "e4bf72f56e6bd79ee2a85031d5cdaaf6f079eb459edb6fe32cd2d4d66f135dd9",
    "ancillary/extra_one.json": "e00f12c9c6be456940cb7be775df45edec8597a5528482899e7b25d6daf09c50",
    "ancillary/extra_two.json": "67e433868c0141a87f7aad9a20c08a07587103476bf62d6e929bb04c0ff5df0f",
    "ancillary/watermark.txt": "8397e4142bb8af79b2ffd833967e26a413b0ac9aaf217bc575c23d097aceb3d4",
    "hosts/host-alpha.json": "ce54c86e19a11135eb0d857685f4fd2e9d37ed645c67ba53e75f78c525b05da2",
    "hosts/host-beta.json": "bd7fb994ab42b4ee7c45cf381dc0a89b41ccdded1277b8478c02dcc16f3909d8",
    "hosts/host-bronze.json": "eb727fc93e73647e0836e433bb84c4d282b23e4f5af092492296f0df5f6dcf78",
    "hosts/host-delta.json": "62779a1144282945417166bd63f04f029f54911d86e05b08a94af1825e628147",
    "hosts/host-epsilon.json": "c1a5e46ee1528d0966f2eeb4de74e08ce49292a414e87e9d5a796d10f5c3281a",
    "hosts/host-eta.json": "1775a7c6e9f9702b933a29daf9cd4f886004abae5f6711cfc56aaa0ccdc0e735",
    "hosts/host-gamma.json": "1f7aa98d83a2632bbcccf6c267ced47f1f147a183e29eb35ddcfccdd69eb19c0",
    "hosts/host-iota.json": "5e8836df868649a4fd04d9b421ff9f4e152b1eb01f5d789ae096d92c4545226d",
    "hosts/host-kappa.json": "032b14222c8ad5de867644d7d6d7a3853755e0d4b896af6b4870028c0ee58545",
    "hosts/host-zeta.json": "28fe3dc7e257d5e4c0027d0039bf028182265613f352d075fbcc0910209c6d85",
    "incident_log.json": "982464e2eb81608c5fcf15c5fa4e19923f9cf815c820427b152e329325336908",
    "policy.json": "2c7f7d5155e61ab28d0832971b639a87544f926b66b8f49cc1059d48a207496e",
    "pool_state.json": "d08fc110d88d5fd10ee292e6075d32f5944d4f2ea4b07fd132824a072b52304a",
    "slots/slot-alpha1.json": "f498af5429fc4946f261aeab04334c4fcc9518f9efc0262ba42abbc981cbebee",
    "slots/slot-beta2.json": "499f39d8a1fe9022de0707d2e01357acb38f211c004d00ac0fdfba00aaca11ff",
    "slots/slot-bronze3.json": "8ba848233aec65a8fa2541cd3bfe3e8eb08eecc72de62910e8f36384c8a70a40",
    "slots/slot-gamma4.json": "850adab59d010bf4466d260f5d7848df0ae3f0c882992a2f5522f7bb253322f9",
    "slots/slot-kappa7.json": "5c41ec810675942d7c93b3a0bc5784995607a29360775d9be465ecd7623037d7",
    "slots/slot-shared.json": "90b56844b804e65727615ba3057ca30b3e8d3d30e766b13341f971940469e6c7",
    "slots/slot-silver5.json": "06e893887325c645d3ec1e35359bf4911546fc515847e1f3778f61e50e95b64b",
    "slots/slot-vault.json": "55bc8d2e4cfc86f68050cb9c3ce87a4b3ac1194b6b5efea1534f15d99c9c9096",
    "slots/slot-zeta6.json": "d44de0499135483ee6c2ac0ce176d4820be8b99fd6f71c01a5cf13e252b6015d",
    "witnesses/slot-beta2.json": "3e7da546fe01a32a4991264ea070eab38f1e92ae48f5be9230a87d00cc1426e6",
    "witnesses/slot-bronze3.json": "9b3144e9516af02b7f023a865e1fffa9134a3ab67e94c3247d660c7321afccf9",
    "witnesses/slot-shared.json": "65667afa8a2040ef66897842d23501cf332f1fc2ae2aa6a0b149c4ce999f451f",
    "witnesses/slot-zeta6.json": "65d4722ea9aabaea2756ee1c05cb17b467f658f01db53aa93c53722bb61d808b",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "incident_journal.json": "8150cbbc2d6d15475a03530ac92c2990575d6bbdd8ada2af8eb6d0ad1dba129e",
    "lease_verdicts.json": "e0f529885614e47bdc7c3e9e5cd466544b319537dbabde6e61b81a84dd0911aa",
    "slot_contention.json": "050ae4b683a93cf4e1355d0d020e51cda8cb2bac8ad515f145dbe074a54e2bae",
    "summary.json": "ff010fe0a1be0756381797c08acd05f53cc1724b42d5efb021cd0f59d2c5b6ae",
    "tier_policy.json": "7e0962b1544ea1afe868afaa2270121773a73d911d868f0f2de0ed8c2f09d8bb",
}

EXPECTED_FIELD_HASHES = {
    "incident_journal.applied_events": "3b28a63148977c2377ce54522f58ee9c5f2d9e4c04e95354693ce76c00fbae3a",
    "lease_verdicts.leases": "7a2b0701badb801f692d0bb9006704bcec48e14dd1c5e232539237980af47a9d",
    "slot_contention.slots": "09a7e982e6d7e6eb151d7edbee2898713bc95dd9af7b74c356b15299fc0591e1",
    "summary.active_leases": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.applied_incident_events": "e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683",
    "summary.burst_throttled_leases": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.contested_slots": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.expired_leases": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.frozen_leases": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.grace_leases": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.ignored_incident_events": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.leases_total": "3fdba35f04dc8c462986c992bcf875546257113072a909c162f7e470e581e278",
    "summary.quarantined_leases": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.renewal_capped_leases": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.witness_pending_leases": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "tier_policy.tiers": "0b77b60ec0ae427f5689edc55223b50655546d0ef7b097586261a8b85bdd630f",
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
        lv = outputs["lease_verdicts.json"]
        assert isinstance(lv, dict)
        assert (
            _sha256_bytes(_canonical(lv["leases"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["lease_verdicts.leases"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in (
            "active_leases",
            "applied_incident_events",
            "burst_throttled_leases",
            "contested_slots",
            "expired_leases",
            "frozen_leases",
            "grace_leases",
            "ignored_incident_events",
            "leases_total",
            "quarantined_leases",
            "renewal_capped_leases",
            "witness_pending_leases",
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

        sc = outputs["slot_contention.json"]
        assert isinstance(sc, dict)
        assert (
            _sha256_bytes(_canonical(sc["slots"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["slot_contention.slots"]
        )

        tp = outputs["tier_policy.json"]
        assert isinstance(tp, dict)
        assert (
            _sha256_bytes(_canonical(tp["tiers"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["tier_policy.tiers"]
        )


class TestLeaseOrdering:
    """Verify deterministic ordering rules on lease rows."""

    def test_lease_rows_sorted_by_host_then_slot(self, outputs: dict[str, object]) -> None:
        """`leases` must list rows in ascending `(host_id, slot_id)` order."""
        lv = outputs["lease_verdicts.json"]
        assert isinstance(lv, dict)
        rows = lv["leases"]
        assert isinstance(rows, list)
        keys = [(str(r["host_id"]), str(r["slot_id"])) for r in rows]
        assert keys == sorted(keys)


class TestLeaseVerdictSemantics:
    """Spot-check bundled rows that exercise distinct status branches."""

    def _row(
        self, outputs: dict[str, object], host_id: str, slot_id: str
    ) -> dict[str, object]:
        rows = outputs["lease_verdicts.json"]["leases"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("host_id") == host_id and r.get("slot_id") == slot_id:
                return r
        raise AssertionError(f"missing lease row {host_id}/{slot_id}")

    def test_force_expire_row(self, outputs: dict[str, object]) -> None:
        """`host-alpha` on `slot-alpha1` is forced expired with the directive reason."""
        r = self._row(outputs, "host-alpha", "slot-alpha1")
        assert r["computed_status"] == "expired"
        assert r["renewal_blocked"] is True
        assert r["reasons"] == ["force_expire_incident"]

    def test_host_compromise_quarantine(self, outputs: dict[str, object]) -> None:
        """`host-delta` is quarantined on every lease after host compromise."""
        r = self._row(outputs, "host-delta", "slot-beta2")
        assert r["computed_status"] == "quarantined"
        assert r["renewal_blocked"] is True
        assert r["reasons"] == []

    def test_slot_compromise_quarantine(self, outputs: dict[str, object]) -> None:
        """`slot-vault` leases are quarantined after slot compromise."""
        r = self._row(outputs, "host-epsilon", "slot-vault")
        assert r["computed_status"] == "quarantined"
        assert r["reasons"] == []

    def test_freeze_renewals_row(self, outputs: dict[str, object]) -> None:
        """`host-gamma` is frozen while still inside its lease window."""
        r = self._row(outputs, "host-gamma", "slot-gamma4")
        assert r["computed_status"] == "frozen"
        assert r["renewal_blocked"] is True

    def test_witness_pending_on_contested_slot(self, outputs: dict[str, object]) -> None:
        """`host-zeta` on contested `slot-zeta6` lacks gold-tier witness quorum."""
        r = self._row(outputs, "host-zeta", "slot-zeta6")
        assert r["computed_status"] == "witness_pending"
        assert r["reasons"] == ["insufficient_witnesses"]

    def test_grace_period_row(self, outputs: dict[str, object]) -> None:
        """`host-kappa` sits in grace after lease end but inside bronze grace."""
        r = self._row(outputs, "host-kappa", "slot-kappa7")
        assert r["computed_status"] == "grace"
        assert r["renewal_blocked"] is False
        assert r["reasons"] == []

    def test_renewal_capped_row(self, outputs: dict[str, object]) -> None:
        """`host-eta` on `slot-silver5` hits the silver renewal cap."""
        r = self._row(outputs, "host-eta", "slot-silver5")
        assert r["computed_status"] == "renewal_capped"
        assert r["reasons"] == ["renewal_cap_reached"]

    def test_burst_throttled_on_shared_slot(self, outputs: dict[str, object]) -> None:
        """`host-alpha` on contested `slot-shared` exceeds the gold renewal-burst
        limit even though two witness pairs were credited."""
        r = self._row(outputs, "host-alpha", "slot-shared")
        assert r["computed_status"] == "burst_throttled"
        assert r["renewal_blocked"] is True
        assert r["reasons"] == ["renewal_burst_exceeded"]
        assert r["witness_pairs_credited"] == 2

    def test_provisional_veto_blocks_beta_shared_witness(
        self, outputs: dict[str, object]
    ) -> None:
        """`host-beta` on `slot-shared` loses `host-alpha` as a witness because
        provisional burst throttling on alpha disqualifies that cohost."""
        r = self._row(outputs, "host-beta", "slot-shared")
        assert r["computed_status"] == "witness_pending"
        assert r["reasons"] == ["insufficient_witnesses"]
        assert r["witness_pairs_credited"] == 0

    def test_host_eta_zeta6_witness_pending_after_veto(
        self, outputs: dict[str, object]
    ) -> None:
        """Silver `host-eta` on contested `slot-zeta6` cannot use `host-zeta` after
        provisional burst throttling removes that cohost from witness eligibility."""
        r = self._row(outputs, "host-eta", "slot-zeta6")
        assert r["computed_status"] == "witness_pending"
        assert r["renewal_blocked"] is True
        assert r["witness_pairs_credited"] == 0

    def test_host_bronze_witness_pending_after_staleness(
        self, outputs: dict[str, object]
    ) -> None:
        """`host-bronze` on `slot-bronze3` retains only one stale-window witness pair
        after the witness staleness horizon, so quorum two is not met."""
        r = self._row(outputs, "host-bronze", "slot-bronze3")
        assert r["computed_status"] == "witness_pending"
        assert r["renewal_blocked"] is True
        assert r["reasons"] == ["insufficient_witnesses"]
        assert r["witness_pairs_credited"] == 1

    def test_host_beta_beta2_active_via_quarantined_cotenant_witness(
        self, outputs: dict[str, object]
    ) -> None:
        """`host-beta` on contested `slot-beta2` accepts an attestation from
        quarantined co-tenant `host-delta` because eligibility keys off lease rows."""
        r = self._row(outputs, "host-beta", "slot-beta2")
        assert r["computed_status"] == "active"
        assert r["renewal_blocked"] is False

    def test_witness_pairs_shared_burst_row(self, outputs: dict[str, object]) -> None:
        """Contest `slot-shared` still credits two post-staleness pairs for `host-alpha`
        from `host-beta` before burst throttling applies."""
        r = self._row(outputs, "host-alpha", "slot-shared")
        assert r["witness_pairs_credited"] == 2

    def test_witness_pairs_zero_before_witness_stage(self, outputs: dict[str, object]) -> None:
        """Quarantine short-circuits precedence before witness scoring, so credited pairs
        stay zero even when the slot is contested."""
        r = self._row(outputs, "host-delta", "slot-beta2")
        assert r["witness_pairs_credited"] == 0

    def test_witness_pairs_zero_on_uncontested_slot(self, outputs: dict[str, object]) -> None:
        """Uncontested slots never run witness sufficiency, so credited pairs are zero."""
        r = self._row(outputs, "host-kappa", "slot-kappa7")
        assert r["witness_pairs_credited"] == 0


class TestTierPolicy:
    """Tier aggregates reflect incident deltas from the spec."""

    def test_silver_grace_includes_extend_delta(self, outputs: dict[str, object]) -> None:
        """Silver effective grace includes the bundled extend_grace incident."""
        tiers = outputs["tier_policy.json"]["tiers"]
        assert isinstance(tiers, dict)
        silver = tiers["silver"]
        assert silver["base_grace"] == 5
        assert silver["grace_delta_sum"] == 2
        assert silver["effective_grace"] == 7

    def test_bronze_max_renewals_includes_cap_delta(self, outputs: dict[str, object]) -> None:
        """Bronze effective max renewals includes renewal_cap_delta."""
        tiers = outputs["tier_policy.json"]["tiers"]
        bronze = tiers["bronze"]
        assert bronze["base_max_renewals"] == 3
        assert bronze["renewal_cap_delta_sum"] == 1
        assert bronze["effective_max_renewals"] == 4


class TestSlotContention:
    """Contention map lists sorted hosts and quorum metadata."""

    def _row(
        self, outputs: dict[str, object], host_id: str, slot_id: str
    ) -> dict[str, object]:
        rows = outputs["lease_verdicts.json"]["leases"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("host_id") == host_id and r.get("slot_id") == slot_id:
                return r
        raise AssertionError(f"missing lease row {host_id}/{slot_id}")

    def test_shared_slot_is_contested(self, outputs: dict[str, object]) -> None:
        """`slot-shared` lists both alpha and beta hosts as active."""
        slots = outputs["slot_contention.json"]["slots"]
        assert isinstance(slots, dict)
        body = slots["slot-shared"]
        assert body["contested"] is True
        assert body["active_hosts"] == ["host-alpha", "host-beta"]
        assert body["quorum_required"] == 1

    def test_bronze3_override_quorum(self, outputs: dict[str, object]) -> None:
        """`slot-bronze3` documents the witness quorum override from its slot file."""
        slots = outputs["slot_contention.json"]["slots"]
        assert slots["slot-bronze3"]["quorum_required"] == 2

    def test_zeta6_reporting_quorum_differs_from_gold_sufficiency(
        self, outputs: dict[str, object]
    ) -> None:
        """`slot-zeta6` reports bronze-tier quorum_required while gold `host-zeta`
        still needs two witness pairs for sufficiency."""
        slots = outputs["slot_contention.json"]["slots"]
        assert slots["slot-zeta6"]["quorum_required"] == 1
        r = self._row(outputs, "host-zeta", "slot-zeta6")
        assert r["computed_status"] == "witness_pending"
        assert r["witness_pairs_credited"] == 1


class TestIncidentJournal:
    """Journal mirrors accepted, in-window, well-formed incidents."""

    def test_journal_sorted_by_day_then_id(self, outputs: dict[str, object]) -> None:
        """Applied events appear in ascending (day, event_id) order."""
        evs = outputs["incident_journal.json"]["applied_events"]
        assert isinstance(evs, list)
        keys = [(int(e["day"]), str(e["event_id"])) for e in evs]
        assert keys == sorted(keys)

    def test_journal_includes_expected_event_ids(self, outputs: dict[str, object]) -> None:
        """The bundled log applies the six well-formed incidents before the pool day."""
        evs = outputs["incident_journal.json"]["applied_events"]
        ids = {str(e["event_id"]) for e in evs}
        assert ids == {"e001", "e002", "e003", "e004", "e005", "e006"}

    def test_summary_ignored_incident_count(self, outputs: dict[str, object]) -> None:
        """Three log rows are ignored (rejected, future day, or unknown kind)."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert sm["ignored_incident_events"] == 3
        assert sm["applied_incident_events"] == 6


class TestSummaryCounts:
    """Summary status buckets align with per-lease verdict rows."""

    def test_status_counts_match_lease_rows(self, outputs: dict[str, object]) -> None:
        """Each summary counter equals the number of leases with that status."""
        rows = outputs["lease_verdicts.json"]["leases"]
        sm = outputs["summary.json"]
        assert isinstance(rows, list)
        assert isinstance(sm, dict)
        tallies: dict[str, int] = {}
        for r in rows:
            status = str(r["computed_status"])
            tallies[status] = tallies.get(status, 0) + 1
        assert sm["leases_total"] == len(rows)
        assert sm["quarantined_leases"] == tallies.get("quarantined", 0)
        assert sm["frozen_leases"] == tallies.get("frozen", 0)
        assert sm["witness_pending_leases"] == tallies.get("witness_pending", 0)
        assert sm["expired_leases"] == tallies.get("expired", 0)
        assert sm["grace_leases"] == tallies.get("grace", 0)
        assert sm["burst_throttled_leases"] == tallies.get("burst_throttled", 0)
        assert sm["renewal_capped_leases"] == tallies.get("renewal_capped", 0)
        assert sm["active_leases"] == tallies.get("active", 0)
