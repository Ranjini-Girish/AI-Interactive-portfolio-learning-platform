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
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "81392e3feb8d0e216b4e5482c8bb05c7da79f07b7bdee6f73702c158eb6fac4a",
    "ancillary/channel_tag.json": "e3f743dfbbdb07da2b40a8cb71d92bdda53bd0eed55e247c35b38c7dce951a91",
    "ancillary/ci_guard.json": "0ecfe0ba66d080f854e5704d7442c62e8a8f7b315e7d617d1135e874b9b1d4f8",
    "ancillary/extra_one.json": "220aa04e25113593bb0f4ffcbfbf64b73c7520df0da633fd8b14417b0fecea7a",
    "ancillary/extra_two.json": "bc821685311c618465390595375c4f5f65a30dcd5df50e6317dd3079deb90d0a",
    "ancillary/watermark.txt": "53e18be76281523eac67dcf79c274696eaf561e115361a2f506ab63e14ae1e08",
    "incident_log.json": "50769d21bab721c930c22677a3296a9451244a8e64e3827f3029073a749a8e5c",
    "links/cross_refs.json": "9acc15ea8195561fd686275caebce283b3f832af9064bd7e1b474d94dad260f3",
    "nodes/node-alpha.json": "3ab782186763d128441468678413be734e3322e6d3f276f322f2c76047d6610f",
    "nodes/node-beta.json": "7175d3dd7975d9beb839bb0f80aead2f9ce6a5ecec84dfcd8980658215333a5f",
    "nodes/node-delta.json": "b673dc3c73e6d23b2bbe53aa704049a480e9f8308f2af2f1ae84fb6ebcebaea5",
    "nodes/node-epsilon.json": "fe2fb1e4a6e16d84dec355827d5367a4face668cd1b3c559cee0b6580e0a87cd",
    "nodes/node-eta.json": "afb89592a02045ee8d86526298b9f87ed614b93b11259399943497e18dcc5fa9",
    "nodes/node-gamma.json": "9ace1db36c6042bffeac5c5e8a284ccda5465f9e9b6b144a1e1ff2744e7d175f",
    "nodes/node-iota.json": "a846e961871eda88db8eace2ffe8e1a24e2a4a891ec98111f431427a359c76c8",
    "nodes/node-kappa.json": "16b5390f3c2a76ffbc63d53e053f82b455e2390e1ab69a1a5cd779c3b8eb500a",
    "nodes/node-lambda.json": "479bcfdd12a68368efd0d34f3db04d639be63be9ea0984b5c95f4662ebe7a00d",
    "nodes/node-mu.json": "876b5d27efdc88e16091323ff2530ce98ae1a45ccfe26b45581b5bdfd5a6e643",
    "nodes/node-theta.json": "481a52b7aca1b56cb5f365746411236b9e42490490c6cf7d257b4b4eae48dbe2",
    "nodes/node-zeta.json": "0b0ce3fff11d76c12c2e468bb42f20a9a46072b61d21ea3dd8e900bd352343d3",
    "policy.json": "563e1cc8d47ef9c6def4f09054f1ccc006d6e4d9341e39b299a13935c5858a6e",
    "pool_state.json": "bc383d68e9727a5442852b4f4b55c1302361c4e1666ecd6ffd26fb181095b1c7",
    "registry/forest_index.json": "cab037744dc47a72ce35d6d4705a77fcc56774a9537b1001f8555d0d60c0e927",
    "registry/tier_labels.json": "bbb692f10cfd7dc9c1cb0c07b5a0a27f42d1130e9dcc70b66aef42420d6b4c58",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "dependency_touchpoints.json": "22ddad0b1f6529a95bb17ecb3ac650132ba9e181e6ffe8fbf7e61e225168134d",
    "incident_journal.json": "9580c239547c08c47791c33abf4eb781a53cb0c5e1dfd7a042f71444bfe3f4af",
    "node_verdicts.json": "7515afc5e4f62b5f896841ee1d0f327fe5677243c1c855792f9a1fb245b702a3",
    "summary.json": "8412ab3536f76e944ee83b27cf5103d47df1e17410178190d39b8dc80523b064",
    "tier_policy.json": "65042a8d33502f41a0dbcef141730ec7aefc590fa5e47bcd7672748afb852b9e",
}


EXPECTED_FIELD_HASHES = {
    "dependency_touchpoints.parents": "41f6216e4fadf5225dd9402f27854e740e49186780ccececebfda7d99fc0dc09",
    "incident_journal.applied_events": "201c2e4ab179caa4cb88cb2e545395821a78537b4fc4873dea2529b7a2408e3e",
    "node_verdicts.nodes": "0562ae759405619a7fc2c6937b5a43c59a9eacdc526509287cf6f9e1105bff8c",
    "summary.applied_incident_events": "19581e27de7ced00ff1ce50b2047e7a567c76b1cbaebabe5ef03f7c3017bb5b7",
    "summary.degraded_nodes": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
    "summary.flapping_nodes": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.healthy_nodes": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.ignored_incident_events": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.inherited_degraded_nodes": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.isolated_nodes": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.nodes_total": "6b51d431df5d7f141cbececcf79edf3dd861c3b4069f0b11661a3eefacbba918",
    "summary.soaking_nodes": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.unhealthy_nodes": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "tier_policy.tiers": "cb5ca204f943f26f9a1c7d4aa344f9527e81f98833c5f0d94b95fc42c6288dd2",
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
        """`node-iota` still trips the silver fail threshold after a wider silver
        window pulls in an extra fail day, a fail-day suppression shaves one
        counted failure, and the remaining effective failures meet the tier
        threshold."""
        r = self._row(outputs, "node-iota")
        assert r["computed_status"] == "unhealthy"
        assert r["reasons"] == ["threshold_exceeded"]
        assert r["raw_failures"] == 4
        assert r["effective_failures"] == 3

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

    def test_healthy_rows_empty_reasons(self, outputs: dict[str, object]) -> None:
        """Clean leaves emit healthy with empty reasons arrays."""
        for nid in ("node-gamma", "node-theta", "node-eta"):
            r = self._row(outputs, nid)
            assert r["computed_status"] == "healthy"
            assert r["reasons"] == []
            assert r["degraded"] is False


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
        """The bundled log applies nine well-formed incidents spanning soak,
        flap and fail suppressions, threshold and span deltas, directives, and a
        rejected malformed entry."""
        evs = outputs["incident_journal.json"]["applied_events"]
        ids = {str(e["event_id"]) for e in evs}
        assert ids == {"e01", "e02", "e03", "e04", "e05", "e06", "e08", "e09", "e10"}
