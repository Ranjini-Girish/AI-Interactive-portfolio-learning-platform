"""Behavioral tests for the guild-bounty-lattice-audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GBL_DATA_DIR", "/app/bounty"))
AUDIT_DIR = Path(os.environ.get("GBL_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "completion_audit.json",
    "quest_graph.json",
    "guild_ledger.json",
    "cluster_pool.json",
    "incident_trace.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "03c33af1d69e29c3f8eae998581f427fa194c4d822c6c80de14dc32accdf59de",
    "anchors/a1.txt": "f52d41a136460be53eeb985b25db6c6f63fa7dc6b4b8939d30c66b4792fa2ffd",
    "anchors/a2.txt": "f52d41a136460be53eeb985b25db6c6f63fa7dc6b4b8939d30c66b4792fa2ffd",
    "anchors/a3.txt": "f52d41a136460be53eeb985b25db6c6f63fa7dc6b4b8939d30c66b4792fa2ffd",
    "guilds/g-alpha.json": "79106c64837c62ece4fc3afe5a34d6f37ee33b3c0941442a69dee476c1a52d74",
    "guilds/g-beta.json": "d8fbd417ea3a6c7f9fabe4aab0d734e04f1ff0f0ea0b69b09768f012c3a4a3b6",
    "guilds/g-delta.json": "1517b18e984c4e0d5beda8ea2c92ad0716a8ae487a8f04ee6bce8d9e675f8b73",
    "guilds/g-gamma.json": "f6a1d0658dabe062295444379d051ec4a884a85ad0ec74e4755befd5510996f2",
    "incidents.json": "659e6009199572fcba4d8a61d0b249236105ddc7cf1a97fe611cd5a30a3422ff",
    "ledger/seq.json": "489f4d0a83cda0909ad15217d6e52102a9a272342800fa4cc6b331708239f626",
    "ledger/tag.json": "3f61f588efd71c5ad3cd0095b4526d9a9fd323ef11ea35b2dc2634f4b2c47242",
    "policy.json": "6918764f44f785a6e3d533c47bd8af2b00f5e62bff47df2310a2a0cb5f09a0af",
    "pool_state.json": "3446d7a57b8dd12af6838feaf487bfcf6fac4a1d202a7e4631059866db7f0197",
    "quests/q-bear.json": "a358d5281a885881e68c1024a9040907acdd0348fe4838cebfa6cdb34510a9d0",
    "quests/q-cycle-a.json": "1bc38f1bb38e488707de9a4757054e9419434a6297a9717fa9359381951a2ace",
    "quests/q-cycle-b.json": "9c1a576385b298c444ef0c50c928cf0ae679d2775fa6d362e73fbef8e0419cd9",
    "quests/q-dragon.json": "d247db16fdbce2757c32f21cb7538b2eaf5250438fe2a42b3421803dbc7610ea",
    "quests/q-gem.json": "ecfefbea9d6e3ced6df9304894d15b18cd29d4b4af821d3923686004b90b5368",
    "quests/q-honor.json": "22a9c709b48a80e9f3363879b574faf78e2a6258d984ce11a22c56e92397a0e6",
    "quests/q-kite.json": "53d31e6be696a41a74557662a6b4486d132c85350e624ab063147ddc59e23209",
    "quests/q-ore.json": "be256ed4345f900a4372e1e07fef4e6086bc7fc4dddcd3553bdd4e4fba9e34e9",
    "quests/q-salt.json": "b4d60d728213f69509cf02877759ceddea7d40da44b25df012c74396fd2af960",
    "quests/q-trail.json": "cb1154bd925bec3abd6cedbc616cfde234cbdd3244fcc4c5044252ede65fb885",
    "quests/q-wolf.json": "49e66cf080fd93e636872df1f16cd0782c3fe529629f6b0045a452f6665fea63",
    "submissions/g-alpha.json": "899d399bdcc0fb4cc9b4a912b02a44ef256090efa7a679e7617bb94d60f9a165",
    "submissions/g-beta.json": "b6c884b58932fddd57a3275ee4489b8a0b0600139edb4a25774084bee8d7ede3",
    "submissions/g-delta.json": "f7cdec168d409be52d2727ca08ee4944ca220e932c411a1e13ab086a0261ad7f",
    "submissions/g-gamma.json": "2d83790be3bf7ffb8f812e46552d3d5d31ca2bd921a774335c836c23edaa9575",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "completion_audit.json": "1541bb7ad54fe430450285f2f75c0f8727e1edeaf1e9d01e70d982a7c8e9a54d",
    "quest_graph.json": "33ee1b1897b6a0526e75e4cfd21d0fc6a3172fe36c6468fdc7a5417c060f08ad",
    "guild_ledger.json": "b339629a4fda068f7f58f4ea3ba7dd85f7ca2be38f05e9f12d1127aa1438ff3b",
    "cluster_pool.json": "65bbb08192daffd9321742665e261dad6c846346492a8d3ad57a81a589a557d2",
    "incident_trace.json": "f4a5019fc3b758a6bc4442cde11d8eabe22b0fb62fcd8cd0f514ae8a4a981049",
    "summary.json": "46079bced9c21fe97acfb468e2884a5112041afa02a0d92027e17895993fded1",
}

EXPECTED_FIELD_HASHES = {
    "completion_audit.entries": "45529abd43f810d4f63a42e4c2318c3c0af7740e17791573d810f10bcc18b2f3",
    "quest_graph.order": "dd401f6b21cf02fb1c079bdb4f5436d3069dbab7da5d56273dcc05479111b1c5",
    "guild_ledger.guilds": "da8dbba88c68aa28e94567e65a7b688b8f20f6bc1f0412e0faa64b68b3c6f921",
    "cluster_pool.clusters": "47a82652c3f7c3e1ab39f82075e0b84330907702a508143735a6e48aad91a544",
    "summary.by_status": "504ebfaad816e1f4ab2b9cfb9376412659858f0ea462904a5583a03cce8079bb",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"


def _canonical_sha256(value: object) -> str:
    return _sha256_bytes(_canonical(value).encode())


@pytest.fixture(scope="module")
def loaded_outputs():
    out = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing required output file: /app/audit/{name}"
        text = path.read_text(encoding="utf-8")
        out[name] = {"text": text, "obj": json.loads(text)}
    return out


class TestInputIntegrity:
    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_unchanged(self, rel, expected):
        """Each input file's SHA-256 must match the locked baseline."""
        path = DATA_DIR / rel
        assert path.is_file(), f"input file missing: {rel}"
        assert _sha256_bytes(path.read_bytes()) == expected


class TestReportStructure:
    @pytest.mark.parametrize("name", OUTPUT_FILES)
    def test_output_canonical_hash(self, name, loaded_outputs):
        """Canonical SHA-256 of each output must match the locked baseline."""
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        assert actual == EXPECTED_OUTPUT_CANONICAL_HASHES[name]

    def test_summary_top_level_keys(self, loaded_outputs):
        """summary.json exposes the documented top-level keys."""
        keys = set(loaded_outputs["summary.json"]["obj"].keys())
        assert keys == {
            "by_final_payout", "by_preliminary_payout", "by_status",
            "current_day", "guilds_total", "ignored_incident_events",
            "quests_total", "season_id",
        }


class TestFieldHashes:
    def test_completion_entries_field(self, loaded_outputs):
        """completion_audit.entries must canonicalise to the locked hash."""
        v = loaded_outputs["completion_audit.json"]["obj"]["entries"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["completion_audit.entries"]

    def test_quest_graph_order_field(self, loaded_outputs):
        """quest_graph.order must canonicalise to the locked hash."""
        v = loaded_outputs["quest_graph.json"]["obj"]["order"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["quest_graph.order"]

    def test_guild_ledger_field(self, loaded_outputs):
        """guild_ledger.guilds must canonicalise to the locked hash."""
        v = loaded_outputs["guild_ledger.json"]["obj"]["guilds"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["guild_ledger.guilds"]

    def test_cluster_pool_field(self, loaded_outputs):
        """cluster_pool.clusters must canonicalise to the locked hash."""
        v = loaded_outputs["cluster_pool.json"]["obj"]["clusters"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["cluster_pool.clusters"]

    def test_summary_by_status_field(self, loaded_outputs):
        """summary.by_status must canonicalise to the locked hash."""
        v = loaded_outputs["summary.json"]["obj"]["by_status"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["summary.by_status"]


class TestCompletionAudit:
    ALLOWED = {
        "valid", "failed", "void", "tainted", "frozen",
        "blocked_prereq", "chain_blocked",
    }

    def test_entries_sorted(self, loaded_outputs):
        """entries are sorted by guild_id then quest_id."""
        entries = loaded_outputs["completion_audit.json"]["obj"]["entries"]
        keys = [(e["guild_id"], e["quest_id"]) for e in entries]
        assert keys == sorted(keys)

    def test_status_enum_coverage(self, loaded_outputs):
        """Every documented completion status appears in the dataset."""
        seen = {e["status"] for e in loaded_outputs["completion_audit.json"]["obj"]["entries"]}
        assert self.ALLOWED <= seen

    def test_known_void_from_sabotage(self, loaded_outputs):
        """q-wolf rows become void after quest_sabotage."""
        entries = loaded_outputs["completion_audit.json"]["obj"]["entries"]
        row = next(e for e in entries if e["guild_id"] == "g-alpha" and e["quest_id"] == "q-wolf")
        assert row["status"] == "void"
        assert "quest_sabotage" in row["reasons"]

    def test_known_cluster_taint(self, loaded_outputs):
        """Cluster mates of a voided guild are tainted on otherwise valid rows."""
        entries = loaded_outputs["completion_audit.json"]["obj"]["entries"]
        row = next(e for e in entries if e["guild_id"] == "g-beta" and e["quest_id"] == "q-ore")
        assert row["status"] == "tainted"
        assert "cluster_taint" in row["reasons"]

    def test_known_guild_freeze(self, loaded_outputs):
        """guild_freeze marks every row for the named guild frozen."""
        entries = loaded_outputs["completion_audit.json"]["obj"]["entries"]
        for e in entries:
            if e["guild_id"] == "g-delta":
                assert e["status"] == "frozen"
                assert "guild_freeze" in e["reasons"]

    def test_known_chain_blocked(self, loaded_outputs):
        """Quests participating in a prerequisite cycle are chain_blocked."""
        entries = loaded_outputs["completion_audit.json"]["obj"]["entries"]
        row = next(e for e in entries if e["guild_id"] == "g-alpha" and e["quest_id"] == "q-cycle-a")
        assert row["status"] == "chain_blocked"
        assert "cycle" in row["reasons"]

    def test_known_blocked_prereq(self, loaded_outputs):
        """Missing prerequisite completions yield blocked_prereq."""
        entries = loaded_outputs["completion_audit.json"]["obj"]["entries"]
        row = next(e for e in entries if e["guild_id"] == "g-beta" and e["quest_id"] == "q-bear")
        assert row["status"] == "blocked_prereq"
        assert "missing_prereq" in row["reasons"]

    def test_known_failed_witness(self, loaded_outputs):
        """Attempts below min_witness are failed."""
        entries = loaded_outputs["completion_audit.json"]["obj"]["entries"]
        row = next(e for e in entries if e["guild_id"] == "g-beta" and e["quest_id"] == "q-kite")
        assert row["status"] == "failed"
        assert "low_witness" in row["reasons"]

    def test_known_pity_bonus(self, loaded_outputs):
        """A pity streak awards pity_bonus on the next successful completion."""
        entries = loaded_outputs["completion_audit.json"]["obj"]["entries"]
        row = next(e for e in entries if e["guild_id"] == "g-gamma" and e["quest_id"] == "q-gem")
        assert row["status"] == "valid"
        assert "pity_bonus" in row["reasons"]


class TestGuildLedger:
    def test_payout_review_blocked_when_tainted(self, loaded_outputs):
        """payout_review is skipped when the guild has tainted rows."""
        guilds = loaded_outputs["guild_ledger.json"]["obj"]["guilds"]
        beta = next(g for g in guilds if g["guild_id"] == "g-beta")
        assert beta["final_payout"] == "withheld"
        assert "payout_review" not in beta["reasons"]

    def test_payout_review_applies_for_gamma(self, loaded_outputs):
        """A clean guild keeps a winning payout_review override."""
        guilds = loaded_outputs["guild_ledger.json"]["obj"]["guilds"]
        gamma = next(g for g in guilds if g["guild_id"] == "g-gamma")
        assert gamma["final_payout"] == "paid"
        assert "payout_review" in gamma["reasons"]


class TestQuestGraph:
    def test_cycle_present(self, loaded_outputs):
        """Prerequisite cycles are reported in quest_graph.cycles."""
        cycles = loaded_outputs["quest_graph.json"]["obj"]["cycles"]
        assert cycles == [["q-cycle-a", "q-cycle-b"]]


class TestSummary:
    def test_by_status_sums_to_entries(self, loaded_outputs):
        """by_status counts sum to completion_audit entry count."""
        entries = loaded_outputs["completion_audit.json"]["obj"]["entries"]
        by_status = loaded_outputs["summary.json"]["obj"]["by_status"]
        assert sum(by_status.values()) == len(entries)

    def test_guild_and_quest_totals(self, loaded_outputs):
        """summary totals match on-disk guild and quest files."""
        summary = loaded_outputs["summary.json"]["obj"]
        guild_count = len(list((DATA_DIR / "guilds").glob("*.json")))
        quest_count = len(list((DATA_DIR / "quests").glob("*.json")))
        assert summary["guilds_total"] == guild_count
        assert summary["quests_total"] == quest_count
