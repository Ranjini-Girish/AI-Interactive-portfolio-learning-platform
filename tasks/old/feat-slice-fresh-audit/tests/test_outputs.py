"""Behavioral tests for the feature slice freshness audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("FSF_DATA_DIR", "/app/featstore"))
AUDIT_DIR = Path(os.environ.get("FSF_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "capacity_summary.json",
    "cluster_rollups.json",
    "lineage_events.json",
    "slice_profiles.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "80fdab1903e42a0f097650ef425862d9438e971037da012ebeb0d4846d3ef6fd",
    "anchors/a1.txt": "0a955c03416aeeb149e7acfbadbf076e63bff17362d43a8b8eb6c12283f83578",
    "anchors/a2.txt": "0c182c7fd9d1b68404889c2980a4e8f3a0fb2530ff9bb2313a98cc4aa6be9b34",
    "anchors/a3.txt": "2516bdd38eb68cf45b9a10ff30b2233f74428d72511455b02859c5fdcad8e9e6",
    "clusters/c-east.json": "e95fc74a164a273f979f71f8f0be43264b45d48f39b66159f7ffcb4f1f2e98c6",
    "clusters/c-north.json": "fbea869cf5dc98d3248a3130ed10f376cd28677fd3c7e0051f104df4e4c59104",
    "clusters/c-west.json": "abeae52fca2a46c9aa39fcf88c1659ff1019376d372fd7720fce009c89f9924a",
    "incidents.json": "189d8ec0ac12844ed580e8a28cada0567ffabf8cf2a0168ae93014f4d8572e3a",
    "policy.json": "d391cfb70d5670f40a0294dabd2a583f5ad233ef2a2e5c2c79a3dfcc1b3e2e67",
    "pool_state.json": "cec950bad6f7a7af6e9ef7636bac2f695a2df99f770a755ef07492e69198db0b",
    "registry/r01.json": "ff2f6644661ee3f5b7d2901d0e16b0b5b7bb6d2b293000d083e0fcc2ae3a9517",
    "registry/r02.json": "e5f83ed0a2128eda7e84d8acf8f699b844d66887c8cf76c8651a0a5d64fa9b42",
    "slices/s-01.json": "28f407acd9d353dde250b4dee0f0fce0877a1a393975d1d7f44ad58922697e95",
    "slices/s-02.json": "976a6bd639f9c995fd7c9a512529ffa74a101e9077e6c943966d493763144299",
    "slices/s-03.json": "836766ef739a2ce2027fb09b27899b57bf6c68cafbb216e60f09868f31d43fd3",
    "slices/s-04.json": "86c6d11a10669a0fa351f46e6a4c970229c35008214b67b58654440e251addd8",
    "slices/s-05.json": "a6813f0c752752b91392e0f226382b8d01a8477cc8974cddf1c4c613704c04fe",
    "slices/s-06.json": "e1a58662278d2879958e9bf34ad977e4cef0e2ef48628cc108f47a1e1bfde8f9",
    "slices/s-07.json": "f253dddeeac24c8c8d942ce9753cb0bd931b911c829db39ec11e2f70ba9a2827",
    "slices/s-08.json": "d8051390bcd30acb23abcf9ab08ad676ad55af9345dc9c4eccbdd1f1a9f199ab",
    "slices/s-09.json": "28c994ac5897ce06cbd4f26b295fba5c9322b68efb07ffe38354c1502b07759a",
    "slices/s-10.json": "82dda7fb3aef6ce6f4094309478250432b199382ae1f6190922b36a320d3ae12",
    "slices/s-11.json": "8edc6f2e7b71e33ec5a274408fc9c6d2ce3ffc90a4b50ecf111af25c85c9ff1b",
    "slices/s-12.json": "d7c50d3be2080b509097dbbeb77a71568b5c2a23b771a49359af1da4c0e971c8",
    "slices/s-13.json": "c9ffbe8f2fc106137fca07e36a15758264b3731bb0de23f61b083cc624235f9a",
    "slices/s-14.json": "6aa05bbd0bc6006622db216af1967d7482a56e61f055d4d07849409da94b5500",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "capacity_summary.json": "e3cdbf2d0f2867ec2552af99aba00a84552a77f3ecfa817aed94e98eaed0326e",
    "cluster_rollups.json": "3da5bd753688597d48e29e1a310bd4ebb4f495d3f0e705718c19abc6bb4c603a",
    "lineage_events.json": "b9c8a79fa8f1500b5a9d21c7c767b5397068e4bcefe9fcc72230392b98732f71",
    "slice_profiles.json": "4d686a9a0f8c950de17fd715e341326f816eaef1d8834bee5c38b51815135c16",
    "summary.json": "3e45be2102a72406e48337165c010a60e10dede42b8f08379ee6a8fc42dc70bf",
}

EXPECTED_FIELD_HASHES = {
    "slice_profiles.slices": "a82f32b0b2df0a1b5e375b9ed95b24cde871a77cfcc2bec8cc51c79ad3280380",
    "cluster_rollups.clusters": "14d5d4acd9043ecf96060707c4707069cb419ea3378916e6864b7f602f509733",
    "summary.clusters": "ab5c628dcc88f11792f83e595b13424f6a1a4a7401ac6b00c41149360cab4e11",
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
        sp = outputs["slice_profiles.json"]
        assert isinstance(sp, dict)
        assert (
            _sha256_bytes(_canonical(sp["slices"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["slice_profiles.slices"]
        )

        cr = outputs["cluster_rollups.json"]
        assert isinstance(cr, dict)
        assert (
            _sha256_bytes(_canonical(cr["clusters"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["cluster_rollups.clusters"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["clusters"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.clusters"]
        )


class TestSliceOrdering:
    """Deterministic ordering rules on slice rows."""

    def test_slices_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`slices` must list rows in ascending ASCII `slice_id` order."""
        rows = outputs["slice_profiles.json"]["slices"]
        assert isinstance(rows, list)
        ids = [str(r["slice_id"]) for r in rows]
        assert ids == sorted(ids)


class TestFreshnessSemantics:
    """Spot-check slices that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], sid: str) -> dict[str, object]:
        rows = outputs["slice_profiles.json"]["slices"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("slice_id") == sid:
                return r
        raise AssertionError(f"missing slice row {sid}")

    def test_capacity_floor_caps_declared_gold(self, outputs: dict[str, object]) -> None:
        """`s-02` declares gold but row count only satisfies the bronze floor."""
        r = self._row(outputs, "s-02")
        assert r["effective_tier"] == "bronze"
        assert r["freshness"] == "fresh"

    def test_stale_gold_slice(self, outputs: dict[str, object]) -> None:
        """`s-03` exceeds the gold staleness budget."""
        r = self._row(outputs, "s-03")
        assert r["freshness"] == "stale"

    def test_force_tier_incident_overrides_capacity(self, outputs: dict[str, object]) -> None:
        """`s-07` keeps gold row capacity but the force_tier note sets bronze."""
        r = self._row(outputs, "s-07")
        assert r["effective_tier"] == "bronze"
        assert r["freshness"] == "fresh"

    def test_cluster_compromise_quarantines_west(self, outputs: dict[str, object]) -> None:
        """`s-08` and `s-09` in `c-west` become quarantined with zero effective rows."""
        for sid in ("s-08", "s-09"):
            r = self._row(outputs, sid)
            assert r["freshness"] == "quarantined"
            assert r["effective_row_count"] == 0

    def test_underfilled_capacity_tier(self, outputs: dict[str, object]) -> None:
        """`s-10` falls below every row floor and is labeled underfilled."""
        r = self._row(outputs, "s-10")
        assert r["effective_tier"] == "underfilled"
        assert r["freshness"] == "fresh"

    def test_lineage_lag_from_stale_parent(self, outputs: dict[str, object]) -> None:
        """`s-06` inherits lineage_lag because parent `s-03` is stale."""
        r = self._row(outputs, "s-06")
        assert r["freshness"] == "lineage_lag"

    def test_lineage_lag_from_refresh_gap(self, outputs: dict[str, object]) -> None:
        """`s-14` lags parent `s-10` because its refresh day is before the grace window."""
        r = self._row(outputs, "s-14")
        assert r["freshness"] == "lineage_lag"


class TestLineageJournal:
    """Lineage events list stays sorted and aligned with lineage_lag slices."""

    def test_lineage_events_sorted(self, outputs: dict[str, object]) -> None:
        """Lineage events list by slice id ascending."""
        evs = outputs["lineage_events.json"]["events"]
        assert isinstance(evs, list)
        ids = [str(e["slice_id"]) for e in evs]
        assert ids == sorted(ids)

    def test_expected_lineage_lag_slices(self, outputs: dict[str, object]) -> None:
        """The bundled dataset emits lineage events for `s-06` and `s-14`."""
        evs = outputs["lineage_events.json"]["events"]
        ids = {str(e["slice_id"]) for e in evs}
        assert ids == {"s-06", "s-14"}


class TestRollups:
    """Cluster rollups reflect final freshness labels."""

    def test_c_west_quarantined_counts(self, outputs: dict[str, object]) -> None:
        """`c-west` records two quarantined slices and no fresh rows."""
        clusters = outputs["cluster_rollups.json"]["clusters"]
        assert isinstance(clusters, dict)
        west = clusters["c-west"]
        assert west["quarantined"] == 2
        assert west["fresh"] == 0

    def test_summary_stale_total(self, outputs: dict[str, object]) -> None:
        """Summary stale_total matches slices labeled stale in profiles."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert sm["stale_total"] == 3
        assert sm["quarantined_total"] == 2


class TestCapacitySummary:
    """Capacity summary tracks underfilled ids and tier counts."""

    def test_underfilled_slice_list(self, outputs: dict[str, object]) -> None:
        """Only `s-10` is listed as underfilled by capacity."""
        cap = outputs["capacity_summary.json"]
        assert isinstance(cap, dict)
        assert cap["underfilled_slices"] == ["s-10"]
