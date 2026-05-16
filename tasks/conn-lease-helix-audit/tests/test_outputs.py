"""Behavioral tests for the conn helix lease audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CLA_DATA_DIR", "/app/connhelix"))
AUDIT_DIR = Path(os.environ.get("CLA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "wrapper_verdicts.json",
    "reclaim_events.json",
    "pool_counters.json",
    "freeze_echo.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "f8e802fb5fbf79f96b111b4b4caf624218309bd5984945163f7024ba626a699f",
    "anchors/anchor_a.txt": "d5b95f3e4e57915daf7ea0d482e4255e596869da47025c5b4257a48b41ed8542",
    "anchors/anchor_b.txt": "5e70d791d6c9a321224c413cbf639cfc5431b7f346fe3a862298bd9a034e4a63",
    "anchors/anchor_c.txt": "143fc0e5cd06d2efde2997a27a53d0679951eaf01e2afec2da3efff135ae1010",
    "ancillary/ci_guard.json": "4580708db19b1d964fcd82ec0cf886bd9ea07d9f7719429a884802a76dd12376",
    "ancillary/pack_meta.json": "6506b77e7fe396ff0ac815da5d8d715e4f284abfeab8dcb2ad78057687cdb61d",
    "freeze_windows.json": "f9ad9331b8419f8010fa55ea2f69d6cc31ffc746cd39103e37a084125f67f729",
    "ledger/channel_tag.json": "d2579cb9aec47c6c952eb80ff89244ec078cac2297fd19f40d102165f0624ebb",
    "ledger/ci_guard.json": "f5ef9b929a5cd47393aa715612c7f88a4c634a2ec9f1c1ef30aecae9ace987f4",
    "policy.json": "9ce9168d3d63e5785ec4086401da70b596d4c7fd31659c17b6454d7974901d82",
    "pool_state.json": "f1e210eb78671cb2824139c28678617be0401170a879aa01848f43c5881253bc",
    "wrappers/w01.json": "8a19d5674fbe260d6d3dbfa693b3deb1b37516c95d88dd4f629afd437a8ca46a",
    "wrappers/w02.json": "809d4798f68f14b8fab4432297fa727f1404798f0e11a5958afd27d8070f7c1e",
    "wrappers/w03.json": "560b928efa329975d2249bcdd5b718f06b725b91fbf0a973d7224b35483555bc",
    "wrappers/w04.json": "e7bfec5a51a1bc92ea9f90881728afbf707eb38eda7fd03d6bfeb75f8782d483",
    "wrappers/w05.json": "30ff22ae45257a639a991a9c21ac66e1b269fb0813210a33bdfb853404ba0383",
    "wrappers/w06.json": "67e94ebddd1d1e2ebde49aa88baf4207265cb3a7488eb46cb1f0fda6597a8a7f",
    "wrappers/w07.json": "19025885c3ea4873504ad0816b35f2de2772ae5560a6c2c08eb5734503b806f2",
    "wrappers/w08.json": "99b3e411618dd7e218f9bd05973d28d7d2f3da593542310802b730e221c0eacb",
    "wrappers/w09.json": "d508a28a23be830cf76f3fd5af2ed0a698e0e635df652cdb37a3e3be37d5a203",
    "wrappers/w10.json": "f82e57dd534bc262cadec11d08721df16a9828ee34ff8b120dc22fb8f904d5c8",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "freeze_echo.json": "bc6842f1662b361c4b5c2f9eced205ed2e9014bb716a9e70ddc49d44b2eccbf5",
    "pool_counters.json": "50c8877e56f1d4f26a5d9d6f403a2fa3e34df06af1009cfee16c99ada828dfd7",
    "reclaim_events.json": "4e24fea989cd267a391ad557c9bf086a7435e1ee1d3510b1f2108a26021ec7bc",
    "summary.json": "9692b17adaa4b2a65f9762473cb3ee6eeb07de99555f7a2fd69dd9bd99b4fa19",
    "wrapper_verdicts.json": "11947414d9a95a6d54de19998bbbc3853de6d5965ed97f4c3fcee873e97689b0",
}


EXPECTED_FIELD_HASHES = {
    "pool_counters.idle_evictions": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.segments": "a3e185260009ab5be7bb16f3bed296075f27322fb87d99209710a28ef3e8d99e",
    "summary.unique_verdicts": "3a6305033b3d166d859d7f8a5bd8f98a0df1bc5432227cd9b7cbe945384cf44f",
    "wrapper_verdicts.wrappers": "73c67af1ed74f334138730d364e7f7b0a7c3b9fa7f915c3ebe9c055affc6bf51",
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
        wv = outputs["wrapper_verdicts.json"]
        assert isinstance(wv, dict)
        assert (
            _sha256_bytes(_canonical(wv["wrappers"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["wrapper_verdicts.wrappers"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in ("segments", "unique_verdicts"):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )

        pc = outputs["pool_counters.json"]
        assert isinstance(pc, dict)
        assert (
            _sha256_bytes(_canonical(pc["idle_evictions"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["pool_counters.idle_evictions"]
        )


class TestWrapperOrdering:
    """Deterministic ordering rules on wrapper rows."""

    def test_wrapper_rows_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`wrappers` must list rows in ascending ASCII `wrapper_id` order."""
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        assert isinstance(rows, list)
        ids = [str(r["wrapper_id"]) for r in rows]
        assert ids == sorted(ids)


class TestReclaimOrdering:
    """Reclaim journal reflects leak-first ordering then idle walk order."""

    def test_leaks_precede_idle_reclaims(self, outputs: dict[str, object]) -> None:
        """All leak rows precede idle rows, with leak ties broken by wrapper id."""
        evs = outputs["reclaim_events.json"]["events"]
        assert isinstance(evs, list)
        kinds = [str(e["kind"]) for e in evs]
        first_idle = next((i for i, k in enumerate(kinds) if k == "idle_reclaim"), len(kinds))
        assert all(k == "leak_reclaim" for k in kinds[:first_idle])
        leaks = [e for e in evs if str(e["kind"]) == "leak_reclaim"]
        keys = [(int(e["lease_ms"]), str(e["wrapper_id"])) for e in leaks]
        assert keys == sorted(keys, key=lambda t: (-t[0], t[1]))

    def test_idle_reclaim_sequence_matches_spec_walk(self, outputs: dict[str, object]) -> None:
        """Idle reclaims follow ascending entered-idle time with stable wrapper id tie breaks."""
        evs = outputs["reclaim_events.json"]["events"]
        idle_ids = [str(e["wrapper_id"]) for e in evs if str(e["kind"]) == "idle_reclaim"]
        assert idle_ids == ["w08", "w10", "w03", "w06"]


class TestVerdictSemantics:
    """Spot-check bundled wrappers that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], wid: str) -> dict[str, object]:
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("wrapper_id") == wid:
                return r
        raise AssertionError(f"missing wrapper row {wid}")

    def test_long_lease_surfaces_leak_verdict(self, outputs: dict[str, object]) -> None:
        """`w01` exceeds the lease ceiling and is reclaimed as a leak."""
        r = self._row(outputs, "w01")
        assert r["verdict"] == "reclaimed_leak"

    def test_tight_idle_age_stays_healthy(self, outputs: dict[str, object]) -> None:
        """`w04` sits exactly on the idle timeout boundary and must remain healthy idle."""
        r = self._row(outputs, "w04")
        assert r["verdict"] == "healthy_idle"

    def test_segment_freeze_preserves_idle(self, outputs: dict[str, object]) -> None:
        """`w05` is on a frozen segment and keeps the freeze preservation verdict."""
        r = self._row(outputs, "w05")
        assert r["verdict"] == "idle_preserved_freeze"

    def test_short_lease_stays_healthy_leased(self, outputs: dict[str, object]) -> None:
        """`w07` remains leased with a lease span under the configured ceiling."""
        r = self._row(outputs, "w07")
        assert r["verdict"] == "healthy_leased"

    def test_second_segment_leak(self, outputs: dict[str, object]) -> None:
        """`w09` mirrors the long-lease leak path on the gamma segment."""
        r = self._row(outputs, "w09")
        assert r["verdict"] == "reclaimed_leak"


class TestPoolCounters:
    """Counters line up with final verdict tallies."""

    def test_counters_match_verdicts(self, outputs: dict[str, object]) -> None:
        """Pool counters must echo the verdict counts implied by the wrapper table."""
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        pc = outputs["pool_counters.json"]
        assert isinstance(rows, list) and isinstance(pc, dict)

        def cnt(v: str) -> int:
            return sum(1 for r in rows if isinstance(r, dict) and str(r.get("verdict")) == v)

        assert int(pc["leak_reclaims"]) == cnt("reclaimed_leak")
        assert int(pc["idle_evictions"]) == cnt("reclaimed_idle")
        assert int(pc["idle_preserved_freeze"]) == cnt("idle_preserved_freeze")
        assert int(pc["idle_retained_cap"]) == cnt("idle_retained_cap")
        assert int(pc["healthy_leased_remaining"]) == cnt("healthy_leased")
        assert int(pc["healthy_idle_remaining"]) == cnt("healthy_idle")
        assert int(pc["wrappers_total"]) == len(rows)


class TestFreezeEcho:
    """Freeze echo mirrors sorted input windows."""

    def test_windows_sorted(self, outputs: dict[str, object]) -> None:
        """Echoed freeze windows follow start, end, segment print, then scope ordering."""
        wins = outputs["freeze_echo.json"]["windows"]
        assert isinstance(wins, list)
        keys = [
            (
                int(w["start_tick_ms"]),
                int(w["end_tick_ms"]),
                str(w.get("segment")),
                str(w["scope"]),
            )
            for w in wins
        ]
        assert keys == sorted(keys)
