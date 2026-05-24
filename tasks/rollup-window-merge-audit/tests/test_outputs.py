"""Behavioral tests for the rollup window merge audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RWM_DATA_DIR", "/app/rollupmerge"))
AUDIT_DIR = Path(os.environ.get("RWM_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "bucket_rollups.json",
    "compromise_report.json",
    "series_profiles.json",
    "stale_report.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "a8362d51762a76ca0dabdad3c840704f75ce44263a67aeafc4015189f0bd8a45",
    "anchors/t1.txt": "d7c068017aafa4a562fc6aaf6cd249d832f6ec576cf26a65b16d86facbcb5e6b",
    "anchors/t2.txt": "e4bb3829dd31c8a2f2d74cd8ba3929d3fab2f119c9df8b51dfd421767589b3b4",
    "incidents.json": "20e64039bdb625822de0a55efef28b56f6473ae32fd778593101d7f68819c985",
    "ledger/lane.json": "b35b2a7bb954dc861564dac0615766236fc945be8b0eb9d366ea5dab9d9191f7",
    "ledger/tag.json": "b59409b825d10c6c296e31f7e6b7ab80846d717dd6f96f03e5cd75c4e84960d5",
    "overlays/o1.json": "5369a65497a87dd7838dbd40ec3870f72e9f28588dfd9439130d996b0d17797c",
    "overlays/o2.json": "adcd212ac0aee1b6f346b9f102d8c0ad4308ead21c5f71f865ba7dc209cf65fc",
    "policy.json": "3b2dd6f6b1c151bd0651fdaf39e8b41b68eae99007958cda8bab726161d18346",
    "pool_state.json": "26c2a7d56953496bc1cb82f5ef24ec4437e87b8c89819a904c31e09aa650d4af",
    "series/sr-01.json": "01f20054b2ccc155fd708e0305893188d09e76c25751fcd7bddf24ec569f9281",
    "series/sr-02.json": "5f203da360b66a5554aff266d5698f85f3b489815cb9be819ceb0b950634ee83",
    "series/sr-03.json": "460187d53f16c7ce5b5d83c3b9cd67504d872428e6325c38968119fb3d62422f",
    "series/sr-04.json": "754e9bb03b52ecdb16b51c6a0bf62af1712a4263c953ae4985448767e67f3717",
    "series/sr-05.json": "b48d1aadcf9e32a96c9eb6f51477fd7e3b9ce3b3d052813e2247aee271aea7a8",
    "series/sr-06.json": "95794ca8337c629c5399e7c7cdbf8dd70b91f0541e68ae9bf3cce2e9be09c3a5",
    "series/sr-07.json": "9328256c5faf5d5ee0770a1fd60fb101d13353c06c1414d6122381a1a2e05b6d",
    "series/sr-08.json": "1c293c949e01e434ef29ae0182334248657956bd708a4b11756577efb9d9434b",
    "series/sr-09.json": "c02acb91214ade4651d1ce2354b14ca831dce3ef41828bbc8850beb8e2f5b701",
    "series/sr-10.json": "211d63a8baa2288ab79a68c9f3cb765e9c92d804199d63ab553ae44cfea69667",
    "series/sr-11.json": "d4ece3b4b17787a15950e6469f26a44f281de3c612e06f205cf7551ef92cfa06",
    "series/sr-12.json": "61ebd13e52f9278b5f132653e8106a432f415b2f4d8a45a94c56acbfb81f7767",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "bucket_rollups.json": "a7912b8a8bdb34d2b8742a3c22d2044cfd06de2ecb35e14e5c31e979d9aa0e5a",
    "compromise_report.json": "afd97706464f2c92689df60a5f2ad68ba47c841be3d97bda48d8fd73f7fa1e76",
    "series_profiles.json": "fa74f40abb7dbe0fb98ea8cab0c310c8fece8bf3924f6972fd1e6862eb3674b6",
    "stale_report.json": "723a71ddb246ad347c8deaf2019d4405fc06034a826855734a15a3821b3d2979",
    "summary.json": "fb393d8640033a5615ba08306780527d01d3f913033fa09788fd32b7d9e15021",
}


EXPECTED_FIELD_HASHES = {
    "bucket_rollups.buckets": "c37f03f419762526401e2697f549890c83f664be7fd9fc09ca53254bf68fd79e",
    "series_profiles.series": "d3b7024c51f04dbae247e8abe369423588c11a5dea42c991a52ee443dfaad5b5",
    "summary.complete_bucket_starts": "8024ffe17674cbd200405639391f3ffc579bbfc13ac8b393aec0de25ce970cb7",
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
        sp = outputs["series_profiles.json"]
        assert isinstance(sp, dict)
        assert (
            _sha256_bytes(_canonical(sp["series"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["series_profiles.series"]
        )

        br = outputs["bucket_rollups.json"]
        assert isinstance(br, dict)
        assert (
            _sha256_bytes(_canonical(br["buckets"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["bucket_rollups.buckets"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["complete_bucket_starts"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.complete_bucket_starts"]
        )


class TestSeriesOrdering:
    """Deterministic ordering rules on profile rows."""

    def test_series_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`series` must list rows in ascending ASCII `series_id` order."""
        rows = outputs["series_profiles.json"]["series"]
        assert isinstance(rows, list)
        ids = [str(r["series_id"]) for r in rows]
        assert ids == sorted(ids)


class TestProfileSemantics:
    """Spot-check series that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], sid: str) -> dict[str, object]:
        rows = outputs["series_profiles.json"]["series"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("series_id") == sid:
                return r
        raise AssertionError(f"missing series row {sid}")

    def test_compromise_nulls_window_sum(self, outputs: dict[str, object]) -> None:
        """`sr-03` from `src-bad` is quarantined with a null window_sum."""
        r = self._row(outputs, "sr-03")
        assert r["status"] == "quarantined"
        assert r["window_sum"] is None

    def test_stale_watermark_marks_sr02(self, outputs: dict[str, object]) -> None:
        """`sr-02` crosses the grace boundary and is classified stale."""
        r = self._row(outputs, "sr-02")
        assert r["stale_flag"] is True
        assert r["status"] == "stale"

    def test_anchor_hold_on_sr11(self, outputs: dict[str, object]) -> None:
        """`sr-11` keeps rollup buckets but anchor text forces status hold."""
        r = self._row(outputs, "sr-11")
        assert r["status"] == "hold"
        assert r["complete_buckets"] == [10, 17]

    def test_partial_bucket_samples_ignored(self, outputs: dict[str, object]) -> None:
        """`sr-07` only has samples in the trailing partial bucket so buckets stay empty."""
        r = self._row(outputs, "sr-07")
        assert r["complete_buckets"] == []

    def test_min_sample_count_blocks_sr06(self, outputs: dict[str, object]) -> None:
        """`sr-06` has a single in-window sample and never earns a complete bucket."""
        r = self._row(outputs, "sr-06")
        assert r["complete_buckets"] == []


class TestBucketRollups:
    """Bucket contributors respect caps and overlay exclusions."""

    def _bucket(self, outputs: dict[str, object], start: int) -> dict[str, object]:
        buckets = outputs["bucket_rollups.json"]["buckets"]
        assert isinstance(buckets, list)
        for b in buckets:
            if isinstance(b, dict) and b.get("bucket_start") == start:
                return b
        raise AssertionError(f"missing bucket {start}")

    def test_only_complete_bucket_starts_emitted(self, outputs: dict[str, object]) -> None:
        """Rollups cover bucket starts 10 and 17 but skip the partial tail at 24."""
        buckets = outputs["bucket_rollups.json"]["buckets"]
        assert isinstance(buckets, list)
        starts = [int(b["bucket_start"]) for b in buckets]
        assert starts == [10, 17]

    def test_bucket_cap_drops_sr10(self, outputs: dict[str, object]) -> None:
        """Bucket 10 keeps the four lexicographically smallest qualifying series."""
        b = self._bucket(outputs, 10)
        ids = [str(r["series_id"]) for r in b["series"]]
        assert ids == ["sr-02", "sr-04", "sr-08", "sr-09"]

    def test_excluded_source_absent_from_rollups(self, outputs: dict[str, object]) -> None:
        """`src-noisy` series never appear in bucket rollups even when samples qualify."""
        for b in outputs["bucket_rollups.json"]["buckets"]:
            assert isinstance(b, dict)
            for row in b["series"]:
                assert str(row["series_id"]) != "sr-05"


class TestStaleReport:
    """Stale listing omits quarantined rows."""

    def test_stale_report_lists_sr02_only(self, outputs: dict[str, object]) -> None:
        """Only non-quarantined stale series appear in stale_report.json."""
        rows = outputs["stale_report.json"]["series"]
        assert isinstance(rows, list)
        ids = [str(r["series_id"]) for r in rows]
        assert ids == ["sr-02"]


class TestCompromiseReport:
    """Compromise report enumerates quarantined sources and series."""

    def test_compromise_sources_and_series(self, outputs: dict[str, object]) -> None:
        """Accepted compromise pins src-bad and lists sr-03."""
        rep = outputs["compromise_report.json"]
        assert isinstance(rep, dict)
        assert rep["sources"] == ["src-bad"]
        series_ids = [str(r["series_id"]) for r in rep["series"]]
        assert series_ids == ["sr-03"]


class TestSummaryTotals:
    """Summary counters reconcile with profile rows."""

    def test_summary_reconciles_stale_and_quarantine(self, outputs: dict[str, object]) -> None:
        """Summary exposes two stale flags, one quarantined profile, and two complete buckets."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert int(sm["stale_total"]) == 2
        assert int(sm["quarantined_total"]) == 1
        assert int(sm["bucket_count"]) == 2
        assert sm["complete_bucket_starts"] == [10, 17]
