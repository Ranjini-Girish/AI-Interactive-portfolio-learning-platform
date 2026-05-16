"""Behavioral tests for the SLO burn window audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SBWA_DATA_DIR", "/app/slo-matrix"))
AUDIT_DIR = Path(os.environ.get("SBWA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "burn_report.json",
    "tier_budgets.json",
    "dependency_taint.json",
    "incident_journal.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "5cd7932dc3826a2d081f38a6e3f5932cce1857dd05e825be38e89e80491e7498",
    "ancillary/channel_tag.json": "0cff3eacf13bf169e82fc67fd2ed3901d9a26fdee91b2cb41bad7ff04752fff1",
    "ancillary/ci_guard.json": "943bb35ebaa33b1044813809135f029537859528790c387a7c84110a4b0b9b7b",
    "ancillary/extra_one.json": "e00f12c9c6be456940cb7be775df45edec8597a5528482899e7b25d6daf09c50",
    "ancillary/extra_two.json": "67e433868c0141a87f7aad9a20c08a07587103476bf62d6e929bb04c0ff5df0f",
    "ancillary/packaging_stamp.json": "0d92f1a3d7ea78c4bfdd94c4f58c637c450f20e1e8aaac775994aada43df5b53",
    "ancillary/watermark.txt": "f1a4fd10b44971d72cd31a8353d8e6e287b3651021c0a0a52fcfb9561bf80d63",
    "consumers/consumer_index.json": "df1e2eddf36bac7ba733374ee869fa49b74b19f1d2a015fe52e197b6abc2dde3",
    "consumers/edges.json": "1226e346a0c4f92a88989af77457e60b180819ecd6fd6b9426d2d766f5f1b94d",
    "incident_log.json": "c5c5a84b24597435d58fb9d3111266112cbb0cda779cd4fe9fcfe471477499ac",
    "meta/notes.txt": "3f12d422cff5139faafdec39b2d25ca3e580df0e3ff865ad9837fa3973733aa1",
    "meta/version.json": "c9c45fc4c7426cd631c8321a07e7b2966d45d8e07cf13d36ef6b9a5ead5fef7e",
    "policy.json": "ac792a8b08f510f9425a0869a036c824da3f6d1f72e23ed0e41f1a9c1313649c",
    "pool_state.json": "068206e07450b8139d6edc2382747b73ac1c38a8daf4f5d877b99cd473a5e2b7",
    "services/svc-auth.json": "8d47a81e9256e820852f1780307f1c6717382c7fab080d42cd182b02b1a5e265",
    "services/svc-batch.json": "95e7ceca86113ffadc4e4c93832130a3d5dd22587198176e61a7476fcabe9ed9",
    "services/svc-cache.json": "5a70f00fbdd3f383daa0632be266bb5da4dd45d8fd4208ba4e92a7f3d067c114",
    "services/svc-gateway.json": "b5f34fefb56d2ba9232758e2dbfcb8d3345693b1f86de1f0efff1a852734ad80",
    "services/svc-ledger.json": "9af65b57ef2cffd3118dd3fcbbea3e3089836393a7e43e41b729ca0e105b7e9c",
    "services/svc-notify.json": "185e7e7f9631087b909325776bfefa1c6fe5b46531725b1c20f69f08c1c3b183",
    "services/svc-search.json": "541eb22d9e8aa8222523479e8d4ba33b699e5f89c67182eec25f7ee8270bc6f1",
    "services/svc-worker.json": "c2574eceffe92aca47eb09848ff508c3bd15b7479ff096b59ca63ba77b7348ae",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "burn_report.json": "972ce6ea954a8ef74a5e590b06807de0bda92cf7e9a15e1cf9a9b9ab2b53e488",
    "tier_budgets.json": "4304070b9d581c1bda513179a4e87bcf66650ac81004eda086e4c3a25d5421db",
    "dependency_taint.json": "8815e3cc849a08e9b00faf8f214b1958eb70cff2cddc9e7b8cf3a086428a3e9a",
    "incident_journal.json": "1bb88807e3404dc1cb9a710ca7f0da4830162f62fb62ab4e96d2a7e02a5d85c6",
    "summary.json": "09482ea6e1b9be728c13d3cf2dfd66e14e5f5401b15a82797150efd310470282",
}


EXPECTED_FIELD_HASHES = {
    "burn_report.services": "2646d9df251a572ef1aa949ea1931071a038cc842b78b880435697796491bdb9",
    "tier_budgets.tiers": "7c5dc8862de2deb4e830c9d7f17b9e41fc8c0a0b52ceec47fe8a09508c1051e9",
    "dependency_taint.consumers": "b0b6c0c5ce315cc8a61993589e442170dd6a4f30da467376c267de82370ed9e9",
    "incident_journal.applied_events": "c9f0ecc44289454ee36e03dd8bfee6a195026ea5121d09c2bf5c59c911cf0291",
    "summary.applied_incident_events": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.breached_services": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.compromise_services": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.ignored_incident_events": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.inherited_compromise_consumers": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.ok_services": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.services_total": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "summary.warning_services": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _spec_json_bytes(value: object) -> bytes:
    """SPEC.md canonical JSON: UTF-8, two-space indent, ASCII, sorted keys, trailing newline."""
    text = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


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


class TestSbwaPaths:
    """SBWA_DATA_DIR and SBWA_AUDIT_DIR must drive verifier I/O (see tests/test.sh exports)."""

    def test_sbwa_environment_pins_io_roots(self) -> None:
        """Non-empty SBWA_* values from the harness must match DATA_DIR and AUDIT_DIR resolution."""
        raw_data = os.environ.get("SBWA_DATA_DIR", "").strip()
        raw_audit = os.environ.get("SBWA_AUDIT_DIR", "").strip()
        assert raw_data, "SBWA_DATA_DIR must be set for verifier runs (tests/test.sh exports it)"
        assert raw_audit, "SBWA_AUDIT_DIR must be set for verifier runs (tests/test.sh exports it)"
        assert DATA_DIR == Path(raw_data)
        assert AUDIT_DIR == Path(raw_audit)


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

    def test_output_on_disk_matches_spec_json_encoding(self, outputs: dict[str, object]) -> None:
        """Each audit file's bytes must match SPEC.md canonical JSON (indent, sorted keys, trailing newline)."""
        for name in OUTPUT_FILES:
            path = AUDIT_DIR / name
            raw = path.read_bytes()
            expected = _spec_json_bytes(outputs[name])
            assert raw == expected, f"encoding mismatch for {name}"

    def test_output_sha256_hashes(self) -> None:
        """Each audit file's on-disk UTF-8 bytes must match the pinned SHA-256 digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            path = AUDIT_DIR / name
            raw = path.read_bytes()
            digest = _sha256_bytes(raw)
            assert digest == expected, f"output digest mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        br = outputs["burn_report.json"]
        assert isinstance(br, dict)
        assert (
            _sha256_bytes(_canonical(br["services"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["burn_report.services"]
        )

        tb = outputs["tier_budgets.json"]
        assert isinstance(tb, dict)
        assert (
            _sha256_bytes(_canonical(tb["tiers"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["tier_budgets.tiers"]
        )

        dt = outputs["dependency_taint.json"]
        assert isinstance(dt, dict)
        assert (
            _sha256_bytes(_canonical(dt["consumers"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["dependency_taint.consumers"]
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
            "breached_services",
            "compromise_services",
            "ignored_incident_events",
            "inherited_compromise_consumers",
            "ok_services",
            "services_total",
            "warning_services",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestBurnReportOrdering:
    """Verify deterministic ordering on burn report rows."""

    def test_services_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`services` must list rows in ascending ASCII `service_id` order."""
        rows = outputs["burn_report.json"]["services"]
        assert isinstance(rows, list)
        ids = [str(r["service_id"]) for r in rows]
        assert ids == sorted(ids)


class TestBurnSemantics:
    """Spot-check bundled rows that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], sid: str) -> dict[str, object]:
        rows = outputs["burn_report.json"]["services"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("service_id") == sid:
                return r
        raise AssertionError(f"missing service row {sid}")

    def test_gateway_fast_window_drives_breach(self, outputs: dict[str, object]) -> None:
        """`svc-gateway` breaches because the one-day fast burn exceeds the gold critical band."""
        r = self._row(outputs, "svc-gateway")
        assert r["burn_rate_milli_fast"] == 6428
        assert r["burn_rate_milli_slow"] == 1140
        assert r["effective_burn_rate_milli"] == 6428
        assert r["slo_status"] == "breached"

    def test_cache_freeze_keeps_gold_ok(self, outputs: dict[str, object]) -> None:
        """`svc-cache` stays ok after frozen days zero out late-window bad minutes."""
        r = self._row(outputs, "svc-cache")
        assert r["consumed_bad_minutes_slow"] == 32
        assert r["effective_burn_rate_milli"] == 640
        assert r["slo_status"] == "ok"

    def test_notify_compromise_forces_breach(self, outputs: dict[str, object]) -> None:
        """`svc-notify` is numerically mild but compromised with zero remaining budget."""
        r = self._row(outputs, "svc-notify")
        assert r["slo_status"] == "breached"
        assert r["remaining_budget_minutes"] == 0
        assert r["reasons"] == ["service_compromise"]

    def test_auth_review_override_warning(self, outputs: dict[str, object]) -> None:
        """`svc-auth` is overridden to warning despite numeric breach-level burn."""
        r = self._row(outputs, "svc-auth")
        assert r["slo_status"] == "warning"
        assert r["reasons"] == ["slo_review_override"]

    def test_ledger_silver_warning_band(self, outputs: dict[str, object]) -> None:
        """`svc-ledger` lands in warning from tier-adjusted silver thresholds."""
        r = self._row(outputs, "svc-ledger")
        assert r["tier"] == "silver"
        assert r["allowed_bad_minutes_slow"] == 40
        assert r["slo_status"] == "warning"

    def test_search_bronze_breached(self, outputs: dict[str, object]) -> None:
        """`svc-search` breaches because the fast window burn exceeds the bronze critical band."""
        r = self._row(outputs, "svc-search")
        assert r["tier"] == "bronze"
        assert r["slo_status"] == "breached"
        assert r["burn_rate_milli_slow"] == 1050
        assert r["burn_rate_milli_fast"] == 1500
        assert r["effective_burn_rate_milli"] == 1500


class TestDependencyTaint:
    """Consumer taint follows compromised producers along dependency edges."""

    def test_batch_inherits_notify_compromise(self, outputs: dict[str, object]) -> None:
        """`svc-batch` lists `svc-notify` as the compromised producer."""
        rows = outputs["dependency_taint.json"]["consumers"]
        assert isinstance(rows, list)
        batch = next(r for r in rows if r["consumer_id"] == "svc-batch")
        assert batch["taint_status"] == "inherited_compromise"
        assert batch["compromised_producers"] == ["svc-notify"]

    def test_gateway_clean_without_upstream_compromise(self, outputs: dict[str, object]) -> None:
        """`svc-gateway` depends on `svc-cache`, which is not compromised."""
        rows = outputs["dependency_taint.json"]["consumers"]
        gw = next(r for r in rows if r["consumer_id"] == "svc-gateway")
        assert gw["taint_status"] == "clean"
        assert gw["compromised_producers"] == []

    def test_consumers_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """Dependency rows are sorted by ascending `consumer_id`."""
        rows = outputs["dependency_taint.json"]["consumers"]
        ids = [str(r["consumer_id"]) for r in rows]
        assert ids == sorted(ids)


class TestIncidentJournal:
    """Journal mirrors accepted, in-window, well-formed incidents."""

    def test_journal_sorted_by_day_then_id(self, outputs: dict[str, object]) -> None:
        """Applied events appear in ascending (day, event_id) order."""
        evs = outputs["incident_journal.json"]["applied_events"]
        assert isinstance(evs, list)
        keys = [(int(e["day"]), str(e["event_id"])) for e in evs]
        assert keys == sorted(keys)

    def test_journal_includes_expected_event_ids(self, outputs: dict[str, object]) -> None:
        """The bundled log applies the four well-formed incidents before the pool day."""
        evs = outputs["incident_journal.json"]["applied_events"]
        ids = {str(e["event_id"]) for e in evs}
        assert ids == {"e01", "e02", "e03", "e04"}

    def test_journal_covers_all_supported_kinds(self, outputs: dict[str, object]) -> None:
        """Each supported incident kind appears at least once in the applied journal."""
        evs = outputs["incident_journal.json"]["applied_events"]
        kinds = {str(e["kind"]) for e in evs}
        assert kinds == {
            "burn_freeze",
            "service_compromise",
            "slo_review_override",
            "tier_budget_delta",
        }


class TestTierBudgets:
    """Tier budget table reflects policy plus applied deltas."""

    def test_silver_adjusted_budget_after_delta(self, outputs: dict[str, object]) -> None:
        """Silver tier gains five minutes from the applied tier_budget_delta incident."""
        tiers = outputs["tier_budgets.json"]["tiers"]
        assert isinstance(tiers, dict)
        silver = tiers["silver"]
        assert silver["base_budget_minutes"] == 35
        assert silver["delta_sum_minutes"] == 5
        assert silver["adjusted_budget_minutes"] == 40


class TestSummaryCounts:
    """Summary counters align with emitted service and taint rows."""

    def test_summary_matches_row_counts(self, outputs: dict[str, object]) -> None:
        """Aggregate summary fields match statuses and taint rows in the bundle."""
        sm = outputs["summary.json"]
        rows = outputs["burn_report.json"]["services"]
        assert sm["services_total"] == len(rows)
        breached = sum(1 for r in rows if r["slo_status"] == "breached")
        warning = sum(1 for r in rows if r["slo_status"] == "warning")
        ok = sum(1 for r in rows if r["slo_status"] == "ok")
        assert sm["breached_services"] == breached
        assert sm["warning_services"] == warning
        assert sm["ok_services"] == ok
        taint_rows = outputs["dependency_taint.json"]["consumers"]
        inherited = sum(1 for r in taint_rows if r["taint_status"] == "inherited_compromise")
        assert sm["inherited_compromise_consumers"] == inherited
