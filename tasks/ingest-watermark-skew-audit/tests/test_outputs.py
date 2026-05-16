"""Behavioral tests for the ingest watermark skew audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("IWSA_DATA_DIR", "/app/ingest_buffers"))
AUDIT_DIR = Path(os.environ.get("IWSA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "partition_ledger.json",
    "source_verdicts.json",
    "dedup_journal.json",
    "incident_journal.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "59d2cfc0e243da508f8b54bc6b93900c19f4bb775e6edaf4a53d38a839a4bb62",
    "ancillary/ci_guard.json": "0b0720f50133910f1da7f15dd221353dc27300dce526ddeaa2d9330e61432500",
    "ancillary/extra_one.json": "dba7fd315545325d9142df1e0953e960747589d983926990fed8bd3b56739a31",
    "ancillary/extra_two.json": "9d9d848ca8681a5a0fb716d431bf7962909bb2236d35f06fc52ef73cd72add0b",
    "ancillary/ingest_tag.json": "55fea6125bc4863a890cd1ae92d446dff11afb040bf52885d7378c79742652ea",
    "ancillary/watermark.txt": "7c4baf157b367aa2af2ab937938214e36348a9210cb8d99820a87944a317a695",
    "batches/b-aur-1.json": "d8e553e0404dc24a7c510d4154e0caca7c9679e9ab04d21441ace429186e04ea",
    "batches/b-aur-2.json": "103c3f11179a631292c4c39c6ff6517c712000da53e417e4027822e97a2b582b",
    "batches/b-bor-a-1.json": "0ba07bab5dd645f51a48912b5eaf59342b2d2b2894231c911e0ef6a8555358fb",
    "batches/b-bor-a-2.json": "b07b05c97803d175e52d154a88b5ad2e4cf91001b50a2f89d85cac5a82d9dbbf",
    "batches/b-bor-b-1.json": "f37bbe0d500e062d4ad63331ea2d2872aaa7bd65839a65cad6713cd078856f0b",
    "batches/b-bor-b-2.json": "74a33595f3635198cf3e103c52b960bae8da1c62e2ea8be1d39332c46ceece4d",
    "batches/b-bor-b-3.json": "ac48f70b713e9f6598169d50d1e0934cd41274a12915bf6b4f18d0985667525c",
    "batches/b-cet-1.json": "08add2d4314dfd5ab12d2bec4ad6829bf871c7fece322251deb709dc631e480c",
    "batches/b-cet-2.json": "b4de786e7aaeb47006b52f19004d13c0cb417929e013599aaf978cac544ed495",
    "batches/b-drf-1.json": "d6ab9455206d4db249ccd566e84b8d5dbb64631404fcfa0a5043dd2c17e5ae5e",
    "batches/b-drf-2.json": "bb8c7c6b4140e3d066e35820877e7af97d17e700611e63932d9572f7d8cf0260",
    "batches/b-flx-1.json": "91d0e6c77f425940bf1fb876eac42f99db5861ff56206601e13e9f729f4a76f6",
    "batches/b-old.json": "1bcaa2e88a54d1f34a7d1eb6b157f0764de4a275692ffe84e317d62c35f4bde6",
    "incident_log.json": "c2a6561b616bc59fbd7ee6513c2dbc1a8f498576382a15c36e3f5c956295d566",
    "partitions/part-aurora-a.json": "8383bb34350adb8b1876b8b990bd8a221799539dbae54a00adead654f844cdf9",
    "partitions/part-boreal-a.json": "3aeadb87110d8b6aa9cc73f134f25388c1fb30828e886fa52f0f935e08fefda3",
    "partitions/part-boreal-b.json": "5a81a8c3003b4872d67bc85c78f1128751a7fbeb3a78809cf6a1b68127dec75b",
    "partitions/part-cetus-a.json": "177f538d2d8d6a211f1de2df8e06f8f1b9a722deeaf5f30bf2b9c5cd25ca32e1",
    "partitions/part-drift-a.json": "9876499cd5894ef4f57ba577219284c44f964a85688b3515a806a70fbbdb6240",
    "partitions/part-flux-a.json": "101d7e48ec7bef24ece9230a560a9f49435c88d7e087279dba39cbe5e0f88f36",
    "policy.json": "d021bec371c392777e68a634ac620d906e7d1b5e0709e0abdce092a9945f2783",
    "pool_state.json": "d08fc110d88d5fd10ee292e6075d32f5944d4f2ea4b07fd132824a072b52304a",
    "sources/src-aurora.json": "f2df743a3232c80dfa2774e48ea0c01697c481e68c32d0fcfed804d67d20a921",
    "sources/src-boreal.json": "0a861a54f529065fffb251f86f87e55adfd864aa1452c133f0bfd89d2f9e3b04",
    "sources/src-cetus.json": "66f4c2d83fdaabd6fdfe4c872c2b0ba8700f95e17dd4cdd23312e016eb6b4b3e",
    "sources/src-drift.json": "e6bbf45ed95b169861d3ec53a61b2a8c629a5146c2626129cc4a2286dac5f4c2",
    "sources/src-edge.json": "5d1051750b7527440800d595fbfa5069350f7790c470d071ce79e1a1f9514b15",
    "sources/src-flux.json": "36b439d68153962feac64d3f89fc321d447428dd7c88628e2d92673242e99c50",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "dedup_journal.json": "32f2c0afd26b73c1989672a993ef6b4fecb4b0cfe5a31b3a882757ccdfce159a",
    "incident_journal.json": "8da10b550f5c7bc9a803d9b5b4a2990a765dd48f0829dadace7bd54a18e70cc7",
    "partition_ledger.json": "791416869d6022f5e5e8f2d1fa12f96d6012c68314373ebe51326b60fbbc474a",
    "source_verdicts.json": "939f23add4312a6d1383d8a11e35f9ee9597e3935e571aa476677076aea0e23a",
    "summary.json": "71754dd718e5a3a4aaa1b48dedb6ced5c37c70f5279fccb787a78fe361589012",
}

EXPECTED_FIELD_HASHES = {
    "dedup_journal.supersessions": "88fe0d9b26fd67a0b2771148721f1216a141d7000861189f39f319db39c11163",
    "incident_journal.applied_events": "8f7e302ae775cb7933fd9d53dbf6bc38e0dab35030aa2d9b9366eb141c725000",
    "partition_ledger.partitions": "6270f30be81b3f2de75f0aab941c0f71d5eccf423ab318ffd01640517e1b8387",
    "source_verdicts.sources": "d085fa268f4090208128c80646702a732961fc289429165dffdd17d98a0dc3b9",
    "summary.applied_incident_events": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.ignored_incident_events": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.partitions_total": "e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683",
    "summary.partitions_with_skew_exceeded": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.quarantined_sources": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.sources_total": "e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683",
    "summary.total_accepted": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "summary.total_duplicate_superseded": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.total_rejected_quarantine": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.total_rejected_stale": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
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
        pl = outputs["partition_ledger.json"]
        assert isinstance(pl, dict)
        assert (
            _sha256_bytes(_canonical(pl["partitions"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["partition_ledger.partitions"]
        )

        sv = outputs["source_verdicts.json"]
        assert isinstance(sv, dict)
        assert (
            _sha256_bytes(_canonical(sv["sources"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["source_verdicts.sources"]
        )

        dj = outputs["dedup_journal.json"]
        assert isinstance(dj, dict)
        assert (
            _sha256_bytes(_canonical(dj["supersessions"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["dedup_journal.supersessions"]
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
            "ignored_incident_events",
            "partitions_total",
            "partitions_with_skew_exceeded",
            "quarantined_sources",
            "sources_total",
            "total_accepted",
            "total_duplicate_superseded",
            "total_rejected_quarantine",
            "total_rejected_stale",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestPartitionOrdering:
    """Verify deterministic ordering rules on partition rows."""

    def test_partition_rows_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`partitions` must list rows in ascending ASCII `partition_id` order."""
        rows = outputs["partition_ledger.json"]["partitions"]
        assert isinstance(rows, list)
        ids = [str(r["partition_id"]) for r in rows]
        assert ids == sorted(ids)


class TestPartitionSemantics:
    """Spot-check bundled partitions that exercise skew, grace, and dedup paths."""

    def _row(self, outputs: dict[str, object], pid: str) -> dict[str, object]:
        rows = outputs["partition_ledger.json"]["partitions"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("partition_id") == pid:
                return r
        raise AssertionError(f"missing partition row {pid}")

    def test_gold_stale_rejects_before_dedup_winner(
        self, outputs: dict[str, object]
    ) -> None:
        """`part-aurora-a` drops a stale gold event and keeps the later dedup winner."""
        r = self._row(outputs, "part-aurora-a")
        assert r["accepted_count"] == 1
        assert r["rejected_stale_count"] == 1
        assert r["duplicate_superseded_count"] == 1
        assert r["watermark_day"] == 99
        assert r["reasons"] == ["dedup_superseded", "stale_events_present"]

    def test_grace_partition_accepts_older_event_day(
        self, outputs: dict[str, object]
    ) -> None:
        """`part-boreal-b` grace lets day 92 land while an earlier ingest without grace stays stale."""
        r = self._row(outputs, "part-boreal-b")
        assert r["accepted_count"] == 2
        assert r["rejected_stale_count"] == 1
        assert r["watermark_day"] == 96

    def test_skew_penalty_lowers_watermark(self, outputs: dict[str, object]) -> None:
        """`part-cetus-a` spans more than the skew guard and applies the penalty to the watermark."""
        r = self._row(outputs, "part-cetus-a")
        assert r["skew_exceeded"] is True
        assert r["watermark_day"] == 98
        assert "skew_exceeded" in r["reasons"]

    def test_compromise_partition_quarantine_touch(
        self, outputs: dict[str, object]
    ) -> None:
        """`part-drift-a` records a quarantined ingest while keeping the pre-compromise watermark."""
        r = self._row(outputs, "part-drift-a")
        assert r["rejected_quarantine_count"] == 1
        assert r["accepted_count"] == 1
        assert r["watermark_day"] == 98
        assert r["reasons"] == ["source_quarantine"]


class TestSourceVerdicts:
    """Source-level disposition and accepted-event totals."""

    def _src(self, outputs: dict[str, object], sid: str) -> dict[str, object]:
        rows = outputs["source_verdicts.json"]["sources"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("source_id") == sid:
                return r
        raise AssertionError(f"missing source row {sid}")

    def test_quarantined_source_compromise(self, outputs: dict[str, object]) -> None:
        """`src-drift` is quarantined with the compromise reason after the day-100 incident."""
        r = self._src(outputs, "src-drift")
        assert r["disposition"] == "quarantined"
        assert r["reasons"] == ["source_compromise"]

    def test_active_source_with_zero_accepted(self, outputs: dict[str, object]) -> None:
        """`src-edge` stays active even with no ingest batches in the window."""
        r = self._src(outputs, "src-edge")
        assert r["disposition"] == "active"
        assert r["accepted_events"] == 0
        assert r["reasons"] == []


class TestDedupJournal:
    """Supersession rows follow the spec sort order and bundled keys."""

    def test_supersessions_sorted(self, outputs: dict[str, object]) -> None:
        """`supersessions` is sorted by (source_id, idempotency_key, superseded_event_id)."""
        rows = outputs["dedup_journal.json"]["supersessions"]
        assert isinstance(rows, list)
        keys = [
            (
                str(r["source_id"]),
                str(r["idempotency_key"]),
                str(r["superseded_event_id"]),
            )
            for r in rows
        ]
        assert keys == sorted(keys)

    def test_bundled_supersession_ids(self, outputs: dict[str, object]) -> None:
        """The fixture emits three dedup supersessions across aurora, boreal, and flux."""
        rows = outputs["dedup_journal.json"]["supersessions"]
        kept = {str(r["kept_event_id"]) for r in rows}
        assert kept == {"e-a3", "e-bb3", "e-f2"}


class TestIncidentJournal:
    """Journal mirrors accepted, in-window, well-formed incidents."""

    def test_journal_sorted_by_day_then_id(self, outputs: dict[str, object]) -> None:
        """Applied events appear in ascending (day, event_id) order."""
        evs = outputs["incident_journal.json"]["applied_events"]
        assert isinstance(evs, list)
        keys = [(int(e["day"]), str(e["event_id"])) for e in evs]
        assert keys == sorted(keys)

    def test_journal_includes_expected_event_ids(self, outputs: dict[str, object]) -> None:
        """The bundled log applies the four well-formed incidents through day 100."""
        evs = outputs["incident_journal.json"]["applied_events"]
        ids = {str(e["event_id"]) for e in evs}
        assert ids == {"i01", "i02", "i03", "i04"}
