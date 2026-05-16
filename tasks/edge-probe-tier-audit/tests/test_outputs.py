"""Behavioral tests for the edge probe tier audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("EPT_DATA_DIR", "/app/edgeprobes"))
AUDIT_DIR = Path(os.environ.get("EPT_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "anomaly_events.json",
    "endpoint_profiles.json",
    "mad_summary.json",
    "summary.json",
    "tier_rollups.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "29c7103489350dcca84ef052aec4d611013b043efda2edd384b9675c89d683d1",
    "anchors/t1.txt": "0111f7554519f7126c570c154b894f1fbcddf4faa126f6d644b974dab6c77411",
    "anchors/t2.txt": "333d36c15ed252b52c66eda5bf9c1ad3e730b6d6eef9401a336db63ccf7558e7",
    "anchors/t3.txt": "16691bb6cb08a74f1a31391b670055beae1009beeb789b8edc6a48dc97eefa66",
    "ancillary/a1.json": "edb6ed214d3807cfb593fe9c23e11f00c087899e7312cd7d542fa4819468df0a",
    "ancillary/a2.json": "0e3a764bd4de34415dc368625baca10eefb7d5d506f998a1b26d46804e5cd94b",
    "incidents.json": "1abb679ab8e120c5468f217da5309881b2c5dba57e8a090234a0ad17415405fd",
    "ledger/lane.json": "0c0116ea2b944464ca414bd18bd8a5e0c2859963f4e3e92bc3f4754264fd3766",
    "ledger/tag.json": "9e169d5a8bd1b5655bf9242e165edcf97a9f54d6fdb6be8aa2ebe73ac7902a57",
    "policy.json": "fb31b35a684052bac89dab016626163cb3ee6633e42dc1cefa85bda815c62ad5",
    "pool_state.json": "52448ba317d0d4db0353ac72b7da948b915d96e7100ddc8640a0591a1ea2d3b3",
    "probes/ep-01.json": "9df4be768207edaa2df0e01caec9f527f26636827a8f1f46424c5dddf56c8518",
    "probes/ep-02.json": "33f8f3cf2c7f920ef9cea992e53e0808a987cb4c598ae9b6a0b6ca36a4484da9",
    "probes/ep-03.json": "40cef234d2d46849c9000cf21245b2b09b1e1310dd862fb0039857852cef73fe",
    "probes/ep-04.json": "11707afef5423d07a3fe259a546336693d1cd1b89148fadf3336ab3091d38c6d",
    "probes/ep-05.json": "a1cb76501882f3e18ce80b5095dd2301be04cd5feb07a6f7151a3f047175172c",
    "probes/ep-06.json": "c624b28b2b018aaca1ab5a99f2e1bc2b681cd9695e342e23389e5ce4982d5bcc",
    "probes/ep-07.json": "98cd37be07218b2823e8d2847e5791143d525f90db8e96eb2adf9541e379885d",
    "probes/ep-08.json": "3ce64e1ea8c554caa6a5418db9d317b6190f1fc6828c86c52737690d5fd31998",
    "probes/ep-09.json": "ff7ae74c5b73fe9cb05e3fb0a1eac8976af451b382453bee2cb13637e6af65f0",
    "probes/ep-10.json": "0eb50079a1b71357f22641a4d97ffb965b5afc2fe86df7fa72ed56826e5c1a40",
    "probes/ep-11.json": "9ff0351692461d15ed5504fad4ed7411674697388dfcad89383fa6645ba0f653",
    "probes/ep-12.json": "2ddf969427fdcb019f52f5db2b4d9c0870a3c9714d720fe16cd37bdd010fff5e",
    "probes/ep-h03.json": "cd9deb71913157042a60c103dc0dee5b9295c28f3c19913ebe930d20127b8340",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "anomaly_events.json": "eddd81c2dfa690a6828df014b65aa0a039aad403f3ce547d38583119a42b536f",
    "endpoint_profiles.json": "501439f210ab7043527370b18d11ef19052cfcd28aa88becba56e5aa090222b7",
    "mad_summary.json": "c26f1cc64803c460b7d728f4bfe896ab5d5934c34b2d19a20be33160d0162af9",
    "summary.json": "7bf79e78218c236a442ec0f003347e831ce30d11e8d842a3401588ff0fab7203",
    "tier_rollups.json": "1e65e44404fb5ec8d59a22cb07ee4711c845d69e0bebf55bddd2e473c769d880",
}


EXPECTED_FIELD_HASHES = {
    "endpoint_profiles.endpoints": "6cdb392a5ed26dbcb96a0ff6f13bf06315002f8f5c9c5200e7be576864b1cd4c",
    "summary.regions": "1852c030138195237b6c7a06b787f7760ba93b8b2a202ff62b1c38ae020cee10",
    "tier_rollups.tiers": "0fa33aefc590b65063d60379cc419ccef6dca821d43bb27a69479efc3064947c",
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
        ep = outputs["endpoint_profiles.json"]
        assert isinstance(ep, dict)
        assert (
            _sha256_bytes(_canonical(ep["endpoints"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["endpoint_profiles.endpoints"]
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
            _sha256_bytes(_canonical(sm["regions"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.regions"]
        )


class TestEndpointOrdering:
    """Deterministic ordering rules on endpoint rows."""

    def test_endpoints_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`endpoints` must list rows in ascending ASCII `endpoint_id` order."""
        rows = outputs["endpoint_profiles.json"]["endpoints"]
        assert isinstance(rows, list)
        ids = [str(r["endpoint_id"]) for r in rows]
        assert ids == sorted(ids)


class TestTierSemantics:
    """Spot-check probes that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], eid: str) -> dict[str, object]:
        rows = outputs["endpoint_profiles.json"]["endpoints"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("endpoint_id") == eid:
                return r
        raise AssertionError(f"missing endpoint row {eid}")

    def test_status_floor_marks_failed(self, outputs: dict[str, object]) -> None:
        """`ep-07` crosses the configured status floor and is classified FAILED."""
        r = self._row(outputs, "ep-07")
        assert r["tier"] == "FAILED"
        assert r["anomaly_flag"] is False

    def test_incident_forces_slow_without_forcing_anomaly(self, outputs: dict[str, object]) -> None:
        """`ep-h03` keeps a healthy RTT but the incident note forces SLOW without MAD flag."""
        r = self._row(outputs, "ep-h03")
        assert r["tier"] == "SLOW"
        assert r["anomaly_flag"] is False

    def test_high_rtt_success_triggers_anomaly(self, outputs: dict[str, object]) -> None:
        """`ep-06` is a successful probe with an extreme RTT so MAD marks it."""
        r = self._row(outputs, "ep-06")
        assert r["anomaly_flag"] is True


class TestAnomalyJournal:
    """Anomaly events list stays sorted and aligned with MAD outliers."""

    def test_anomaly_events_sorted(self, outputs: dict[str, object]) -> None:
        """Anomaly events list by endpoint id ascending."""
        evs = outputs["anomaly_events.json"]["events"]
        assert isinstance(evs, list)
        ids = [str(e["endpoint_id"]) for e in evs]
        assert ids == sorted(ids)

    def test_expected_outlier_endpoints(self, outputs: dict[str, object]) -> None:
        """The bundled dataset emits MAD outliers on four successful endpoints."""
        evs = outputs["anomaly_events.json"]["events"]
        ids = {str(e["endpoint_id"]) for e in evs}
        assert ids == {"ep-04", "ep-05", "ep-06", "ep-12"}


class TestRollups:
    """Tier rollups reflect final labels after incidents."""

    def test_us_slow_bucket_counts_forced_row(self, outputs: dict[str, object]) -> None:
        """US region records three SLOW rows including the forced endpoint."""
        tiers = outputs["tier_rollups.json"]["tiers"]
        assert isinstance(tiers, dict)
        us = tiers["us"]
        assert isinstance(us, dict)
        assert int(us["SLOW"]) == 3
        assert int(us["FAILED"]) == 1


class TestMadSummary:
    """MAD summary exposes population stats."""

    def test_mad_sample_size_matches_success_pool(self, outputs: dict[str, object]) -> None:
        """Twelve successful probes feed the MAD sample in the bundled dataset."""
        ms = outputs["mad_summary.json"]
        assert isinstance(ms, dict)
        assert int(ms["sample_size"]) == 12
        assert ms["global_median_ms"] is not None
        assert ms["global_mad_ms"] is not None
