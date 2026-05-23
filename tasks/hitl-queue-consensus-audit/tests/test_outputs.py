"""Behavioral tests
 for the hitl-consensus-queue-audit task.

These tests assert the agent's outputs against the documented contract in
``instruction.md`` and ``/app/hitl/SPEC.md``. Hash-locked anti-cheat
fixtures are computed independently from the input data and compared
against the agent's emitted JSON files; an agent cannot pass these tests
by writing arbitrary or hand-tweaked output.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("HCQ_DATA_DIR", "/app/hitl"))
AUDIT_DIR = Path(os.environ.get("HCQ_AUDIT_DIR", "/app/audit"))

REQUIRED_OUTPUT_FILES = [
    "annotator_reliability.json",
    "compliance_flags.json",
    "consensus_report.json",
    "queue_order.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "663223ba149e852006f7354ee89450b42180e28945ab347ab2af8b96cfe92f20",
    "annotators/alice.json": "3a6a8b00ff4612ea8d150174a9089691a5216a5ee6d73f763b7d89d19a9c7535",
    "annotators/bob.json": "36bd9cd725c72c3bd2d7efba4b08fb1e4fb0ce07e01b8aa54b449c4eb06bf906",
    "annotators/carol.json": "6cccbac6ad1d66975db947f0eb48fdd928c050c65a0d796560b00f858cb5b881",
    "annotators/dave.json": "da3e59f1cf27653da70ac8a1097ce8013cefa7996f1f4ee64234213d34ffd3fc",
    "annotators/eddie.json": "051a0bc572971c7a58e3d28831d8a03f302f5f091085d4b2d0b884afc49de28a",
    "annotators/frank.json": "85fa3b65fe145f840f0290407e4f22dddb539a11294df30bde72e502c08c7a12",
    "batches/ba.json": "fbf223afb89ec0a6769427baef39cce2de49335f28abde4b21f392e2877fcbab",
    "batches/bb.json": "1fd1e1a000619bfca1fe6696e0a0a3ad2f3ac20558f804206229b227b463fed5",
    "batches/bf.json": "16c8968a9160b313bd31d22ad536da2030205e82fe35cac1ce1eada5f4be7336",
    "batches/bn.json": "39a4b2ef36087ee51cd9ec3683ab7087f64e9a844adc8d3812c7c9891bcf2a17",
    "batches/bq.json": "6bd2e7ee36ee745b5f9dae0f658ea2d31f57e602b7be1a41315da1412cda1409",
    "incident_log.json": "52ee4f2f9dd8b0851d3e31fae75e323eb6264637bd1e6f9f199e2d428491b1e8",
    "items/item-fz.json": "a75a146f3b350f1f68dec8290303ed2899d80fd946170b1be5efca75df9d69b6",
    "items/item-g1.json": "54a2eb8ea4115a12741aedb0a8b2af37e689950c189c8f1bfd15315865baca5b",
    "items/item-o1.json": "c2d4c3b7026ce054ace2fbb628adf2565536662a6cae4619f633a1475009bd3b",
    "items/item-o2.json": "8472c1288de51f6987165654c6117caa50298049e9f312ae2b07ef49e323e872",
    "items/item-o3.json": "c3449a631869ccd769dd54d2b99e1992da11b0c8f39de7a03be6f2d105a9fcf9",
    "items/item-o4.json": "902a1a80dcfc738c459bc0dd643f1116565f8cbe9b2faa44ad1597cee1b21a7d",
    "items/item-o6.json": "d352fd15def7ecdbdbee8ac27e284b353d4ff4bd6e2ebf3093911371a3be3df9",
    "items/item-tie.json": "f8ce6b5e276df361ff34aaf925212adcbddbe7cfc5a03ecd3b1b4ce9f042a85a",
    "policy.json": "afbfdd1dc56f1095588e2a44da7808202bb64d12a7b3ca76cae117f3184ec6c1",
    "pool_state.json": "20ec1cb7eaffa1d97408915448e5e75d1c3e7c04a6a5eb4e5727a975607ca696",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "annotator_reliability.json": "3b00b652b8ec8d3155f00215573f225a1b88da43214c823e931d9209efd11c2f",
    "compliance_flags.json": "49f7dec062e0470a5cef114dda76eef17dfe3202db6d7634fd50e43cda206160",
    "consensus_report.json": "78ff925459eba178504862a941c75b80b199e9f1f4f1a632d0f1ca4b7b4a7c0d",
    "queue_order.json": "f87be0e35ea0ab7129588207d87dbac11add67648919cf93ec6271e0502d9dde",
    "summary.json": "8daf35ed9c749adc7c8b30e833fc6763cdf48ecd00923a6a76036b2f106a7987",
}

EXPECTED_FIELD_HASHES = {
    "annotator_reliability.annotators": "4e85ba661382e17c57f6e4ab7237c6785a1dba4f3e6f448b2d9804175c64fdb5",
    "compliance_flags.flags": "614af7bb7ffe2cb8551fac937ad0ea16f2dcc8d1dc7d0cbdec5b988150b0c5e4",
    "consensus_report.items": "28bedfe0c090932b70c8bdf76271aa1448aa5746553d37d246c0de28014a43b7",
    "queue_order.backlog": "a2a4e03b47c80d45341c32c378c6cb59cee03fede6a151193e4bcd7abe5d09ee",
    "summary.audit_version": "e1052f233bfca615eab04f9ceaebd208a2e1e16d7bcc2cf080b355c78ad211b3",
    "summary.blocked_batches": "827d42131a00993e083d4a4e1e8f9fc4f58333b796a51ee77384297842a17457",
    "summary.by_status": "10f460fcedf811011df107d93de21d50df4d6d3a82dfbab162a3778cda3867a2",
    "summary.current_day": "9a92adbc0cee38ef658c71ce1b1bf8c65668f166bfb213644c895ccb1ad07a25",
    "summary.ignored_incidents": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.totals": "701013dbd2da9bbb7cc175589bce08064ad0e516eeb617a9a88904c0aadca6a8",
}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: {AUDIT_DIR.as_posix()}/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output {AUDIT_DIR.as_posix()}/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


class TestInputIntegrity:
    """Inputs must remain byte-identical to the original fixtures."""

    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_unchanged(self, rel, expected):
        """Each input file's canonical SHA-256 must match the locked baseline."""
        p = DATA_DIR / rel
        assert p.is_file(), f"missing input fixture: hitl/{rel}"
        if p.suffix == ".json":
            obj = json.loads(p.read_text(encoding="utf-8"))
            actual = _canonical_sha256(obj)
        else:
            actual = _sha256_bytes(p.read_bytes())
        assert actual == expected, f"input fixture hitl/{rel} was modified"


class TestReportStructure:
    """The five output files must exist with the right top-level shape and canonical encoding."""

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_required_file_exists(self, name, loaded_outputs):
        """Every required output file must be present and parseable."""
        assert name in loaded_outputs

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_canonical_hash_each_file(self, name, loaded_outputs):
        """Each output file must hash to the locked canonical baseline."""
        assert _canonical_sha256(loaded_outputs[name]["obj"]) == EXPECTED_OUTPUT_CANONICAL_HASHES[name]

    def test_files_are_pretty_printed(self, loaded_outputs):
        """Every output file must use 2-space indent and end with one trailing newline."""
        for name, data in loaded_outputs.items():
            text = data["text"]
            assert text.endswith("\n"), f"{name} must end with a newline"
            assert not text.endswith("\n\n"), f"{name} must not end with multiple newlines"
            expected = json.dumps(data["obj"], indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            assert text == expected, f"{name} is not canonical 2-space indented sorted JSON"

    def test_top_level_keys_exactly(self, loaded_outputs):
        """Each output file must contain exactly its documented top-level keys."""
        expected_keys = {
            "annotator_reliability.json": {"annotators"},
            "compliance_flags.json": {"flags"},
            "consensus_report.json": {"items"},
            "queue_order.json": {"backlog"},
            "summary.json": {
                "audit_version",
                "blocked_batches",
                "by_status",
                "current_day",
                "ignored_incidents",
                "totals",
            },
        }
        for name, keys in expected_keys.items():
            assert set(loaded_outputs[name]["obj"].keys()) == keys, (
                f"{name} top-level keys must equal {sorted(keys)}"
            )


class TestFieldHashes:
    """Field-level hashes catch silent drift inside nested structures."""

    @pytest.mark.parametrize("field,expected", sorted(EXPECTED_FIELD_HASHES.items()))
    def test_field_hash(self, field, expected, loaded_outputs):
        """Each named field must match its locked canonical hash."""
        file_name, _, path = field.partition(".")
        obj = loaded_outputs[f"{file_name}.json"]["obj"]
        cur = obj
        for part in path.split("."):
            cur = cur[part]
        assert _canonical_sha256(cur) == expected, f"field {field} drifted"


class TestConsensusSemantics:
    """Spot-check statuses that depend on interacting policy rules."""

    def test_frozen_batch_blocks_open_item(self, loaded_outputs):
        """A frozen batch forces blocked_freeze with null labels."""
        rows = {r["item_id"]: r for r in loaded_outputs["consensus_report.json"]["obj"]["items"]}
        fz = rows["item-fz"]
        assert fz["status"] == "blocked_freeze"
        assert fz["final_label"] is None

    def test_calibration_gold_locks_label(self, loaded_outputs):
        """Gold items ignore majority disagreement."""
        rows = {r["item_id"]: r for r in loaded_outputs["consensus_report.json"]["obj"]["items"]}
        g1 = rows["item-g1"]
        assert g1["status"] == "gold_locked"
        assert g1["final_label"] == "pos"

    def test_quorum_bump_increases_requirement(self, loaded_outputs):
        """Batch-scoped quorum bumps raise the distinct-voter floor."""
        rows = {r["item_id"]: r for r in loaded_outputs["consensus_report.json"]["obj"]["items"]}
        o3 = rows["item-o3"]
        assert o3["status"] == "insufficient_quorum"
        assert o3["required_distinct"] == 3

    def test_low_confidence_when_below_winner_floor(self, loaded_outputs):
        """Open items with thin totals stay low_confidence but still name a label."""
        rows = {r["item_id"]: r for r in loaded_outputs["consensus_report.json"]["obj"]["items"]}
        o4 = rows["item-o4"]
        assert o4["status"] == "low_confidence"
        assert o4["final_label"] == "pos"

    def test_weighted_runner_up_on_open_item(self, loaded_outputs):
        """Runner-up reflects the second distinct weighted total."""
        rows = {r["item_id"]: r for r in loaded_outputs["consensus_report.json"]["obj"]["items"]}
        o2 = rows["item-o2"]
        assert o2["status"] == "resolved"
        assert o2["final_label"] == "neg"
        assert o2["runner_up_label"] == "pos"


class TestQueueSemantics:
    """Backlog ordering must follow SPEC tie-breakers."""

    def test_queue_excludes_ineligible_statuses(self, loaded_outputs):
        """Frozen and quorum-short items never appear in backlog."""
        bl = loaded_outputs["queue_order.json"]["obj"]["backlog"]
        ids = {r["item_id"] for r in bl}
        assert "item-fz" not in ids
        assert "item-o3" not in ids
        assert "item-o6" not in ids

    def test_queue_ranks_are_dense(self, loaded_outputs):
        """Ranks are contiguous starting at one."""
        bl = loaded_outputs["queue_order.json"]["obj"]["backlog"]
        ranks = [r["rank"] for r in bl]
        assert ranks == list(range(1, len(ranks) + 1))


class TestReliabilitySemantics:
    """Annotator summaries reflect gold mistakes and active scalers."""

    def test_bob_has_gold_disagreement_and_halving(self, loaded_outputs):
        """Bob disagreed on calibration gold and is flagged as halved."""
        rows = {r["annotator_id"]: r for r in loaded_outputs["annotator_reliability.json"]["obj"]["annotators"]}
        bob = rows["bob"]
        assert bob["gold_disagreements"] >= 1
        assert bob["weight_halved"] is True
