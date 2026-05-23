# scaffold-status: oracle-pending
"""Verifier suite for vnode-handoff-ring-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("VHR_DATA_DIR", "/app/vnodering"))
AUDIT_DIR = Path(os.environ.get("VHR_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "handoff_plan.json",
    "move_outcomes.json",
    "ring_violations.json",
    "summary.json",
    "vnode_states.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "78f15d9538d78b8605e80d2efc6866b86e424657ff0c4ba6f6b0d7c6699f1066",
    "anchors/a1.txt": "94f48ae357fe3879cf9db1aa027fdf2935a974a9ef22ca272b00122d5eb892b0",
    "anchors/a2.txt": "354f9fa4d8bf9a6ee817b1fc16423a8ea115d02cc58dd3f11ae67f647d6ac566",
    "ancillary/limits.json": "9145b15095e45c5412ba0aa29e18cb9c9f104acd9c05e290e32a93e985276aab",
    "ancillary/meta.json": "31704a7ffc68febda6a1931f0d43c81d89dc05c7aa750c9606a6c25ebc23a6d8",
    "ancillary/notes.json": "e0f5fcae30068156d37c73608f46020562e6e97bb4d89e3240ffd041cb2d6fcf",
    "ancillary/shards.json": "38d0a8f072717cc15cb6ec2867f68ffa1da486e71afc5f818c0871849b9a006d",
    "epochs.json": "87113d7b11f0f51f0ebfec57796229507e461d86f3c1bf2a22ae95f330266da0",
    "grid/dims.json": "4a2616730345cc9811e954a10396f73951b4066fd965e7a6fb5257cd00485f50",
    "keys.json": "ad0b5a7dbaf4ec9efd3bc43ccd6dd6be60aa6c737716da0d790e0ab7abaf1723",
    "manifest.json": "95aa743be09b33eb6c53641ae3aa3e7c4325dd51805c5f435a9456db9d1f19df",
    "meta/seq.json": "8017ae0f9db02143541fa370c11d93d1e0262a60ca9ac1a06a849bc3a450c42e",
    "moves.json": "7aa90efe8a4daf1d989f9a5fa4c170287e020a1cb4747ace67d62b8fd11713f8",
    "policy.json": "88088a9d3c7e10edbfc8608a6beda26ce2b3bfe696105bb0813135f950d10e74",
    "vnodes/vn_a.json": "37729fa24e94e860139601690b5a9c2f563e5a63d184f42555f113edb03f58a8",
    "vnodes/vn_b.json": "09e200bf83c5468f345e0109b7232379bd95b7759e55f3f2f39d28f2dbeab06f",
    "vnodes/vn_c.json": "c5727d34a66173dbbe9ed0b76f3a2c0a6468fc141817c2c5e64b14bd695ef0c9",
    "vnodes/vn_d.json": "909ee8d036158ed8a6d97b91959ebb23ca4438377b416d7722093872bd48e464",
    "vnodes/vn_e.json": "451440a1421813e56d6e185c2cae7b8d768df7ffdb75abfb4e284481ad4e90a0",
    "vnodes/vn_old.json": "3415153bbb4dc37f6d1c4f888b101f20585371995f2ccad49004de4d61bef27d",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "handoff_plan.json": "1159a65bbbf59c264183f69e3824e9956b86a59ef86282d33bc0c8725da3bb07",
    "move_outcomes.json": "af7deb7d8a158a1b60a8f7d5b4cf1b6ba8fd56b1db4522146e438cefab57aa21",
    "ring_violations.json": "68f4f90072d56372348d70c359d10e2aa3e38f7ccc0541bbf24180a277cd151b",
    "summary.json": "c0da08d149a4302660e3d3890b0ceda4027ec531cebc23f73aad8756b3de9e2a",
    "vnode_states.json": "f95e4e0d967e0643133c4b3ad21a54cd30d82c51cae22fe1909ca32c1d7e905d",
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "handoff_plan.json": "6309f3021500510e81c3f9ba14d3e1cdd7176eddd40812588c85f5f44b9a2659",
    "move_outcomes.json": "04ccd561db6193831b0dc8c18a79d840356df7ab84a4dada00d098b51bd8fc04",
    "ring_violations.json": "5680d371df240094390771ffff9e4893df8a089e9cfa37ce429dc98d64b9b7a5",
    "summary.json": "eca75e71b588f027f0844f2b9dacb41901c9d42f4e81a71dbb5d5101332b9718",
    "vnode_states.json": "e5eb250c89595670f7011f7c1fba0adbd85aed7980e45e838f5e91ead2c331e2",
}

EXPECTED_FIELD_HASHES = {
    "summary.effective_vote_ratio": "ce5d3aa79ae56155078af52e8fac68eb2d0a78489f82bc26c1e1bbc667ba9fde",
}
def _sha256_bytes(data: bytes) -> str:
    """Return hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Minified canonical JSON for hash comparison."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Load UTF-8 JSON from path."""
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

    def test_output_raw_byte_hashes(self) -> None:
        """Each audit file UTF-8 bytes must match normative layout."""
        for name, expected in EXPECTED_OUTPUT_RAW_HASHES.items():
            digest = _sha256_bytes((AUDIT_DIR / name).read_bytes())
            assert digest == expected, f"raw byte mismatch for {name}"

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_output_files_single_trailing_newline(self) -> None:
        """Root JSON objects must end with exactly one line feed after the closing brace."""
        for name in OUTPUT_FILES:
            raw = (AUDIT_DIR / name).read_text(encoding="utf-8")
            assert raw.endswith("}\n"), f"{name} must end with exactly one LF after root brace"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected summary fields must match pinned canonical digests."""
        for key, expected in EXPECTED_FIELD_HASHES.items():
            field = key.split(".", 1)[1]
            val = outputs["summary.json"][field]
            assert _sha256_bytes(_canonical(val).encode()) == expected

class TestVnodeRingSemantics:
    """Semantic checks for vote quorum, ownership, and stale targets."""

    def test_shard_spill_vote_ratio(self, outputs: dict[str, object]) -> None:
        """Mismatched shard tags must raise effective_vote_ratio by spill_penalty."""
        assert outputs["summary.json"]["effective_vote_ratio"] == 0.75

    def test_step4_handoff_rejected(self, outputs: dict[str, object]) -> None:
        """Low agree-weight on a step must reject handoff for k_delta."""
        row = next(
            m for m in outputs["move_outcomes.json"]["moves"]
            if m["step"] == 4 and m["key_id"] == "k_delta"
        )
        assert row["outcome"] == "handoff_rejected"

    def test_step3_handoff_recorded(self, outputs: dict[str, object]) -> None:
        """Accepted ownership change must appear in handoff_plan."""
        handoffs = outputs["handoff_plan.json"]["handoffs"]
        assert any(h["key_id"] == "k_gamma" and h["step"] == 3 for h in handoffs)

    def test_orphan_key_outcome(self, outputs: dict[str, object]) -> None:
        """Keys outside initial ownership must be orphan_key."""
        row = next(
            m for m in outputs["move_outcomes.json"]["moves"]
            if m["key_id"] == "k_missing"
        )
        assert row["outcome"] == "orphan_key"

    def test_stale_target_skipped(self, outputs: dict[str, object]) -> None:
        """Handoff to a stale vnode must be stale_skipped."""
        row = next(
            m for m in outputs["move_outcomes.json"]["moves"]
            if m["key_id"] == "k_alpha" and m["step"] == 7
        )
        assert row["outcome"] == "stale_skipped"

    def test_warmup_skipped_present(self, outputs: dict[str, object]) -> None:
        """Warmup moves must emit warmup_skipped outcomes."""
        outcomes = {m["outcome"] for m in outputs["move_outcomes.json"]["moves"]}
        assert "warmup_skipped" in outcomes
