"""Verifier suite for trap-grid-chain-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("TGC_DATA_DIR", "/app/trapgrid"))
AUDIT_DIR = Path(os.environ.get("TGC_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "trap_states.json",
    "trigger_plan.json",
    "disarm_plan.json",
    "room_status.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "4095199093580e2c0fefd5ecce842d729d3f0a52929ee7c854de6f6f1d6b670d",
    "anchors/a1.txt": "d58b76ef6935b283f63cd1c648d0a0a2a236daeb5160c6fc114f91d56d808441",
    "anchors/a2.txt": "0669e4f2d6a4a61669bbffb5707d53a3df17b72376d071980f2213f1ec2ba903",
    "grid/dims.json": "73f2be6b123b7232bb0a7b59ade19ab75522fe28c7f2ebc6f2124718637cd707",
    "incidents.json": "c4e0343f470c62640232a8ab6168203b0e86117f372bfccbaac4cc27a09f1713",
    "links.json": "7b6b668d3137f7e65b99000bbf3faec28aaa07960fd91e97fed8083c2fccf5dd",
    "manifest/seq.json": "ba3ec5a89c28644af0903bf25c6b6bb8b7a320ffd8df972395eb86a293a59ee3",
    "manifest/tag.json": "9ac8a324807ab8cc4472a3494e2b5006422b38aaeda4a0e2487f56797419e77d",
    "policy.json": "6f5ba9d92747b9ec467d3f597520e56307cd483df0fc727518f50f8f572807a9",
    "pool_state.json": "34c7ac9f42ea261b688a37b2285a4015785fd5b9c4431b6f239e86768e5f3a9e",
    "rooms.json": "a8ee2c655830d2b9fa9277232f80058be8c5db5d2b27a95f17edade8d6074b12",
    "traps/t01.json": "962844331d1947e518dfa911b6abfc524592eecd7e1695b425fbf6bcf957e8e7",
    "traps/t02.json": "d6e6aa2b9b5a695fe87ad4fd5d638533867842f0fe62b62d64835164912d4559",
    "traps/t03.json": "d49fa6d5354c3056ee4f6a086be3f8df6736a9067048f4373113ca81922cf6fe",
    "traps/t04.json": "2ee726d9eceb6420c79285bfa81dc2efb1f6d52ad2bc74dad4f3b992b7b2d765",
    "traps/t05.json": "baba5b9e7d1567962bce172649fff0eaa057d00c2b91775e724540a1bacce979",
    "traps/t06.json": "d09fd0b4101ffc051e9bcf26965abb7499f9f58a39d23138a371e0eeb8d650ef",
    "traps/t07.json": "b891c929084cfe57cc0977ef9623e85bf58c67ea04ae105ae023561b52847a86",
    "traps/t08.json": "b49d599425a1f939fc57ec27fd3c32047eb079e091b311ea4e37e20000d0057c",
    "traps/t09.json": "396ca6266ea5d32e66dc3b407713210f611339a6741a88109176f8e96846cc61",
    "traps/t10.json": "ef4e7010b667b304c343d9f9a3c523fa5658da0ae1638f7ce15e823dfc00699c",
    "traps/t11.json": "a38ddffe274f1071383bb26c173400d2109c028ae7ebe371b4470d2966717721",
    "traps/t12.json": "973f2d3739d974d448fb70c942052c99fd1962491c2483e89c31c84847e1fb89",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "trap_states.json": "c030b6e2e2d35b7b061656fe7d948c20508bd1f7bbe84977a382de8fccb92910",
    "trigger_plan.json": "d65e3c53b2bafe3e67b704c3abcebbf83ca650e6ca8548a1771fb65a55dbf1a6",
    "disarm_plan.json": "f21422daa589c12ee822a8e7dfd3c2e159185ae75363552d77e603d9f342c413",
    "room_status.json": "05394b3b3ce6605a6b5bb223b82d485b365e645c94f6d2ca75f8b064d5cbba3b",
    "summary.json": "041f9be52eb89b18a820e47d28a36afaf5f511f47b486d94c31d8bdcb7b6ab3c",
}

EXPECTED_FIELD_HASHES = {
    "summary.hazardous_rooms": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "trap_states.traps.t03": "5de160857834a7cd95d3f6fac6de7e073895d79b4d866cb06560aec93d709fec",
    "trigger_plan.waves": "f05673cfc3a516aa1fc5e240831691579d9196d57deac42fea1a069b448b5692",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _trap_index(outputs: dict[str, object]) -> dict[str, dict[str, object]]:
    traps = outputs["trap_states.json"]["traps"]
    assert isinstance(traps, list)
    return {row["trap_id"]: row for row in traps if isinstance(row, dict)}


def _disarm_index(outputs: dict[str, object]) -> dict[str, dict[str, object]]:
    entries = outputs["disarm_plan.json"]["entries"]
    assert isinstance(entries, list)
    return {row["trap_id"]: row for row in entries if isinstance(row, dict)}


def _room_index(outputs: dict[str, object]) -> dict[str, dict[str, object]]:
    rooms = outputs["room_status.json"]["rooms"]
    assert isinstance(rooms, list)
    return {row["room_id"]: row for row in rooms if isinstance(row, dict)}


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
        waves = outputs["trigger_plan.json"]["waves"]
        assert (
            _sha256_bytes(_canonical(waves).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["trigger_plan.waves"]
        )
        traps = _trap_index(outputs)
        assert (
            _sha256_bytes(_canonical(traps["t03"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["trap_states.traps.t03"]
        )
        summary = outputs["summary.json"]
        assert (
            _sha256_bytes(_canonical(summary["hazardous_rooms"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.hazardous_rooms"]
        )


class TestChainPropagation:
    """Cover undirected link waves and hop indexing."""

    def test_wave_zero_lists_initial_pulses(self, outputs: dict[str, object]) -> None:
        """Wave zero must include every armed initial pulse plus the forced cooldown trap."""
        waves = outputs["trigger_plan.json"]["waves"]
        assert isinstance(waves, list) and waves
        assert waves[0] == ["t01", "t03", "t09"]

    def test_chain_reaches_t04_on_hop_two(self, outputs: dict[str, object]) -> None:
        """Linked traps must appear on later waves with the documented hop index."""
        traps = _trap_index(outputs)
        assert traps["t04"]["chain_hops"] == 2
        assert traps["t02"]["chain_hops"] == 1

    def test_t10_follows_t09(self, outputs: dict[str, object]) -> None:
        """Hall-d pair must chain from the hall-d seed pulse."""
        waves = outputs["trigger_plan.json"]["waves"]
        assert waves[1] == ["t02", "t10"]


class TestCooldownAndForce:
    """Exercise rearm suppression versus force_pulse override."""

    def test_t11_is_cooldown_suppressed(self, outputs: dict[str, object]) -> None:
        """A pulsed trap still inside rearm cooldown must stay off the trigger plan."""
        traps = _trap_index(outputs)
        assert traps["t11"]["final_state"] == "cooldown_suppressed"
        assert traps["t11"]["chain_hops"] == -1

    def test_t03_force_pulse_triggers(self, outputs: dict[str, object]) -> None:
        """Force pulse must override rearm cooldown for the named trap."""
        traps = _trap_index(outputs)
        assert traps["t03"]["final_state"] == "triggered"
        assert traps["t03"]["chain_hops"] == 0


class TestDisarmStatuses:
    """Pin tier cap, boost, hot cooloff, and sealed blocks."""

    def test_effective_cap_includes_boost(self, outputs: dict[str, object]) -> None:
        """Same-day disarm_boost must raise the silver cap from three to four."""
        assert outputs["disarm_plan.json"]["effective_disarm_cap"] == 4

    def test_t08_blocked_difficulty(self, outputs: dict[str, object]) -> None:
        """Difficulty above the boosted cap must block disarm."""
        assert _disarm_index(outputs)["t08"]["disarm_status"] == "blocked_difficulty"

    def test_t01_blocked_hot(self, outputs: dict[str, object]) -> None:
        """Traps triggered on the evaluation day stay too hot to disarm."""
        assert _disarm_index(outputs)["t01"]["disarm_status"] == "blocked_hot"

    def test_t05_blocked_sealed(self, outputs: dict[str, object]) -> None:
        """Sealed hall-b traps must never be disarmed."""
        assert _disarm_index(outputs)["t05"]["disarm_status"] == "blocked_sealed"

    def test_t12_not_applicable(self, outputs: dict[str, object]) -> None:
        """Disarmed fixtures must use the not_applicable status."""
        assert _disarm_index(outputs)["t12"]["disarm_status"] == "not_applicable"


class TestRoomStatus:
    """Cover room-level sealed, hazardous, and partial classifications."""

    def test_hall_b_sealed(self, outputs: dict[str, object]) -> None:
        """Room seal incidents must mark the entire room sealed."""
        assert _room_index(outputs)["hall-b"]["status"] == "sealed"

    def test_hall_a_hazardous(self, outputs: dict[str, object]) -> None:
        """Any triggered trap must make its room hazardous."""
        assert _room_index(outputs)["hall-a"]["status"] == "hazardous"

    def test_hall_c_partial(self, outputs: dict[str, object]) -> None:
        """Mixed idle, suppressed, and disarmable traps yield partial clearance."""
        assert _room_index(outputs)["hall-c"]["status"] == "partial"


class TestSummaryTotals:
    """Verify aggregate counters align with per-trap rows."""

    def test_summary_counts_match_rows(self, outputs: dict[str, object]) -> None:
        """Summary integers must equal the bundled trap and room classifications."""
        summary = outputs["summary.json"]
        traps = _trap_index(outputs)
        assert summary["trap_total"] == len(traps)
        triggered = sum(1 for t in traps.values() if t["final_state"] == "triggered")
        sealed = sum(1 for t in traps.values() if t["final_state"] == "sealed")
        suppressed = sum(
            1 for t in traps.values() if t["final_state"] == "cooldown_suppressed"
        )
        assert summary["triggered_total"] == triggered
        assert summary["sealed_total"] == sealed
        assert summary["cooldown_suppressed_total"] == suppressed
