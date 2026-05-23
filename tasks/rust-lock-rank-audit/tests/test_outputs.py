# scaffold-status: oracle-pending
"""Verifier suite for rust-lock-rank-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RLR_DATA_DIR", "/app/lockrank"))
AUDIT_DIR = Path(os.environ.get("RLR_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "hold_graph.json",
    "lock_states.json",
    "summary.json",
    "thread_holds.json",
    "trace_outcomes.json",
    "violations.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "a5b2e864eecbeda6bace6dfd4ee693d7c30864e26b89258e4c967275a5184336",
    "anchors/a1.txt": "0081d925ae6ffbf232e997d5fabc1bfe9912e493f69296104270557a5950d63f",
    "anchors/a2.txt": "cd10fbef69a6c7045ac67498cf013dcae238377d34a02657afe06a7ba9ee5605",
    "ancillary/meta.json": "3158eb90c0f126a37600d0c7cc1007ba50cad4a47ef9ef8cfe737087ebcc632f",
    "ancillary/notes.json": "e0f5fcae30068156d37c73608f46020562e6e97bb4d89e3240ffd041cb2d6fcf",
    "epochs.json": "74d0df6b2da068335c9f47cea7a106bda059a331139ac65ba0f0f6873fad0aa0",
    "grid/dims.json": "570390b875276e013dd2350b2669bd1eab9b87b48ac27e343cd4900a510fc874",
    "locks/lk_a.json": "6386ed1ad07803c1269c63253964d604368d2ccea63a53b7b923194cb37caaf1",
    "locks/lk_b.json": "ffd8cf02e1cb0f6a9f74719d4f4e5e959533f8f5d52749db92195f40f1867be8",
    "locks/lk_c.json": "c9e585b2538748d38c970b5bd12e1ec7435ba0ba3f01d574a700d4a1a1457fda",
    "locks/lk_d.json": "31071a15d4ade098d819826f0969a84f88d3109f833b7c937cb12cc173137d26",
    "locks/lk_e.json": "c91cc56bd9dade102f03010974e4b68a6c4428c3cbd7f389d6916d7dc1fe0f52",
    "locks/lk_f.json": "17e490a5c23bc74727a5689fc59174f94466d92b567a3510495be8caa6b39d16",
    "locks/lk_g.json": "4935b04bb8f5ec32b89815ae4ff344352e86c4d0d8596f8b5f499406c43b439c",
    "locks/lk_h.json": "f8c256fe62198c3ae11ead75d1d34f1fe6c2f8a3f6f774373bade1d97b5c3e40",
    "locks/lk_old.json": "c8c0192577eb0270e893000350f3d2dd3fff866f3ac9744f99e4d4d5f4962453",
    "locks/lk_z.json": "960867dd181f45531a5cd2ef477ffd985d8c3259b16f279aeb7b38266970c5cd",
    "manifest.json": "4224393d20336520385dc4ffb0d9b9c1c178754628d77cc0b77243c8f300fcbc",
    "meta/seq.json": "5f13187a33f202a8e711072610ef96aabfc4906f846beba6e67f8ce44056f56e",
    "policy.json": "96a246879de3277d8ed99c8461b2bf17ab7e39820ddb53efffdcf3b6a98ed21d",
    "threads/t1.json": "0cd2d949c8a6c445ade847b825f263d2b05e2238f3d6592c7d58502726456f23",
    "threads/t2.json": "515e2795d360b5a1ca9f0777176a32b73a426e6cf61d549c799715f3f4103840",
    "threads/t3.json": "5f97cebe3c2c86960990a219ef37506c105568ea63acca6e822bc44fe2ad81cc",
    "threads/t4.json": "ede36096d2689fe761796cb49c0e6affbb2f297f194c9e45d7f25e3215f6bad1",
    "trace.json": "c8bf833ecde3a33ab7d348a6e57d6a7c4a4cdd21227616ea2ca6052ca14895ec",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "hold_graph.json": "4727d0a89be7999b4f4d81c4774594c9726b02c1bd8ebcb15a8109edca0d2f92",
    "lock_states.json": "489ec2e7592c8c86f16df439cec6fd3cdf71da0a6727d8182830774e8f481b19",
    "summary.json": "7e798cfec1a13dfd22d5358b872f829979b377425faa0d1e065d88df64db09c4",
    "thread_holds.json": "b7f2ff4bae9cdbaa95d02ba66341e1e7d1faa745aca71a13e7c43c59517ed018",
    "trace_outcomes.json": "683c60124891485354a201a80f68b405c57bb2acd99c60f4d018b29b59b4c1e8",
    "violations.json": "8daad328b825ab2fea35d49ff57cf6ddabf2cb9cb0ed5dd7fbe8c99a71346a76",
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "hold_graph.json": "b4e9b1d90c2ea39e196420b1d5918bfa9a7732cab1abf5ef9ede2cacf4a5bcab",
    "lock_states.json": "c75c7592991cdba5f1474e7d6ef16b145e2568915d56cc9f17b6c9fa12b26e9f",
    "summary.json": "a4a30f0d99f43c3d44affbd5c6563ef3ccd31caae6a9caf9ae04373cff205c47",
    "thread_holds.json": "c55b79eda0326868b3c9325fd640a9f4b76d8b21b87c0a35f43af454d89ce2e4",
    "trace_outcomes.json": "abca0a3e1081023b009a66fd8e9e7770a14f82b98245d70999826dea1adeb1f4",
    "violations.json": "4ec08e733afbdedbe5e18e1f3dacc4253daac0b4aff4337bc97c8debba5e2ee1",
}

EXPECTED_FIELD_HASHES = {
    "summary.effective_rank_base": "f97a13577367c1d604d37c4d2b6242d7193c7ba04aa4d1a64c322b23b2f9bd2a",
    "violations.rank_inversion_step3": "4daf54d8264394aca336c7ea53dfab9e2ac03353358d26e9662f302ea5cf0113",
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
        """Selected nested fields must match pinned canonical digests."""
        for key, expected in EXPECTED_FIELD_HASHES.items():
            top, field = key.split(".", 1)
            if top == "violations":
                row = next(
                    v
                    for v in outputs["violations.json"]["violations"]
                    if v["violation"] == "rank_inversion" and v["step"] == 3
                )
                val = row
            else:
                val = outputs["summary.json"][field]
            assert _sha256_bytes(_canonical(val).encode()) == expected


class TestLockRankSemantics:
    """Semantic checks for rank inversion, conflicts, fences, and stale rows."""

    def test_step3_rank_inversion_outcome(self, outputs: dict[str, object]) -> None:
        """Acquiring a lower-ranked lock while holding a higher-ranked lock is a violation."""
        events = outputs["trace_outcomes.json"]["events"]
        row = next(e for e in events if e["step"] == 3 and e["lock_id"] == "lk_b")
        assert row["outcome"] == "violation"

    def test_step3_conflict_hold_violation(self, outputs: dict[str, object]) -> None:
        """Holding lk_a then acquiring lk_b in the same conflict group is a violation."""
        kinds = {v["violation"] for v in outputs["violations.json"]["violations"]}
        assert "conflict_hold" in kinds

    def test_step9_acquire_known_lock_not_unknown(self, outputs: dict[str, object]) -> None:
        """Acquire on a catalogued lock must not be unknown_lock."""
        events = outputs["trace_outcomes.json"]["events"]
        row = next(e for e in events if e["step"] == 9 and e["lock_id"] == "lk_z")
        assert row["outcome"] != "unknown_lock"

    def test_step11_unknown_lock_on_missing_id(self, outputs: dict[str, object]) -> None:
        """Release on a lock id absent from the catalog must be unknown_lock."""
        events = outputs["trace_outcomes.json"]["events"]
        row = next(e for e in events if e["step"] == 11 and e["lock_id"] == "lk_x")
        assert row["outcome"] == "unknown_lock"

    def test_step10_orphan_release_outcome(self, outputs: dict[str, object]) -> None:
        """Releasing a catalogued lock that is not held must be orphan_release."""
        events = outputs["trace_outcomes.json"]["events"]
        row = next(e for e in events if e["step"] == 10 and e["lock_id"] == "lk_c")
        assert row["outcome"] == "orphan_release"

    def test_step8_stale_skipped_outcome(self, outputs: dict[str, object]) -> None:
        """Stale lock acquire must record stale_skipped without violations."""
        events = outputs["trace_outcomes.json"]["events"]
        row = next(e for e in events if e["step"] == 8 and e["lock_id"] == "lk_old")
        assert row["outcome"] == "stale_skipped"

    def test_warmup_skipped_present(self, outputs: dict[str, object]) -> None:
        """Warmup steps must emit warmup_skipped outcomes."""
        outcomes = {e["outcome"] for e in outputs["trace_outcomes.json"]["events"]}
        assert "warmup_skipped" in outcomes

    def test_profile_halving_effective_rank_base(self, outputs: dict[str, object]) -> None:
        """Mismatched profile and run tags must halve effective_rank_base in summary."""
        assert outputs["summary.json"]["effective_rank_base"] == 50.0

    def test_lk_old_marked_stale(self, outputs: dict[str, object]) -> None:
        """Locks below current_epoch-1 must be stale in lock_states."""
        locks = {r["lock_id"]: r for r in outputs["lock_states.json"]["locks"]}
        assert locks["lk_old"]["stale"] is True
