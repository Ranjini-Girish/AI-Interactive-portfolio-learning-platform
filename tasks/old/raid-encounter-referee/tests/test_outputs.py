"""Behavioral tests for raid-encounter-referee."""

from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

RAID_DIR = Path(os.environ.get("RER_RAID_DIR", "/app/raid"))
RESULTS_DIR = Path(os.environ.get("RER_RESULTS_DIR", "/app/results"))
SRC_DIR = Path(os.environ.get("RER_SRC_DIR", "/app/src"))
BIN_PATH = Path(os.environ.get("RER_BIN_PATH", "/app/bin/referee"))

REQUIRED_OUTPUT_FILES = [
    "bench_plan.json",
    "loot_draft.json",
    "match_cards.json",
    "sanction_board.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "24eb4fa640b494184973dcd67c007abbba852c29246b2f48e637413e02e6ac7f",
    "history/duel_history.json": "6b0f16245c7d4c6e328d03d7e10a77f84c65230462dda52a13155f551271bc8e",
    "incidents/incident_log.json": "23b5509a7ff80d17d98414d1ea201f274fff4aa04af60c03654db1597d9ab858",
    "loot/crates.json": "9f1c0a8b727899565b98c4c2286ba979046fb36beb988f2b2fb69fd632ffc236",
    "players/p01.json": "94fa22d8e76510bb27bb21fda4021f366b18d4ec7626feb74e5173948e0ee826",
    "players/p02.json": "9de061dd40ff2cda6c45c49b3fd6bac2040bab6b8019f86d99b9a3fbf4bfc9c0",
    "players/p03.json": "3c1be5ce1879f85998872d80d9019f807da3ab38ce0c0da263610a8ad1d7b490",
    "players/p04.json": "32faca28590a819a6f7eea4a9824ae6708ab8a5dd81446a7d54adc003fc8a3d2",
    "players/p05.json": "34d7d04b74ff99a6bddddbb17c0cfbc0624a56c9e980703c744954ae9d8643df",
    "players/p06.json": "a175b89ce016358ca11c266f75d6847945ff3b86e0113538fa9a86939a08cf92",
    "players/p07.json": "5cb404ac3bb5f0931e196d5a973bb041c4f8219e9f0070b4ef6a3376a6e128ee",
    "players/p08.json": "1db90bc81a54a6f40beafa03de4db957b798099baa091849f9e99483f5584bf1",
    "players/p09.json": "10cc0d5fe1074c2846a96fac9abef99487e293982e8bafc24b1f93fb5c9dd02b",
    "policy/rules.json": "3554a15d577f39c3ce46f4f1ac5c3bb31cd64b7ba2050f6d62ab38735908ea1e",
    "pool_state.json": "327b0f53e1becdd72a616faa2c66e4c3ff0ebb5a8feb490b6008cc4b08762884",
    "teams/tiers.json": "d687c3a59e8432ccbfb5eef54360288a567e2d129cbd238e608bb50446edb20d",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "bench_plan.json": "2bcfd17a4b7169338085a7faba1d610ad039666f7c3b7f64a254d3165de467b0",
    "loot_draft.json": "9185cd47943536869c6ea6748805cb611b315966f5e11d337b8ba5f5b4aaa962",
    "match_cards.json": "e6b07213ea92a9981346c9807cb3033c0eaaa70b31deab39aa2dfdb35c432b6a",
    "sanction_board.json": "cd05a1888731384d6c4a261b955e22e2f7151558d43114edaf10ab109f2aea85",
    "summary.json": "d5be87516e06998426351f24f099a34e95298bc1d4bb295ca3d2b28c3d22cf8a",
}

EXPECTED_FIELD_HASHES = {
    "bench_plan.players": "10200f8879041e035068bcb7cacee8fffe87a0d0b0d298961de969ea77fbae4e",
    "loot_draft.allocations": "cc6e2ef9fbed765ef8a35a842993718976d72ba555f4cb604b27df267ad1e476",
    "match_cards.byes": "6758f74af1a98a6604ce3bae12cb8cb5713c07aced846effe0d46e460b6575d0",
    "match_cards.matches": "6a6968d0ae1908df47a11c4dbd3717722758faadd33f6b2088407561c8e682b7",
    "sanction_board.players": "c9bc243d1d8f5a9bfe84a4dcbf51135065d9e0d7bc2ad05718b6a608cde0e3b3",
    "summary.active_count": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.bye_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.crates_epic": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.crates_total": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.disqualified_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.duel_count": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.forced_rematch_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.probation_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.suspended_count": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
    "summary.teams_locked_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _canonical_sha256(obj) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        path = RESULTS_DIR / name
        assert path.is_file(), f"missing required output file: /app/results/{name}"
        text = path.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            pytest.fail(f"output /app/results/{name} is not valid JSON: {exc}")
        out[name] = {"text": text, "bytes": text.encode("utf-8"), "obj": obj}
    return out


class TestInputIntegrity:
    """Input fixture files remain byte-identical."""

    @pytest.mark.parametrize("rel", sorted(EXPECTED_INPUT_HASHES))
    def test_input_file_unchanged(self, rel):
        path = RAID_DIR / rel
        assert path.is_file(), f"required input file missing: {path}"
        assert _sha256_bytes(path.read_bytes()) == EXPECTED_INPUT_HASHES[rel]


class TestOutputStructure:
    """Output directory shape and deterministic encoding."""

    def test_only_expected_result_files_exist(self):
        actual = sorted(p.name for p in RESULTS_DIR.iterdir() if p.is_file())
        assert actual == sorted(REQUIRED_OUTPUT_FILES)

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_trailing_newline_exactly_once(self, loaded_outputs, name):
        data = loaded_outputs[name]["bytes"]
        assert data.endswith(b"\n")
        assert not data.endswith(b"\n\n")

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_pretty_canonical_bytes(self, loaded_outputs, name):
        obj = loaded_outputs[name]["obj"]
        expected = (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        assert loaded_outputs[name]["bytes"] == expected

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_object_keys_sorted(self, name):
        ordered = json.loads((RESULTS_DIR / name).read_text(encoding="utf-8"), object_pairs_hook=collections.OrderedDict)
        violations: list[str] = []

        def walk(node, node_path):
            if isinstance(node, collections.OrderedDict):
                keys = list(node.keys())
                if keys != sorted(keys):
                    violations.append(f"{node_path}: {keys}")
                for k, v in node.items():
                    walk(v, f"{node_path}.{k}")
            elif isinstance(node, list):
                for idx, item in enumerate(node):
                    walk(item, f"{node_path}[{idx}]")

        walk(ordered, name)
        assert not violations

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_canonical_hash(self, loaded_outputs, name):
        assert _canonical_sha256(loaded_outputs[name]["obj"]) == EXPECTED_OUTPUT_CANONICAL_HASHES[name]


class TestMatchCards:
    """Match layout, reason coverage, and deterministic field hash."""

    def test_schema(self, loaded_outputs):
        obj = loaded_outputs["match_cards.json"]["obj"]
        assert set(obj.keys()) == {"byes", "matches"}
        assert isinstance(obj["byes"], list)
        assert isinstance(obj["matches"], list)

    def test_reason_coverage(self, loaded_outputs):
        reasons = {m["pairing_reason"] for m in loaded_outputs["match_cards.json"]["obj"]["matches"]}
        assert reasons == {"score_pair", "forced_rematch"}

    def test_byes_sorted(self, loaded_outputs):
        byes = loaded_outputs["match_cards.json"]["obj"]["byes"]
        assert byes == sorted(byes)

    def test_field_hashes(self, loaded_outputs):
        obj = loaded_outputs["match_cards.json"]["obj"]
        assert _canonical_sha256(obj["matches"]) == EXPECTED_FIELD_HASHES["match_cards.matches"]
        assert _canonical_sha256(obj["byes"]) == EXPECTED_FIELD_HASHES["match_cards.byes"]


class TestLootDraft:
    """Loot allocation constraints and deterministic hash lock."""

    def test_schema(self, loaded_outputs):
        rows = loaded_outputs["loot_draft.json"]["obj"]["allocations"]
        assert rows and isinstance(rows, list)
        assert [r["crate_id"] for r in rows] == sorted(r["crate_id"] for r in rows)

    def test_probation_cannot_win_epic(self, loaded_outputs):
        statuses = {
            p["player_id"]: p["status"]
            for p in loaded_outputs["sanction_board.json"]["obj"]["players"]
        }
        for row in loaded_outputs["loot_draft.json"]["obj"]["allocations"]:
            if row["rarity"] == "epic":
                assert statuses[row["awarded_to"]] != "probation"

    def test_field_hash(self, loaded_outputs):
        rows = loaded_outputs["loot_draft.json"]["obj"]["allocations"]
        assert _canonical_sha256(rows) == EXPECTED_FIELD_HASHES["loot_draft.allocations"]


class TestSanctionBoard:
    """Status coverage and lockout cascade behavior."""

    def test_status_coverage(self, loaded_outputs):
        statuses = {p["status"] for p in loaded_outputs["sanction_board.json"]["obj"]["players"]}
        assert statuses == {"active", "probation", "suspended", "disqualified"}

    def test_jade_team_lockout_cascade(self, loaded_outputs):
        by_id = {p["player_id"]: p for p in loaded_outputs["sanction_board.json"]["obj"]["players"]}
        assert "raid_lockout" in by_id["p07"]["sources"]
        assert "raid_lockout" in by_id["p08"]["sources"]
        assert "raid_lockout" in by_id["p09"]["sources"]
        assert by_id["p07"]["status"] == "suspended"
        assert by_id["p08"]["status"] == "disqualified"
        assert by_id["p09"]["status"] == "suspended"

    def test_locked_team_excluded_from_matches_and_bench(self, loaded_outputs):
        locked_players = {"p07", "p08", "p09"}
        match_ids = set(loaded_outputs["match_cards.json"]["obj"]["byes"])
        for m in loaded_outputs["match_cards.json"]["obj"]["matches"]:
            match_ids.add(m["red_player"])
            match_ids.add(m["blue_player"])
        bench_ids = {r["player_id"] for r in loaded_outputs["bench_plan.json"]["obj"]["players"]}
        assert not (locked_players & match_ids)
        assert not (locked_players & bench_ids)

    def test_field_hash(self, loaded_outputs):
        rows = loaded_outputs["sanction_board.json"]["obj"]["players"]
        assert _canonical_sha256(rows) == EXPECTED_FIELD_HASHES["sanction_board.players"]


class TestBenchPlan:
    """Bench-state coverage and deterministic row hash."""

    def test_bench_state_coverage(self, loaded_outputs):
        states = {r["bench_state"] for r in loaded_outputs["bench_plan.json"]["obj"]["players"]}
        assert states == {"forced_bench", "hold", "rotate"}

    def test_sort_order(self, loaded_outputs):
        state_rank = {"forced_bench": 0, "hold": 1, "rotate": 2}
        rows = loaded_outputs["bench_plan.json"]["obj"]["players"]
        keys = [(state_rank[r["bench_state"]], r["player_id"]) for r in rows]
        assert keys == sorted(keys)

    def test_field_hash(self, loaded_outputs):
        rows = loaded_outputs["bench_plan.json"]["obj"]["players"]
        assert _canonical_sha256(rows) == EXPECTED_FIELD_HASHES["bench_plan.players"]


class TestSummary:
    """Summary schema and per-key canonical hashes."""

    def test_summary_keys(self, loaded_outputs):
        expected = {
            "active_count",
            "bye_count",
            "crates_epic",
            "crates_total",
            "disqualified_count",
            "duel_count",
            "forced_rematch_count",
            "probation_count",
            "suspended_count",
            "teams_locked_count",
        }
        assert set(loaded_outputs["summary.json"]["obj"].keys()) == expected

    @pytest.mark.parametrize(
        "key",
        sorted(k.split(".", 1)[1] for k in EXPECTED_FIELD_HASHES if k.startswith("summary.")),
    )
    def test_summary_key_hashes(self, loaded_outputs, key):
        actual = _canonical_sha256(loaded_outputs["summary.json"]["obj"][key])
        assert actual == EXPECTED_FIELD_HASHES[f"summary.{key}"]


class TestImplementationLanguage:
    """The deliverable must be produced by a Go binary."""

    def test_go_source_present(self):
        assert SRC_DIR.is_dir(), f"{SRC_DIR} must exist"
        go_files = list(SRC_DIR.rglob("*.go"))
        assert go_files, f"no .go files found under {SRC_DIR}"
        has_main = False
        for go_file in go_files:
            text = go_file.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^\s*package\s+main\b", text, re.MULTILINE):
                has_main = True
                break
        assert has_main, "no Go file declares package main"

    def test_binary_present(self):
        assert BIN_PATH.is_file(), f"{BIN_PATH} must exist"
        assert os.access(BIN_PATH, os.X_OK), f"{BIN_PATH} must be executable"

    def test_binary_reproduces_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env["RER_DATA_DIR"] = str(RAID_DIR)
            env["RER_RESULTS_DIR"] = td
            result = subprocess.run(
                [str(BIN_PATH)],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, (
                f"binary exit code {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
            for name in REQUIRED_OUTPUT_FILES:
                expected = (RESULTS_DIR / name).read_bytes()
                actual = (Path(td) / name).read_bytes()
                assert expected == actual
