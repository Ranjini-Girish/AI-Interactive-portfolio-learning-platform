"""Behavioral tests for the patch-slot-lattice-audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("PSLA_DATA_DIR", "/app/patch_slots"))
AUDIT_DIR = Path(os.environ.get("PSLA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "host_plan.json",
    "region_ledger.json",
    "bundle_matrix.json",
    "incident_journal.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "7506c858c39aa763c2b29528abd385f38e0475fc3c5b46e30c4a1b809c26a300",
    "ancillary/channel_tag.json": "605a72b76e44bfe91f45c52cd61a4ad660b6837aee55c48b70db3465217f4800",
    "ancillary/ci_guard.json": "5a0d912b82837f38d2ade81fd312a8e5c2fb0ef47010d33ed2e15ed844d1cd1d",
    "ancillary/watermark.txt": "97a9429e6ab4ee389687ba491a90a08318c2df7ab1633bd6d24e4d8778c069ab",
    "bundles/b-app.json": "2fb24062001748fa61da972aa9d4db722a6d0d122f28236a5ab564d11e34b7e3",
    "bundles/b-base.json": "df6e31be973da730c70eaa3f969dc63bd0b14d658fb6e3b7a49243a9ae620de4",
    "bundles/b-db.json": "3a9a05bf8ca9db812f0f1bc61660a725ae97b3896ae796e91193d122bad2d881",
    "bundles/b-heavy.json": "2f40df99068ffb37161fedd7d856140de158730b3f399fa9b0308e4c77fbad64",
    "bundles/b-mon.json": "db480d6cd14aac93157de318b98bfd10336864be51a82815a2752a836908d767",
    "bundles/b-net.json": "44faee9aa03fec7f208dc79b038eb8bcfb21c781fd332c734da892eae7a93181",
    "hosts/h-d1.json": "93915a71adba99fdad614c288acb5f871560ea91445975a82e89e448da6390d0",
    "hosts/h-d2.json": "7f27a6ef0d41f10abf995f96d83668f8a0ff389521f70ba4fe9a913ccc466564",
    "hosts/h-idle.json": "f533665a68691b20fe61d75180a5184cc9ceb471ae1cb94738467d1ab0f2dced",
    "hosts/h-n1.json": "af2d7f7902437925a844d2c684c97b06d0f430e28b76f7723809a2a0a5e0df59",
    "hosts/h-out.json": "02cce98b4d32d6b5d241ea0e1c874bae81ee6f08e894fbc4d6cff4bea05adf6d",
    "hosts/h-p1.json": "8fec2c033c26d05db498680b6f0dd6f1aef98df5f17affbf736e871cdf87beff",
    "hosts/h-p2.json": "c0d0854d3341883ff95647e45746ffd2308f33b3adea561509473261aca1e276",
    "hosts/h-p3.json": "f649063b74ffce67bd8148ce071863337b9bb9af5e257e3bd8665077472f6bb1",
    "hosts/h-p4.json": "d5a48c89e78aceaa4b581c7441f31520b546899678ec118fdd914eceb2621c7b",
    "hosts/h-s1.json": "c2c41d53555446ae510bcdea198e5f56a46a6de5ed0c7be5fb9f53b2cad5a6bc",
    "hosts/h-s2.json": "3a0ea33081f9ccedc894a6fbab7cb9ffcc425c4559360381d09880cb960011e4",
    "hosts/h-s3.json": "0d2950446cf2febd1c77cea07643e9f49714c6bd224a6b0d84b14751385973e9",
    "incident_log.json": "d805e8dad9cd137f213abaf0ea2063cae6af93cc6ec9cd4cdcba9e8831de0560",
    "policy.json": "deba363776e556544cfdfed69f935e4ef5eb5d2db6861b0f4af129e5c2cc8906",
    "pool_state.json": "78c533edbd96f582aa124618c50b9a5d74899b9950f7d4216ebf06190e051031",
    "regions/r-east.json": "4f99c389df9dc0aa64e90e09d9507c54bd7f9da02d090bb7c84c5774e14776cf",
    "regions/r-north.json": "e74f207ac4ac66a507723b588a079ed8ede1474761f3e46ff9894ef6e3034824",
    "regions/r-west.json": "72caa30a089ed0d0bdf641ebc227b2b5ebb77662e534e3c21e29a853659e182e",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "bundle_matrix.json": "876d5c9601bc9cead0ae8ee4114886ceac18ecd725067212add7d444cc020e3d",
    "host_plan.json": "30cd83d9bbd2615ccf28b4166e62cc20b61c008e819068d2a2df1c7eb96b6c9b",
    "incident_journal.json": "40a2c5847ca0deb0203e438cd0a3c692cb68c83bfb9e60de875e339ebc3187c5",
    "region_ledger.json": "31792f119396b488dc4a290ade130f6ea87158c3468517c7239123441cc2ea5c",
    "summary.json": "2a917f5176f8eda490f8ce40dd53e966c63549bd009e9eef4fc5166bcaba5abb",
}

EXPECTED_FIELD_HASHES = {
    "bundle_matrix.bundles": "8b5d3a92545b0c0d11235f463590b1e6811ad272fc15036258c0709983371eec",
    "host_plan.hosts": "3bb4c6016a78dbbce4e8638aba82335da45abff1dbf0e6bd3ecf93a044eb6bae",
    "incident_journal.applied_events": "125a6e59bd5daefbb14f3cb0ede410fe2259f730fd1a284b375acc4b52c77416",
    "region_ledger.regions": "c6665f753643615159fa72820d4ac0c278c7906156d8015d882d753a74ff45ed",
    "summary.applied_incident_events": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.bundles_total": "e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683",
    "summary.deferred_hosts": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.frozen_hosts": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.hosts_total": "6b51d431df5d7f141cbececcf79edf3dd861c3b4069f0b11661a3eefacbba918",
    "summary.idle_hosts": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.ignored_incident_events": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.quarantined_hosts": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.scheduled_bundles_today": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.scheduled_hosts": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
}

HOST_STATUSES = frozenset(
    {"quarantined", "frozen_region", "deferred_capacity", "scheduled", "idle"}
)
BLOCK_REASONS = frozenset(
    {
        "quarantine",
        "region_frozen",
        "capacity_deferred",
        "embargoed",
        "outside_window",
        "missing_dependency",
        "reboot_over_budget",
    }
)


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

    def test_output_files_are_strictly_canonical_bytes(self) -> None:
        """Each audit file must match the documented byte layout independently of
        the data hashes: UTF-8, two-space indent, ASCII-only escapes, object keys
        sorted lexicographically at every depth, `: ` between keys and values, and
        exactly one trailing `\\n` at EOF. A compact or 4-space-indented file with
        correct data still satisfies the data hashes but must fail this check."""
        for name in OUTPUT_FILES:
            path = AUDIT_DIR / name
            raw = path.read_bytes()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AssertionError(f"{name} is not valid JSON: {exc}") from exc
            try:
                raw.decode("ascii")
            except UnicodeDecodeError as exc:
                raise AssertionError(
                    f"{name} contains non-ASCII bytes; ensure_ascii escaping required"
                ) from exc
            assert raw.endswith(b"\n"), f"{name} missing trailing newline"
            assert not raw.endswith(b"\n\n"), f"{name} has more than one trailing newline"
            expected_bytes = (
                json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=True).encode(
                    "utf-8"
                )
                + b"\n"
            )
            assert raw == expected_bytes, (
                f"{name} bytes do not match the documented canonical layout "
                f"(2-space indent, sorted keys, ASCII-only, single trailing newline)"
            )

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        hp = outputs["host_plan.json"]
        assert isinstance(hp, dict)
        assert (
            _sha256_bytes(_canonical(hp["hosts"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["host_plan.hosts"]
        )

        rl = outputs["region_ledger.json"]
        assert isinstance(rl, dict)
        assert (
            _sha256_bytes(_canonical(rl["regions"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["region_ledger.regions"]
        )

        bm = outputs["bundle_matrix.json"]
        assert isinstance(bm, dict)
        assert (
            _sha256_bytes(_canonical(bm["bundles"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["bundle_matrix.bundles"]
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
            "bundles_total",
            "deferred_hosts",
            "frozen_hosts",
            "hosts_total",
            "idle_hosts",
            "ignored_incident_events",
            "quarantined_hosts",
            "scheduled_bundles_today",
            "scheduled_hosts",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestHostOrdering:
    """Deterministic ordering rules on host rows."""

    def test_hosts_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`hosts` must list rows in ascending ASCII `host_id` order."""
        rows = outputs["host_plan.json"]["hosts"]
        assert isinstance(rows, list)
        ids = [str(r["host_id"]) for r in rows]
        assert ids == sorted(ids)


class TestHostStatusCoverage:
    """Bundled fixtures exercise every documented host_status value."""

    def _statuses(self, outputs: dict[str, object]) -> set[str]:
        rows = outputs["host_plan.json"]["hosts"]
        return {str(r["host_status"]) for r in rows}

    def test_quarantined_status_present(self, outputs: dict[str, object]) -> None:
        """At least one host row carries `quarantined` from a compromise incident."""
        assert "quarantined" in self._statuses(outputs)

    def test_frozen_region_status_present(self, outputs: dict[str, object]) -> None:
        """At least one host row carries `frozen_region` from a region freeze."""
        assert "frozen_region" in self._statuses(outputs)

    def test_deferred_capacity_status_present(self, outputs: dict[str, object]) -> None:
        """At least one host row carries `deferred_capacity` after the regional cap."""
        assert "deferred_capacity" in self._statuses(outputs)

    def test_scheduled_status_present(self, outputs: dict[str, object]) -> None:
        """At least one host row carries `scheduled` with a bundle assigned today."""
        assert "scheduled" in self._statuses(outputs)

    def test_idle_status_present(self, outputs: dict[str, object]) -> None:
        """At least one host row carries `idle` when nothing can be scheduled."""
        assert "idle" in self._statuses(outputs)


class TestBlockedReasonCoverage:
    """Bundled fixtures surface distinct blocked-candidate reasons."""

    def _reasons(self, outputs: dict[str, object]) -> set[str]:
        found: set[str] = set()
        for row in outputs["host_plan.json"]["hosts"]:
            for bc in row.get("blocked_candidates") or []:
                found.add(str(bc["reason"]))
        return found

    def test_capacity_deferred_reason_present(self, outputs: dict[str, object]) -> None:
        """A deferred host cites `capacity_deferred` for its would-be bundle."""
        assert "capacity_deferred" in self._reasons(outputs)

    def test_embargoed_reason_present(self, outputs: dict[str, object]) -> None:
        """The embargo incident blocks at least one bundle with `embargoed`."""
        assert "embargoed" in self._reasons(outputs)

    def test_outside_window_reason_present(self, outputs: dict[str, object]) -> None:
        """A host outside the effective window cites `outside_window`."""
        assert "outside_window" in self._reasons(outputs)

    def test_reboot_over_budget_reason_present(self, outputs: dict[str, object]) -> None:
        """An over-budget bundle cites `reboot_over_budget` on an otherwise eligible host."""
        assert "reboot_over_budget" in self._reasons(outputs)


class TestVerdictSemantics:
    """Spot-check bundled rows that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], host_id: str) -> dict[str, object]:
        for row in outputs["host_plan.json"]["hosts"]:
            if row["host_id"] == host_id:
                return row
        raise AssertionError(f"missing host row {host_id}")

    def test_compromise_host_quarantined(self, outputs: dict[str, object]) -> None:
        """`h-p2` is quarantined with compromise blocking every pending bundle."""
        row = self._row(outputs, "h-p2")
        assert row["host_status"] == "quarantined"
        assert row["scheduled_bundle"] is None
        assert all(bc["reason"] == "quarantine" for bc in row["blocked_candidates"])

    def test_freeze_region_blocks_west_hosts(self, outputs: dict[str, object]) -> None:
        """`h-p3` in frozen `r-west` cites `region_frozen` on pending bundles."""
        row = self._row(outputs, "h-p3")
        assert row["host_status"] == "frozen_region"
        assert row["region"] == "r-west"
        assert row["blocked_candidates"]
        assert all(bc["reason"] == "region_frozen" for bc in row["blocked_candidates"])

    def test_cap_bump_allows_three_east_schedules(self, outputs: dict[str, object]) -> None:
        """`r-east` effective cap 3 schedules `h-p1`, `h-p4`, and `h-s1` on day 15."""
        scheduled = {
            r["host_id"]
            for r in outputs["host_plan.json"]["hosts"]
            if r["host_status"] == "scheduled" and r["region"] == "r-east"
        }
        assert scheduled == {"h-p1", "h-p4", "h-s1"}

    def test_deferred_host_cites_capacity_on_chosen_bundle(
        self, outputs: dict[str, object]
    ) -> None:
        """`capacity_deferred` is bundle-scoped: on deferred `h-s3` only the chosen
        bundle `b-db` carries it. `b-heavy` keeps `reboot_over_budget` and `b-mon`
        keeps `embargoed` per their own per-bundle conditions, proving the ledger
        does not blanket every row on a deferred host with `capacity_deferred`."""
        row = self._row(outputs, "h-s3")
        assert row["host_status"] == "deferred_capacity"
        reasons = {bc["bundle_id"]: bc["reason"] for bc in row["blocked_candidates"]}
        assert reasons.get("b-db") == "capacity_deferred"
        assert reasons.get("b-heavy") == "reboot_over_budget"
        assert reasons.get("b-mon") == "embargoed"
        capacity_rows = [
            bc for bc in row["blocked_candidates"] if bc["reason"] == "capacity_deferred"
        ]
        assert len(capacity_rows) == 1

    def test_deferred_host_other_bundles_keep_per_bundle_reasons(
        self, outputs: dict[str, object]
    ) -> None:
        """`h-d2` defers `b-net` with `capacity_deferred`; the remaining unscheduled
        bundles surface a mix of `missing_dependency` and other per-bundle reasons
        rather than a uniform `capacity_deferred`, exercising the bundle-scoped rule
        across a host that has more than two non-applied bundles."""
        row = self._row(outputs, "h-d2")
        assert row["host_status"] == "deferred_capacity"
        reasons = {bc["bundle_id"]: bc["reason"] for bc in row["blocked_candidates"]}
        assert reasons.get("b-net") == "capacity_deferred"
        capacity_count = sum(1 for r in reasons.values() if r == "capacity_deferred")
        assert capacity_count == 1
        non_capacity_reasons = {r for r in reasons.values() if r != "capacity_deferred"}
        assert non_capacity_reasons.issubset(
            {"embargoed", "outside_window", "missing_dependency", "reboot_over_budget"}
        )
        assert non_capacity_reasons, "deferred host must surface at least one per-bundle reason"

    def test_idle_host_has_no_pending_bundles(self, outputs: dict[str, object]) -> None:
        """`h-idle` already applied every bundle and stays idle with an empty block list."""
        row = self._row(outputs, "h-idle")
        assert row["host_status"] == "idle"
        assert row["scheduled_bundle"] is None
        assert row["blocked_candidates"] == []

    def test_outside_window_host_idle(self, outputs: dict[str, object]) -> None:
        """`h-out` has no effective maintenance window on the audit day."""
        row = self._row(outputs, "h-out")
        assert row["host_status"] == "idle"
        assert any(bc["reason"] == "outside_window" for bc in row["blocked_candidates"])


class TestRegionLedger:
    """Regional counters align with host outcomes."""

    def test_r_east_effective_cap_three(self, outputs: dict[str, object]) -> None:
        """`cap_bump` raises `r-east` effective cap from 2 to 3 for day 15."""
        reg = outputs["region_ledger.json"]["regions"]["r-east"]
        assert reg["max_hosts_per_day"] == 2
        assert reg["effective_cap"] == 3
        assert reg["hosts_scheduled"] == 3
        assert reg["hosts_deferred"] == 2

    def test_r_north_zero_cap_defers_everyone(self, outputs: dict[str, object]) -> None:
        """`r-north` base cap zero defers its contender without scheduling anyone."""
        reg = outputs["region_ledger.json"]["regions"]["r-north"]
        assert reg["effective_cap"] == 0
        assert reg["hosts_scheduled"] == 0
        assert reg["hosts_deferred"] == 1


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
    """Summary status counts partition the host fleet."""

    def test_status_counts_sum_to_hosts_total(self, outputs: dict[str, object]) -> None:
        """Quarantine, freeze, defer, schedule, and idle counts sum to `hosts_total`."""
        sm = outputs["summary.json"]
        total = (
            sm["quarantined_hosts"]
            + sm["frozen_hosts"]
            + sm["deferred_hosts"]
            + sm["scheduled_hosts"]
            + sm["idle_hosts"]
        )
        assert total == sm["hosts_total"]
