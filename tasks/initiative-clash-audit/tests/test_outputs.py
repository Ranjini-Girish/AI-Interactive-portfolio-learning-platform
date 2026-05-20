"""Verifier suite for initiative-clash-audit (hard)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("ICA_DATA_DIR", "/app/init_clash"))
AUDIT_DIR = Path(os.environ.get("ICA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ("turn_order.json", "clashes.json", "summary.json")


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "0b9b83d7b86c00614f8e16398af317941673d4c2a61f10e279a8eff4f1d70e13",
    "incidents.json": "a7d05e4d76d26c35df9057bd5e67031ade005f30e99f7049437585e4ce858cdf",
    "loadouts/u01.json": "b0323fdba549839dc4e5ebf7b42b27fad1e0b79595d7f7cfa2c1c6af1db18207",
    "loadouts/u02.json": "2029fb94c546b5a9ddc5937c2557b91b89fe743d2db100f3f91bc9f0e24034f3",
    "loadouts/u03.json": "800013d3615c68c1741dc66e9488aae1b229950d37fb7b8c6b3a2d751e4208eb",
    "loadouts/u04.json": "73596a572101269d2e0499692548b7b3245cf1d980e0ebbfa83978259523b385",
    "loadouts/u05.json": "118e0f8775237df96526fb0a3a544e0a6049c0efadb4f03a4d6db3d05b363af3",
    "loadouts/u06.json": "ea1ad92e7e22cd16a41f7ac2a4b3180cb95230e106e704d89dc90fe039164628",
    "loadouts/u07.json": "2029fb94c546b5a9ddc5937c2557b91b89fe743d2db100f3f91bc9f0e24034f3",
    "loadouts/u08.json": "0e1debb7119e35a0dc60b3d0c6a222e3c2eb7a967cdc7605e480b27eda7ee79a",
    "loadouts/u09.json": "b0323fdba549839dc4e5ebf7b42b27fad1e0b79595d7f7cfa2c1c6af1db18207",
    "loadouts/u10.json": "4ce9436087de02290b4b2989b203c9846596254feef0992be02f84ddcd95c6aa",
    "overclock.json": "166ff0de4f13d7697bb0d33c7c5c322441fc2850e041e3fa7c736125b2823036",
    "policy.json": "2f9ecd26bb1814ae80970cccd660fece94cb70d994d417230ba316bd9048a57d",
    "units/u01.json": "b65c7067c866263a0a5fd3ca7547181f6fe883b2d4e403f0e4b8cf10bf6400a4",
    "units/u02.json": "1d6d28484be173cfb2e9bd4b155419957dac98589413f2285f335a8fcfa907e5",
    "units/u03.json": "38174e9f593dade6ed9e8fffe3b5b9c34139d9828b741203b9bec5b41e04edfb",
    "units/u04.json": "84cb161556958eab98ba1477355b042a7147458fa15f8fef2c973e91fa881cea",
    "units/u05.json": "07e12e69bc4708d0d8cec3680e7e0db8c41b3c7f245e9264d6faa2e93e0dda16",
    "units/u06.json": "308974e3523258849f919fdbc8ac1c87efe1b83469cb89225a44048ddca4386f",
    "units/u07.json": "ce4f3d11bf5cddd77277068bc79535152856285fcbe2087cbfbc18ad35c31d98",
    "units/u08.json": "c1240d7ba97ba8bfd4394528813722350e4680e746105f34464713cc21d45b44",
    "units/u09.json": "41a9f240780a4dbfb9f28751858ec465f193be8f7ef5ea73d1f8b3a9aa023cd0",
    "units/u10.json": "0e1fd2f376bbec94a7572b39b614b1c3e6885bc4fc65bfaf46359520eb1dfb5f",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "turn_order.json": "71f5f84213e5a90a8c71329e33ed44017121394a3a1abba90d5a05f3331ecc51",
    "clashes.json": "b120c28477c5d71babb7c71fea14ea50966fe51c3fa38878643fd519b1234c30",
    "summary.json": "6a262e36e983e4a66a6bc458cb33585875d9bea2180ae41dc9b0931cb05d5d77",
}


EXPECTED_FIELD_HASHES = {
    "clashes.clashes": "dd672ef87e8eb3d71dda516f46b4a7c62583d4599fc1d12ccb0d08e3a3e11918",
    "summary.band_counts": "dc1491cd1a8b1b8f58e66bf88be0a397ffde69e5f493828a0d3f37a197e1d41f",
    "summary.status_counts": "7524143bea5119bee8377bc6b111111d869feccc4a00e8508fffc0e5ffd403da",
    "turn_order.ordered_unit_ids": "2a9f961b1dafb1c31b28db7caa7370efe8419512c6140a56205d24bb05f1be2f",
    "turn_order.per_unit.u03": "d87039150866220e643d53460545e64760892f2c19771e4c703da073feb2242f",
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
        turn = outputs["turn_order.json"]
        assert (
            _sha256_bytes(_canonical(turn["ordered_unit_ids"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["turn_order.ordered_unit_ids"]
        )
        per = turn["per_unit"]
        assert isinstance(per, dict)
        assert (
            _sha256_bytes(_canonical(per["u03"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["turn_order.per_unit.u03"]
        )
        clashes = outputs["clashes.json"]["clashes"]
        assert (
            _sha256_bytes(_canonical(clashes).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["clashes.clashes"]
        )
        summary = outputs["summary.json"]
        assert (
            _sha256_bytes(_canonical(summary["band_counts"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.band_counts"]
        )
        assert (
            _sha256_bytes(_canonical(summary["status_counts"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.status_counts"]
        )


class TestStatusBuckets:
    """Exercise documented status_counts semantics on the bundled roster."""

    def test_status_counts_partition_the_roster(self, outputs: dict[str, object]) -> None:
        """Every unit must land in exactly one summary bucket and the counts must sum."""
        summary = outputs["summary.json"]
        sc = summary["status_counts"]
        total = summary["total_units"]
        assert sc["degraded"] + sc["delayed"] + sc["ready"] == total

    def test_throttled_unit_counts_as_degraded(self, outputs: dict[str, object]) -> None:
        """The throttled skirmisher must be counted under degraded."""
        assert outputs["summary.json"]["status_counts"]["degraded"] >= 1
        row = outputs["turn_order.json"]["per_unit"]["u04"]
        assert isinstance(row, dict)
        assert row["throttled"] is True

    def test_jammed_unit_counts_as_delayed(self, outputs: dict[str, object]) -> None:
        """The jammed skirmisher must be counted under delayed when not throttled."""
        assert outputs["summary.json"]["status_counts"]["delayed"] >= 1
        row = outputs["turn_order.json"]["per_unit"]["u07"]
        assert isinstance(row, dict)
        assert row["jammed"] is True
        assert row["throttled"] is False

    def test_echo_sunk_does_not_increment_delayed(self, outputs: dict[str, object]) -> None:
        """Jam echo units stay ready in status_counts even when sunk in turn order."""
        row = outputs["turn_order.json"]["per_unit"]["u03"]
        assert isinstance(row, dict)
        assert row["echo_sunk"] is True
        assert row["jammed"] is False
        assert outputs["summary.json"]["echo_sink_count"] >= 1


class TestDayFilters:
    """Ensure incident days gate battlefield effects."""

    def test_stale_jam_does_not_flag_u01(self, outputs: dict[str, object]) -> None:
        """A jam on a prior day must not mark u01 as jammed on the policy current_day."""
        row = outputs["turn_order.json"]["per_unit"]["u01"]
        assert isinstance(row, dict)
        assert row["jammed"] is False


class TestClashLedger:
    """Cover clash emission for tied intrinsic bands."""

    def test_clash_lists_u05_and_u06(self, outputs: dict[str, object]) -> None:
        """The bundled roster includes one clash between u05 and u06 at the base score."""
        clashes = outputs["clashes.json"]["clashes"]
        assert isinstance(clashes, list)
        assert len(clashes) == outputs["summary.json"]["clash_count"]
        members = {tuple(c["members"]) for c in clashes if isinstance(c, dict)}
        assert ("u05", "u06") in members

    def test_clash_uses_base_priority_not_stim_boost(self, outputs: dict[str, object]) -> None:
        """Stim must not change the shared_priority_score recorded for a clash row."""
        clashes = outputs["clashes.json"]["clashes"]
        pair = next(c for c in clashes if c["members"] == ["u05", "u06"])
        assert pair["shared_priority_score"] == 55


class TestTurnOrdering:
    """Pin ordering rules inside dense final bands."""

    def test_u05_priority_above_u06_after_stim(self, outputs: dict[str, object]) -> None:
        """Stim raises u05 priority_score above u06 even after rally pulls both into band three."""
        per = outputs["turn_order.json"]["per_unit"]
        assert per["u05"]["priority_score"] > per["u06"]["priority_score"]
        order = outputs["turn_order.json"]["ordered_unit_ids"]
        i5 = order.index("u05")
        i6 = order.index("u06")
        assert i6 < i5

    def test_u10_leads_and_u05_closes(self, outputs: dict[str, object]) -> None:
        """Highest priority skirmisher opens the queue and the jammed gamma anchor closes it."""
        order = outputs["turn_order.json"]["ordered_unit_ids"]
        assert order[0] == "u10"
        assert order[-1] == "u05"

    def test_escort_tail_inverts_priority(self, outputs: dict[str, object]) -> None:
        """Escort-anchored units in the roster tail band sort by ascending priority."""
        order = outputs["turn_order.json"]["ordered_unit_ids"]
        tail = [order.index("u09"), order.index("u08"), order.index("u02")]
        assert tail == sorted(tail)


class TestBraceStackedThrottleSuppress:
    """Cover brace lifts, stacked throttle markers, and stim suppressors."""

    def test_u01_brace_applies_before_blocked_stim(self, outputs: dict[str, object]) -> None:
        """Brace must lift the base stack while suppress cancels the same-day stim bonus."""
        row = outputs["turn_order.json"]["per_unit"]["u01"]
        assert isinstance(row, dict)
        assert row["priority_score"] == 102

    def test_u10_stim_suppressed_keeps_base_score(self, outputs: dict[str, object]) -> None:
        """A stim row paired with suppress must not add stim_delta to u10."""
        row = outputs["turn_order.json"]["per_unit"]["u10"]
        assert isinstance(row, dict)
        assert row["priority_score"] == 108

    def test_u04_double_throttle_moves_two_steps(self, outputs: dict[str, object]) -> None:
        """Two same-day thermal_throttle hits stack before the roster band ceiling."""
        row = outputs["turn_order.json"]["per_unit"]["u04"]
        assert isinstance(row, dict)
        assert row["throttled"] is True
        assert row["intrinsic_band"] == 1
        assert row["final_band"] == 3


class TestEchoPriorityCoupling:
    """Cover optional echo coupling against jammed allies."""

    def test_echo_sink_requires_priority_window(self, outputs: dict[str, object]) -> None:
        """With echo_max_abs_priority_delta set, u03 still couples to the jammed alpha ally."""
        row = outputs["turn_order.json"]["per_unit"]["u03"]
        assert isinstance(row, dict)
        assert row["echo_sunk"] is True
        assert outputs["summary.json"]["echo_sink_count"] >= 1


class TestOverclockSemantics:
    """Validate overclock versus throttle interactions on representative units."""

    def test_u03_shows_overclock_flag(self, outputs: dict[str, object]) -> None:
        """Eligible non-throttled overclock moves must set overclocked true on u03."""
        row = outputs["turn_order.json"]["per_unit"]["u03"]
        assert isinstance(row, dict)
        assert row["overclocked"] is True
        assert row["final_band"] != row["intrinsic_band"]

    def test_u04_suppresses_overclock(self, outputs: dict[str, object]) -> None:
        """Throttling must suppress overclock markers even when lists overlap."""
        row = outputs["turn_order.json"]["per_unit"]["u04"]
        assert isinstance(row, dict)
        assert row["throttled"] is True
        assert row["overclocked"] is False

    def test_u07_defend_blocks_overclock_penalty(self, outputs: dict[str, object]) -> None:
        """Defend stance must ignore overclock list movement when policy blocks it."""
        row = outputs["turn_order.json"]["per_unit"]["u07"]
        assert isinstance(row, dict)
        assert row["final_band"] == row["intrinsic_band"]
        assert row["overclocked"] is False


class TestJamCascade:
    """Cover same-faction proximity jam spreading after direct jams."""

    def test_u06_jammed_by_gamma_cascade(self, outputs: dict[str, object]) -> None:
        """A jammed gamma anchor must cascade to u06 within the bundled slack window."""
        row = outputs["turn_order.json"]["per_unit"]["u06"]
        assert isinstance(row, dict)
        assert row["jammed"] is True

    def test_u03_not_jammed_when_slack_too_tight(self, outputs: dict[str, object]) -> None:
        """Alpha ally u03 stays unjammed when priority delta exceeds jam_cascade_slack."""
        row = outputs["turn_order.json"]["per_unit"]["u03"]
        assert isinstance(row, dict)
        assert row["jammed"] is False
        assert row["echo_sunk"] is True


class TestRallyFactionLift:
    """Cover post-escort rally lifts that drag faction mates into higher bands."""

    def test_rally_pulls_gamma_units_to_tail_band(self, outputs: dict[str, object]) -> None:
        """u06 rally must lift u05 and u06 into the roster tail band after escort anchoring."""
        per = outputs["turn_order.json"]["per_unit"]
        assert per["u05"]["final_band"] == 3
        assert per["u06"]["final_band"] == 3
