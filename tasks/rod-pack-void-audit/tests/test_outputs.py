# scaffold-status: oracle-pending
"""Verifier suite for the rod pack void audit task.

Tests assert both frozen digest locks on the bundled fixtures and a handful
of semantic invariants that would fail if incident ordering, ghosting, or
cluster clipping regressed while digests stayed accidentally aligned.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RPV_DATA_DIR", "/app/rod_lat"))
AUDIT_DIR = Path(os.environ.get("RPV_AUDIT_DIR", "/app/rod_audit"))

OUTPUT_FILES = (
    "cluster_voids.json",
    "cell_snapshots.json",
    "incident_trail.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "0d233f4eef6836ab430d868001d7c4063506e42d5bbfa9157a65117cffb875cb",
    "anchors/cal_note.json": "6bdc8d40d7b1e7089d8d3b15d76dc5578ff42f6ce27d44649d6028eb7e3ac6c7",
    "anchors/window.json": "c7c868c6d771ede23b770d25830c2ca5555a039516fcf82c6e205674c07abf87",
    "ancillary/extra_meta.json": "2ee28c5f1bcd56b8707955da4a64c9e64d1a02951e6857f95d55c9f00c80ed3d",
    "ancillary/ghost_rods.json": "2eca87e98e657b0ab4afa5c944d0ba3c84866967981bfedf91eae8fd183c3224",
    "ancillary/labels.json": "8a66c84ae4344fafe06ccdb30db520c29125b5c4efda1e2ca1edc6499e26f477",
    "cells/c01.json": "06f263b106add199a0fc8a4a323f961b692bff01f93e979f8aaf6f301b701864",
    "cells/c02.json": "9db64507f2d8e4d5f4fe54abda6aa5d83446fdde85325b4f2b76f085bdb9f29f",
    "cells/c03.json": "6d9183cf8dc73b08035d3f7cf2c7a776011b70f663cdb3c5427f355accace738",
    "cells/c04.json": "c529e745834f57d78cc40b33dfcc7af61525b96ca49addb30e47a64ab6264780",
    "cells/c05.json": "bb39a5214a14dfb3df8b339685b334d61bed1c834a987b037cdf1606615004c5",
    "cells/c06.json": "727a854aacf9a856bdce54008e63cad86ef1a6373facaa58f07554e0718a851e",
    "cells/c07.json": "f598dd7240dda663914f3b559a38e9cf905295c56a427a41b4c1b60d5f3b2a97",
    "cells/c08.json": "147cfe4af0f5f0764817ee70b5aab8d09b02999856f92b7b548174b6b56bb229",
    "cells/c09.json": "8a17a87dd88c6698160ea612298d6b74ce0651967c3624900cbf1d15ffeb9c19",
    "cells/c10.json": "d4f55320af9341504c534fd340f979c30425b381afb9b09e921473ed3ad7b871",
    "cells/c11.json": "a604524d72cf34d3eceaeb8bd08e5983b6b7602cbf9736b837434abbf44e9c58",
    "cells/c12.json": "c15d555bbd6795dff0627f9666a7ed5e9a87e3d4cdf198e4faef98d3f44616e9",
    "domain_layout.json": "faf46411e20e4fbd9327a4343a90005a097a1158447b9c21ca128dd5df360282",
    "incident_log.json": "2bea38fdd8cd51b4134b4f79e46e97dea924c11da110d857c7a235fbf8ec112c",
    "policy.json": "abbc1b9d05020c4c9b99f361961b290adbbc97fd74922cc1f56ae5737f10d6c2",
    "pool_state.json": "b271a446a2d7b805dca500b6b3155c1287cfdada4e26fcfc3a3f5567833c720c",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "cell_snapshots.json": "27fd6193be6ecf75c0a382c9545ebc8e80c9ed2aeeb3ec811a446a07ab6aca4c",
    "cluster_voids.json": "6c9c4009d4c3f14ca0ac90855158b97617e9697cebb7c30d873342bbd61d0256",
    "incident_trail.json": "762ca6cfbd1c2c062a39c210cade6fa1ea05a1ad9b913cae2002233baae35743",
    "summary.json": "e9e9e9160df92e5fed13f394fa2ec197c443be842776a0e6b5a58cc3ac073023",
}


EXPECTED_FIELD_HASHES = {
    "cluster_voids.clusters": "88ebad2b08c8b92e72a24f7c1664ede7709bf661bc2fa6f7dc8390518eda3c1b",
    "incident_trail.applied": "95b36e08cef71875dca2b0cc59ba0584d21ae2d3fe68a923c468f96bcd5eeb7c",
    "summary.weighted_void_ppm": "df61f9f8bfae765c9b2c7dbeea597d4bb486a936575c4e50e012f79c4e0aedac",
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

    def test_nested_field_hashes(self, outputs: dict[str, object]) -> None:
        """Nested collections remain stable under canonical serialisation."""
        cv = outputs["cluster_voids.json"]
        assert isinstance(cv, dict)
        clusters = _canonical(cv["clusters"])
        assert (
            _sha256_bytes(clusters.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["cluster_voids.clusters"]
        )

        tr = outputs["incident_trail.json"]
        assert isinstance(tr, dict)
        applied = _canonical(tr["applied"])
        assert (
            _sha256_bytes(applied.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_trail.applied"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        wv = _canonical(sm["weighted_void_ppm"])
        assert (
            _sha256_bytes(wv.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.weighted_void_ppm"]
        )


class TestClusterRollups:
    """Spot-check bundled cluster metrics for clipping and union math."""

    def test_alpha_cluster_metrics(self, outputs: dict[str, object]) -> None:
        """The alpha cluster spans both packing cells and matches the expected union length."""
        clusters = outputs["cluster_voids.json"]["clusters"]
        assert isinstance(clusters, list)
        alpha = clusters[0]
        assert alpha["name"] == "alpha"
        assert alpha["span_len"] == 200
        assert alpha["occupied_len"] == 110
        assert alpha["void_ppm"] == 450000
        assert alpha["segments_used"] == 3

    def test_beta_cluster_metrics(self, outputs: dict[str, object]) -> None:
        """The beta cluster spans the high-side cells with two disjoint rods after clipping."""
        clusters = outputs["cluster_voids.json"]["clusters"]
        beta = clusters[1]
        assert beta["name"] == "beta"
        assert beta["span_lo"] == 300
        assert beta["span_hi"] == 500
        assert beta["occupied_len"] == 138
        assert beta["void_ppm"] == 310000


class TestIncidentSemantics:
    """Incident filtering and ordering checks."""

    def test_applied_incidents_sorted(self, outputs: dict[str, object]) -> None:
        """Applied incidents follow ascending day then event_id order."""
        applied = outputs["incident_trail.json"]["applied"]
        keys = [(int(e["day"]), str(e["event_id"])) for e in applied]
        assert keys == sorted(keys)

    def test_ignored_and_applied_counts(self, outputs: dict[str, object]) -> None:
        """Three incidents are ignored while three eligible incidents mutate rods."""
        tr = outputs["incident_trail.json"]
        sm = outputs["summary.json"]
        assert tr["ignored"] == 3
        assert sm["ignored_incidents"] == 3
        assert sm["applied_incidents"] == 3


class TestCellSnapshots:
    """Post-process rod lists per cell."""

    def test_c01_drops_r1_keeps_ghost_and_nudges(self, outputs: dict[str, object]) -> None:
        """Ghost rod survives, baseline r1 is stripped, and nudges shift remaining rods."""
        cells = {c["cell_id"]: c for c in outputs["cell_snapshots.json"]["cells"]}
        c1 = cells["c01"]
        ids = {r["rod_id"] for r in c1["rods"]}
        assert "r1" not in ids
        assert "g1" in ids
        assert "r2" in ids
        by_id = {r["rod_id"]: r for r in c1["rods"]}
        assert by_id["g1"]["a"] == 40 and by_id["g1"]["b"] == 50
        assert by_id["r2"]["a"] == 65 and by_id["r2"]["b"] == 95

    def test_c02_nudge_shifts_r3(self, outputs: dict[str, object]) -> None:
        """The bundled nudge incident slides the long rod left within its cell."""
        cells = {c["cell_id"]: c for c in outputs["cell_snapshots.json"]["cells"]}
        r3 = next(r for r in cells["c02"]["rods"] if r["rod_id"] == "r3")
        assert r3["a"] == 105 and r3["b"] == 175


class TestSummaryRollups:
    """Summary rollups stay coherent with per-cluster ppm values."""

    def test_weighted_void_matches_span_weighting(self, outputs: dict[str, object]) -> None:
        """Weighted ppm equals integer span-weighted mean of cluster ppm rows."""
        clusters = outputs["cluster_voids.json"]["clusters"]
        num = sum(int(c["void_ppm"]) * int(c["span_len"]) for c in clusters)
        den = sum(int(c["span_len"]) for c in clusters)
        assert den > 0
        assert outputs["summary.json"]["weighted_void_ppm"] == num // den

    def test_ghost_mode_echo(self, outputs: dict[str, object]) -> None:
        """Summary echoes the bundled ghost mode string."""
        assert outputs["summary.json"]["ghost_mode_used"] == "include"
