"""Behavioral tests for the compose-start-order-audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CSOA_DATA_DIR", "/app/compose_plans"))
AUDIT_DIR = Path(os.environ.get("CSOA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "stack_plan.json",
    "cluster_ledger.json",
    "service_matrix.json",
    "incident_journal.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "2ba61cb7557e7c9283359a7b5e6674f1d25a30f33b2409807392c0f5027e9f78",
    "ancillary/channel_tag.json": "21f0fcd78463678e9fb4b6ba9017e5f6471726d35ede7abcb9f1deb06e172542",
    "ancillary/ci_guard.json": "2a6fc058bf1b6df7a6778e70ca6b216880f145d8db508dad63252ef98e85d145",
    "ancillary/watermark.txt": "97a9429e6ab4ee389687ba491a90a08318c2df7ab1633bd6d24e4d8778c069ab",
    "clusters/r-east.json": "06cfac55dadf7fa236d4c696c02c0804271069ebd3b14b97bee567acd05a8efc",
    "clusters/r-north.json": "198e2dbb742bc53e113359bc50677f8429e0dee9a8fd07ca9712e811d58c026c",
    "clusters/r-west.json": "8531d4c2e097e21ea72a5a8f36abe0e4e3d543c3f943b000216d8765a2bbe7cf",
    "incident_log.json": "b27ebc44198884c4ed90a67a3595498f72354ce07586c31981cf88588308ac30",
    "policy.json": "78d310eb9f8a3278a2d922d84ac0397355e78d7151fd94c5d2d5e6c65945aa09",
    "pool_state.json": "c8b9e98a5963f211e754a4678893db0014d6fbd744b2379b93d70fd83b85f8b9",
    "services/b-app.json": "c598f3f1b0ff585aa7fdf967637e81f54390e4581331648c6dd1b60e3a6291a7",
    "services/b-base.json": "96ed784d7fd524a8070f1578e35fc22f6e8f2f8a7b7763fcf8923af1a3c74524",
    "services/b-db.json": "15cf45eb612af46b693a5a26bee2c68231907cb81da6a07864ec83ccac269d62",
    "services/b-heavy.json": "0a25303187262d60f57187043090156d4de51f1ae98eddd8d53e21cd9e5467b0",
    "services/b-mon.json": "6563da941247a24833d833dc4bbf53a9fe30379318e57a50ea7855659aefa0c9",
    "services/b-net.json": "d69d3cdb4181cbe6114c503dde057465d590122f65daaddf95b5b0e181c79589",
    "stacks/h-d1.json": "54220ee1f758fec3159072c2de7a5584cb16a0e4d0401ad6f31dff8fe0be150b",
    "stacks/h-d2.json": "189c5ece54d18d358cfa1487b4bf2f48fce38a3d9ce98a80c708cf660285d441",
    "stacks/h-idle.json": "fd9fc51ec89828945df09948f9e7300cdc84b5525b95faf5a580cd630d969426",
    "stacks/h-n1.json": "919fc587bfd5d0a8cb69a687a4b87b3a71ac6b07bd2819360785d52b72d30d69",
    "stacks/h-out.json": "20f80b87729cbed9000e3fa404f1b0fbba5c14f6d8409ef07e1f795c6f8a49ef",
    "stacks/h-p1.json": "b8d6f401f30587264073a0037f69ec1b1ac3ff4d70cd84460e74dfb1b9d2787d",
    "stacks/h-p2.json": "2ee225eea45fea2a2de9830b7d88c1d9aa1a1feee8fd91ec440e471769e19cf4",
    "stacks/h-p3.json": "0837729b4fa4f51e2f8638d860afd8eba6be21573a91e08cf855ec85ec674180",
    "stacks/h-p4.json": "70acf6394c175b33b37d905a8a86acba55749e74538de4aead7c40ec27326bc0",
    "stacks/h-s1.json": "018b82ea57907faf68197a06f3f196a1713272d302407b123d5fbca79a50f48e",
    "stacks/h-s2.json": "5eb0fa2a353e3616da008bdf1df8928c229dace9503e733220d238b04fed0aa2",
    "stacks/h-s3.json": "abf595de6038d4f8778fd4e84921492665fee6bfee97b94eb387f52397b31711",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "stack_plan.json": "b7dac13bc3aa16745eb1f45b5f2d499c0a6c3e3f62895801a746dae29e2fbb42",
    "cluster_ledger.json": "57f867e5d95f979aefefb67b23af4758f0ae7979ac7c463f0e78c690f3a26838",
    "service_matrix.json": "503ddd195d3e9422fd7b2cb25c5e8d03d50762a9afce6ed98ae4ca51e7c431da",
    "incident_journal.json": "9204a1f778849e1599ecbf9aa345fc1e60bfba87d6c61cf1f0144c87fdae145e",
    "summary.json": "40dcb8e5fd8014d8efeb200cacb06d50044cfd02a032b94ed4a91b7e5a646b15",
}

EXPECTED_FIELD_HASHES = {
    "cluster_ledger.clusters": "c51a18fe102e5cb65b4c433bb4c539360fadfccc5ce6b674a640fce922dab4d7",
    "incident_journal.applied_events": "d5533374d6eb00dd57c296d28f87ff1be925889db3eef2c1f50c1834e269f96e",
    "service_matrix.services": "30127e3f84daca3c33df5023ba897b231f56eaf33725f2427d38c2f02c3017f2",
    "stack_plan.stacks": "3d1b2baf401870da8ae240f12037730ae141666ac2a3cab79d422fb3f18ff494",
    "summary.applied_incident_events": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "summary.clusters_total": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.deferred_stacks": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.frozen_stacks": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.idle_stacks": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.ignored_incident_events": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.quarantined_stacks": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.scheduled_services_today": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.scheduled_stacks": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.services_total": "e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683",
    "summary.stacks_total": "6b51d431df5d7f141cbececcf79edf3dd861c3b4069f0b11661a3eefacbba918",
    "summary.warmup_deferred_stacks": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
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
        sp = outputs["stack_plan.json"]
        assert isinstance(sp, dict)
        assert (
            _sha256_bytes(_canonical(sp["stacks"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["stack_plan.stacks"]
        )

        cl = outputs["cluster_ledger.json"]
        assert isinstance(cl, dict)
        assert (
            _sha256_bytes(_canonical(cl["clusters"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["cluster_ledger.clusters"]
        )

        smx = outputs["service_matrix.json"]
        assert isinstance(smx, dict)
        assert (
            _sha256_bytes(_canonical(smx["services"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["service_matrix.services"]
        )

        ij = outputs["incident_journal.json"]
        assert isinstance(ij, dict)
        assert (
            _sha256_bytes(_canonical(ij["applied_events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_journal.applied_events"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in (
            "applied_incident_events",
            "clusters_total",
            "deferred_stacks",
            "frozen_stacks",
            "idle_stacks",
            "ignored_incident_events",
            "quarantined_stacks",
            "scheduled_services_today",
            "scheduled_stacks",
            "services_total",
            "stacks_total",
            "warmup_deferred_stacks",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestStackOrdering:
    """Deterministic ordering rules on stack rows."""

    def test_stacks_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`stacks` must list rows in ascending ASCII `stack_id` order."""
        rows = outputs["stack_plan.json"]["stacks"]
        assert isinstance(rows, list)
        ids = [str(r["stack_id"]) for r in rows]
        assert ids == sorted(ids)


class TestStackStatusCoverage:
    """Bundled fixtures exercise every documented stack_status value."""

    def _statuses(self, outputs: dict[str, object]) -> set[str]:
        rows = outputs["stack_plan.json"]["stacks"]
        return {str(r["stack_status"]) for r in rows}

    def test_quarantined_status_present(self, outputs: dict[str, object]) -> None:
        """At least one stack row carries `quarantined` from a compromise incident."""
        assert "quarantined" in self._statuses(outputs)

    def test_cluster_frozen_status_present(self, outputs: dict[str, object]) -> None:
        """At least one stack row carries `cluster_frozen` from a cluster freeze."""
        assert "cluster_frozen" in self._statuses(outputs)

    def test_deferred_capacity_status_present(self, outputs: dict[str, object]) -> None:
        """At least one stack row carries `deferred_capacity` after the start cap."""
        assert "deferred_capacity" in self._statuses(outputs)

    def test_warmup_deferred_status_present(self, outputs: dict[str, object]) -> None:
        """At least one stack row carries `warmup_deferred` when credits are exhausted."""
        assert "warmup_deferred" in self._statuses(outputs)

    def test_scheduled_status_present(self, outputs: dict[str, object]) -> None:
        """At least one stack row carries `scheduled` with a service assigned today."""
        assert "scheduled" in self._statuses(outputs)

    def test_idle_status_present(self, outputs: dict[str, object]) -> None:
        """At least one stack row carries `idle` when nothing can be started."""
        assert "idle" in self._statuses(outputs)


class TestBlockedReasonCoverage:
    """Bundled fixtures surface distinct blocked-candidate reasons."""

    def _reasons(self, outputs: dict[str, object]) -> set[str]:
        found: set[str] = set()
        for row in outputs["stack_plan.json"]["stacks"]:
            for bc in row.get("blocked_candidates") or []:
                found.add(str(bc["reason"]))
        return found

    def test_capacity_deferred_reason_present(self, outputs: dict[str, object]) -> None:
        """A capacity-deferred stack cites `capacity_deferred` for its would-be service."""
        assert "capacity_deferred" in self._reasons(outputs)

    def test_warmup_deferred_reason_present(self, outputs: dict[str, object]) -> None:
        """A warmup-deferred stack cites `warmup_deferred` for its chosen service."""
        assert "warmup_deferred" in self._reasons(outputs)

    def test_embargoed_reason_present(self, outputs: dict[str, object]) -> None:
        """The embargo incident blocks at least one service with `embargoed`."""
        assert "embargoed" in self._reasons(outputs)

    def test_outside_window_reason_present(self, outputs: dict[str, object]) -> None:
        """A stack outside the effective window cites `outside_window`."""
        assert "outside_window" in self._reasons(outputs)

    def test_profile_mismatch_reason_present(self, outputs: dict[str, object]) -> None:
        """A stack with disjoint profiles cites `profile_mismatch` on pending services."""
        assert "profile_mismatch" in self._reasons(outputs)

    def test_insufficient_health_reason_present(self, outputs: dict[str, object]) -> None:
        """A stack below the health streak cites `insufficient_health` on a service."""
        assert "insufficient_health" in self._reasons(outputs)

    def test_warmup_over_budget_reason_present(self, outputs: dict[str, object]) -> None:
        """An over-tier-warmup service cites `warmup_over_budget` on an otherwise eligible stack."""
        assert "warmup_over_budget" in self._reasons(outputs)


class TestVerdictSemantics:
    """Spot-check bundled rows that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], stack_id: str) -> dict[str, object]:
        for row in outputs["stack_plan.json"]["stacks"]:
            if row["stack_id"] == stack_id:
                return row
        raise AssertionError(f"missing stack row {stack_id}")

    def test_compromise_stack_quarantined(self, outputs: dict[str, object]) -> None:
        """`h-p2` is quarantined with compromise blocking every pending service."""
        row = self._row(outputs, "h-p2")
        assert row["stack_status"] == "quarantined"
        assert row["scheduled_service"] is None
        assert all(bc["reason"] == "quarantine" for bc in row["blocked_candidates"])

    def test_freeze_cluster_blocks_west_stacks(self, outputs: dict[str, object]) -> None:
        """`h-p3` in frozen `r-west` cites `cluster_frozen` on pending services."""
        row = self._row(outputs, "h-p3")
        assert row["stack_status"] == "cluster_frozen"
        assert row["cluster_id"] == "r-west"
        assert row["blocked_candidates"]
        assert all(bc["reason"] == "cluster_frozen" for bc in row["blocked_candidates"])

    def test_east_schedules_two_net_starts(self, outputs: dict[str, object]) -> None:
        """`r-east` schedules `h-p1` and `h-p4` for `b-net` after warmup debits."""
        scheduled = {
            r["stack_id"]: r["scheduled_service"]
            for r in outputs["stack_plan.json"]["stacks"]
            if r["stack_status"] == "scheduled" and r["cluster_id"] == "r-east"
        }
        assert scheduled == {"h-p1": "b-net", "h-p4": "b-net"}

    def test_warmup_deferred_stack_cites_warmup_on_chosen_service(
        self, outputs: dict[str, object]
    ) -> None:
        """`h-s1` defers with `warmup_deferred` on `b-net` after east credits are spent."""
        row = self._row(outputs, "h-s1")
        assert row["stack_status"] == "warmup_deferred"
        reasons = {bc["service_id"]: bc["reason"] for bc in row["blocked_candidates"]}
        assert reasons.get("b-net") == "warmup_deferred"

    def test_north_capacity_deferred_stack(self, outputs: dict[str, object]) -> None:
        """`h-n1` in `r-north` ends `deferred_capacity` when effective cap is zero."""
        row = self._row(outputs, "h-n1")
        assert row["stack_status"] == "deferred_capacity"
        assert row["cluster_id"] == "r-north"

    def test_profile_mismatch_stack_idle(self, outputs: dict[str, object]) -> None:
        """`h-d2` has only `batch-only` profiles and stays idle with profile mismatches."""
        row = self._row(outputs, "h-d2")
        assert row["stack_status"] == "idle"
        assert row["scheduled_service"] is None
        assert any(bc["reason"] == "profile_mismatch" for bc in row["blocked_candidates"])

    def test_idle_stack_has_no_pending_services(self, outputs: dict[str, object]) -> None:
        """`h-idle` already started every service and stays idle with an empty block list."""
        row = self._row(outputs, "h-idle")
        assert row["stack_status"] == "idle"
        assert row["scheduled_service"] is None
        assert row["blocked_candidates"] == []


class TestClusterLedger:
    """Cluster counters align with stack outcomes and warmup pools."""

    def test_r_east_credit_pool_depleted(self, outputs: dict[str, object]) -> None:
        """`r-east` starts with two credits, schedules two debits, and ends at zero remaining."""
        cl = outputs["cluster_ledger.json"]["clusters"]["r-east"]
        assert cl["start_credits_start"] == 2
        assert cl["start_credits_remaining"] == 0
        assert cl["stacks_scheduled"] == 2
        assert cl["stacks_deferred_warmup"] == 1

    def test_r_north_zero_cap_defers_contender(self, outputs: dict[str, object]) -> None:
        """`r-north` base cap zero defers its contender without scheduling anyone."""
        cl = outputs["cluster_ledger.json"]["clusters"]["r-north"]
        assert cl["effective_cap"] == 0
        assert cl["stacks_scheduled"] == 0
        assert cl["stacks_deferred_capacity"] == 1


class TestIncidentJournal:
    """Journal mirrors accepted, in-window, well-formed incidents."""

    def test_journal_event_ids(self, outputs: dict[str, object]) -> None:
        """Five kept incidents match the bundled acceptance rules."""
        evs = outputs["incident_journal.json"]["applied_events"]
        ids = {str(e["event_id"]) for e in evs}
        assert ids == {"e01", "e02", "e03", "e04", "e07"}

    def test_journal_sorted(self, outputs: dict[str, object]) -> None:
        """Applied events appear in ascending (day, event_id) order."""
        evs = outputs["incident_journal.json"]["applied_events"]
        keys = [(int(e["day"]), str(e["event_id"])) for e in evs]
        assert keys == sorted(keys)


class TestSummaryPartition:
    """Summary status counts partition the stack fleet."""

    def test_status_counts_sum_to_stacks_total(self, outputs: dict[str, object]) -> None:
        """Quarantine, freeze, defer, warmup-defer, schedule, and idle counts sum to total."""
        sm = outputs["summary.json"]
        total = (
            sm["quarantined_stacks"]
            + sm["frozen_stacks"]
            + sm["deferred_stacks"]
            + sm["warmup_deferred_stacks"]
            + sm["scheduled_stacks"]
            + sm["idle_stacks"]
        )
        assert total == sm["stacks_total"]
