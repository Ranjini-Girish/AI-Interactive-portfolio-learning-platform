"""Behavioral tests for the probe flap chain audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("PFCA_DATA_DIR", "/app/probeflaps"))
AUDIT_DIR = Path(os.environ.get("PFCA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "node_verdicts.json",
    "tier_policy.json",
    "incident_journal.json",
    "dependency_touchpoints.json",
    "cross_ref_overlay.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "647ac4324f657bb55756532c69fea92a6b0d2460f2798d15d2268daec1212c6c",
    "ancillary/channel_tag.json": "e3f743dfbbdb07da2b40a8cb71d92bdda53bd0eed55e247c35b38c7dce951a91",
    "ancillary/ci_guard.json": "0ecfe0ba66d080f854e5704d7442c62e8a8f7b315e7d617d1135e874b9b1d4f8",
    "ancillary/extra_one.json": "220aa04e25113593bb0f4ffcbfbf64b73c7520df0da633fd8b14417b0fecea7a",
    "ancillary/extra_two.json": "bc821685311c618465390595375c4f5f65a30dcd5df50e6317dd3079deb90d0a",
    "ancillary/watermark.txt": "53e18be76281523eac67dcf79c274696eaf561e115361a2f506ab63e14ae1e08",
    "incident_log.json": "e90390d3b5583df175007cc069fd29615112614438d67818d290ddf11b23daf3",
    "links/cross_refs.json": "4c9345e158757c2af92335e1ff9eb0ee76691f8e413c136a16bef23459a1c256",
    "nodes/node-alpha.json": "3ab782186763d128441468678413be734e3322e6d3f276f322f2c76047d6610f",
    "nodes/node-beta.json": "7175d3dd7975d9beb839bb0f80aead2f9ce6a5ecec84dfcd8980658215333a5f",
    "nodes/node-delta.json": "b673dc3c73e6d23b2bbe53aa704049a480e9f8308f2af2f1ae84fb6ebcebaea5",
    "nodes/node-epsilon.json": "fe2fb1e4a6e16d84dec355827d5367a4face668cd1b3c559cee0b6580e0a87cd",
    "nodes/node-eta.json": "afb89592a02045ee8d86526298b9f87ed614b93b11259399943497e18dcc5fa9",
    "nodes/node-gamma.json": "9ace1db36c6042bffeac5c5e8a284ccda5465f9e9b6b144a1e1ff2744e7d175f",
    "nodes/node-iota.json": "a846e961871eda88db8eace2ffe8e1a24e2a4a891ec98111f431427a359c76c8",
    "nodes/node-kappa.json": "16b5390f3c2a76ffbc63d53e053f82b455e2390e1ab69a1a5cd779c3b8eb500a",
    "nodes/node-lambda.json": "479bcfdd12a68368efd0d34f3db04d639be63be9ea0984b5c95f4662ebe7a00d",
    "nodes/node-mu.json": "ad9d2c0cab917a55d520431a5f3d9925b997b7204ec902c6742a833468c2182d",
    "nodes/node-nu.json": "36371e82c93eaa9f399b6a6a567cd525d50f114c8e8bdff9a7c9bbac1465f451",
    "nodes/node-omega.json": "314816db2114211bf1639d80ee5c32d718922ec887516a20459580baa108b1fe",
    "nodes/node-theta.json": "481a52b7aca1b56cb5f365746411236b9e42490490c6cf7d257b4b4eae48dbe2",
    "nodes/node-zeta.json": "de9b88c465020917dcec320615ae7227c0fc76184ba89d30c9fc0a2faba975a5",
    "policy.json": "563e1cc8d47ef9c6def4f09054f1ccc006d6e4d9341e39b299a13935c5858a6e",
    "pool_state.json": "bc383d68e9727a5442852b4f4b55c1302361c4e1666ecd6ffd26fb181095b1c7",
    "registry/forest_index.json": "cab037744dc47a72ce35d6d4705a77fcc56774a9537b1001f8555d0d60c0e927",
    "registry/tier_labels.json": "bbb692f10cfd7dc9c1cb0c07b5a0a27f42d1130e9dcc70b66aef42420d6b4c58",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "cross_ref_overlay.json": "5800e072cd626c5abaee4eb788f01c5346d36e68e44d6c84076b92875e800e6b",
    "dependency_touchpoints.json": "22ddad0b1f6529a95bb17ecb3ac650132ba9e181e6ffe8fbf7e61e225168134d",
    "incident_journal.json": "a42e3bded5c96330af245348d1372fa8e0e5ced2f6d58198e419d2c7f29d89d5",
    "node_verdicts.json": "239542aefe93082c70a2b21e70998d9cc4382b23951a923a4d941caa00e43e2e",
    "summary.json": "806683b4a52ac05c38f2dc5568f38fae612deb81512b9c3fb32d9d8096583e8d",
    "tier_policy.json": "49140e8da0e4faf74ce17dff8384d7b2726ea3a19fbe55458958e3727a2399f3",
}


EXPECTED_FIELD_HASHES = {
    "cross_ref_overlay.pressured_nodes": "46f428f48dbaf3dd047c6ba77c2d106af301abe3148fde305ce2036b32635576",
    "dependency_touchpoints.parents": "41f6216e4fadf5225dd9402f27854e740e49186780ccececebfda7d99fc0dc09",
    "incident_journal.applied_events": "e8c796c862e562480c9acc934ced86fcf61a8699ebd4ca61e76205655911d65d",
    "node_verdicts.nodes": "7e3a6b6566f0f3e22cae78639b1e85ce3bf93eb439d583d6bc6057f988992d40",
    "summary.applied_incident_events": "4a44dc15364204a80fe80e9039455cc1608281820fe2b24f1e5233ade6af1dd5",
    "summary.cross_ref_pressured_nodes": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.degraded_nodes": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "summary.flapping_nodes": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.healthy_nodes": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.ignored_incident_events": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.inherited_degraded_nodes": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.isolated_nodes": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.nodes_total": "8527a891e224136950ff32ca212b45bc93f69fbb801c3b1ebedac52775f99e61",
    "summary.soaking_nodes": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.unhealthy_nodes": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "tier_policy.tiers": "741e44ca690f60566781f9208fb1b927dca1b0f5758934d50122863917ade560",
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
        nv = outputs["node_verdicts.json"]
        assert isinstance(nv, dict)
        assert (
            _sha256_bytes(_canonical(nv["nodes"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["node_verdicts.nodes"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in (
            "applied_incident_events",
            "cross_ref_pressured_nodes",
            "degraded_nodes",
            "flapping_nodes",
            "healthy_nodes",
            "ignored_incident_events",
            "inherited_degraded_nodes",
            "isolated_nodes",
            "nodes_total",
            "soaking_nodes",
            "unhealthy_nodes",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )

        ij = outputs["incident_journal.json"]
        assert isinstance(ij, dict)
        assert (
            _sha256_bytes(_canonical(ij["applied_events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_journal.applied_events"]
        )

        dt = outputs["dependency_touchpoints.json"]
        assert isinstance(dt, dict)
        assert (
            _sha256_bytes(_canonical(dt["parents"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["dependency_touchpoints.parents"]
        )

        tp = outputs["tier_policy.json"]
        assert isinstance(tp, dict)
        assert (
            _sha256_bytes(_canonical(tp["tiers"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["tier_policy.tiers"]
        )

        cro = outputs["cross_ref_overlay.json"]
        assert isinstance(cro, dict)
        assert (
            _sha256_bytes(_canonical(cro["pressured_nodes"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["cross_ref_overlay.pressured_nodes"]
        )


class TestNodeOrdering:
    """Verify deterministic ordering rules on node rows."""

    def test_node_rows_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`nodes` must list rows in ascending ASCII `node_id` order."""
        nv = outputs["node_verdicts.json"]
        assert isinstance(nv, dict)
        rows = nv["nodes"]
        assert isinstance(rows, list)
        ids = [str(r["node_id"]) for r in rows]
        assert ids == sorted(ids)


class TestVerdictSemantics:
    """Spot-check bundled rows that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], nid: str) -> dict[str, object]:
        rows = outputs["node_verdicts.json"]["nodes"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("node_id") == nid:
                return r
        raise AssertionError(f"missing node row {nid}")

    def test_force_unhealthy_row(self, outputs: dict[str, object]) -> None:
        """`node-alpha` is forced unhealthy with only the directive reason."""
        r = self._row(outputs, "node-alpha")
        assert r["computed_status"] == "unhealthy"
        assert r["degraded"] is True
        assert r["reasons"] == ["force_unhealthy_incident"]

    def test_isolated_row(self, outputs: dict[str, object]) -> None:
        """`node-delta` is isolated by incident despite clean probes."""
        r = self._row(outputs, "node-delta")
        assert r["computed_status"] == "isolated"
        assert r["degraded"] is True
        assert r["reasons"] == ["isolate_incident"]

    def test_inherited_degraded_child(self, outputs: dict[str, object]) -> None:
        """`node-epsilon` inherits degradation from unhealthy parent `node-alpha`."""
        r = self._row(outputs, "node-epsilon")
        assert r["computed_status"] == "inherited_degraded"
        assert r["degraded"] is True
        assert r["reasons"] == ["parent_degraded_inheritance"]

    def test_threshold_unhealthy_row(self, outputs: dict[str, object]) -> None:
        """`node-iota` trips the silver fail threshold after the wider silver window
        pulls in an extra fail day, a fail-day suppression shaves one counted
        failure, and the remaining effective failures meet the tier threshold.
        Also pins `last_fail_day` to the most recent unsuppressed fail day."""
        r = self._row(outputs, "node-iota")
        assert r["computed_status"] == "unhealthy"
        assert r["reasons"] == ["threshold_exceeded"]
        assert r["raw_failures"] == 4
        assert r["effective_failures"] == 3
        assert r["suppressed_fail_days"] == [106]
        assert r["last_fail_day"] == 105

    def test_flapping_row_after_suppress(self, outputs: dict[str, object]) -> None:
        """`node-beta` remains flapping after flap-day suppression and soak elapsed."""
        r = self._row(outputs, "node-beta")
        assert r["computed_status"] == "flapping"
        assert r["degraded"] is False
        assert r["reasons"] == ["flap_threshold_exceeded"]
        assert r["raw_flap_transitions"] == 6
        assert r["effective_flap_transitions"] == 4

    def test_soaking_row(self, outputs: dict[str, object]) -> None:
        """`node-lambda` is in soak after a recent fail under bronze thresholds."""
        r = self._row(outputs, "node-lambda")
        assert r["computed_status"] == "soaking"
        assert r["reasons"] == ["soaking_period"]
        assert r["last_fail_day"] == 108

    def test_inherited_degraded_child_mu(self, outputs: dict[str, object]) -> None:
        """`node-mu` inherits degradation from unhealthy parent `node-iota`."""
        r = self._row(outputs, "node-mu")
        assert r["computed_status"] == "inherited_degraded"
        assert r["degraded"] is True
        assert r["reasons"] == ["parent_degraded_inheritance"]

    def test_only_gamma_is_plain_healthy(self, outputs: dict[str, object]) -> None:
        """`node-gamma` is the sole node whose final status is `healthy` with an
        empty reasons array; every other clean leaf is either inherited-degraded,
        flapping, soaking, or cross-ref-pressured."""
        r = self._row(outputs, "node-gamma")
        assert r["computed_status"] == "healthy"
        assert r["reasons"] == []
        assert r["degraded"] is False


class TestEffectiveTier:
    """Audit-day effective tier drives every threshold and window lookup."""

    def _row(self, outputs: dict[str, object], nid: str) -> dict[str, object]:
        rows = outputs["node_verdicts.json"]["nodes"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("node_id") == nid:
                return r
        raise AssertionError(f"missing node row {nid}")

    def test_promotion_log_lifts_node_into_higher_tier(self, outputs: dict[str, object]) -> None:
        """`node-nu` has a static `bronze` tier but a promotion entry whose
        `as_of_day` is ≤ `current_day`, so the audit-day effective tier is `gold`.
        The fail threshold and rolling window applied to the row must be the gold
        ones, and the row trips the gold fail threshold even though the raw bronze
        thresholds would have left it healthy."""
        r = self._row(outputs, "node-nu")
        assert r["tier"] == "bronze"
        assert r["effective_tier"] == "gold"
        assert r["effective_fail_threshold"] == 2
        assert r["effective_failures"] == 2
        assert r["computed_status"] == "unhealthy"
        assert r["reasons"] == ["threshold_exceeded"]

    def test_promotion_log_does_not_change_static_tier_field(self, outputs: dict[str, object]) -> None:
        """`node-zeta`'s effective tier is `silver` (per its history) but its
        emitted `tier` field still preserves the static bronze value from the
        source file. Threshold fields on the row come from the silver policy row."""
        r = self._row(outputs, "node-zeta")
        assert r["tier"] == "bronze"
        assert r["effective_tier"] == "silver"
        assert r["effective_fail_threshold"] == 3
        assert r["effective_soak_days"] == 4

    def test_future_promotion_is_ignored(self, outputs: dict[str, object]) -> None:
        """`node-zeta` has a history entry with `as_of_day = 200` (> current_day 110)
        that must NOT take effect; the chosen tier is the largest `as_of_day` ≤
        current_day, not the largest of all entries."""
        r = self._row(outputs, "node-zeta")
        assert r["effective_tier"] == "silver"

    def test_missing_promotion_log_uses_static_tier(self, outputs: dict[str, object]) -> None:
        """`node-gamma` has no tier_history; its effective tier equals the static field."""
        r = self._row(outputs, "node-gamma")
        assert r["tier"] == "bronze"
        assert r["effective_tier"] == "bronze"

    def test_tier_policy_assigned_nodes_uses_effective_tier(
        self, outputs: dict[str, object]
    ) -> None:
        """`assigned_nodes` partitions all emitted nodes by effective tier, not by the
        static `tier` field. With three promotions in the bundled fixture, gold and
        silver each gain a member relative to a naive static-tier count."""
        tiers = outputs["tier_policy.json"]["tiers"]
        assigned = {t: tiers[t]["assigned_nodes"] for t in ("bronze", "gold", "silver")}
        assert assigned == {"bronze": 4, "gold": 5, "silver": 5}
        assert sum(assigned.values()) == 14


class TestSuppressionAdjustsLastFailDay:
    """`fail_day_suppress` removes the day from both effective_failures and last_fail_day."""

    def _row(self, outputs: dict[str, object], nid: str) -> dict[str, object]:
        rows = outputs["node_verdicts.json"]["nodes"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("node_id") == nid:
                return r
        raise AssertionError(f"missing node row {nid}")

    def test_omega_flaps_after_suppression_skips_soak(self, outputs: dict[str, object]) -> None:
        """`node-omega` has fail probes on day 106 and day 108, and the incident log
        suppresses day 108 for this node. Without the suppression-aware last_fail_day
        rule, day 108 sits within the bronze soak window of 4 days and the node
        would resolve to `soaking`. With the rule, `last_fail_day` shifts back to 106
        (110 - 106 = 4 ≥ 4, so soak does NOT fire), the flap count clears the
        threshold, and the final status is `flapping`."""
        r = self._row(outputs, "node-omega")
        assert r["raw_failures"] == 2
        assert r["effective_failures"] == 1
        assert r["suppressed_fail_days"] == [108]
        assert r["last_fail_day"] == 106
        assert r["effective_flap_transitions"] == 5
        assert r["computed_status"] == "flapping"
        assert r["reasons"] == ["flap_threshold_exceeded"]

    def test_iota_last_fail_day_excludes_suppressed_day(self, outputs: dict[str, object]) -> None:
        """`node-iota` has consecutive fail probes on days 103-106 in its window.
        Day 106 is the most recent fail probe but is also a suppressed fail day, so
        `last_fail_day` must be the next-most-recent unsuppressed fail day (105),
        not 106."""
        r = self._row(outputs, "node-iota")
        assert r["suppressed_fail_days"] == [106]
        assert r["last_fail_day"] == 105


class TestCrossRefOverlay:
    """Cross-reference overlay reclassifies otherwise-healthy nodes as `cross_ref_pressured`."""

    def _row(self, outputs: dict[str, object], nid: str) -> dict[str, object]:
        rows = outputs["node_verdicts.json"]["nodes"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("node_id") == nid:
                return r
        raise AssertionError(f"missing node row {nid}")

    def test_eta_pressured_by_single_degraded_source(self, outputs: dict[str, object]) -> None:
        """`node-eta` would resolve to `healthy` on probes and parent alone, but the
        directed cross-reference edge from the unhealthy `node-iota` makes its final
        status `cross_ref_pressured`. The cross-ref pressure source is also
        recorded in the overlay file."""
        r = self._row(outputs, "node-eta")
        assert r["computed_status"] == "cross_ref_pressured"
        assert r["degraded"] is False
        assert r["reasons"] == ["cross_ref_pressure"]
        cro = outputs["cross_ref_overlay.json"]
        entries = {e["node_id"]: e for e in cro["pressured_nodes"]}
        assert "node-eta" in entries
        assert entries["node-eta"]["pressure_sources"] == ["node-iota"]

    def test_theta_pressured_by_multiple_degraded_sources(
        self, outputs: dict[str, object]
    ) -> None:
        """`node-theta` is reachable from two degraded sources via cross-reference
        edges (the forced-unhealthy `node-alpha` and the isolated `node-delta`); its
        pressure source list contains both in ascending node-id order. The edge
        from `node-eta` (itself cross_ref_pressured, but not degraded) does NOT
        contribute pressure — cross-ref pressure does not transit through
        non-degraded intermediaries."""
        r = self._row(outputs, "node-theta")
        assert r["computed_status"] == "cross_ref_pressured"
        assert r["reasons"] == ["cross_ref_pressure"]
        cro = outputs["cross_ref_overlay.json"]
        entries = {e["node_id"]: e for e in cro["pressured_nodes"]}
        assert "node-theta" in entries
        assert entries["node-theta"]["pressure_sources"] == ["node-alpha", "node-delta"]

    def test_cross_ref_pressure_does_not_override_primary_non_healthy(
        self, outputs: dict[str, object]
    ) -> None:
        """`node-omega` is reachable from an unhealthy cross-reference source
        (`node-iota`) but its primary status is `flapping`, not `healthy`. The
        overlay therefore must NOT change its status, and it must NOT appear in
        the cross_ref_overlay output. Cross-ref pressure only applies to nodes
        whose primary status is `healthy`."""
        r = self._row(outputs, "node-omega")
        assert r["computed_status"] == "flapping"
        cro = outputs["cross_ref_overlay.json"]
        ids = {e["node_id"] for e in cro["pressured_nodes"]}
        assert "node-omega" not in ids

    def test_overlay_includes_only_repressured_nodes_and_is_sorted(
        self, outputs: dict[str, object]
    ) -> None:
        """The overlay output lists exactly the nodes whose final status is
        `cross_ref_pressured`, sorted by ascending node_id, and the pressure-sources
        per entry are themselves sorted ascending."""
        cro = outputs["cross_ref_overlay.json"]
        assert isinstance(cro, dict)
        entries = cro["pressured_nodes"]
        assert isinstance(entries, list)
        ids = [str(e["node_id"]) for e in entries]
        assert ids == sorted(ids)
        for e in entries:
            sources = [str(x) for x in e["pressure_sources"]]
            assert sources == sorted(sources)
        rows = outputs["node_verdicts.json"]["nodes"]
        pressured_in_rows = {
            str(r["node_id"]) for r in rows if r["computed_status"] == "cross_ref_pressured"
        }
        assert pressured_in_rows == set(ids)

    def test_self_loops_and_unknown_ids_are_dropped(self, outputs: dict[str, object]) -> None:
        """The bundled cross_refs include a self-loop on `node-theta` and an edge
        from an unknown source id; neither shows up as a pressure source. The test
        derives the expected pressure-source mapping directly from the bundled
        edges file rather than copying a literal."""
        cross_path = DATA_DIR / "links" / "cross_refs.json"
        edges = json.loads(cross_path.read_text(encoding="utf-8"))["directed_pressure"]
        seen_self_loop = any(e["from"] == e["to"] for e in edges)
        seen_unknown = any(e["from"] not in {r["node_id"] for r in outputs["node_verdicts.json"]["nodes"]}
                           for e in edges)
        assert seen_self_loop, "bundle should exercise the self-loop drop path"
        assert seen_unknown, "bundle should exercise the unknown-source drop path"
        for e in outputs["cross_ref_overlay.json"]["pressured_nodes"]:
            for src in e["pressure_sources"]:
                assert src != e["node_id"]
                node_ids = {r["node_id"] for r in outputs["node_verdicts.json"]["nodes"]}
                assert src in node_ids


class TestDependencyTouchpoints:
    """Parent maps list children in sorted order with evaluated parent status."""

    def test_child_nodes_sorted(self, outputs: dict[str, object]) -> None:
        """Each parent block lists child node ids in ascending ASCII order."""
        parents = outputs["dependency_touchpoints.json"]["parents"]
        assert isinstance(parents, dict)
        for _pid, body in parents.items():
            assert isinstance(body, dict)
            kids = body["child_nodes"]
            assert isinstance(kids, list)
            skids = [str(x) for x in kids]
            assert skids == sorted(skids)


class TestTierPolicyWindows:
    """Rolling span accumulators surface per-tier effective window lengths."""

    def test_effective_rolling_spans_differ_by_tier(self, outputs: dict[str, object]) -> None:
        """Silver is widened, bronze is narrowed, and gold keeps the base span."""
        tiers = outputs["tier_policy.json"]["tiers"]
        assert isinstance(tiers, dict)
        assert tiers["silver"]["effective_rolling_span_days"] == 8
        assert tiers["silver"]["rolling_span_delta_sum"] == 1
        assert tiers["bronze"]["effective_rolling_span_days"] == 6
        assert tiers["bronze"]["rolling_span_delta_sum"] == -1
        assert tiers["gold"]["effective_rolling_span_days"] == 7
        assert tiers["gold"]["rolling_span_delta_sum"] == 0


class TestIncidentJournal:
    """Journal mirrors accepted, in-window, well-formed incidents."""

    def test_journal_sorted_by_day_then_id(self, outputs: dict[str, object]) -> None:
        """Applied events appear in ascending (day, event_id) order."""
        evs = outputs["incident_journal.json"]["applied_events"]
        assert isinstance(evs, list)
        keys = [(int(e["day"]), str(e["event_id"])) for e in evs]
        assert keys == sorted(keys)

    def test_journal_includes_expected_event_ids(self, outputs: dict[str, object]) -> None:
        """The bundled log applies ten well-formed in-window incidents spanning
        soak, flap and fail suppressions (including one against `node-omega`),
        threshold and span deltas, and directives. Four log events are rejected
        in total: the unaccepted `x00`, the unknown-kind `e07`, the malformed
        soak delta `e12` (missing target_tier), and the future-dated `e13`."""
        evs = outputs["incident_journal.json"]["applied_events"]
        ids = {str(e["event_id"]) for e in evs}
        assert ids == {"e01", "e02", "e03", "e04", "e05", "e06", "e08", "e09", "e10", "e11"}
