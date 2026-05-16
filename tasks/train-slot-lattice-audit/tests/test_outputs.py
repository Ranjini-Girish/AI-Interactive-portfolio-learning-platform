"""Behavioral tests for the train slot lattice audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("TSL_DATA_DIR", "/app/tslattice"))
AUDIT_DIR = Path(os.environ.get("TSL_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "allocation_plan.json",
    "dependency_graph.json",
    "incident_trace.json",
    "tenant_utilization.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "80cc2b17f055423637de649eed0c67515329b6e444214562a82e602d42d3a453",
    "ancillary/m1.json": "ee2612f227dcb825f507e6cbaaef2aac5f21ada4d1b51b5be3cb6c2b95a13dcc",
    "ancillary/m2.json": "f67ef3ef7207736cc1ba7239a0098c3b809cd266166bbce2590f332864885257",
    "ancillary/m3.json": "da821bc9515ff9a4bb307b5bfcd4164b6ecb6f902c177cebf8e5049a07d6bc16",
    "incidents.json": "01dd0bb42907fea9e4a4e08e8870d5a3b4051c366515f4dbc070906286ea0807",
    "index.json": "3a0253dec2cbcede25c2c984ec036e3eac6058724293ee552d19bf3db58feffc",
    "policy.json": "f9326cda28b4e67bba86a1fec0f1bc91469c871ca28ba95625a677222189e1e7",
    "pool_state.json": "198a6462744fd01584e47aeb8e31535fa595d4cada627302c5263bdc5534821a",
    "requests/r-blocked.json": "54ece07adf64de7fedebcc262ad5cfbe2181118e0906af6bc8ab8e7724dae390",
    "requests/r-child.json": "639c38171d5f333bde78ad8a93e7403ae7321cab0228c04765f1c88f92722ef0",
    "requests/r-cy-a.json": "b4b4abb161e6f17c7cdac00dd277dbf38a83aa51ad40b2c2c1c06fe1ea110b1e",
    "requests/r-cy-b.json": "26fbfcdced4aac888b4c62a57aec961a88126acab050c679f784587795cca06e",
    "requests/r-east-late.json": "73ba052cb4bb1b27b113a7b59ccf5fb785deca163e15169f78d53c50ef120317",
    "requests/r-future.json": "d7e9b99f76962dc85b99bc5b45c665e2448e30817325559880c979c15d55048e",
    "requests/r-ghost.json": "b03411fd36dd1bacc25c40906c2a78759c25d9d4c3e516ebc6c467ad44080cc3",
    "requests/r-loop.json": "65ea361c7193d460ef8f37dedd20b799f51a7cba64554c3d5f8481ecefdad3c3",
    "requests/r-override.json": "3217f8603fe43592866689beefaaf6ea9c399afdd57c903ff5e7ab7646358ead",
    "requests/r-parent.json": "3dea2c7824c60e9fa361fdff68f23d49f17756f27b47ca5202837d27a4313d55",
    "requests/r-sat-a.json": "8a8d18f4ee39cbc726e8bef372cf9ef1f49ff5df053e759e7c48e12322d7e2d8",
    "requests/r-sat-b.json": "399b2fb960ce8d11849664ec1997f18316eb325af44ebbe9240239cad4005b64",
    "tenants/lab-east.json": "b74813d80b14f93d868434845687c70eeaf777a35753f04c396e7d9b65acd981",
    "tenants/lab-west.json": "d9726035ca1dd3a1265e9f80c6aa76c918328d7b877490fbe3f3585e024d94cd",
    "tenants/solo.json": "7aaf252b294d960d92d1ce590f37b060f46e3e0d99b8d97910b50ad45efdd7c1",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "allocation_plan.json": "a2454e5814788f1d90b0281e5cd8d711b5c1d33a7fe408e7c609d7906c39e62b",
    "dependency_graph.json": "84d8bff6d5b5298e112f7eaafd5883310fa226334f237f4eb765e171c88eb424",
    "incident_trace.json": "4d2b9a7ef745449ff8b320cba519bc51b7b9f0f6e2a6be4597be8dc759e857d6",
    "summary.json": "a5313cfa8ac5062476498b553733472240fd895a8fd598d45f6018a51a7cb95e",
    "tenant_utilization.json": "0eebfd98c8956691bec0e0fdbd4f43e92089f76b0f11b3bdc8b07398b60fee32",
}


EXPECTED_FIELD_HASHES = {
    "allocation_plan.allocations": "37be55e97b52780bb095d9823607ea27c9de97b7ecdff1096c6f1dbcb086fd22",
    "dependency_graph.cycle_groups": "93dcaaa5739e10d33d68a10010e6a454ea73f37a30777e4d87b4948cf25fe317",
    "incident_trace.events": "67dd2bd7a3f148d0e5d8d3d84204e59e80dcd48113b848440336be12e9d032b5",
    "summary.effective_cluster_slot_cap": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "summary.eligible_total": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "tenant_utilization.tenants": "1ce95f43c1f97bd31a65a5d0e52acf5f95849b431f500c60836c69bc01bc89e4",
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


@pytest.fixture(scope="session")
def allocations(outputs: dict[str, object]) -> dict[str, dict[str, object]]:
    """Index allocation rows by run_id."""
    plan = outputs["allocation_plan.json"]
    assert isinstance(plan, dict)
    rows = plan["allocations"]
    assert isinstance(rows, list)
    out: dict[str, dict[str, object]] = {}
    for row in rows:
        assert isinstance(row, dict)
        rid = row["run_id"]
        assert isinstance(rid, str)
        out[rid] = row
    return out


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
        ap = outputs["allocation_plan.json"]
        assert isinstance(ap, dict)
        assert (
            _sha256_bytes(_canonical(ap["allocations"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["allocation_plan.allocations"]
        )

        dg = outputs["dependency_graph.json"]
        assert isinstance(dg, dict)
        assert (
            _sha256_bytes(_canonical(dg["cycle_groups"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["dependency_graph.cycle_groups"]
        )

        it = outputs["incident_trace.json"]
        assert isinstance(it, dict)
        assert (
            _sha256_bytes(_canonical(it["events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_trace.events"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["effective_cluster_slot_cap"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.effective_cluster_slot_cap"]
        )
        assert (
            _sha256_bytes(_canonical(sm["eligible_total"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.eligible_total"]
        )

        tu = outputs["tenant_utilization.json"]
        assert isinstance(tu, dict)
        assert (
            _sha256_bytes(_canonical(tu["tenants"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["tenant_utilization.tenants"]
        )


class TestSummaryCounts:
    """Sanity-check aggregate counters against the bundled timeline."""

    def test_summary_matches_fixture_totals(self, outputs: dict[str, object]) -> None:
        """Pinned summary counters reflect the bundled incidents and requests."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert sm["requests_total"] == 12
        assert sm["eligible_total"] == 5
        assert sm["granted_positive_total"] == 3
        assert sm["cycle_bound_total"] == 3
        assert sm["incidents_seen_total"] == 5
        assert sm["incidents_applied_total"] == 4
        assert sm["effective_cluster_slot_cap"] == 5


class TestDependencyGraph:
    """Structural checks on the emitted dependency graph."""

    def test_cycle_groups_partition_mutual_and_self_cycles(self, outputs: dict[str, object]) -> None:
        """Mutual cycle and self-loop appear as distinct sorted groups."""
        dg = outputs["dependency_graph.json"]
        assert isinstance(dg, dict)
        groups = dg["cycle_groups"]
        assert isinstance(groups, list)
        flat = [g for g in groups if isinstance(g, list)]
        joined = sorted({x for g in flat for x in g})
        assert joined == ["r-cy-a", "r-cy-b", "r-loop"]

    def test_known_run_ids_sorted(self, outputs: dict[str, object]) -> None:
        """Known run identifiers are the sorted union of bundled request ids."""
        dg = outputs["dependency_graph.json"]
        assert isinstance(dg, dict)
        kids = dg["known_run_ids"]
        assert isinstance(kids, list)
        assert kids == sorted(kids)
        assert set(kids) == {
            "r-blocked",
            "r-child",
            "r-cy-a",
            "r-cy-b",
            "r-east-late",
            "r-future",
            "r-ghost",
            "r-loop",
            "r-override",
            "r-parent",
            "r-sat-a",
            "r-sat-b",
        }


class TestIncidentTrace:
    """Incident replay markers."""

    def test_future_incident_not_applied(self, outputs: dict[str, object]) -> None:
        """Horizon incidents remain flagged as future while in-window ones apply."""
        it = outputs["incident_trace.json"]
        assert isinstance(it, dict)
        events = it["events"]
        assert isinstance(events, list)
        by_seq = {int(e["seq"]): e for e in events if isinstance(e, dict)}
        assert by_seq[99]["applied"] is False
        assert by_seq[99]["note"] == "future"
        assert by_seq[1]["applied"] is True
        assert by_seq[1]["note"] == "ok"


class TestAllocationSemantics:
    """Per-run classification checks drawn from the bundled manifest."""

    def test_mutual_cycle_runs_marked_cycle(self, allocations: dict[str, dict[str, object]]) -> None:
        """Two-run dependency loop is classified as cycle-bound."""
        for rid in ("r-cy-a", "r-cy-b"):
            row = allocations[rid]
            assert row["denied_reason"] == "cycle"
            assert row["granted_slots"] == 0

    def test_self_loop_marked_cycle(self, allocations: dict[str, dict[str, object]]) -> None:
        """A self-edge is treated as a cycle-bound run."""
        row = allocations["r-loop"]
        assert row["denied_reason"] == "cycle"
        assert row["granted_slots"] == 0

    def test_prerequisite_in_cycle_blocks_dependent(
        self, allocations: dict[str, dict[str, object]]
    ) -> None:
        """A run depending on a cycle-bound predecessor is blocked."""
        row = allocations["r-blocked"]
        assert row["denied_reason"] == "blocked_dependency"
        assert row["granted_slots"] == 0

    def test_missing_dependency_target_unknown(
        self, allocations: dict[str, dict[str, object]]
    ) -> None:
        """Unknown dependency targets surface as unknown_dependency."""
        row = allocations["r-ghost"]
        assert row["denied_reason"] == "unknown_dependency"
        assert row["granted_slots"] == 0

    def test_freeze_blocks_late_submit_same_tenant(
        self, allocations: dict[str, dict[str, object]]
    ) -> None:
        """Freeze starting day seven blocks lab-east runs submitted on or after that day."""
        row = allocations["r-east-late"]
        assert row["denied_reason"] == "frozen_tenant"
        assert row["granted_slots"] == 0

    def test_future_submit_not_submitted(self, allocations: dict[str, dict[str, object]]) -> None:
        """Runs beyond the current horizon stay not_submitted."""
        row = allocations["r-future"]
        assert row["denied_reason"] == "not_submitted"
        assert row["granted_slots"] == 0

    def test_capacity_exhaustion_marks_saturated_bronze_runs(
        self, allocations: dict[str, dict[str, object]]
    ) -> None:
        """After higher-priority grants consume the effective cap, bronze runs saturate."""
        for rid in ("r-sat-a", "r-sat-b"):
            row = allocations[rid]
            assert row["denied_reason"] == "saturated"
            assert row["granted_slots"] == 0

    def test_dependency_chain_child_receives_partial_when_cap_tight(
        self, allocations: dict[str, dict[str, object]]
    ) -> None:
        """Silver child follows gold parent and receives the remaining single slot."""
        parent = allocations["r-parent"]
        child = allocations["r-child"]
        assert parent["denied_reason"] is None
        assert parent["granted_slots"] == 2
        assert child["denied_reason"] is None
        assert child["granted_slots"] == 1

    def test_total_granted_matches_effective_cap(self, allocations: dict[str, dict[str, object]]) -> None:
        """Sum of positive grants equals the post-incident cluster capacity."""
        total = sum(int(row["granted_slots"]) for row in allocations.values())
        assert total == 5


class TestTenantUtilization:
    """Per-tenant aggregates."""

    def test_solo_tenant_served_multiple_runs(self, outputs: dict[str, object]) -> None:
        """Solo tenant should show multiple served runs when grants land."""
        tu = outputs["tenant_utilization.json"]
        assert isinstance(tu, dict)
        tenants = tu["tenants"]
        assert isinstance(tenants, dict)
        solo = tenants["solo"]
        assert isinstance(solo, dict)
        assert solo["slots_granted"] == 5
        assert solo["requests_served"] == 3
