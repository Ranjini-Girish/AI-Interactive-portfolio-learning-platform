"""Behavioral tests for the artifact-promote-lattice-audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("APLA_DATA_DIR", "/app/promote_lattice"))
AUDIT_DIR = Path(os.environ.get("APLA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "artifact_plan.json",
    "pool_ledger.json",
    "stage_matrix.json",
    "incident_journal.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "4f2e1c4a1f3b0280dbe3196de242bdf580ffa834c625607c5726110604a87b8f",
    "ancillary/channel_tag.json": "e3d74bfeb74946b2879b8f397422443fc51989f52c9fcf7aa8ebdb55a60a6581",
    "ancillary/ci_guard.json": "83144d396179849e33a72a7a7106f9485c9af9928dac2b98f760566ab632218b",
    "ancillary/watermark.txt": "fc99585338cbe169c6f2625326957f2d3738ed6e890a100bdb834a155fbc4024",
    "artifacts/a-app.json": "b8312b37f79982dff8969305e50cc917b9669721be9cd7352f6a8314e23f9612",
    "artifacts/a-base.json": "16372f98eb6f580395a4bff6ecdda44e9bca9586f834f3634a7d434e3330cb34",
    "artifacts/a-d1.json": "28b2107eb63527924cfcc12d2719677eb4e66824e73bc4c83187e92348cab3e4",
    "artifacts/a-db.json": "cb13916788b0b03c98da4708196e51e026898da96d91173dd8b15176205104bb",
    "artifacts/a-extra.json": "9d730bc19c878a14820f1f261232c478feb55879b4d679d5f7b6309d502674bf",
    "artifacts/a-heavy.json": "1e27d4619831589a96fe4698bf8af956af12c7edd80b1a6d54c6a8a356b17420",
    "artifacts/a-idle.json": "aae8d3603d8903bb8a176a3787ee3d5055eb16cea14c8017d43e6f35eed81464",
    "artifacts/a-mon.json": "1463ffc3bbd6ad7c52f2f96335d7cdbfda63d71d73c6ff4da4bd7194cc65679a",
    "artifacts/a-net.json": "430dda1e319996ef4bed80dc54b27382be06d5fad7b5e9f17aaf0758f351861d",
    "artifacts/a-p2.json": "d79d8388ea9c9d98eedc60cf5a2aa29af4d4034381e35b8446c472bb1ba15ba4",
    "artifacts/a-p4.json": "fc6bb618a3e373c8699a7f9994f2b10d005000cb0999752eb78e23c89cfeab3a",
    "artifacts/a-s1.json": "2de30c3aba34485d46ef44cbcf63d84fbb5fc4ff4becee3db85da4e8ae2a04a1",
    "artifacts/a-s2.json": "de06a8ed74fa44aa3a803fa020c0ce68ec2e06408bba07f22ada2fff8df41d66",
    "incident_log.json": "dd5385e379a47889e28808b54bf384af41ef0fc78dac4807fa9fbb65719c9d60",
    "policy.json": "a80b9edd764b2099d7ec8cd58591d214d1c23f92a2510faef4f0c02dd78f0ee7",
    "pool_state.json": "78c533edbd96f582aa124618c50b9a5d74899b9950f7d4216ebf06190e051031",
    "pools/p-east.json": "45f97753559ddaa607745927ff175b9b34aae3aaa4ba5b397f5595b0e59b900b",
    "pools/p-north.json": "0e40747ca1912606bbc26ac8db44e0d1e165868eb6a2b6483f7360f39ce044d1",
    "pools/p-west.json": "553998e961fa6c277b987fbd3c0a9dcc3e96300ae7609d4c5bfa0633b4f509fe",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "artifact_plan.json": "b7970cb905c2da5aaf4c1a13e88d16dd515cb9850cd2ec1d3ea3e59c45a99911",
    "incident_journal.json": "6a2cb33902a28be679adc190e685745b5fa45be4b15200d2e60418e8c3236200",
    "pool_ledger.json": "9586f7e4d044b7ae82abe55f233f05daa84d1d9cf465697594e8ea83ade32f2d",
    "stage_matrix.json": "62ebf46b8fb0af49df93780cc593f2decf0a9d8f1a507b2bfd79b9c9409c439f",
    "summary.json": "12c3d19dc15138f7b21863a0a51ca80326d98fbcd9902c0edc88b0bfaab907c2",
}

EXPECTED_FIELD_HASHES = {
    "artifact_plan.artifacts": "2f21257848b9f48cf23dd806afdd7d24d98c6d266ce5dc2dd0823272ffdf90b5",
    "incident_journal.applied_events": "3198fc4d03fa8e6d2af32b447b37a2b057d988af667b4883cb413daa4097f178",
    "pool_ledger.pools": "55daca6574c7c03cce0b0a5667a73c6e25515b7d3df7b0d8f33a2e7892a5e334",
    "stage_matrix.stages": "0c70fce2d0dd20e563e7a2392c82cc5acc0d2d2e4e2ad91ed261bd9d4f301f62",
    "summary.applied_incident_events": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.artifacts_total": "3fdba35f04dc8c462986c992bcf875546257113072a909c162f7e470e581e278",
    "summary.deferred_artifacts": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.frozen_artifacts": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.idle_artifacts": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.ignored_incident_events": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.promoted_artifacts": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.promotions_today": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.quarantined_artifacts": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.soak_waiting_artifacts": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _spec_canonical_json_bytes(value: object) -> bytes:
    """UTF-8 bytes for SPEC.md canonical JSON (two-space indent, sorted keys, ASCII, one trailing newline)."""
    text = json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


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
        ap = outputs["artifact_plan.json"]
        assert isinstance(ap, dict)
        assert (
            _sha256_bytes(_canonical(ap["artifacts"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["artifact_plan.artifacts"]
        )

        pl = outputs["pool_ledger.json"]
        assert isinstance(pl, dict)
        assert (
            _sha256_bytes(_canonical(pl["pools"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["pool_ledger.pools"]
        )

        smx = outputs["stage_matrix.json"]
        assert isinstance(smx, dict)
        assert (
            _sha256_bytes(_canonical(smx["stages"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["stage_matrix.stages"]
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
            "artifacts_total",
            "deferred_artifacts",
            "frozen_artifacts",
            "idle_artifacts",
            "ignored_incident_events",
            "promoted_artifacts",
            "promotions_today",
            "quarantined_artifacts",
            "soak_waiting_artifacts",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )

    def test_output_files_match_spec_canonical_encodings(self, outputs: dict[str, object]) -> None:
        """Each audit file's on-disk UTF-8 must match SPEC canonical JSON (indent, sorted keys, ASCII, one trailing newline)."""
        for name in OUTPUT_FILES:
            path = AUDIT_DIR / name
            raw = path.read_bytes()
            expected = _spec_canonical_json_bytes(outputs[name])
            assert raw == expected, f"non-canonical on-disk JSON for {name}"


class TestStageMatrixContract:
    """Normative shape rules from SPEC.md for the stage matrix."""

    def test_stage_matrix_lists_every_policy_stage_sorted(self, outputs: dict[str, object]) -> None:
        """Each name in policy stage_order appears exactly once, ascending lexicographic target_stage."""
        policy = _load_json(DATA_DIR / "policy.json")
        assert isinstance(policy, dict)
        raw_order = policy["stage_order"]
        assert isinstance(raw_order, list)
        want = sorted(str(s) for s in raw_order)
        stages = outputs["stage_matrix.json"]["stages"]
        assert isinstance(stages, list)
        got = [str(row["target_stage"]) for row in stages]
        assert got == want
        assert len(got) == len(set(got))


class TestArtifactOrdering:
    """Deterministic ordering rules on artifact rows."""

    def test_artifacts_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`artifacts` must list rows in ascending ASCII `artifact_id` order."""
        rows = outputs["artifact_plan.json"]["artifacts"]
        assert isinstance(rows, list)
        ids = [str(r["artifact_id"]) for r in rows]
        assert ids == sorted(ids)


class TestArtifactStatusCoverage:
    """Bundled fixtures exercise every documented artifact_status value."""

    def _statuses(self, outputs: dict[str, object]) -> set[str]:
        rows = outputs["artifact_plan.json"]["artifacts"]
        return {str(r["artifact_status"]) for r in rows}

    def test_quarantined_status_present(self, outputs: dict[str, object]) -> None:
        """At least one artifact row carries `quarantined` from a compromise incident."""
        assert "quarantined" in self._statuses(outputs)

    def test_pool_frozen_status_present(self, outputs: dict[str, object]) -> None:
        """At least one artifact row carries `pool_frozen` from a pool freeze."""
        assert "pool_frozen" in self._statuses(outputs)

    def test_deferred_capacity_status_present(self, outputs: dict[str, object]) -> None:
        """At least one artifact row carries `deferred_capacity` after the pool cap."""
        assert "deferred_capacity" in self._statuses(outputs)

    def test_promoted_status_present(self, outputs: dict[str, object]) -> None:
        """At least one artifact row carries `promoted` with a stage assigned today."""
        assert "promoted" in self._statuses(outputs)

    def test_soak_waiting_status_present(self, outputs: dict[str, object]) -> None:
        """At least one artifact row carries `soak_waiting` when only soak blocks promotion."""
        assert "soak_waiting" in self._statuses(outputs)

    def test_idle_status_present(self, outputs: dict[str, object]) -> None:
        """At least one artifact row carries `idle` when promotion cannot proceed."""
        assert "idle" in self._statuses(outputs)


class TestBlockedReasonCoverage:
    """Bundled fixtures surface distinct blocked-promotion reasons."""

    def _reasons(self, outputs: dict[str, object]) -> set[str]:
        found: set[str] = set()
        for row in outputs["artifact_plan.json"]["artifacts"]:
            for bp in row.get("blocked_promotions") or []:
                found.add(str(bp["reason"]))
        return found

    def test_quarantine_reason_present(self, outputs: dict[str, object]) -> None:
        """A compromised artifact cites `quarantine` on its next stage."""
        assert "quarantine" in self._reasons(outputs)

    def test_pool_frozen_reason_present(self, outputs: dict[str, object]) -> None:
        """A frozen-pool artifact cites `pool_frozen` on its next stage."""
        assert "pool_frozen" in self._reasons(outputs)

    def test_capacity_deferred_reason_present(self, outputs: dict[str, object]) -> None:
        """A deferred artifact cites `capacity_deferred` for its would-be promotion."""
        assert "capacity_deferred" in self._reasons(outputs)

    def test_embargoed_reason_present(self, outputs: dict[str, object]) -> None:
        """The embargo incident blocks at least one artifact with `embargoed`."""
        assert "embargoed" in self._reasons(outputs)

    def test_soak_not_met_reason_present(self, outputs: dict[str, object]) -> None:
        """An artifact still soaking cites `soak_not_met` on its next stage."""
        assert "soak_not_met" in self._reasons(outputs)

    def test_missing_dependency_reason_present(self, outputs: dict[str, object]) -> None:
        """An artifact with an unmet dependency cites `missing_dependency`."""
        assert "missing_dependency" in self._reasons(outputs)


class TestVerdictSemantics:
    """Spot-check bundled rows that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], artifact_id: str) -> dict[str, object]:
        for row in outputs["artifact_plan.json"]["artifacts"]:
            if row["artifact_id"] == artifact_id:
                return row
        raise AssertionError(f"missing artifact row {artifact_id}")

    def test_compromise_artifact_quarantined(self, outputs: dict[str, object]) -> None:
        """`a-p2` is quarantined with compromise blocking promotion to prod."""
        row = self._row(outputs, "a-p2")
        assert row["artifact_status"] == "quarantined"
        assert row["promoted_to"] is None
        assert all(bp["reason"] == "quarantine" for bp in row["blocked_promotions"])

    def test_freeze_pool_blocks_west_artifacts(self, outputs: dict[str, object]) -> None:
        """`a-heavy` in frozen `p-west` cites `pool_frozen` on its next stage."""
        row = self._row(outputs, "a-heavy")
        assert row["artifact_status"] == "pool_frozen"
        assert row["pool"] == "p-west"
        assert row["blocked_promotions"]
        assert all(bp["reason"] == "pool_frozen" for bp in row["blocked_promotions"])

    def test_cap_bump_allows_two_east_promotions(self, outputs: dict[str, object]) -> None:
        """`p-east` effective cap 2 promotes `a-base` and `a-p4` on day 15."""
        promoted = {
            r["artifact_id"]
            for r in outputs["artifact_plan.json"]["artifacts"]
            if r["artifact_status"] == "promoted" and r["pool"] == "p-east"
        }
        assert promoted == {"a-base", "a-p4"}

    def test_deferred_artifact_cites_capacity(self, outputs: dict[str, object]) -> None:
        """`a-extra` defers prod promotion with `capacity_deferred` after the east cap fills."""
        row = self._row(outputs, "a-extra")
        assert row["artifact_status"] == "deferred_capacity"
        reasons = {bp["target_stage"]: bp["reason"] for bp in row["blocked_promotions"]}
        assert reasons.get("prod") == "capacity_deferred"

    def test_terminal_artifact_idle_without_blocks(self, outputs: dict[str, object]) -> None:
        """`a-idle` is already at prod and stays idle with an empty block list."""
        row = self._row(outputs, "a-idle")
        assert row["artifact_status"] == "idle"
        assert row["current_stage"] == "prod"
        assert row["promoted_to"] is None
        assert row["blocked_promotions"] == []

    def test_net_missing_dependency_on_prod_target(self, outputs: dict[str, object]) -> None:
        """`a-net` cannot reach prod while `a-base` remains at staging in the input snapshot."""
        row = self._row(outputs, "a-net")
        assert row["artifact_status"] == "idle"
        assert any(
            bp["reason"] == "missing_dependency" and bp["target_stage"] == "prod"
            for bp in row["blocked_promotions"]
        )


class TestPoolLedger:
    """Pool counters align with artifact outcomes."""

    def test_p_east_effective_cap_two(self, outputs: dict[str, object]) -> None:
        """`cap_bump` raises `p-east` effective cap from 1 to 2 for day 15."""
        pool = outputs["pool_ledger.json"]["pools"]["p-east"]
        assert pool["max_promotions_per_day"] == 1
        assert pool["effective_cap"] == 2
        assert pool["artifacts_promoted"] == 2
        assert pool["artifacts_deferred"] == 1

    def test_p_north_promotes_one(self, outputs: dict[str, object]) -> None:
        """`p-north` schedules `a-d1` dev to staging under its base cap."""
        pool = outputs["pool_ledger.json"]["pools"]["p-north"]
        assert pool["effective_cap"] == 3
        assert pool["artifacts_promoted"] == 1
        assert pool["artifacts_deferred"] == 0


class TestIncidentJournal:
    """Journal mirrors accepted, in-window, well-formed incidents."""

    def test_journal_event_ids(self, outputs: dict[str, object]) -> None:
        """Four kept incidents match the bundled acceptance rules."""
        evs = outputs["incident_journal.json"]["applied_events"]
        ids = {str(e["event_id"]) for e in evs}
        assert ids == {"e01", "e02", "e03", "e04"}

    def test_journal_sorted(self, outputs: dict[str, object]) -> None:
        """Applied events appear in ascending (day, event_id) order."""
        evs = outputs["incident_journal.json"]["applied_events"]
        keys = [(int(e["day"]), str(e["event_id"])) for e in evs]
        assert keys == sorted(keys)


class TestSummaryPartition:
    """Summary status counts partition the artifact fleet."""

    def test_status_counts_sum_to_artifacts_total(self, outputs: dict[str, object]) -> None:
        """Quarantine, freeze, defer, promote, soak, and idle counts sum to `artifacts_total`."""
        sm = outputs["summary.json"]
        total = (
            sm["quarantined_artifacts"]
            + sm["frozen_artifacts"]
            + sm["deferred_artifacts"]
            + sm["promoted_artifacts"]
            + sm["soak_waiting_artifacts"]
            + sm["idle_artifacts"]
        )
        assert total == sm["artifacts_total"]

    def test_promotions_today_matches_promoted_rows(self, outputs: dict[str, object]) -> None:
        """`promotions_today` equals the number of artifact rows with non-null `promoted_to`."""
        sm = outputs["summary.json"]
        rows = outputs["artifact_plan.json"]["artifacts"]
        promoted_rows = sum(1 for r in rows if r["promoted_to"] is not None)
        assert sm["promotions_today"] == promoted_rows
        assert sm["promoted_artifacts"] == promoted_rows
