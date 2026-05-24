"""Verifier suite for phase-skew-hold-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("PSHA_DATA_DIR", "/app/psh_lab"))
AUDIT_DIR = Path(os.environ.get("PSHA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ("report.json",)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "c7b0cc6f489059cf334d7d291f08225ca1d7e8d2874f859213151a97969ba988",
    "streaks/st_00.json": "4e00f4657f3da766a7146080318b7a074e60bd1684419d995588dbe042a95b97",
    "streaks/st_01.json": "656339ff4042d7f6cb22643f7572f35cb6c509b82eb381719206fc7ffa94234e",
    "streaks/st_02.json": "e63f089b76e63fa5b15144eb6b0fdb699b05977c98e82ee1fbb204bacbbcff48",
    "streaks/st_03.json": "82442d49e4cea97b3b1a65a5ca3d10aae6b2e461c35bef5f41f314010581b388",
    "streaks/st_04.json": "b426d6e5ac744c4094e1d5431648159590fd15aa19c755e65fb24b6f325fb044",
    "streaks/st_05.json": "45d9dc2fd0e8e7228a97335f6de6f70022ac26e205f90675eb9a5ec3e32a60d0",
    "streaks/st_06.json": "ec7d8986523a23514fd47712e691efc5298e8c1ecdd8ed315549b0f6cc7fa5a3",
    "streaks/st_07.json": "5bf8b11efcf8990475b1a6a260f0ea525fd70352da76bb4a631ebb7b352e8272",
    "streaks/st_08.json": "d1b192fa2c806e262bda7c819262a482d97b46f920d01e4b88e218b4ee021f6b",
    "streaks/st_09.json": "080f9a8569c71132290c9efbb55c1f4995b6aa41f8d9aa4dc72ff0627b2dd941",
    "streaks/st_10.json": "08400b2e871ef879eac9cdd45d6b3a09990b60970e0b905feb6af7dd6df2fece",
    "streaks/st_11.json": "8369f42319392811412916b56569a38c7a8ff2172072e2b6b00e43c19a099b38",
    "streaks/st_12.json": "1577ba6f64d0a564746ab0d0319f61cdea3f51084b5b3902db5d9f6754cd17ab",
    "anchors/day_floor.json": "27a4cde34a4bf4c0bf12709e9469540fcc2e6813b4f38bf12cecefd8a265f5a5",
    "anchors/window.json": "5ccdee8ab5b73658b7b9996ec392578e15baf3691b86406de154ca61cdc8efec",
    "ancillary/meta.json": "15362fb2aa08c77b7a8b2f0c6ceb462bda58e9c13c1ef65ce70fabc521bfe454",
    "ancillary/notes.json": "1ecf2fb55a38b0ac3a64844172aa19b00ff6e5115735efaa4ee8487571fe8314",
    "domain_layout.json": "39adba158c5878756e5264c25037314759b24e36a8c2892868dd8719a527c066",
    "incident_log.json": "795f9d75aa57124e9960431a43ff75ef80fd1b19627909f0849c2dfd8fb7974f",
    "policy.json": "738c380f293901c6d4f40e6d19ef42bc3d7f8b2c80a0298743a567f0be27ec78",
    "pool_state.json": "bba6362e8c036fe99264008757a8ae9f6a75a116238e17156da0623e3d9824bc",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "report.json": "1cb24d9aa2ca637ab89bc221253aeecd94afd39f90de42a982d278cbc3f52a3c",
}


EXPECTED_FIELD_HASHES = {
    "site_days": "a8b8cd721d9c97231c29e1f8506f50078024eff6088108c6bda213f95a171cb4",
    "summary.days_span": "1ffcbca1d3f7509a9b96ee0d1bb4ed703eef064065c70f87bf95211774c74fc9",
    "summary.rows_ingested": "eb1e33e8a81b697b75855af6bfcdbcbf7cbbde9f94962ceaec1ed8af21f5a50f",
    "summary.site_day_rows": "5f9c4ab08cac7457e9111a30e4664920607ea2c115a1433d7be98e97e64244ca",
    "summary.sites_considered": "3fdba35f04dc8c462986c992bcf875546257113072a909c162f7e470e581e278",
    "summary.state_counts": "9c3528bf01f425e4303aa9cc1fc513e258130cb0e0463493bd9733716f092559",
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest for a byte string."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize using the verifier's minified JSON contract."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _spec_json_bytes(value: object) -> bytes:
    """Serialize exactly as SPEC mandates for on-disk audit JSON."""
    text = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from disk."""
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
    """Verify emitted JSON matches the canonical contract."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_output_on_disk_matches_spec_json_encoding(
        self, outputs: dict[str, object],
    ) -> None:
        """Each audit file's bytes must match SPEC canonical JSON formatting."""
        for name in OUTPUT_FILES:
            path = AUDIT_DIR / name
            raw = path.read_bytes()
            expected = _spec_json_bytes(outputs[name])
            assert raw == expected, f"encoding mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        report = outputs["report.json"]
        site_days = report["site_days"]
        assert (
            _sha256_bytes(_canonical(site_days).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["site_days"]
        )
        summary = report["summary"]
        for key in (
            "days_span",
            "rows_ingested",
            "site_day_rows",
            "sites_considered",
            "state_counts",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(summary[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestAggregateStates:
    """Positively exercise aggregate_state values emitted by the fixtures."""

    def _table(self, outputs: dict[str, object]) -> dict[tuple[str, int], dict[str, object]]:
        """Index site-day rows for lookup."""
        out: dict[tuple[str, int], dict[str, object]] = {}
        for row in outputs["report.json"]["site_days"]:
            out[(str(row["site"]), int(row["day"]))] = row
        return out

    def test_cool_window_row(self, outputs: dict[str, object]) -> None:
        """Aurora day 103 must be classified as cool with a merged phase."""
        row = self._table(outputs)[("aurora", 103)]
        assert row["aggregate_state"] == "cool"
        assert row["merged_phase_deg"] == 13

    def test_hold_after_grace_gap(self, outputs: dict[str, object]) -> None:
        """Gamma day 509 must enter hold with no merged phase."""
        row = self._table(outputs)[("gamma", 509)]
        assert row["aggregate_state"] == "hold"
        assert row["merged_phase_deg"] is None

    def test_site_compromise_suppresses_merge(self, outputs: dict[str, object]) -> None:
        """Delta day 116 must be compromised with a null merge."""
        row = self._table(outputs)[("delta", 116)]
        assert row["aggregate_state"] == "compromised"
        assert row["merged_phase_deg"] is None

    def test_below_floor_suppresses_merge(self, outputs: dict[str, object]) -> None:
        """Delta day 108 must sit below the published floor with a null merge."""
        row = self._table(outputs)[("delta", 108)]
        assert row["aggregate_state"] == "below_floor"
        assert row["merged_phase_deg"] is None

    def test_weak_quality_aggregate(self, outputs: dict[str, object]) -> None:
        """Echo day 150 must aggregate to weak while still merging the clean trace."""
        row = self._table(outputs)[("echo", 150)]
        assert row["aggregate_state"] == "weak"
        assert row["merged_phase_deg"] == 57

    def test_quarantine_blocks_merge_for_day112(self, outputs: dict[str, object]) -> None:
        """Delta day 112 must be quarantined for the north instrument with null merge."""
        row = self._table(outputs)[("delta", 112)]
        assert row["aggregate_state"] == "quarantined"
        assert row["merged_phase_deg"] is None

    def test_crux_quarantine_aggregate_keeps_merge(self, outputs: dict[str, object]) -> None:
        """Crux day 300 must stay quarantined at the aggregate while merging survivors."""
        row = self._table(outputs)[("crux", 300)]
        assert row["aggregate_state"] == "quarantined"
        assert row["merged_phase_deg"] == 101


class TestSummarySemantics:
    """Cross-check summary counters against the emitted site-day table."""

    def test_rows_ingested_matches_fixture_rows(self, outputs: dict[str, object]) -> None:
        """summary.rows_ingested must equal the number of streak rows ingested."""
        total = 0
        for path in sorted((DATA_DIR / "streaks").glob("*.json")):
            doc = _load_json(path)
            total += len(doc["rows"])
        assert outputs["report.json"]["summary"]["rows_ingested"] == total

    def test_site_day_rows_matches_table_len(self, outputs: dict[str, object]) -> None:
        """summary.site_day_rows must match the emitted table length."""
        rows = outputs["report.json"]["site_days"]
        assert outputs["report.json"]["summary"]["site_day_rows"] == len(rows)

    def test_state_counts_sum(self, outputs: dict[str, object]) -> None:
        """summary.state_counts must sum to the number of site-day rows."""
        counts = outputs["report.json"]["summary"]["state_counts"]
        assert sum(int(v) for v in counts.values()) == len(outputs["report.json"]["site_days"])
