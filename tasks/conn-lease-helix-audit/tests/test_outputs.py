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
    "SPEC.md": "887d8a8a0dd472ac3f227fed16785610b7ff7c9bbe94f2f0d312ed45d984e362",
    "anchors/anchor_a.txt": "c72883c4ef0c5773d87479ccdc2ea1a9aecf906175463b3b89b9dab8738e8331",
    "anchors/anchor_b.txt": "4558978b8fb40e9b5da3e0565f94fafc3d000155eaf6400c8a058735230d3c40",
    "anchors/anchor_c.txt": "4b578769ed30ac1717257e72fc48533b9d1e7b55c11fb5130ffc33eb431d4a18",
    "anchors/anchor_d.txt": "6b2c9c1ccef270630400e6789de3953b6ddbed094b6233a8a906c1f2437636a7",
    "ancillary/ci_guard.json": "4580708db19b1d964fcd82ec0cf886bd9ea07d9f7719429a884802a76dd12376",
    "ancillary/pack_meta.json": "6506b77e7fe396ff0ac815da5d8d715e4f284abfeab8dcb2ad78057687cdb61d",
    "freeze_windows.json": "350a5fbcc1e932eed8e71e3ff3acacf4dea3518d181c4cc4749476f7342706ac",
    "ledger/channel_tag.json": "d2579cb9aec47c6c952eb80ff89244ec078cac2297fd19f40d102165f0624ebb",
    "ledger/ci_guard.json": "f5ef9b929a5cd47393aa715612c7f88a4c634a2ec9f1c1ef30aecae9ace987f4",
    "policy.json": "1acb2d09160e5c357d12c33f3e1423f24ac37962dddf19213ee4d1ac11cf1f37",
    "pool_state.json": "f1e210eb78671cb2824139c28678617be0401170a879aa01848f43c5881253bc",
    "wrappers/w01.json": "2ef447bac846c972d382163b97bad99a7da1057e679f8bb19a5003b155d6eb5e",
    "wrappers/w02.json": "8f3c042090bfa7990fece2755ce06f01798d8eaa35ebe19f16f8078a49ed1bdc",
    "wrappers/w03.json": "f0a963357e427cce580febd87b855cd6fa312bce5bd79a575a188856914972c2",
    "wrappers/w04.json": "45cfd5c00a5012f10ac642cb0d87f624efcbad7a2323eb17cbbc5f3b43f7d536",
    "wrappers/w05.json": "c26f2e63758eaf679237656b9ff8c1c33fb1e9358f658ad2c0a31af9108e3b23",
    "wrappers/w06.json": "f292dbe71001cd538fb5829bceeb40d005a2e967530608f14a8285e1d27fb0ae",
    "wrappers/w07.json": "c53ed18e09cf9a0de3c6517e24728380f30d9dd96d2c1c32ed6e3b20966a3810",
    "wrappers/w08.json": "269e39a2309caf6c82605290c217b57360f51894e2a414bafee89a432144ac09",
    "wrappers/w09.json": "2cf7332f7b8a67dc100b5b3574d9b9c682897b4e40c7c9d19b539cc3b35edfd5",
    "wrappers/w10.json": "57e00d3a44ef7d04c51e1d478e72798bed642180134e6b78c1e7a35f324d6e1d",
    "wrappers/w11.json": "12961f1fca8689a5c9c67298e2a5256199dc5e22a502a680ebd6106cfe2a3ec3",
    "wrappers/w12.json": "d33510754e18b912770e82ce75d7380474c9d5ed972e66b66e3bce434fad23cd",
    "wrappers/w13.json": "4d130f1413a1c750b79647fb29b1cf438932924507a22d52bc4d116b1c1c86fb",
    "wrappers/w14.json": "5115f92de65e6d09bc7a3e8c662db0c31895d957aa32a610f14f81313330cb5c",
    "wrappers/w15.json": "f56a944a93605b13cae059d5ac4eefab4cfe319a1a67599c7833967924df7d81",
    "wrappers/w16.json": "b094094e7dcd0ef11cf3a8de189bfa993a09b5b888ad70f02d769c422691f299",
    "wrappers/w17.json": "9c6e561cf90bb902b8fbc6adbf2c2d086c8388430d3b4b2a0b66ffd1f66738af",
    "wrappers/w18.json": "ff12f9140ac70562ede27b0f5723735951ebac573a86999b1067a206e59467fa",
    "wrappers/w19.json": "b701576934179be4e327513a34dbc19d8bb796e02839cc8cd23f8c0fe0440358",
    "wrappers/w20.json": "2634c3d0b970a781d406b075d9f140245845939cf7db79d60e88cece4f910a8e",
    "wrappers/w21.json": "f2f504f45d4e4812f1515073354d76c3535546d1d7ba0cbc96a5eeacbc4c5a58",
    "wrappers/w22.json": "00aa96d4d8f73be41f1547da350bb2ab733f886aa5765bfb8c832ed18452cdbe",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "freeze_echo.json": "09b386abf0facc917d08ce8ae31cda70aab9f50956f3afbe2f0fd865cd45b899",
    "pool_counters.json": "a02b2c9f7831585c5c2b5ef1d1bec3808bb26ca284c62386f15b5ef9bce47609",
    "reclaim_events.json": "29f74793d82382d9163e9ecf229d6819d5268a76c2d10354fc4496fae916e891",
    "summary.json": "1591bbb07691e7bd4f441fb40a2c958d694d7f7a7cda0372794d24651f8ac591",
    "wrapper_verdicts.json": "77c0b61e301b6fba81df9aa4069d6250203147b8d1dc3efe03c00d10c50b27e0",
}


EXPECTED_FIELD_HASHES = {
    "pool_counters.cascade_reclaims": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "pool_counters.idle_evictions": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "pool_counters.idle_retained_cap_global": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "pool_counters.idle_retained_cap_segment": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "reclaim_events.events": "d9df5aa9e9b814e61fca17d9332e36718a0c1fe4b8be77231dca4c0d10ade9ef",
    "summary.ignored_renewals": "e956fc48edc46e54908e36fd5cce6e1d9f2c85d0aaab138d974ed32cea4d0acc",
    "summary.segments": "a3e185260009ab5be7bb16f3bed296075f27322fb87d99209710a28ef3e8d99e",
    "summary.unique_verdicts": "373fc79963aa8f7182985d7e826f8745c2df15cc861097ba387a1597e729faa7",
    "wrapper_verdicts.wrappers": "c455982a94e7c33a20a6ba00ee6f0f10f41b0fa0ecfab52fb1c06d9c01f3b943",
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
        for key in ("ignored_renewals", "segments", "unique_verdicts"):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )

        pc = outputs["pool_counters.json"]
        assert isinstance(pc, dict)
        for key in (
            "cascade_reclaims",
            "idle_evictions",
            "idle_retained_cap_global",
            "idle_retained_cap_segment",
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
        # Each contiguous group must appear in leak-rank order.
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


class TestRenewalSemantics:
    """Anchor renewal pass folds into the leak computation."""

    def _row(self, outputs: dict[str, object], wid: str) -> dict[str, object]:
        rows = outputs["wrapper_verdicts.json"]["wrappers"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("wrapper_id") == wid:
                return r
        raise AssertionError(f"missing wrapper row {wid}")

    def test_renewal_rescues_apparent_leak(self, outputs: dict[str, object]) -> None:
        """`w01` would exceed the lease cap by raw checkout but is rescued by the latest renewal."""
        r = self._row(outputs, "w01")
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


class TestCascadeSemantics:
    """Cascade reclaim propagates through parent_wrapper_id chains."""

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

    def test_transitive_grandchild_is_cascaded(self, outputs: dict[str, object]) -> None:
        """`w15` reaches a leak only via its grandparent and must still be reclaimed_cascade."""
        r = self._row(outputs, "w15")
        assert r["verdict"] == "reclaimed_cascade"

    def test_cascade_depth_recorded(self, outputs: dict[str, object]) -> None:
        """The transitive grandchild `w15` is recorded at depth 2; direct children at depth 1."""
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
