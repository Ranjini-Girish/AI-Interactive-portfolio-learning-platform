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
    "SPEC.md": "90a17c18c33569e05cf64f5616b97166dd8fa4240a1c01bde25524bc459e03a4",
    "anchors/anchor_a.txt": "2711b54830332b6d62df18d35a0cd94b78dc381ee35009128aeb738322a88322",
    "anchors/anchor_b.txt": "acdbf60cc8a2cc4eecf2dbbf915fed5f387e1f58517cf3b115276c5575a87fc8",
    "anchors/anchor_c.txt": "058ceb700bfe5ee7f8776908e2dd1f83bc69045f21cc39eb47afa127a5368751",
    "anchors/anchor_d.txt": "5c87404553971914a30d2415ef70f97e7d241b22c7c5031538ed54e6a5967b24",
    "ancillary/ci_guard.json": "4580708db19b1d964fcd82ec0cf886bd9ea07d9f7719429a884802a76dd12376",
    "ancillary/pack_meta.json": "6506b77e7fe396ff0ac815da5d8d715e4f284abfeab8dcb2ad78057687cdb61d",
    "freeze_windows.json": "350a5fbcc1e932eed8e71e3ff3acacf4dea3518d181c4cc4749476f7342706ac",
    "ledger/channel_tag.json": "d2579cb9aec47c6c952eb80ff89244ec078cac2297fd19f40d102165f0624ebb",
    "ledger/ci_guard.json": "f5ef9b929a5cd47393aa715612c7f88a4c634a2ec9f1c1ef30aecae9ace987f4",
    "policy.json": "b90ea61d74af8878e0618993c3dbe778162eaede513fa13210cf4a0513bddd40",
    "pool_state.json": "f1e210eb78671cb2824139c28678617be0401170a879aa01848f43c5881253bc",
    "wrappers/w01.json": "f2c2e83bb75db15b82172a330cee923940c0e2d675852a4673c6664889be6418",
    "wrappers/w02.json": "a5cfaade9bfd488113c80b29608f2bcb4d443061e5a1df31316bb1126448df7e",
    "wrappers/w03.json": "def46d09b55053b1e3d4b8f73fbcff68909d06b6cf9bbfe35e2c4d321d0c44fd",
    "wrappers/w04.json": "c8a6c26029f40b2725fdda1daecb4d430c7160f6cf7b63e93da71719f3d04bc9",
    "wrappers/w05.json": "07a9929b4cef2efac81e92040fa608fabc0962c8ee3377ee6552ac41b95efdc4",
    "wrappers/w06.json": "5701f4b5b4086ef5f4c4075b7c145fec2aee507a4025b90f99b63150104df196",
    "wrappers/w07.json": "e0658ade6cc39a71d4774cdba9fbd74fef9e32a9b257d17857312a54c5490fc9",
    "wrappers/w08.json": "07e75b40448943ddfc2d71b6b4b9a362ade50f50562f1593a2705a52b34447f1",
    "wrappers/w09.json": "552a6b135b51fb69afe17f5c410870b7a2e48a317fd38875e1d32ffbc19ad98b",
    "wrappers/w10.json": "2a31689109da8b986cbe651b0d2aeac8af312fc8563514467becf6e9e05ba9e6",
    "wrappers/w11.json": "b4d109e6e09cbf14dfb427c11a263f3fc5cba53c1cb1e9f671d7b28bd0bf8c2b",
    "wrappers/w12.json": "ecbab0f1bf64f6740e1d66ef25e018112314977a52c6aff937718496c034a2d4",
    "wrappers/w13.json": "f2a7e2794c649041301eaadd086ddaad725e7e3955150e4e5801a55ed10418e2",
    "wrappers/w14.json": "a7c820b686ff84f99e8db806d01d60885a1e196fd31f141d1e0b6e17d826eb44",
    "wrappers/w15.json": "0ae9e86712123d191c91f02c8a8fa693d8253b7e817abb6753e131f01e597a0c",
    "wrappers/w16.json": "3f8b2c084d05352be6c6c975fe8e09361955dc1b5e4099ff417480adcd9f2446",
    "wrappers/w17.json": "ea89381b8ff48b386ad22404de24bc4440e643d2ee2fab659706e7d6afd136a0",
    "wrappers/w18.json": "4e1ecb0c151ba10ca5fe8180b5be491c4208b2b678c4b8420edbd23b8351320a",
    "wrappers/w19.json": "7b0d533e98e2b680e4c179464e1e5b0a475b25088043e7ebdbb835d34da61402",
    "wrappers/w20.json": "08b840999b0b10fc2dcf346649339828c4c2907fb03c62b5a255eb2a942708ca",
    "wrappers/w21.json": "591e4827cd76becad0594a583062de404c4e8754a02659ff56bb20a686611f67",
    "wrappers/w22.json": "371a89dad527f4d592fc235002e4108772a99c10d1720d7a227f7764b474afc9",
    "wrappers/w23.json": "d17f6b672ccc98fde9bd6cb3984474a1bed7408617ecc8f1611b567382202290",
    "wrappers/w24.json": "7b6d2fb2eeb144495e5160712cfb8f68deba3f8790302120adaef56387dad9d8",
    "wrappers/w25.json": "d2e8333592d0873a78bca1684c7df07dd668492a4dfde59281ccd7b788e20257",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "freeze_echo.json": "09b386abf0facc917d08ce8ae31cda70aab9f50956f3afbe2f0fd865cd45b899",
    "pool_counters.json": "61c43231d60b28324352638111b790b397b3a9bdce05df055b1b915bf9c0feb5",
    "reclaim_events.json": "fab653218ac0e0725b68354839fb9b712f9a69b727696caee8a0069b28fff347",
    "summary.json": "ce3eb1c948aaa5751c159a2cf292509917f9594ffe42a183ee0315ee4c79639b",
    "wrapper_verdicts.json": "e182465195c535f386e6b3b15c1d34b191680c5a846baaf9218078485a40d95c",
}


EXPECTED_FIELD_HASHES = {
    "pool_counters.cascade_orphans": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "pool_counters.cascade_reclaims": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "pool_counters.idle_evictions": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "pool_counters.idle_retained_cap_global": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "pool_counters.idle_retained_cap_segment": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "pool_counters.leak_reclaims": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "reclaim_events.events": "d5b542a5971194ea1babb2d075ed4c02d0126b1295be755d99f862e792c212f6",
    "summary.ignored_renewals": "5fefa4fe71ed107dea27f8d562cce90a6f572d8e5d1a223037f303d6357a0d56",
    "summary.segments": "a3e185260009ab5be7bb16f3bed296075f27322fb87d99209710a28ef3e8d99e",
    "summary.under_quorum_renewals": "99cbeb3d799785b13d37ff64772c3c88bf83ec96cb2c3c853912c6f8a4262c23",
    "summary.unique_verdicts": "bd84ae09ffb5a08816fef9102eb12442757f6afef349e322e0edb9cf8259dd2d",
    "wrapper_verdicts.wrappers": "47bf63be0057d11b23d7d58d5173aea984f721f09b3fc36b698256fa2792827d",
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
        for key in ("ignored_renewals", "segments", "under_quorum_renewals", "unique_verdicts"):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )

        pc = outputs["pool_counters.json"]
        assert isinstance(pc, dict)
        for key in (
            "cascade_orphans",
            "cascade_reclaims",
            "idle_evictions",
            "idle_retained_cap_global",
            "idle_retained_cap_segment",
            "leak_reclaims",
        ):
            field = f"pool_counters.{key}"
            assert (
                _sha256_bytes(_canonical(pc[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )

        re_ = outputs["reclaim_events.json"]
        assert isinstance(re_, dict)
        assert (
            _sha256_bytes(_canonical(re_["events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["reclaim_events.events"]
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
    """Reclaim journal reflects leak-first then cascade-by-leak then idle walk order."""

    def test_event_categories_segmented_in_order(
        self, outputs: dict[str, object]
    ) -> None:
        """All leak events come before all cascade events, which come before all idle events."""
        evs = outputs["reclaim_events.json"]["events"]
        assert isinstance(evs, list)
        kinds = [str(e["kind"]) for e in evs]
        rank = {"leak_reclaim": 0, "cascade_reclaim": 1, "idle_reclaim": 2}
        ordered_keys = [rank[k] for k in kinds]
        assert ordered_keys == sorted(ordered_keys)

    def test_leak_ordering(self, outputs: dict[str, object]) -> None:
        """Leak rows must sort by effective lease descending, wrapper id ascending."""
        evs = outputs["reclaim_events.json"]["events"]
        leaks = [e for e in evs if str(e["kind"]) == "leak_reclaim"]
        keys = [(int(e["lease_ms"]), str(e["wrapper_id"])) for e in leaks]
        assert keys == sorted(keys, key=lambda t: (-t[0], t[1]))

    def test_cascade_grouped_by_leak_rank(self, outputs: dict[str, object]) -> None:
        """Cascade events appear grouped by parent_leak_id in the order their leak row appeared."""
        evs = outputs["reclaim_events.json"]["events"]
        leak_order = [str(e["wrapper_id"]) for e in evs if str(e["kind"]) == "leak_reclaim"]
        cascade_groups: list[str] = []
        for e in evs:
            if str(e["kind"]) != "cascade_reclaim":
                continue
            pid = str(e["parent_leak_id"])
            if not cascade_groups or cascade_groups[-1] != pid:
                cascade_groups.append(pid)
        seen: set[str] = set()
        for pid in cascade_groups:
            assert pid not in seen, f"cascade rows for {pid} are not contiguous"
            seen.add(pid)
        rank = {pid: i for i, pid in enumerate(leak_order)}
        assert [rank[g] for g in cascade_groups] == sorted(rank[g] for g in cascade_groups)

    def test_cascade_within_group_sorted_by_depth_then_id(
        self, outputs: dict[str, object]
    ) -> None:
        """Within each cascade group, rows sort by depth ascending then wrapper_id ascending."""
        evs = outputs["reclaim_events.json"]["events"]
        by_parent: dict[str, list[tuple[int, str]]] = {}
        for e in evs:
            if str(e["kind"]) != "cascade_reclaim":
                continue
            by_parent.setdefault(str(e["parent_leak_id"]), []).append(
                (int(e["depth"]), str(e["wrapper_id"]))
            )
        for pid, rows in by_parent.items():
            assert rows == sorted(rows), f"cascade group {pid} not sorted"

    def test_idle_reclaim_sequence_matches_spec_walk(
        self, outputs: dict[str, object]
    ) -> None:
        """Idle reclaims follow ascending entered-idle time with stable wrapper id tie breaks."""
        evs = outputs["reclaim_events.json"]["events"]
        idle_ids = [str(e["wrapper_id"]) for e in evs if str(e["kind"]) == "idle_reclaim"]
        assert idle_ids == ["w10", "w03", "w22"]

    def test_orphan_excluded_from_events(self, outputs: dict[str, object]) -> None:
        """Wrappers classified as `cascade_orphaned` must NOT appear in the reclaim event journal."""
        evs = outputs["reclaim_events.json"]["events"]
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        orphan_ids = {str(r["wrapper_id"]) for r in rows if r["verdict"] == "cascade_orphaned"}
        event_ids = {str(e["wrapper_id"]) for e in evs}
        assert orphan_ids.isdisjoint(event_ids)


class TestRenewalSemantics:
    """Anchor renewal pass folds into the leak computation with channel and quorum rules."""

    def _row(self, outputs: dict[str, object], wid: str) -> dict[str, object]:
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("wrapper_id") == wid:
                return r
        raise AssertionError(f"missing wrapper row {wid}")

    def test_renewal_rescues_apparent_leak_when_quorum_met(
        self, outputs: dict[str, object]
    ) -> None:
        """`w01` would exceed the lease cap by raw checkout but is rescued by renewals across the quorate channel set."""
        r = self._row(outputs, "w01")
        assert r["verdict"] == "healthy_leased"

    def test_multi_channel_rescue_marks_healthy(
        self, outputs: dict[str, object]
    ) -> None:
        """`w23` would leak on raw checkout; renewals from three permitted channels rescue it."""
        r = self._row(outputs, "w23")
        assert r["verdict"] == "healthy_leased"

    def test_renewal_against_idle_wrapper_is_ignored(
        self, outputs: dict[str, object]
    ) -> None:
        """A renewal record naming an idle wrapper must surface in ignored_renewals."""
        sm = outputs["summary.json"]
        assert "w03" in sm["ignored_renewals"]
        assert "w04" in sm["ignored_renewals"]

    def test_renewal_against_unknown_wrapper_is_ignored(
        self, outputs: dict[str, object]
    ) -> None:
        """A renewal record naming an unknown wrapper id must surface exactly once in ignored_renewals."""
        sm = outputs["summary.json"]
        ignored = sm["ignored_renewals"]
        assert "w99" in ignored
        assert ignored.count("w99") == 1

    def test_ignored_renewals_sorted_unique(self, outputs: dict[str, object]) -> None:
        """ignored_renewals must be sorted ascending with no duplicates."""
        ignored = outputs["summary.json"]["ignored_renewals"]
        assert list(ignored) == sorted(set(ignored))


class TestChannelBinding:
    """Off-channel renewal records are ignored and surface in summary.ignored_renewals."""

    def _row(self, outputs: dict[str, object], wid: str) -> dict[str, object]:
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("wrapper_id") == wid:
                return r
        raise AssertionError(f"missing wrapper row {wid}")

    def test_off_channel_renewal_added_to_ignored(
        self, outputs: dict[str, object]
    ) -> None:
        """`w24` and `w17` each receive at least one renewal from a channel not in their `bound_channels`; both wrapper ids must surface in ignored_renewals."""
        ignored = outputs["summary.json"]["ignored_renewals"]
        assert "w17" in ignored
        assert "w24" in ignored


class TestQuorumSemantics:
    """Renewal rescue is gated on distinct-channel quorum."""

    def _row(self, outputs: dict[str, object], wid: str) -> dict[str, object]:
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("wrapper_id") == wid:
                return r
        raise AssertionError(f"missing wrapper row {wid}")

    def test_under_quorum_renewals_surfaced(self, outputs: dict[str, object]) -> None:
        """Wrappers with applicable renewals from fewer distinct channels than the quorum must surface in summary.under_quorum_renewals."""
        sm = outputs["summary.json"]
        uqr = sm["under_quorum_renewals"]
        assert "w17" in uqr
        assert "w24" in uqr
        assert list(uqr) == sorted(set(uqr))

    def test_under_quorum_falls_back_to_raw_checkout(
        self, outputs: dict[str, object]
    ) -> None:
        """`w24` has applicable renewals from only one channel; the quorum failure makes it fall back to its raw checkout, exceeding the lease cap and emitting `reclaimed_leak`."""
        r = self._row(outputs, "w24")
        assert r["verdict"] == "reclaimed_leak"

    def test_leak_event_for_under_quorum_records_raw_lease(
        self, outputs: dict[str, object]
    ) -> None:
        """The leak event for `w24` reports the effective lease against raw checkout (eval_tick 5000000 minus checkout 4400000 = 600000)."""
        evs = outputs["reclaim_events.json"]["events"]
        w24 = next(e for e in evs if e.get("wrapper_id") == "w24")
        assert int(w24["lease_ms"]) == 600000

    def test_wrapper_with_no_applicable_renewals_not_under_quorum(
        self, outputs: dict[str, object]
    ) -> None:
        """`w11` and `w12` have zero applicable renewals; the spec excludes such wrappers from under_quorum_renewals."""
        uqr = outputs["summary.json"]["under_quorum_renewals"]
        assert "w11" not in uqr
        assert "w12" not in uqr


class TestCascadeSemantics:
    """Cascade reclaim propagates through parent_wrapper_id chains within the depth cap."""

    def _row(self, outputs: dict[str, object], wid: str) -> dict[str, object]:
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("wrapper_id") == wid:
                return r
        raise AssertionError(f"missing wrapper row {wid}")

    def test_direct_child_of_leak_is_cascaded(self, outputs: dict[str, object]) -> None:
        """`w13` is a direct child of leak `w11` and must be reclaimed_cascade."""
        r = self._row(outputs, "w13")
        assert r["verdict"] == "reclaimed_cascade"

    def test_idle_child_of_leak_is_cascaded(self, outputs: dict[str, object]) -> None:
        """An idle wrapper (`w14`) whose parent is a leak still becomes reclaimed_cascade."""
        r = self._row(outputs, "w14")
        assert r["verdict"] == "reclaimed_cascade"

    def test_transitive_grandchild_at_cap_is_cascaded(
        self, outputs: dict[str, object]
    ) -> None:
        """`w15` reaches a leak via two hops; that equals the cap and must still be reclaimed_cascade."""
        r = self._row(outputs, "w15")
        assert r["verdict"] == "reclaimed_cascade"

    def test_cascade_depth_recorded(self, outputs: dict[str, object]) -> None:
        """The grandchild `w15` is recorded at depth 2; direct children at depth 1."""
        evs = outputs["reclaim_events.json"]["events"]
        by_id = {str(e["wrapper_id"]): e for e in evs if str(e["kind"]) == "cascade_reclaim"}
        assert int(by_id["w13"]["depth"]) == 1
        assert int(by_id["w14"]["depth"]) == 1
        assert int(by_id["w15"]["depth"]) == 2
        assert int(by_id["w16"]["depth"]) == 1
        assert int(by_id["w17"]["depth"]) == 1

    def test_cascade_attributed_to_closest_leak(
        self, outputs: dict[str, object]
    ) -> None:
        """`w15` walks through `w13` (cascade) up to `w11` (leak); its parent_leak_id is `w11`."""
        evs = outputs["reclaim_events.json"]["events"]
        by_id = {str(e["wrapper_id"]): e for e in evs if str(e["kind"]) == "cascade_reclaim"}
        assert str(by_id["w15"]["parent_leak_id"]) == "w11"
        assert str(by_id["w16"]["parent_leak_id"]) == "w12"

    def test_chain_without_leak_does_not_cascade(
        self, outputs: dict[str, object]
    ) -> None:
        """`w21` has a parent (`w02`) that is healthy; the chain hits no leak so no cascade applies."""
        r = self._row(outputs, "w21")
        assert r["verdict"] == "healthy_idle"


class TestCascadeOrphan:
    """Cascade descendants beyond the depth cap receive `cascade_orphaned` and stay live."""

    def _row(self, outputs: dict[str, object], wid: str) -> dict[str, object]:
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("wrapper_id") == wid:
                return r
        raise AssertionError(f"missing wrapper row {wid}")

    def test_descendant_beyond_cap_is_orphaned(
        self, outputs: dict[str, object]
    ) -> None:
        """`w25` reaches leak `w11` only at a hop distance above the cap and must be `cascade_orphaned`."""
        r = self._row(outputs, "w25")
        assert r["verdict"] == "cascade_orphaned"

    def test_orphan_appears_in_unique_verdicts(
        self, outputs: dict[str, object]
    ) -> None:
        """`cascade_orphaned` must surface in summary.unique_verdicts when any wrapper carries it."""
        uv = outputs["summary.json"]["unique_verdicts"]
        assert "cascade_orphaned" in uv

    def test_orphan_counter_matches_verdict_count(
        self, outputs: dict[str, object]
    ) -> None:
        """`pool_counters.cascade_orphans` must equal the number of `cascade_orphaned` verdicts."""
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        pc = outputs["pool_counters.json"]
        n = sum(1 for r in rows if r["verdict"] == "cascade_orphaned")
        assert int(pc["cascade_orphans"]) == n
        assert n >= 1

    def test_orphan_is_live_for_segment_floor(
        self, outputs: dict[str, object]
    ) -> None:
        """Orphans contribute to segment_live: with `w25` counted in alpha, `w18` is retained because evicting it would push alpha below its floor."""
        r = self._row(outputs, "w18")
        assert r["verdict"] == "idle_retained_cap"


class TestEvictionGuards:
    """Two-constraint guard: global min_size plus per-segment floors."""

    def _row(self, outputs: dict[str, object], wid: str) -> dict[str, object]:
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("wrapper_id") == wid:
                return r
        raise AssertionError(f"missing wrapper row {wid}")

    def test_segment_floor_retains_alpha(self, outputs: dict[str, object]) -> None:
        """`w18` is retained because evicting it would push alpha below its floor."""
        r = self._row(outputs, "w18")
        assert r["verdict"] == "idle_retained_cap"

    def test_global_min_retains_gamma(self, outputs: dict[str, object]) -> None:
        """`w06` is retained because evicting it would push the fleet below min_size."""
        r = self._row(outputs, "w06")
        assert r["verdict"] == "idle_retained_cap"

    def test_retained_breakdown_sums_to_total(self, outputs: dict[str, object]) -> None:
        """The split counters always sum to `idle_retained_cap`."""
        pc = outputs["pool_counters.json"]
        assert int(pc["idle_retained_cap_global"]) + int(
            pc["idle_retained_cap_segment"]
        ) == int(pc["idle_retained_cap"])

    def test_segment_freeze_preserves_idle(self, outputs: dict[str, object]) -> None:
        """`w05` lives in a frozen segment and keeps the freeze preservation verdict."""
        r = self._row(outputs, "w05")
        assert r["verdict"] == "idle_preserved_freeze"

    def test_wrapper_scope_freeze_preserves_idle(
        self, outputs: dict[str, object]
    ) -> None:
        """`w08` matches a wrapper-scope freeze and keeps the freeze preservation verdict."""
        r = self._row(outputs, "w08")
        assert r["verdict"] == "idle_preserved_freeze"

    def test_inactive_wrapper_scope_does_not_preserve(
        self, outputs: dict[str, object]
    ) -> None:
        """`w10` has a wrapper-scope window that already ended; it must be reclaimed normally."""
        r = self._row(outputs, "w10")
        assert r["verdict"] == "reclaimed_idle"


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
        assert int(pc["cascade_reclaims"]) == cnt("reclaimed_cascade")
        assert int(pc["cascade_orphans"]) == cnt("cascade_orphaned")
        assert int(pc["idle_evictions"]) == cnt("reclaimed_idle")
        assert int(pc["idle_preserved_freeze"]) == cnt("idle_preserved_freeze")
        assert int(pc["idle_retained_cap"]) == cnt("idle_retained_cap")
        assert int(pc["healthy_leased_remaining"]) == cnt("healthy_leased")
        assert int(pc["healthy_idle_remaining"]) == cnt("healthy_idle")
        assert int(pc["wrappers_total"]) == len(rows)


class TestFreezeEcho:
    """Freeze echo mirrors sorted input windows including wrapper-scope rows."""

    def test_windows_sorted(self, outputs: dict[str, object]) -> None:
        """Echoed windows sort by start, end, scope, segment-print, wrapper-print."""
        wins = outputs["freeze_echo.json"]["windows"]
        assert isinstance(wins, list)
        keys = [
            (
                int(w["start_tick_ms"]),
                int(w["end_tick_ms"]),
                str(w["scope"]),
                "null" if w.get("segment") is None else str(w["segment"]),
                "null" if w.get("wrapper_id") is None else str(w["wrapper_id"]),
            )
            for w in wins
        ]
        assert keys == sorted(keys)

    def test_segment_scope_row_carries_segment_only(
        self, outputs: dict[str, object]
    ) -> None:
        """A segment-scope echo row has a string `segment` and a null `wrapper_id`."""
        wins = outputs["freeze_echo.json"]["windows"]
        seg_rows = [w for w in wins if w["scope"] == "segment"]
        assert seg_rows, "no segment-scope window echoed"
        for row in seg_rows:
            assert isinstance(row["segment"], str)
            assert row["wrapper_id"] is None

    def test_wrapper_scope_row_carries_wrapper_only(
        self, outputs: dict[str, object]
    ) -> None:
        """A wrapper-scope echo row has a string `wrapper_id` and a null `segment`."""
        wins = outputs["freeze_echo.json"]["windows"]
        w_rows = [w for w in wins if w["scope"] == "wrapper"]
        assert w_rows, "no wrapper-scope window echoed"
        for row in w_rows:
            assert isinstance(row["wrapper_id"], str)
            assert row["segment"] is None
