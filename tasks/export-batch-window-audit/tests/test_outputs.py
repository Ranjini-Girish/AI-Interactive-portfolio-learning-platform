"""Behavioral tests for the export-batch-window-audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("EBWA_DATA_DIR", "/app/export_batches"))
AUDIT_DIR = Path(os.environ.get("EBWA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "source_plan.json",
    "warehouse_ledger.json",
    "batch_matrix.json",
    "incident_journal.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "d73e3fb75e911c7a9099379c374bb4fa22a060ed469d605912130731657a4294",
    "ancillary/channel_tag.json": "605a72b76e44bfe91f45c52cd61a4ad660b6837aee55c48b70db3465217f4800",
    "ancillary/ci_guard.json": "5a0d912b82837f38d2ade81fd312a8e5c2fb0ef47010d33ed2e15ed844d1cd1d",
    "ancillary/watermark.txt": "97a9429e6ab4ee389687ba491a90a08318c2df7ab1633bd6d24e4d8778c069ab",
    "batches/b-app.json": "54d07ae77a273491360688a61b67e89e105fda3a25a15cee5d68d4cca3b96526",
    "batches/b-base.json": "b335506a7b8b42430d20bd970cc679e23bffe03b83c46f28c04e3ffb6193fef1",
    "batches/b-db.json": "ca12803397ffd8105b02fb1e843394429626abee6083401ab62f578819d38106",
    "batches/b-heavy.json": "2bf4b016b74741573360aee651139e906de0ea5c5880ee2c27c457074b473c94",
    "batches/b-mon.json": "1b7c65b7367223587f8f0e7c9d2271da8bb8b0caa9de8c6af4c86fc34197f77f",
    "batches/b-net.json": "19b689cd9f2339376c42fd52d6b4ceea3eaef21cc467a0c8c6c13c593e32daf0",
    "incident_log.json": "2c5f2ce3802fffe21abcfd42a885df46ba1d3ba8f98a669ebe938e12f8fca44b",
    "policy.json": "86f28b4c3f25adaaf77a2aee0eae3b89fc2336cdc09a31235fa42ee21aa75e5a",
    "pool_state.json": "78c533edbd96f582aa124618c50b9a5d74899b9950f7d4216ebf06190e051031",
    "sources/h-d1.json": "9d6cf104146ab34381b8710b0ea59aa5a45fd7ec74b5996a508609acf030140d",
    "sources/h-d2.json": "eb8349695ee6616da98b994a131c70087eea96e66cd761e9d7d6ac63798a2e80",
    "sources/h-idle.json": "655c088ea1f5ceb7990391a349a394da19e2f5f2563f506e0d4b838326a33e32",
    "sources/h-n1.json": "f66c39cf75b20a26fb6869f55d600b080e7e9b0f9ee9211f0257db891fade747",
    "sources/h-out.json": "4ec8d2197067da106194a69139e45816cb31835d65357db3c72f5d10c181bfd8",
    "sources/h-p1.json": "90a5dbd9653539b4b14c44ea1a607fbd137bce7b3ee046b6fdfd88c07a23508c",
    "sources/h-p2.json": "ae1edd9328d0bcb7d3f26acc6419281de1fc9efc6e75fd6c3770c1ae66efecb9",
    "sources/h-p3.json": "d3b04cb3ba7b88064329613c9d3aff553ca97e6f7def62e38bedba4821a3e202",
    "sources/h-p4.json": "baec127b62e03f23e1482015a2f591a55fa1e00b9518ea41d60a28b5f77497e6",
    "sources/h-s1.json": "1f23ca9ec998a6eab1d15a8a4dadf579b1648f551fe868783b590509b068acc9",
    "sources/h-s2.json": "553c3edc0886f1788d44e8553e68cbd76557291a1bff76760c991f16eee16643",
    "sources/h-s3.json": "ed2f16e57eb019bc919850884cae36bb69f671cad4cca970156f52b834a66b5b",
    "warehouses/r-east.json": "0a2f07e7a2a2e9b68d3c8f0b5ba8a9c3920f1b5a74c4302b26a5390c47c985d6",
    "warehouses/r-north.json": "290ecdc9417e8714821b1a64d140c221f5a863591655e28e2091a7c250f8950e",
    "warehouses/r-west.json": "355424aa129847f0165b5dfe774d243b803117585b66a0272a1f140ac704514d",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "source_plan.json": "d395381f08c747c36cebc07dbc890e4fd9337751250f7f9dadc70b6dae664323",
    "warehouse_ledger.json": "0f0237dc5a7f147459ba6dcf86e16c920edc390a280259d88a523853d7b06d4c",
    "batch_matrix.json": "bba3443c007c6a2e3f6699fc3ed5f36a095b3b7abb377a50a183aed7fcc9c482",
    "incident_journal.json": "26dc74ed004ce2005cb1b09075f3eca0290f4e95ac49a6726c750256f8cecfea",
    "summary.json": "783137e11815a3e4afe18bf5b99ef1275ecb20bd1bde5db2b9cd8ad9193e185f",
}

EXPECTED_FIELD_HASHES = {
    "batch_matrix.batches": "cad48daa995b30bd118364b4f2636ab521f6cd1c4a8dfe68fd6a766075baef1f",
    "incident_journal.applied_events": "52280aec204c1b21e89ab40bd1573b4e8fd123a47c3d98a8b38baa00a715a856",
    "source_plan.sources": "6e5c1eefa61f62841237335e775d6a4c40633141af9e68e9e0cd3e5ea65d0053",
    "summary.applied_incident_events": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "summary.batches_total": "e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683",
    "summary.credit_deferred_sources": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.deferred_sources": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.frozen_sources": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.idle_sources": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.ignored_incident_events": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.quarantined_sources": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.scheduled_batches_today": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.scheduled_sources": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.sources_total": "6b51d431df5d7f141cbececcf79edf3dd861c3b4069f0b11661a3eefacbba918",
    "warehouse_ledger.warehouses": "4e9bdf48aa3badd46d5e3d1246a64c21ce160606f7a0cfd9d0b99bcf9349223c",
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
        sp = outputs["source_plan.json"]
        assert isinstance(sp, dict)
        assert (
            _sha256_bytes(_canonical(sp["sources"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["source_plan.sources"]
        )

        wl = outputs["warehouse_ledger.json"]
        assert isinstance(wl, dict)
        assert (
            _sha256_bytes(_canonical(wl["warehouses"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["warehouse_ledger.warehouses"]
        )

        bm = outputs["batch_matrix.json"]
        assert isinstance(bm, dict)
        assert (
            _sha256_bytes(_canonical(bm["batches"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["batch_matrix.batches"]
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
            "batches_total",
            "credit_deferred_sources",
            "deferred_sources",
            "frozen_sources",
            "idle_sources",
            "ignored_incident_events",
            "quarantined_sources",
            "scheduled_batches_today",
            "scheduled_sources",
            "sources_total",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestSourceOrdering:
    """Deterministic ordering rules on source rows."""

    def test_sources_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`sources` must list rows in ascending ASCII `source_id` order."""
        rows = outputs["source_plan.json"]["sources"]
        assert isinstance(rows, list)
        ids = [str(r["source_id"]) for r in rows]
        assert ids == sorted(ids)


class TestSourceStatusCoverage:
    """Bundled fixtures exercise every documented source_status value."""

    def _statuses(self, outputs: dict[str, object]) -> set[str]:
        rows = outputs["source_plan.json"]["sources"]
        return {str(r["source_status"]) for r in rows}

    def test_quarantined_status_present(self, outputs: dict[str, object]) -> None:
        """At least one source row carries `quarantined` from a compromise incident."""
        assert "quarantined" in self._statuses(outputs)

    def test_warehouse_frozen_status_present(self, outputs: dict[str, object]) -> None:
        """At least one source row carries `warehouse_frozen` from a warehouse freeze."""
        assert "warehouse_frozen" in self._statuses(outputs)

    def test_deferred_capacity_status_present(self, outputs: dict[str, object]) -> None:
        """At least one source row carries `deferred_capacity` after the export cap."""
        assert "deferred_capacity" in self._statuses(outputs)

    def test_credit_deferred_status_present(self, outputs: dict[str, object]) -> None:
        """At least one source row carries `credit_deferred` when credits are exhausted."""
        assert "credit_deferred" in self._statuses(outputs)

    def test_scheduled_status_present(self, outputs: dict[str, object]) -> None:
        """At least one source row carries `scheduled` with a batch assigned today."""
        assert "scheduled" in self._statuses(outputs)

    def test_idle_status_present(self, outputs: dict[str, object]) -> None:
        """At least one source row carries `idle` when nothing can be scheduled."""
        assert "idle" in self._statuses(outputs)


class TestBlockedReasonCoverage:
    """Bundled fixtures surface distinct blocked-candidate reasons."""

    def _reasons(self, outputs: dict[str, object]) -> set[str]:
        found: set[str] = set()
        for row in outputs["source_plan.json"]["sources"]:
            for bc in row.get("blocked_candidates") or []:
                found.add(str(bc["reason"]))
        return found

    def test_capacity_deferred_reason_present(self, outputs: dict[str, object]) -> None:
        """A capacity-deferred source cites `capacity_deferred` for its would-be batch."""
        assert "capacity_deferred" in self._reasons(outputs)

    def test_credit_deferred_reason_present(self, outputs: dict[str, object]) -> None:
        """A credit-deferred source cites `credit_deferred` for its chosen batch."""
        assert "credit_deferred" in self._reasons(outputs)

    def test_embargoed_reason_present(self, outputs: dict[str, object]) -> None:
        """The embargo incident blocks at least one batch with `embargoed`."""
        assert "embargoed" in self._reasons(outputs)

    def test_outside_window_reason_present(self, outputs: dict[str, object]) -> None:
        """A source outside the effective window cites `outside_window`."""
        assert "outside_window" in self._reasons(outputs)

    def test_credit_over_budget_reason_present(self, outputs: dict[str, object]) -> None:
        """An over-tier-credit batch cites `credit_over_budget` on an otherwise eligible source."""
        assert "credit_over_budget" in self._reasons(outputs)


class TestVerdictSemantics:
    """Spot-check bundled rows that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], source_id: str) -> dict[str, object]:
        for row in outputs["source_plan.json"]["sources"]:
            if row["source_id"] == source_id:
                return row
        raise AssertionError(f"missing source row {source_id}")

    def test_compromise_source_quarantined(self, outputs: dict[str, object]) -> None:
        """`h-p2` is quarantined with compromise blocking every pending batch."""
        row = self._row(outputs, "h-p2")
        assert row["source_status"] == "quarantined"
        assert row["scheduled_batch"] is None
        assert all(bc["reason"] == "quarantine" for bc in row["blocked_candidates"])

    def test_freeze_warehouse_blocks_west_sources(self, outputs: dict[str, object]) -> None:
        """`h-p3` in frozen `r-west` cites `warehouse_frozen` on pending batches."""
        row = self._row(outputs, "h-p3")
        assert row["source_status"] == "warehouse_frozen"
        assert row["warehouse_id"] == "r-west"
        assert row["blocked_candidates"]
        assert all(bc["reason"] == "warehouse_frozen" for bc in row["blocked_candidates"])

    def test_east_schedules_two_net_exports(self, outputs: dict[str, object]) -> None:
        """`r-east` schedules `h-p1` and `h-p4` for `b-net` after credit debits."""
        scheduled = {
            r["source_id"]: r["scheduled_batch"]
            for r in outputs["source_plan.json"]["sources"]
            if r["source_status"] == "scheduled" and r["warehouse_id"] == "r-east"
        }
        assert scheduled == {"h-p1": "b-net", "h-p4": "b-net"}

    def test_credit_deferred_source_cites_credit_on_chosen_batch(
        self, outputs: dict[str, object]
    ) -> None:
        """`h-s1` defers with `credit_deferred` on `b-net` after east credits are spent."""
        row = self._row(outputs, "h-s1")
        assert row["source_status"] == "credit_deferred"
        reasons = {bc["batch_id"]: bc["reason"] for bc in row["blocked_candidates"]}
        assert reasons.get("b-net") == "credit_deferred"

    def test_north_capacity_deferred_source(self, outputs: dict[str, object]) -> None:
        """`h-n1` in `r-north` ends `deferred_capacity` when effective cap is zero."""
        row = self._row(outputs, "h-n1")
        assert row["source_status"] == "deferred_capacity"
        assert row["warehouse_id"] == "r-north"

    def test_idle_source_has_no_pending_batches(self, outputs: dict[str, object]) -> None:
        """`h-idle` already exported every batch and stays idle with an empty block list."""
        row = self._row(outputs, "h-idle")
        assert row["source_status"] == "idle"
        assert row["scheduled_batch"] is None
        assert row["blocked_candidates"] == []


class TestWarehouseLedger:
    """Warehouse counters align with source outcomes and credit pools."""

    def test_r_east_credit_pool_depleted(self, outputs: dict[str, object]) -> None:
        """`r-east` starts with two credits, schedules two debits, and ends at zero remaining."""
        wh = outputs["warehouse_ledger.json"]["warehouses"]["r-east"]
        assert wh["export_credits_start"] == 2
        assert wh["export_credits_remaining"] == 0
        assert wh["sources_scheduled"] == 2
        assert wh["sources_deferred_credit"] == 2

    def test_r_north_zero_cap_defers_contender(self, outputs: dict[str, object]) -> None:
        """`r-north` base cap zero defers its contender without scheduling anyone."""
        wh = outputs["warehouse_ledger.json"]["warehouses"]["r-north"]
        assert wh["effective_cap"] == 0
        assert wh["sources_scheduled"] == 0
        assert wh["sources_deferred_capacity"] == 1


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
    """Summary status counts partition the source fleet."""

    def test_status_counts_sum_to_sources_total(self, outputs: dict[str, object]) -> None:
        """Quarantine, freeze, defer, credit-defer, schedule, and idle counts sum to total."""
        sm = outputs["summary.json"]
        total = (
            sm["quarantined_sources"]
            + sm["frozen_sources"]
            + sm["deferred_sources"]
            + sm["credit_deferred_sources"]
            + sm["scheduled_sources"]
            + sm["idle_sources"]
        )
        assert total == sm["sources_total"]
