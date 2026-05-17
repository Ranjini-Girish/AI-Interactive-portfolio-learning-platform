"""Behavioral tests for the A/B arm allocation audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("AAA_DATA_DIR", "/app/abarmalloc"))
AUDIT_DIR = Path(os.environ.get("AAA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "arm_eligibility.json",
    "compromise_report.json",
    "experiment_profiles.json",
    "summary.json",
    "tier_rollups.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "d650566e3f23ef9a3a73c74f9364fc0d84fe5b2ca49a460f4ba10103f469ba06",
    "anchors/a1.txt": "ef4948097d715a560cd08eb4697a7b050b52eb62762fd5f343e1518a15c43617",
    "anchors/a2.txt": "dad92772257875e368ae97258eed355b5063151267c243e94cd26dac6ff22780",
    "experiments/exp-01.json": "10de6fefe5943dc7edf5d58741e6baa16025b82a320051e5930e4eec9a23a807",
    "experiments/exp-02.json": "79956a5bfa2ba530026451e5de11a3c8f2aac76094c02ce9eb6cc5c89bc9eaeb",
    "experiments/exp-03.json": "d8121ccda5b32c099b297e839bf411ecc68e5cc4b5c20f9e554f5895cb5e2cb9",
    "experiments/exp-04.json": "dfc4dd5e0fb615491b002608390d78c38a539621f3c51342d88be0892bbdcbfa",
    "experiments/exp-05.json": "6d8aaccd110567204b23021b6cb9551695ff746147e999b96134a4d991ee4c50",
    "experiments/exp-06.json": "f443475d3e6b855d442391f560f1f3be7189afb84dba873c26a91bfadae07c7c",
    "experiments/exp-07.json": "451af11839069a2cf69857746be7271fbf7d8c74691bc124c3c2f0518a8df8bc",
    "experiments/exp-08.json": "6ed2f852aea131d0a668d15a08affb938ab35163b2cf8338e2b3c54477c082f1",
    "experiments/exp-09.json": "a9dd468b99b19be70916797040d0d4160a55ce0c62c4592c54241c39e7663246",
    "experiments/exp-10.json": "1abedfb5ef98bde2c23890036eca34976a1cb54efe2dbf1ed20bc18c68d76508",
    "experiments/exp-11.json": "21315831ce76daf7001f4da35191f021f79e1f1e2f8766ca3fef0e8e73164ef1",
    "experiments/exp-12.json": "869e3772cd391e180a26bcb01912a94aa71fd0f95326eb7d9893e56a9d7dc1d8",
    "incidents.json": "65b5ba88e79adb706f7db15682fb6031254d99332829c27ee7ccb7056a9dd0c4",
    "ledger/lane.json": "5a104c658b57d009cee6d81743fc4400d7122da6c078d7a566b3d862a043e21f",
    "ledger/tag.json": "fcdc229a8ff159b9b2513797046dc65b714042b41e4b03fb2e1ecdc59fc45086",
    "overlays/o1.json": "80ab9074ef499d31412c9b2acb951a42296426dab0116032bb4d14dbcbd23038",
    "overlays/o2.json": "bb71987c45dfb29f3f33e5ee2d28b5dccb855af12649a8876a92d02d063eee48",
    "policy.json": "77554948efc4618e5dad11a27977378f9778122dfd2955c9022dcd0383ce5560",
    "pool_state.json": "2ea836d02c804d27335cf1650f8c4c9edc65fa639849f042f6bdbe547183d092",
    "tiers/bronze.json": "da9a419c2d68d612664d4e41780c192acb4964bc66c190f315aeea389f5559e4",
    "tiers/gold.json": "97619bbbd569b990591cc4c1b8cb92c63d5ee84ee726c1c7382a62254ac3d531",
    "tiers/silver.json": "372bb7bda09058c3ccc4376e098a73c17e34968c46e4876cb5849d2a9e934227",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "arm_eligibility.json": "f5f672a406b883412ac80426bf3585d455d2a3187aee3cd4cd1da44b1bd5d647",
    "compromise_report.json": "5f2629b4af51ee228fd2fc99a6227792379804a43a5c9439162754c4289cc66e",
    "experiment_profiles.json": "cfebb8f565621b4fd305185c70f5b1d3696d3ce98bfcf790c82f5774be93b91e",
    "summary.json": "be560b32e446f57cf4a2dd3a263d8bf6b2b8408bdce3eb13d282b704c751b3c3",
    "tier_rollups.json": "49c752ff56bf11d7063a75b89ec6c877b87cf04a15096830fd9ed3628a3b90b4",
}


EXPECTED_FIELD_HASHES = {
    "experiment_profiles.experiments": "e001b691f7a878aae8761948f746ea9ae7b671989eff8d4b002130ca52f1a8a5",
    "summary.quarantined_total": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "tier_rollups.tiers": "f04b1b263fccf0308b5a996c396397421360ee75f4fb690d12d607cb4ad0de2f",
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
        ep = outputs["experiment_profiles.json"]
        assert isinstance(ep, dict)
        assert (
            _sha256_bytes(_canonical(ep["experiments"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["experiment_profiles.experiments"]
        )

        tr = outputs["tier_rollups.json"]
        assert isinstance(tr, dict)
        assert (
            _sha256_bytes(_canonical(tr["tiers"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["tier_rollups.tiers"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["quarantined_total"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.quarantined_total"]
        )


class TestExperimentOrdering:
    """Deterministic ordering rules on profile rows."""

    def test_experiments_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`experiments` must list rows in ascending ASCII `experiment_id` order."""
        rows = outputs["experiment_profiles.json"]["experiments"]
        assert isinstance(rows, list)
        ids = [str(r["experiment_id"]) for r in rows]
        assert ids == sorted(ids)


class TestProfileSemantics:
    """Spot-check experiments that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], eid: str) -> dict[str, object]:
        rows = outputs["experiment_profiles.json"]["experiments"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("experiment_id") == eid:
                return r
        raise AssertionError(f"missing experiment row {eid}")

    def _arm(self, row: dict[str, object], arm_id: str) -> dict[str, object]:
        arms = row["arms"]
        assert isinstance(arms, list)
        for a in arms:
            if isinstance(a, dict) and a.get("arm_id") == arm_id:
                return a
        raise AssertionError(f"missing arm {arm_id}")

    def test_parent_holdout_inheritance_exp03(self, outputs: dict[str, object]) -> None:
        """`exp-03` inherits effective_holdout 10 from parent `exp-02`."""
        r = self._row(outputs, "exp-03")
        assert r["effective_holdout"] == 10

    def test_compromise_nulls_allocations_exp04(self, outputs: dict[str, object]) -> None:
        """`exp-04` is quarantined with null eligible_total and allocation_pct."""
        r = self._row(outputs, "exp-04")
        assert r["status"] == "quarantined"
        assert r["eligible_total"] is None
        assert self._arm(r, "arm-z")["allocation_pct"] is None

    def test_freeze_rollout_exp05(self, outputs: dict[str, object]) -> None:
        """`exp-05` is frozen with null allocations."""
        r = self._row(outputs, "exp-05")
        assert r["status"] == "frozen"
        assert r["eligible_total"] is None

    def test_anchor_pause_hold_exp06(self, outputs: dict[str, object]) -> None:
        """`exp-06` keeps hold status despite stale_flag when anchor forces pause."""
        r = self._row(outputs, "exp-06")
        assert r["status"] == "hold"
        assert r["stale_flag"] is True
        assert r["eligible_total"] == 60

    def test_underpowered_exp08(self, outputs: dict[str, object]) -> None:
        """`exp-08` has a single qualifying observation and is underpowered."""
        r = self._row(outputs, "exp-08")
        assert r["status"] == "underpowered"
        assert self._arm(r, "arm-u")["arm_status"] == "underpowered"

    def test_global_exclude_arm_b_exp09(self, outputs: dict[str, object]) -> None:
        """Overlay exclude_arms marks arm-b excluded on `exp-09`."""
        r = self._row(outputs, "exp-09")
        assert self._arm(r, "arm-b")["arm_status"] == "excluded"

    def test_ok_status_exp10(self, outputs: dict[str, object]) -> None:
        """`exp-10` is within the grace window and classified ok."""
        r = self._row(outputs, "exp-10")
        assert r["status"] == "ok"
        assert r["stale_flag"] is False
        assert r["eligible_total"] == 50

    def test_metric_floor_underpowered_exp11(self, outputs: dict[str, object]) -> None:
        """`exp-11` counts only one observation above metric_floor."""
        r = self._row(outputs, "exp-11")
        assert r["status"] == "underpowered"
        assert self._arm(r, "arm-m")["observation_count"] == 1

    def test_out_of_window_observations_exp12(self, outputs: dict[str, object]) -> None:
        """`exp-12` observations fall outside the window and yield underpowered."""
        r = self._row(outputs, "exp-12")
        assert self._arm(r, "arm-o")["observation_count"] == 0
        assert r["status"] == "underpowered"


class TestTierRollups:
    """Tier rollup rows respect caps and status filters."""

    def _tier(self, outputs: dict[str, object], tier_id: str) -> dict[str, object]:
        tiers = outputs["tier_rollups.json"]["tiers"]
        assert isinstance(tiers, list)
        for t in tiers:
            if isinstance(t, dict) and t.get("tier_id") == tier_id:
                return t
        raise AssertionError(f"missing tier {tier_id}")

    def test_gold_tier_lists_exp10(self, outputs: dict[str, object]) -> None:
        """Gold rollup includes only `exp-10` with eligible_total 50."""
        t = self._tier(outputs, "gold")
        rows = t["experiments"]
        assert isinstance(rows, list)
        assert [str(r["experiment_id"]) for r in rows] == ["exp-10"]
        assert int(rows[0]["eligible_total"]) == 50

    def test_bronze_tier_cap_keeps_exp01(self, outputs: dict[str, object]) -> None:
        """Bronze exposure_cap retains `exp-01` and zeros later bronze experiments."""
        t = self._tier(outputs, "bronze")
        rows = t["experiments"]
        assert isinstance(rows, list)
        assert [str(r["experiment_id"]) for r in rows] == ["exp-01"]


class TestArmEligibility:
    """Eligible arm listing matches profile rows."""

    def test_eligible_arms_sorted(self, outputs: dict[str, object]) -> None:
        """arm_eligibility.json lists eligible arms in experiment_id then arm_id order."""
        rows = outputs["arm_eligibility.json"]["arms"]
        assert isinstance(rows, list)
        keys = [(str(r["experiment_id"]), str(r["arm_id"])) for r in rows]
        assert keys == sorted(keys)


class TestCompromiseReport:
    """Compromise report enumerates quarantined experiments."""

    def test_compromise_lists_exp04(self, outputs: dict[str, object]) -> None:
        """Accepted experiment_compromise pins exp-04."""
        rep = outputs["compromise_report.json"]
        assert isinstance(rep, dict)
        assert rep["experiment_ids"] == ["exp-04"]
        exp_ids = [str(r["experiment_id"]) for r in rep["experiments"]]
        assert exp_ids == ["exp-04"]


class TestSummaryTotals:
    """Summary counters reconcile with profile statuses."""

    def test_summary_status_counts(self, outputs: dict[str, object]) -> None:
        """Summary totals match the bundled profile status labels."""
        sm = outputs["summary.json"]
        profiles = outputs["experiment_profiles.json"]["experiments"]
        assert isinstance(sm, dict)
        assert isinstance(profiles, list)
        assert int(sm["experiment_total"]) == len(profiles)
        status_counts: dict[str, int] = {}
        for row in profiles:
            assert isinstance(row, dict)
            status = str(row["status"])
            status_counts[status] = status_counts.get(status, 0) + 1
        assert int(sm["quarantined_total"]) == status_counts.get("quarantined", 0)
        assert int(sm["frozen_total"]) == status_counts.get("frozen", 0)
        assert int(sm["hold_total"]) == status_counts.get("hold", 0)
        assert int(sm["stale_total"]) == status_counts.get("stale", 0)
        assert int(sm["underpowered_total"]) == status_counts.get("underpowered", 0)

    def test_stale_status_present_in_dataset(self, outputs: dict[str, object]) -> None:
        """At least one profile is classified stale in the bundled dataset."""
        profiles = outputs["experiment_profiles.json"]["experiments"]
        assert any(str(r["status"]) == "stale" for r in profiles)
