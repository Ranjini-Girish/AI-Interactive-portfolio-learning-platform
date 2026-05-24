"""Behavioral tests for the lineage drift borrow audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("LDB_DATA_DIR", "/app/ldb_lab"))
AUDIT_DIR = Path(os.environ.get("LDB_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "channel_verdicts.json",
    "incident_journal.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "5824568c2849f9e890d297faae0df1e375c05063cde41fb2e0d2f2fe1e006f95",
    "anchors/day_index.json": "edebb9370da103147ccf83fd681ec8b94649fac034038ba81acc10a2167c35a7",
    "anchors/window.json": "106712df4fb79d4c55ebea151f842c8070ff3997c22fd9548fce4dca6099ca70",
    "ancillary/guard.json": "7fac543b1c39c5c87bbc9f9ccbca578d5ecc731a4463623c73cc6f1d7a7c5e60",
    "ancillary/meta.json": "73648b08c26538ad83525f86ea3ef88f6434cfdfca91035d5d9e734666069d89",
    "ancillary/notes.json": "ec517087cbe79724577dc21c73c257b101f9d2a0230444bc33bb66af75cf833d",
    "ancillary/stub.json": "2f99984fb8e096b8cad288a9dfe59d59d2db3470ba6645cb93bc0b0773788059",
    "channels/c00.json": "7c14917756a2d29249992f03fbdc41245d2b16d72b73a10cbf49563d0c8cc142",
    "channels/c01.json": "c81b5e9621340af4a578db647839410e6020ae4659e89a00ef5c1e94aafc2706",
    "channels/c02.json": "85ba0b768d0cd794ea3e207eb4fd7011d79f896f7bb5442946812122c53df137",
    "channels/c03.json": "c438824ed78b710cc0b87e5ac902f4828769a578abab97a339c81d547f613073",
    "channels/c04.json": "c9d10e3028075047dc0782b1ed1d5266f8e1d926f910b8059cd014b86d8a68a1",
    "channels/c05.json": "d3ca3fe8bedbcb5911a6b1a0ed14933102b01552abe7611e263b04e1f05b1308",
    "channels/c06.json": "2ec349823c6856f87d8ba5fb6fec27fad9098f32a39edd40b04b58231555b2ce",
    "channels/c07.json": "5fcd500b1bc266a301565bac153e5ca4089d8824cbe2497bc4ba6e1fd65df0de",
    "channels/c08.json": "0b962429a058dc12fa54e85bab653fabbeb95a86e7ccc87a5fe144cc90751dd8",
    "channels/c09.json": "a33b5089d00c2b99117ac279bd24ec1f0d3a321916293fc8edbe2e5f8658320e",
    "channels/c10.json": "52320b3d2c6995cf44ba5c8b81a500759f662d094a658799e3bf3fea838bc629",
    "channels/c11.json": "9400076936101ef73b887cc5e571563bbf73fabb019d45e86bc30baea5c61002",
    "incident_log.json": "a2f8659b7d42ee1310307c2a4c5e3ed59290eedd9aae937408d53a51b53be85f",
    "policy.json": "4066d1ad5423889e9c451da841a89ba3ece7dac39fe741f9c70ab00726cfa9b6",
    "pool_state.json": "1f7fc5e84be0dd06c3f427f138fe2b75228bd5d1f136c3c2044943f71a95b126",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "channel_verdicts.json": "aeee4cafb9a8ee7cabf7d0346a0bf2332e1ae2a6b1db7787fc7af5d6f309bbbe",
    "incident_journal.json": "d6f30cf323c788af60727b99d8f24daa20c21b182bab71d80b0cc2f6ce259ffc",
    "summary.json": "420711bd2988c0e6460635f5d8d61193652baac4ea59de45b40b98784eaed7ef",
}


EXPECTED_FIELD_HASHES = {
    "channel_verdicts.channels": "554ef657cca0599ef7dd58120863313f06cfd60cc5f741c1b64d1d48e566f058",
    "incident_journal.applied_events": "9b57fd8c57becf6def777a17a9669fc6acc1e82a30a87c1669cab4650bcf0f0f",
    "incident_journal.ignored_events": "a043d21d65652f70af2312eed80c8061327ca507eac552872ffff14e518baab5",
    "summary.verdict_counts": "8610ed93e2e619e4f4ee96c63ba7a283b6881cb8fc1c105e136ac039a2644f87",
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
        cv = outputs["channel_verdicts.json"]
        assert isinstance(cv, dict)
        assert (
            _sha256_bytes(_canonical(cv["channels"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["channel_verdicts.channels"]
        )

        ij = outputs["incident_journal.json"]
        assert isinstance(ij, dict)
        assert (
            _sha256_bytes(_canonical(ij["applied_events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_journal.applied_events"]
        )
        assert (
            _sha256_bytes(_canonical(ij["ignored_events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_journal.ignored_events"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["verdict_counts"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.verdict_counts"]
        )


class TestChannelOrdering:
    """Verify deterministic ordering rules on verdict rows."""

    def test_channel_rows_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`channels` must list rows in ascending ASCII `channel_id` order."""
        cv = outputs["channel_verdicts.json"]
        assert isinstance(cv, dict)
        rows = cv["channels"]
        assert isinstance(rows, list)
        ids = [str(r["channel_id"]) for r in rows]
        assert ids == sorted(ids)


class TestLineageSemantics:
    """Spot-check lineage labels that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], cid: str) -> dict[str, object]:
        rows = outputs["channel_verdicts.json"]["channels"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("channel_id") == cid:
                return r
        raise AssertionError(f"missing channel row {cid}")

    def test_cedar_lineage_is_chained(self, outputs: dict[str, object]) -> None:
        """`ch-cedar` depends on `ch-aurora` without participating in a cycle."""
        r = self._row(outputs, "ch-cedar")
        assert r["lineage"] == "chained"

    def test_bloom_lineage_is_root(self, outputs: dict[str, object]) -> None:
        """`ch-bloom` has no resolved parent edge and is classified as a root."""
        r = self._row(outputs, "ch-bloom")
        assert r["lineage"] == "root"

    def test_fjord_lineage_is_cyclic(self, outputs: dict[str, object]) -> None:
        """`ch-fjord` participates in the two-node parent cycle with `ch-frost`."""
        r = self._row(outputs, "ch-fjord")
        assert r["lineage"] == "cyclic"


class TestVerdictSemantics:
    """Spot-check verdict labels that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], cid: str) -> dict[str, object]:
        rows = outputs["channel_verdicts.json"]["channels"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("channel_id") == cid:
                return r
        raise AssertionError(f"missing channel row {cid}")

    def test_granite_verdict_is_embargoed(self, outputs: dict[str, object]) -> None:
        """`ch-granite` is embargoed so the embargo label wins over residual drift."""
        r = self._row(outputs, "ch-granite")
        assert r["verdict"] == "embargoed"

    def test_cedar_verdict_is_escalate(self, outputs: dict[str, object]) -> None:
        """`ch-cedar` retains residual drift above the scaled escalation cut."""
        r = self._row(outputs, "ch-cedar")
        assert r["verdict"] == "escalate"

    def test_aurora_verdict_is_cleared(self, outputs: dict[str, object]) -> None:
        """`ch-aurora` borrows its full effective drift and clears."""
        r = self._row(outputs, "ch-aurora")
        assert r["verdict"] == "cleared"

    def test_heath_verdict_is_watch(self, outputs: dict[str, object]) -> None:
        """`ch-heath` stays on watch because residual drift stays at or below the cut."""
        r = self._row(outputs, "ch-heath")
        assert r["verdict"] == "watch"

    def test_dew_verdict_is_cleared(self, outputs: dict[str, object]) -> None:
        """`ch-dew` clears after borrowing matches its effective drift."""
        r = self._row(outputs, "ch-dew")
        assert r["verdict"] == "cleared"


class TestJournalAndSummary:
    """Exercise incident ordering and summary scalars."""

    def test_applied_incident_order(self, outputs: dict[str, object]) -> None:
        """Applicable incidents replay in stable day, seq, id order."""
        ij = outputs["incident_journal.json"]
        assert isinstance(ij, dict)
        assert ij["applied_events"] == ["inc-a", "inc-b", "inc-c", "inc-d", "inc-e"]

    def test_ignored_outside_window_preserved(self, outputs: dict[str, object]) -> None:
        """Out-of-window incidents surface only in `ignored_events`."""
        ij = outputs["incident_journal.json"]
        assert isinstance(ij, dict)
        assert ij["ignored_events"] == ["inc-out-1"]

    def test_summary_window_and_pool(self, outputs: dict[str, object]) -> None:
        """Summary scalars reflect the closed window length and exhausted pool."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert sm["window_days"] == 5
        assert sm["pool_after_incidents"] == 100
        assert sm["pool_after_borrow"] == 0
        assert sm["ignored_incident_kinds"] == 1
        assert sm["embargoed_channels"] == 1
