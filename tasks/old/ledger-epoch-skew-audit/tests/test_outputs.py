"""Verifier suite for ledger-epoch-skew-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("LES_DATA_DIR", "/app/ledger_epoch"))
AUDIT_DIR = Path(os.environ.get("LES_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "merge_order.json",
    "epoch_skew.json",
    "compaction_gates.json",
    "quarantine_closure.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "7db970955356389db41622b8911f2b825bb63243b06ff38c51e32d5f5728d6fa",
    "incidents/active.json": "bfbb68603b76086a31f34b44ee8ddcb763914f42c7a27d25b3cf9650c0764e29",
    "segments/seg-apex.json": "e4878b11d1c31a045ffb0213d1b735fe61cc8ace4e7c5f9e07040e6609136d12",
    "segments/seg-beacon.json": "aafcdd0490b244f03f3414c22a0ea2306bf5f096379e92d7befb48925a6ca229",
    "segments/seg-cedar.json": "f41181a683783272565ee0245eb01a2ec3b1ebe59c524838175c3b7f9d71d840",
    "segments/seg-drift.json": "86f541dee5bad6a84559e8b483596551b41be9091d5ee6016c2bb82f962480c4",
    "segments/seg-ember.json": "ec273431eb7e37f35ff4e4a0e5029725317af415367df5e682874059a46c7878",
    "segments/seg-fold.json": "8f3dc73a69c50f9ff1d0cb3dfe8157867a9f07ebb969744c0259453ff027d3bd",
    "segments/seg-gate.json": "c62dc89f101b94136d9cd959036c642df8a9a02d000605e85c46ee8a3011c6fe",
    "segments/seg-haze.json": "906be36a03773f297d732adfb29c8bc4f03408282ca6b9670b7b1c6042a32bba",
    "segments/seg-iron.json": "58b47dffd364811441597ff07e3efe2af5c65b84273cb60cd86b09708a03a8f4",
    "segments/seg-jade.json": "36224a0af83fd6563f213a09756429f6cddc3eae89a3d4ba226da1c7eeead54c",
    "segments/seg-kite.json": "5c6a2ae5268abbcbf2a7505222a9cba826520d758c5f21be1c536ce010482d39",
    "segments/seg-lava.json": "a0689f7ee249c05029f8cf5d6a3d093b9b1a8be3f9a6149d26774b91686a6d89",
    "segments/seg-mica.json": "f8d8c5124ce36f0442fffb042b70ec2202e4a138d141e83c6863c8fd2e22e1a1",
    "segments/seg-nest.json": "d33d3d647d78331bf1beef3e93ac6f7c5e70c2342782130fd653d66520fe122f",
    "segments/seg-oath.json": "6d9b64f4f6a04658811f7683552a314f40fc84546b9bb5c7add54d6aa71db413",
    "segments/seg-pond.json": "b4742c328fd6ddfe41c64ffdcea285a464216b49769bf85a9e541ee31143ec39",
    "segments/seg-quip.json": "edfa927dc152e1220bdc3aa254aabbd90fa7cf7df996fdaf856801b9c0875de8",
    "segments/seg-rung.json": "4d827c11c3ce70b9e88385cc84be008b1560b8451d7f00012a323d24431ba1d1",
    "segments/seg-silt.json": "1024a9673f0d2de799e692664105627ebdda468472c90cfd91bb75e9e7d0b38d",
    "segments/seg-tack.json": "8f07b1c892e626cc9ca8e75c7934e207ff6ef7dfc460f57ab831e2de32792158",
    "segments/seg-urn.json": "daa0d3df13025b529b18d1d500815c1d914da5ac660498006b94a454bbccc40f",
    "segments/seg-vane.json": "52fd8ead58b6e56382e33a950bc980ebadc2a97637dccf07e3c0b71bc4dce9f8",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "merge_order.json": "58c76089a7fc99c21c67316f5c6e20e94fc6bd63c6972ac433ade6b9ff8e49af",
    "epoch_skew.json": "75f9fb2d84d5f40abfe3677d4b80212ecb6da94ab377aeb08da610214c609c43",
    "compaction_gates.json": "c21c976b74ef37d02b15e9e0a668fb1809d32c06d3af23425fa9bc5f6ed00810",
    "quarantine_closure.json": "75f202e4efa8ea06023ff689d73c6dd18c6451743d35f924ebee8d7ac8c2db90",
    "summary.json": "9b529144cbe9380484b5938ad074f56d49d958197a37013ede1c9fe0b6568da2",
}


EXPECTED_FIELD_HASHES = {
    "epoch_skew.findings": "80fce9faedfb44f9834599d38b28b761bc6e6b62f45608a1a8b9142a18b2bf72",
    "merge_order.ordered_segment_ids": "1f6c9ec78838fa39d2d20c4f28a0a60866f71e4272702a71d8aeb886c3a34237",
    "quarantine_closure.quarantined_segment_ids": "3c5a68fcdad24ad8ecc41686d16fadc1c0169580ebc53202e3edfd56d82f8403",
    "summary.quarantined_total": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
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
        mo = outputs["merge_order.json"]
        assert isinstance(mo, dict)
        assert (
            _sha256_bytes(_canonical(mo["ordered_segment_ids"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["merge_order.ordered_segment_ids"]
        )

        es = outputs["epoch_skew.json"]
        assert isinstance(es, dict)
        assert (
            _sha256_bytes(_canonical(es["findings"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["epoch_skew.findings"]
        )

        qc = outputs["quarantine_closure.json"]
        assert isinstance(qc, dict)
        assert (
            _sha256_bytes(_canonical(qc["quarantined_segment_ids"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["quarantine_closure.quarantined_segment_ids"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["quarantined_total"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.quarantined_total"]
        )


class TestMergeOrder:
    """Behavioral checks for writer-epoch merge ordering."""

    def test_ascii_tie_break_when_writer_epoch_equal(self, outputs: dict[str, object]) -> None:
        """Equal writer epochs break ties by ascending ASCII segment id."""
        mo = outputs["merge_order.json"]
        assert isinstance(mo, dict)
        ordered = mo["ordered_segment_ids"]
        assert isinstance(ordered, list)
        drift_idx = ordered.index("seg-drift")
        ember_idx = ordered.index("seg-ember")
        assert drift_idx < ember_idx


class TestEpochSkewCodes:
    """Positive coverage for documented skew codes."""

    def test_epoch_behind_present(self, outputs: dict[str, object]) -> None:
        """At least one finding uses epoch_behind as defined in the spec."""
        es = outputs["epoch_skew.json"]
        assert isinstance(es, dict)
        findings = es["findings"]
        assert isinstance(findings, list)
        codes = {f.get("code") for f in findings if isinstance(f, dict)}
        assert "epoch_behind" in codes

    def test_epoch_ahead_present(self, outputs: dict[str, object]) -> None:
        """At least one finding uses epoch_ahead as defined in the spec."""
        es = outputs["epoch_skew.json"]
        assert isinstance(es, dict)
        findings = es["findings"]
        assert isinstance(findings, list)
        codes = {f.get("code") for f in findings if isinstance(f, dict)}
        assert "epoch_ahead" in codes

    def test_missing_parent_ref_present(self, outputs: dict[str, object]) -> None:
        """Missing parent references surface as missing_parent_ref findings."""
        es = outputs["epoch_skew.json"]
        assert isinstance(es, dict)
        findings = es["findings"]
        assert isinstance(findings, list)
        hits = [
            f
            for f in findings
            if isinstance(f, dict)
            and f.get("code") == "missing_parent_ref"
            and f.get("segment_id") == "seg-ember"
        ]
        assert hits

    def test_internal_inversion_present(self, outputs: dict[str, object]) -> None:
        """Inverted epoch bounds surface as internal_inversion findings."""
        es = outputs["epoch_skew.json"]
        assert isinstance(es, dict)
        findings = es["findings"]
        assert isinstance(findings, list)
        hits = [
            f
            for f in findings
            if isinstance(f, dict)
            and f.get("code") == "internal_inversion"
            and f.get("segment_id") == "seg-fold"
        ]
        assert hits

    def test_waived_skew_child_has_no_parent_epoch_finding(self, outputs: dict[str, object]) -> None:
        """Waived child ids skip parent-child skew checks per the incident envelope."""
        es = outputs["epoch_skew.json"]
        assert isinstance(es, dict)
        findings = es["findings"]
        assert isinstance(findings, list)
        drift_hits = [
            f
            for f in findings
            if isinstance(f, dict)
            and f.get("segment_id") == "seg-drift"
            and f.get("code") in {"epoch_behind", "epoch_ahead"}
        ]
        assert not drift_hits


class TestQuarantineClosure:
    """Propagation and incident interaction checks."""

    def test_transitive_quarantine_child_of_base_parent(self, outputs: dict[str, object]) -> None:
        """Children of a base-quarantined parent are quarantined unless exempt."""
        qc = outputs["quarantine_closure.json"]
        assert isinstance(qc, dict)
        qset = set(qc["quarantined_segment_ids"])
        assert "seg-jade" in qset

    def test_transitive_exempt_child_not_quarantined(self, outputs: dict[str, object]) -> None:
        """Exempt children do not inherit transitive quarantine from a quarantined parent."""
        qc = outputs["quarantine_closure.json"]
        assert isinstance(qc, dict)
        qset = set(qc["quarantined_segment_ids"])
        assert "seg-kite" not in qset

    def test_forced_quarantine_in_closure(self, outputs: dict[str, object]) -> None:
        """Forced quarantine ids from the incident appear in the closure list."""
        qc = outputs["quarantine_closure.json"]
        assert isinstance(qc, dict)
        qset = set(qc["quarantined_segment_ids"])
        assert "seg-lava" in qset


class TestCompactionGates:
    """Compaction hold interaction with released hold identifiers."""

    def test_released_hold_deactivates_gate(self, outputs: dict[str, object]) -> None:
        """Released hold tokens deactivate matching compaction gates."""
        cg = outputs["compaction_gates.json"]
        assert isinstance(cg, dict)
        gates = cg["gates"]
        assert isinstance(gates, list)
        by_id = {g["segment_id"]: g for g in gates if isinstance(g, dict)}
        assert by_id["seg-gate"]["gate_active"] is False

    def test_unreleased_hold_stays_active(self, outputs: dict[str, object]) -> None:
        """Hold ids not listed as released keep gates active."""
        cg = outputs["compaction_gates.json"]
        assert isinstance(cg, dict)
        gates = cg["gates"]
        assert isinstance(gates, list)
        by_id = {g["segment_id"]: g for g in gates if isinstance(g, dict)}
        assert by_id["seg-haze"]["gate_active"] is True
