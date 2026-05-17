"""Behavioral tests for the shadow route quorum audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SRQ_DATA_DIR", "/app/shadowroute"))
AUDIT_DIR = Path(os.environ.get("SRQ_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "compromise_report.json",
    "degrade_report.json",
    "dependency_report.json",
    "route_profiles.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "b6fdcee87224cfecce624a4815d2ea52db2ec53f8d573f1132beb72740ac27fb",
    "incidents.json": "057469f2926076e749b743a98e42e2220416b06589a748c8298702a95a4743d3",
    "overlays/o1.json": "27898f637689ba0e5ac71e67f768c3c7c9dd1cbdcad0c74069f4f05975d6a4f5",
    "overlays/o2.json": "c839b54bf2aabde3c2ff16d71a216d8f243f1c7c2c6aeadc17d2eb4f72680799",
    "pins/p1.txt": "41db09ad266451ad7aca3caaf2d521d4686336d69a7339bcf98b937d625d231a",
    "pins/p2.txt": "4780ab23a9a5595599d88c4cd3201d2dd765396ae64c5be300e485a61d23634c",
    "policy.json": "5c59ee9c8e40599348c65805974d6834ee70ad4f5a40341beb2f107bb4a56294",
    "pool_state.json": "63feb2f9f6f4315e352fe42c3141ca722c13bd9daa9b10124e763c37fbbab566",
    "registry/build-stamp.json": "8b16b0bb1dc437441506feb57728e6dcd2deab4ac197646fcfcf0dd20f73c0b7",
    "registry/catalog.json": "4ba54ed14e677e1d52c54d526f2a2cf4541c8a61cb4cb841c5d03ab11e5df120",
    "registry/lanes.json": "c1f8d14930f07041dbb5c922a62ce0b5a8ee30eb706fe8347dae86b7d2f299eb",
    "registry/owner-map.json": "f9c4244cbd5dde83f84864365a79b5b541685da40abbaafe01e0f7af9e500098",
    "registry/tag-index.json": "44f5874faff3cdc1df27e3f966a5a0a0d3ba49d3ad8c6336acf1f3b86bfd0e5f",
    "routes/rt-alpha.json": "49f5cd0615c04d65c6652fd234ab3ce90ba205bbeb4cea64597f3e65037e035e",
    "routes/rt-beta.json": "a6c67d921575a64b2fd92104d3a4fef3a857a4f3089a2d961e32c5c5456c21cb",
    "routes/rt-delta.json": "298413b1629aa5d522081107bb3cfded5f7df2b72e10ea100029bff163826bf2",
    "routes/rt-epsilon.json": "36ba2198b61141f2252cf4bcef1a6536c86d29873f4d39e6bd83ae45a6346a1f",
    "routes/rt-eta.json": "2d866ce1651844ec0f7523ee3686257b0b4379f537fc130e6e57111baa52cf33",
    "routes/rt-gamma.json": "441eb487d9e31c3962c0a8f6ed1e4914468c8388ca30f79f55ef81adbd20e523",
    "routes/rt-iota.json": "ccfe8b72a74588f88f14b1770adde1b6b5fb3d669b0c7aef23a89d2e10b30372",
    "routes/rt-kappa.json": "c363c5842b696b610573306e6d0baa546182ac3863bb593e6479762cac2ac942",
    "routes/rt-theta.json": "b87fe6191d95eefee42576697ccf3277382f732fcad865c0f579979afbec2b19",
    "routes/rt-zeta.json": "da23e12e6a15850c5963896f9bd6687c167b25678bf40c1a13decdc7382954c9",
    "tiers.json": "0877ff68b07e7b46180441add73b57528d3cc764ce76baa9c96b18a17185418e",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "compromise_report.json": "e67db45a9c891e654c819e4c46cb20fc2cef1a810b11459d2f9d0ce2b5950f85",
    "degrade_report.json": "13d64eeb4fe196bf37755088b8d121f4aefd9bb4e6ae4d433a65806a8bc82792",
    "dependency_report.json": "41b2bc1dc50d7fd5d166366fd63efb61aa3392409513b46cd6d45a4061423e54",
    "route_profiles.json": "be96e3e0ac1c72d15d235359be68f885d8b85b66b08c9708e07e2edfe4360a2e",
    "summary.json": "eb13a532e64ec78d3cfb3befe6a97030a2b715cdf6fe9feac06f6b07a4b015a1",
}

EXPECTED_FIELD_HASHES = {
    "route_profiles.routes": "4185b0b790a1e6332771e17f329e41ed0684466a9b0046cf70d066320f5fe47d",
    "summary.quarantined_total": "73b2c3d367e79ae278e76c290128960efe1977c0b7ab649d92fb2f3839983dde",
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
        rp = outputs["route_profiles.json"]
        assert isinstance(rp, dict)
        assert (
            _sha256_bytes(_canonical(rp["routes"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["route_profiles.routes"]
        )
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(
                _canonical({"quarantined_total": sm["quarantined_total"]}).encode("utf-8")
            )
            == EXPECTED_FIELD_HASHES["summary.quarantined_total"]
        )


class TestRouteOrdering:
    """Deterministic ordering rules on profile rows."""

    def test_routes_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`routes` must list rows in ascending ASCII `route_id` order."""
        rows = outputs["route_profiles.json"]["routes"]
        assert isinstance(rows, list)
        ids = [str(r["route_id"]) for r in rows]
        assert ids == sorted(ids)


class TestProfileSemantics:
    """Spot-check routes that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], rid: str) -> dict[str, object]:
        rows = outputs["route_profiles.json"]["routes"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("route_id") == rid:
                return r
        raise AssertionError(f"missing route row {rid}")

    def test_ok_route_rt_alpha(self, outputs: dict[str, object]) -> None:
        """`rt-alpha` stays within the grace window and passes latency checks."""
        r = self._row(outputs, "rt-alpha")
        assert r["status"] == "ok"
        assert r["effective_quorum"] == 4

    def test_stale_route_rt_beta(self, outputs: dict[str, object]) -> None:
        """`rt-beta` has no in-window samples and is stale from an old last_seen_day."""
        r = self._row(outputs, "rt-beta")
        assert r["status"] == "stale"
        assert r["window_sample_count"] == 0

    def test_degraded_route_rt_gamma(self, outputs: dict[str, object]) -> None:
        """`rt-gamma` exceeds twice the median latency on its latest in-window sample."""
        r = self._row(outputs, "rt-gamma")
        assert r["status"] == "degraded"
        assert r["median_latency_ms"] == 22

    def test_quarantined_route_rt_delta(self, outputs: dict[str, object]) -> None:
        """`rt-delta` depends on compromised `m-toxic` and is quarantined."""
        r = self._row(outputs, "rt-delta")
        assert r["status"] == "quarantined"
        assert r["shadow_fraction_effective"] is None

    def test_blocked_route_rt_epsilon(self, outputs: dict[str, object]) -> None:
        """`rt-epsilon` is blocked because dependency `m-frozen` is on hold."""
        r = self._row(outputs, "rt-epsilon")
        assert r["status"] == "blocked"
        assert r["shadow_fraction_effective"] == 0

    def test_hold_route_rt_zeta(self, outputs: dict[str, object]) -> None:
        """`rt-zeta` is frozen by an accepted route_freeze incident on `m-zeta`."""
        r = self._row(outputs, "rt-zeta")
        assert r["status"] == "hold"

    def test_shadow_only_route_rt_eta(self, outputs: dict[str, object]) -> None:
        """`rt-eta` inherits pin `shadow_only` on `m-pin-shadow`."""
        r = self._row(outputs, "rt-eta")
        assert r["status"] == "shadow_only"

    def test_bronze_effective_quorum_rt_gamma(self, outputs: dict[str, object]) -> None:
        """Bronze tier weighting lowers `rt-gamma` quorum to three."""
        r = self._row(outputs, "rt-gamma")
        assert r["tier"] == "bronze"
        assert r["effective_quorum"] == 3


class TestDependencyReport:
    """Dependency edges and blocked-chain reasons."""

    def test_epsilon_blocked_chain(self, outputs: dict[str, object]) -> None:
        """`rt-epsilon` records hold_upstream against `m-frozen`."""
        chains = outputs["dependency_report.json"]["blocked_chains"]
        assert isinstance(chains, list)
        row = next(c for c in chains if c["route_id"] == "rt-epsilon")
        assert row["blocked_by_model_id"] == "m-frozen"
        assert row["reason"] == "hold_upstream"


class TestDegradeReport:
    """Degraded listing matches profile classification."""

    def test_degrade_report_lists_rt_gamma(self, outputs: dict[str, object]) -> None:
        """Only degraded routes appear in degrade_report.json."""
        rows = outputs["degrade_report.json"]["routes"]
        assert isinstance(rows, list)
        ids = [str(r["route_id"]) for r in rows]
        assert ids == ["rt-gamma"]


class TestCompromiseReport:
    """Compromise report enumerates toxic model and quarantined routes."""

    def test_compromise_models_and_routes(self, outputs: dict[str, object]) -> None:
        """Accepted compromise pins `m-toxic` and lists `rt-delta`."""
        rep = outputs["compromise_report.json"]
        assert isinstance(rep, dict)
        assert rep["models"] == ["m-toxic"]
        route_ids = [str(r["route_id"]) for r in rep["routes"]]
        assert route_ids == ["rt-delta"]


class TestSummaryTotals:
    """Summary counters reconcile with profile rows."""

    def test_summary_reconciles_status_counts(self, outputs: dict[str, object]) -> None:
        """Summary totals match per-status counts across route_profiles."""
        sm = outputs["summary.json"]
        rows = outputs["route_profiles.json"]["routes"]
        assert isinstance(sm, dict)
        assert isinstance(rows, list)
        assert int(sm["route_total"]) == len(rows)
        status_counts = {
            "blocked": 0,
            "degraded": 0,
            "hold": 0,
            "quarantined": 0,
            "stale": 0,
        }
        for r in rows:
            st = str(r["status"])
            if st in status_counts:
                status_counts[st] += 1
        assert int(sm["blocked_total"]) == status_counts["blocked"]
        assert int(sm["degraded_total"]) == status_counts["degraded"]
        assert int(sm["hold_total"]) == status_counts["hold"]
        assert int(sm["quarantined_total"]) == status_counts["quarantined"]
        assert int(sm["stale_total"]) == status_counts["stale"]
