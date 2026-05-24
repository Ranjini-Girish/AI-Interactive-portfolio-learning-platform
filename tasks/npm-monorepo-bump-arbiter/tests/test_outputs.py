"""Behavioural test suite for the npm-monorepo-bump-arbiter contract.

Tests are organised into named classes that each cover one slice of the
contract published in `/app/monorepo/SPEC.md`. Hash-locked checks compare
canonical JSON serialisations so byte-equivalent submissions agree
regardless of indentation choices the agent makes. Property-based checks
verify specific enum classifications, sort orders, and arithmetic
identities derived directly from the spec.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("NMB_DATA_DIR", "/app/monorepo"))
ARB_DIR = Path(os.environ.get("NMB_ARB_DIR", "/app/arbitration"))

OUTPUT_FILES = (
    "advisory_status.json",
    "bump_decisions.json",
    "engines_compatibility.json",
    "peer_satisfaction_report.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "advisories.json": "d9527d66a2ac09bcb70ea6089247a5ca6cdac2cde3c32f10d22d5d6b89bfa0a0",
    "current_lock.json": "162fca28a81326699ca4fef7745220f1ca385657f27136941f15582e720344e3",
    "governance/policy.json": "6fa41f2663dbe81338ececdcbcd872fddc1a8d68abbfa7bfa0c4dff27ddf7ff3",
    "incident_log.json": "7e259eb3164f8ac1b266631dda37e458470adf8c17999ac6dea5e9b72b47ab18",
    "monorepo_manifest.json": "451bafb50bc5a465639d5bfb86e0cf12dc6ae12c0d8cc264ba8635164d52316d",
    "packages/admin-console.json": "2ca2194b8307038884e4b6794b32a6c70f5381c14c197d75623241462c466cb6",
    "packages/api-gateway.json": "0084296f3a2566d57e6ee3ff072c40ee866b6f83911c8cd91468a52d99050d55",
    "packages/cli-tools.json": "d881cfef4b4c391a3cfc76c1d57c77d82638b6bedd0738931944dea57100bb9e",
    "packages/shared-types.json": "3c47cb6e9e88b097f68c2f597d636af4a469ff8e4d906dc9201728f0535a0e3a",
    "packages/shared-ui.json": "0809fb2d847d5fca8f218557feb7e441645519b11dcd2c7098acf33bc3bca550",
    "packages/web-app.json": "2e7ab078d30bccee4a10a18d753d7f63c60fe359ce09dd164a551971344d65c4",
    "packages/worker-fleet.json": "0ab8bb3fea7db26874cbe9198edc9ae4efc7ada71fc20a52068e3c42448514c2",
    "pool_state.json": "a1126e7fcccdf77e058ae9e45965cafd3f2cfd4a71f9ec80cb1108c30f7b33bf",
    "registry/flax-http.json": "0c12cafefa79c0bf1e989895ca714ad120491d490c5f4892d04d6a558d75020d",
    "registry/glint-core.json": "edec0a8024a6aa115ae51e71d379482cad892b57dd51989d0d963822216fc11b",
    "registry/glint-dom.json": "015c513fbb6343fbb81f8ab8018728f508ebc0596e77e3df803b77c6955cca86",
    "registry/kiln-bundler.json": "2045323b479c1888c9fb079c7f4e0f943ee31e1f323c4db05cdcc77b4db6b103",
    "registry/pebble-lint.json": "f9dd1c28c4ce18a710733b4dda9f125e7210ff6b5ee27416c4fb4f0625562588",
    "registry/quartz-ts.json": "20ad821a6ce254205fc2f5d32d204c7e274104597037a6212654e628940dec1d",
    "registry/tessera-utils.json": "c9954025e60d01f0b2414ae4d2bd4ebd51de9651fc43d472f8bdb8126cee09a8",
    "SPEC.md": "fc8b39b8cfc6f0879faca45ee982e28b9c7be55751d6101880bbf880e36c77c3",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "advisory_status.json": "993c238b80e62e4147866fc5316ab6db3177da9dc04ce10607f375bb38f19e0d",
    "bump_decisions.json": "be84bacc6c774936124cfbba24dcbd018ec76f2c811be35d722df67bf0933ccb",
    "engines_compatibility.json": "a804b4850709fb6a9fe5cd4e0da31d3a10444dd70d82f943ae4bed1a4a8d3649",
    "peer_satisfaction_report.json": "137ff75227d817435bdbd90956d9d35c1c38fa1134bd0d42672a5f7a9c0f4dfd",
    "summary.json": "3269edc46c9eadc301d160a81ee66a8f180810f6b7c66d8df9dcb29805bff012",
}

EXPECTED_FIELD_HASHES = {
    "advisory_status.advisories": "31fc7bb30b02a5d94d91700b0bbcbb66fce61e2581e8e87ecc98b3ec8ae84b96",
    "bump_decisions.entries": "587bb3347ead9b92d7de7f5f1c712f99abe1078ff3f7255c474e671e7aec6e8e",
    "engines_compatibility.engines_node_workspace_lower": "9d95d43f29d722a4f55084807d731af2a2024315b8342f2e1d3b4449d634ae89",
    "engines_compatibility.engines_node_workspace_upper": "2441e8ecda1661447b871363d8f64451c4f3981f94eb468b87555b3cf586f36f",
    "engines_compatibility.packages": "d66aed8a6f5da4a87f32d78ea3f621742fcebd7a00f029cbf41d5210881dad20",
    "peer_satisfaction_report.peer_links": "7d625b5e9a22b4e188725c46b75b99b24c12b68f1cf30975814c3f8f790fc5c0",
    "summary.action_counts": "9deccc89db44a1a35c091575a1a997d36fe8b29199f3d7a345d3b9050427704d",
    "summary.advisory_counts": "c4001f5f704dae886ba95ad51e69a836a31d9aeced72f44c5c032916408566f9",
    "summary.engines_blocked_versions_total": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.engines_node_workspace_lower": "9d95d43f29d722a4f55084807d731af2a2024315b8342f2e1d3b4449d634ae89",
    "summary.engines_node_workspace_upper": "2441e8ecda1661447b871363d8f64451c4f3981f94eb468b87555b3cf586f36f",
    "summary.ignored_incident_events": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.lockfile_drift_count": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.peer_status_counts": "4830d629056b7b31cd1bfd335a413cfc44d5c0137bc64fbb7cf655627295e375",
    "summary.resolution_kind_counts": "8aeaf4bb173acd4a570dff8896a6e15d97e8bc380cf864bb5091bb1c5d65aaa5",
    "summary.total_entries": "9400f1b21cb527d7fa3d3eabba93557a18ebe7a2ca4e471cfe5e4c5b4ca7f767",
    "summary.total_external_deps": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
    "summary.total_packages": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
}


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs():
    """Load every emitted artifact once per test session."""
    payload = {}
    for name in OUTPUT_FILES:
        path = ARB_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load(path)
    return payload


def _find_entry(entries, package, dep):
    for e in entries:
        if e["package"] == package and e["dep"] == dep:
            return e
    return None


def _find_advisory(advisories, advisory_id):
    for a in advisories:
        if a["advisory_id"] == advisory_id:
            return a
    return None


def _find_peer_link(peer_links, peer_name):
    for p in peer_links:
        if p["peer_name"] == peer_name:
            return p
    return None


def _find_package_engines(packages, name):
    for p in packages:
        if p["package"] == name:
            return p
    return None


# ---------------------------------------------------------------------------
# Structure & integrity
# ---------------------------------------------------------------------------


class TestReportStructure:
    """Top-level structural invariants of every emitted artifact."""

    def test_all_five_artifacts_exist(self):
        """Every required file under the arbitration directory is present."""
        for name in OUTPUT_FILES:
            assert (ARB_DIR / name).is_file(), f"missing: {name}"

    def test_bump_decisions_top_keys(self, outputs):
        """`bump_decisions.json` is a single-key envelope with `entries`."""
        bd = outputs["bump_decisions.json"]
        assert set(bd.keys()) == {"entries"}
        assert isinstance(bd["entries"], list)

    def test_peer_report_top_keys(self, outputs):
        """`peer_satisfaction_report.json` is a single-key envelope with `peer_links`."""
        psr = outputs["peer_satisfaction_report.json"]
        assert set(psr.keys()) == {"peer_links"}

    def test_engines_compatibility_top_keys(self, outputs):
        """`engines_compatibility.json` carries the workspace bounds plus per-package rows."""
        ec = outputs["engines_compatibility.json"]
        assert set(ec.keys()) == {
            "engines_node_workspace_lower",
            "engines_node_workspace_upper",
            "packages",
        }

    def test_advisory_status_top_keys(self, outputs):
        """`advisory_status.json` is a single-key envelope with `advisories`."""
        av = outputs["advisory_status.json"]
        assert set(av.keys()) == {"advisories"}

    def test_summary_top_keys(self, outputs):
        """`summary.json` contains exactly the documented twelve aggregate fields."""
        sm = outputs["summary.json"]
        expected = {
            "action_counts",
            "advisory_counts",
            "engines_blocked_versions_total",
            "engines_node_workspace_lower",
            "engines_node_workspace_upper",
            "ignored_incident_events",
            "lockfile_drift_count",
            "peer_status_counts",
            "resolution_kind_counts",
            "total_entries",
            "total_external_deps",
            "total_packages",
        }
        assert set(sm.keys()) == expected


class TestInputIntegrity:
    """Pin every fixture file to its byte-exact SHA-256."""

    @pytest.mark.parametrize("rel", sorted(EXPECTED_INPUT_HASHES.keys()))
    def test_input_hash(self, rel):
        """Each input file under the monorepo directory matches the expected digest."""
        path = DATA_DIR / rel
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == EXPECTED_INPUT_HASHES[rel], f"input changed: {rel}"


# ---------------------------------------------------------------------------
# Bump decisions
# ---------------------------------------------------------------------------


class TestBumpDecisions:
    """Per-entry decisions across every selection path and action enum."""

    def test_bump_decisions_canonical_hash(self, outputs):
        """The whole `bump_decisions.json` payload matches its canonical digest."""
        assert _sha(_canonical(outputs["bump_decisions.json"])) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["bump_decisions.json"]

    def test_entries_field_hash(self, outputs):
        """The `entries` list matches its canonical digest."""
        assert _sha(_canonical(outputs["bump_decisions.json"]["entries"])) == \
            EXPECTED_FIELD_HASHES["bump_decisions.entries"]

    def test_entries_sorted_by_package_then_dep(self, outputs):
        """Entries are sorted ascending by `(package, dep)`."""
        keys = [(e["package"], e["dep"]) for e in outputs["bump_decisions.json"]["entries"]]
        assert keys == sorted(keys)

    def test_workspace_protocol_star_resolution(self, outputs):
        """`workspace:*` resolves to the in-workspace package version and pins to it."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/api-gateway", "@aurum/shared-types")
        assert e is not None
        assert e["resolution_kind"] == "workspace_protocol"
        assert e["protocol_variant"] == "star"
        assert e["chosen_version"] == "0.9.1"
        assert e["action"] == "hold"
        assert e["reason"] == "satisfied"

    def test_workspace_protocol_caret_resolution(self, outputs):
        """`workspace:^` resolves to the in-workspace package version with `caret` variant."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/web-app", "@aurum/shared-ui")
        assert e is not None
        assert e["protocol_variant"] == "caret"
        assert e["chosen_version"] == "0.6.0"
        assert e["action"] == "bump"

    def test_workspace_protocol_tilde_resolution(self, outputs):
        """`workspace:~` resolves to the in-workspace package version with `tilde` variant."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/admin-console", "@aurum/shared-ui")
        assert e is not None
        assert e["protocol_variant"] == "tilde"
        assert e["chosen_version"] == "0.6.0"
        assert e["action"] == "bump"

    def test_workspace_protocol_missing_target_blocks(self, outputs):
        """A `workspace:` form referencing a non-monorepo package emits `block_no_workspace_target`."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/cli-tools", "@aurum/missing-pkg")
        assert e is not None
        assert e["action"] == "block_no_workspace_target"
        assert e["reason"] == "no_workspace_target"
        assert e["chosen_version"] is None

    def test_force_freeze_safe_action(self, outputs):
        """A `force_freeze` directive whose locked version passes every check emits `freeze`."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/web-app", "glint-core")
        assert e is not None
        assert e["action"] == "freeze"
        assert e["source"] == "incident_log_force_freeze"
        assert e["chosen_version"] == "2.0.0"
        assert e["reason"] == "satisfied"

    def test_force_freeze_advisory_conflict(self, outputs):
        """A `force_freeze` locked into an active advisory range emits `freeze_unsafe`."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/shared-ui", "glint-dom")
        assert e is not None
        assert e["action"] == "freeze_unsafe"
        assert e["reason"] == "freeze_advisory_conflict"
        assert e["source"] == "incident_log_force_freeze"

    def test_dist_tag_pin_safe_action(self, outputs):
        """A `dist_tag_pin` whose target passes every check emits `dist_tag_pin`."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/cli-tools", "quartz-ts")
        assert e is not None
        assert e["action"] == "dist_tag_pin"
        assert e["chosen_version"] == "4.6.0"
        assert e["source"] == "incident_log_dist_tag_pin"

    def test_dist_tag_pin_advisory_block(self, outputs):
        """A `dist_tag_pin` whose target falls in an active advisory emits `block_dist_tag_unsafe`."""
        for pkg in ("@aurum/admin-console", "@aurum/cli-tools"):
            e = _find_entry(outputs["bump_decisions.json"]["entries"], pkg, "pebble-lint")
            assert e is not None
            assert e["action"] == "block_dist_tag_unsafe"
            assert e["chosen_version"] is None
            assert e["reason"] == "dist_tag_unsafe"

    def test_planner_bump_action(self, outputs):
        """A planner-selected entry whose chosen version exceeds the lock emits `bump`."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/worker-fleet", "flax-http")
        assert e is not None
        assert e["action"] == "bump"
        assert e["chosen_version"] == "3.2.0"
        assert e["current_version"] == "3.0.0"
        assert e["source"] == "planner"

    def test_planner_hold_action(self, outputs):
        """A planner-selected entry whose chosen version equals the lock emits `hold`."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/api-gateway", "tessera-utils")
        assert e is not None
        assert e["action"] == "hold"
        assert e["chosen_version"] == "1.0.0"

    def test_planner_downgrade_action(self, outputs):
        """A planner-selected entry whose chosen version trails the lock emits `downgrade`."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/worker-fleet", "tessera-utils")
        assert e is not None
        assert e["action"] == "downgrade"
        assert e["chosen_version"] == "0.9.0"
        assert e["current_version"] == "1.0.0"

    def test_exports_downgrade_drops_offending_condition(self, outputs):
        """An entry requiring an exports condition no eligible version supports drops it in ASCII order."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/api-gateway", "flax-http")
        assert e is not None
        assert e["exports_dropped_set"] == ["node"]
        assert e["reason"] == "exports_downgrade"
        assert e["chosen_version"] == "3.2.0"

    def test_exports_downgrade_with_downgrade_action(self, outputs):
        """The `exports_downgrade` reason composes with any action including `downgrade`."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/shared-types", "tessera-utils")
        assert e is not None
        assert e["exports_dropped_set"] == ["types"]
        assert e["reason"] == "exports_downgrade"
        assert e["action"] == "downgrade"

    def test_no_eligible_version_block(self, outputs):
        """A planner entry whose range admits no version emits `block_no_eligible_version`."""
        e = _find_entry(outputs["bump_decisions.json"]["entries"], "@aurum/worker-fleet", "kiln-bundler")
        assert e is not None
        assert e["action"] == "block_no_eligible_version"
        assert e["chosen_version"] is None
        assert e["reason"] == "no_eligible_version"

    def test_yanked_version_is_excluded_unless_pinned(self, outputs):
        """The yanked `glint-core@2.1.0` is never chosen when not in the lock."""
        for e in outputs["bump_decisions.json"]["entries"]:
            if e["dep"] == "glint-core" and e["chosen_version"] is not None:
                assert e["chosen_version"] != "2.1.0"

    def test_protocol_variant_is_null_for_registry_entries(self, outputs):
        """Every registry-resolved entry leaves `protocol_variant` as JSON null."""
        for e in outputs["bump_decisions.json"]["entries"]:
            if e["resolution_kind"] == "registry":
                assert e["protocol_variant"] is None

    def test_exports_dropped_set_alphabetically_sorted(self, outputs):
        """`exports_dropped_set` is always emitted in ascending ASCII order."""
        for e in outputs["bump_decisions.json"]["entries"]:
            assert e["exports_dropped_set"] == sorted(e["exports_dropped_set"])


# ---------------------------------------------------------------------------
# Peer satisfaction
# ---------------------------------------------------------------------------


class TestPeerSatisfactionReport:
    """peerDependency intersection logic across multi-consumer linkage."""

    def test_peer_report_canonical_hash(self, outputs):
        """The whole `peer_satisfaction_report.json` payload matches its canonical digest."""
        assert _sha(_canonical(outputs["peer_satisfaction_report.json"])) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["peer_satisfaction_report.json"]

    def test_peer_links_field_hash(self, outputs):
        """The `peer_links` list matches its canonical digest."""
        assert _sha(_canonical(outputs["peer_satisfaction_report.json"]["peer_links"])) == \
            EXPECTED_FIELD_HASHES["peer_satisfaction_report.peer_links"]

    def test_peer_links_sorted_by_peer_name(self, outputs):
        """`peer_links` are ordered by `peer_name` ascending."""
        names = [p["peer_name"] for p in outputs["peer_satisfaction_report.json"]["peer_links"]]
        assert names == sorted(names)

    def test_peer_satisfied_status(self, outputs):
        """A peer whose resolved version lies inside the consumer intersection is `satisfied`."""
        p = _find_peer_link(outputs["peer_satisfaction_report.json"]["peer_links"], "glint-core")
        assert p is not None
        assert p["peer_status"] == "satisfied"
        assert p["resolved_peer_version"] == "2.0.0"
        assert p["intersection_range"] == ">=2.0.0 <3.0.0"

    def test_peer_unsatisfiable_intersection(self, outputs):
        """An empty intersection of consumer ranges yields `unsatisfiable_intersection` with null range."""
        p = _find_peer_link(outputs["peer_satisfaction_report.json"]["peer_links"], "glint-dom")
        assert p is not None
        assert p["peer_status"] == "unsatisfiable_intersection"
        assert p["intersection_range"] is None

    def test_peer_outside_intersection(self, outputs):
        """A resolved peer outside a non-empty intersection yields `outside_intersection`."""
        p = _find_peer_link(outputs["peer_satisfaction_report.json"]["peer_links"], "tessera-utils")
        assert p is not None
        assert p["peer_status"] == "outside_intersection"
        assert p["resolved_peer_version"] == "1.0.0"
        assert p["intersection_range"] == ">=0.9.0 <0.10.0"

    def test_peer_unresolved_when_target_absent(self, outputs):
        """A peer whose target dep is not itself an entry yields `peer_unresolved`."""
        p = _find_peer_link(outputs["peer_satisfaction_report.json"]["peer_links"], "forge-runtime")
        assert p is not None
        assert p["peer_status"] == "peer_unresolved"
        assert p["resolved_peer_version"] is None

    def test_consumers_sorted_per_peer(self, outputs):
        """Within each peer link, the `consumers` list is sorted by `(package, dep_chain)`."""
        for p in outputs["peer_satisfaction_report.json"]["peer_links"]:
            keys = [(c["package"], c["dep_chain"]) for c in p["consumers"]]
            assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Engines compatibility
# ---------------------------------------------------------------------------


class TestEnginesCompatibility:
    """Workspace-engines superset check and per-package status enums."""

    def test_engines_report_canonical_hash(self, outputs):
        """The whole `engines_compatibility.json` payload matches its canonical digest."""
        assert _sha(_canonical(outputs["engines_compatibility.json"])) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["engines_compatibility.json"]

    def test_engines_packages_field_hash(self, outputs):
        """The `packages` list field matches its canonical digest."""
        assert _sha(_canonical(outputs["engines_compatibility.json"]["packages"])) == \
            EXPECTED_FIELD_HASHES["engines_compatibility.packages"]

    def test_workspace_lower_field_hash(self, outputs):
        """The workspace lower bound matches its canonical digest."""
        assert _sha(_canonical(outputs["engines_compatibility.json"]["engines_node_workspace_lower"])) == \
            EXPECTED_FIELD_HASHES["engines_compatibility.engines_node_workspace_lower"]

    def test_workspace_upper_field_hash(self, outputs):
        """The workspace upper bound matches its canonical digest."""
        assert _sha(_canonical(outputs["engines_compatibility.json"]["engines_node_workspace_upper"])) == \
            EXPECTED_FIELD_HASHES["engines_compatibility.engines_node_workspace_upper"]

    def test_engines_packages_sorted(self, outputs):
        """`engines_compatibility.packages` is sorted ascending by `package`."""
        names = [p["package"] for p in outputs["engines_compatibility.json"]["packages"]]
        assert names == sorted(names)

    def test_subrange_status_when_within_bounds(self, outputs):
        """A package whose engines range is within the workspace bounds is `subrange`."""
        pkgs = outputs["engines_compatibility.json"]["packages"]
        p = _find_package_engines(pkgs, "@aurum/web-app")
        assert p["package_engines_status"] == "subrange"
        assert p["lower_exceeded_by"] == "0.0.0"
        assert p["upper_exceeded_by"] == "0.0.0"

    def test_lower_violated_status_and_componentwise_diff(self, outputs):
        """A package whose engines lower bound falls below the workspace's emits `lower_violated`."""
        pkgs = outputs["engines_compatibility.json"]["packages"]
        p = _find_package_engines(pkgs, "@aurum/worker-fleet")
        assert p["package_engines_status"] == "lower_violated"
        assert p["lower_exceeded_by"] == "1.0.0"
        assert p["upper_exceeded_by"] == "0.0.0"

    def test_upper_violated_status_and_componentwise_diff(self, outputs):
        """A package whose engines upper bound exceeds the workspace's emits `upper_violated`."""
        pkgs = outputs["engines_compatibility.json"]["packages"]
        p = _find_package_engines(pkgs, "@aurum/api-gateway")
        assert p["package_engines_status"] == "upper_violated"
        assert p["lower_exceeded_by"] == "0.0.0"
        assert p["upper_exceeded_by"] == "1.0.0"

    def test_both_violated_status_and_componentwise_diff(self, outputs):
        """A package whose engines range exceeds the workspace on both ends emits `both_violated`."""
        pkgs = outputs["engines_compatibility.json"]["packages"]
        p = _find_package_engines(pkgs, "@aurum/shared-types")
        assert p["package_engines_status"] == "both_violated"
        assert p["lower_exceeded_by"] == "2.0.0"
        assert p["upper_exceeded_by"] == "1.0.0"

    def test_engines_blocked_count_zero_when_no_isolated_failures(self, outputs):
        """A package whose registry versions are not engines-blocked-alone reports zero."""
        pkgs = outputs["engines_compatibility.json"]["packages"]
        p = _find_package_engines(pkgs, "@aurum/web-app")
        assert p["engines_blocked_versions_count"] == 0

    def test_engines_blocked_count_nonzero_when_isolated_failures(self, outputs):
        """A package with registry versions failing only the engines check reports the exact count."""
        pkgs = outputs["engines_compatibility.json"]["packages"]
        assert _find_package_engines(pkgs, "@aurum/api-gateway")["engines_blocked_versions_count"] == 1
        assert _find_package_engines(pkgs, "@aurum/shared-ui")["engines_blocked_versions_count"] == 2


# ---------------------------------------------------------------------------
# Advisory status
# ---------------------------------------------------------------------------


class TestAdvisoryStatus:
    """Advisory status enum, mitigation-method lookup, and patched-versions list."""

    def test_advisory_status_canonical_hash(self, outputs):
        """The whole `advisory_status.json` payload matches its canonical digest."""
        assert _sha(_canonical(outputs["advisory_status.json"])) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["advisory_status.json"]

    def test_advisories_field_hash(self, outputs):
        """The `advisories` list matches its canonical digest."""
        assert _sha(_canonical(outputs["advisory_status.json"]["advisories"])) == \
            EXPECTED_FIELD_HASHES["advisory_status.advisories"]

    def test_advisories_sorted_by_id(self, outputs):
        """`advisories` are ordered by `advisory_id` ascending."""
        ids = [a["advisory_id"] for a in outputs["advisory_status.json"]["advisories"]]
        assert ids == sorted(ids)

    def test_advisory_overridden_status(self, outputs):
        """An accepted `advisory_override` cancels the advisory with status `overridden`."""
        a = _find_advisory(outputs["advisory_status.json"]["advisories"], "GH-1005")
        assert a["status"] == "overridden"
        assert a["mitigation_method"] == "override"

    def test_advisory_inactive_low_severity_status(self, outputs):
        """An advisory below the severity threshold is `inactive_low_severity`."""
        a = _find_advisory(outputs["advisory_status.json"]["advisories"], "GH-1003")
        assert a["status"] == "inactive_low_severity"
        assert a["mitigation_method"] is None

    def test_advisory_still_open_frozen_status(self, outputs):
        """An advisory whose at-least-one consumer chose `freeze_unsafe` is `still_open_frozen`."""
        a = _find_advisory(outputs["advisory_status.json"]["advisories"], "GH-1006")
        assert a["status"] == "still_open_frozen"
        assert a["mitigation_method"] == "frozen"

    def test_advisory_unmitigated_pinned_status(self, outputs):
        """An advisory whose at-least-one consumer chose `block_dist_tag_unsafe` is `unmitigated_pinned`."""
        a = _find_advisory(outputs["advisory_status.json"]["advisories"], "GH-1004")
        assert a["status"] == "unmitigated_pinned"
        assert a["mitigation_method"] == "pinned"

    def test_advisory_mitigated_by_exports_drop_status(self, outputs):
        """An advisory mitigated by some consumer dropping exports has status `mitigated_by_exports_drop`."""
        a = _find_advisory(outputs["advisory_status.json"]["advisories"], "GH-1002")
        assert a["status"] == "mitigated_by_exports_drop"
        assert a["mitigation_method"] == "exports_drop"
        assert a["patched_versions"] == ["3.2.0"]

    def test_advisory_resolved_by_bump_status(self, outputs):
        """An advisory where every consumer landed in the patched range is `resolved_by_bump`."""
        a = _find_advisory(outputs["advisory_status.json"]["advisories"], "GH-1001")
        assert a["status"] == "resolved_by_bump"
        assert a["mitigation_method"] == "bump"
        assert a["patched_versions"] == ["2.0.0"]

    def test_advisory_still_open_status(self, outputs):
        """An active advisory not resolved by any mechanism is `still_open`."""
        a = _find_advisory(outputs["advisory_status.json"]["advisories"], "GH-1007")
        assert a["status"] == "still_open"
        assert a["mitigation_method"] is None

    def test_advisory_patched_versions_sorted(self, outputs):
        """`patched_versions` is sorted by tuple version comparison ascending."""
        for a in outputs["advisory_status.json"]["advisories"]:
            tuples = [tuple(int(x) for x in v.split(".")) for v in a["patched_versions"]]
            assert tuples == sorted(tuples)

    def test_advisory_patched_versions_inactive_includes_all_consumers(self, outputs):
        """`patched_versions` aggregates consumer chosen versions even on inactive advisories."""
        a = _find_advisory(outputs["advisory_status.json"]["advisories"], "GH-1003")
        assert a["patched_versions"] == ["0.9.0", "1.0.0"]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestSummary:
    """Aggregate counters across the four other artifacts."""

    def test_summary_canonical_hash(self, outputs):
        """The whole `summary.json` payload matches its canonical digest."""
        assert _sha(_canonical(outputs["summary.json"])) == \
            EXPECTED_OUTPUT_CANONICAL_HASHES["summary.json"]

    @pytest.mark.parametrize("field", sorted(k.removeprefix("summary.") for k in EXPECTED_FIELD_HASHES if k.startswith("summary.")))
    def test_summary_field_hash(self, outputs, field):
        """Every named summary field matches its canonical digest."""
        actual = outputs["summary.json"][field]
        expected = EXPECTED_FIELD_HASHES[f"summary.{field}"]
        assert _sha(_canonical(actual)) == expected

    def test_summary_action_counts_keys_are_sorted(self, outputs):
        """`action_counts` keys are emitted in ascending ASCII order."""
        keys = list(outputs["summary.json"]["action_counts"].keys())
        assert keys == sorted(keys)

    def test_summary_advisory_counts_keys_are_sorted(self, outputs):
        """`advisory_counts` keys are emitted in ascending ASCII order."""
        keys = list(outputs["summary.json"]["advisory_counts"].keys())
        assert keys == sorted(keys)

    def test_summary_engines_total_matches_per_package_sum(self, outputs):
        """`engines_blocked_versions_total` equals the sum of per-package counts."""
        engines = outputs["engines_compatibility.json"]["packages"]
        per_pkg_sum = sum(p["engines_blocked_versions_count"] for p in engines)
        assert outputs["summary.json"]["engines_blocked_versions_total"] == per_pkg_sum

    def test_summary_total_entries_matches_bump_decisions(self, outputs):
        """`total_entries` equals the length of `bump_decisions.entries`."""
        assert outputs["summary.json"]["total_entries"] == \
            len(outputs["bump_decisions.json"]["entries"])

    def test_summary_total_packages_matches_engines_rows(self, outputs):
        """`total_packages` equals the number of rows in `engines_compatibility.packages`."""
        assert outputs["summary.json"]["total_packages"] == \
            len(outputs["engines_compatibility.json"]["packages"])

    def test_summary_workspace_bounds_match_engines_report(self, outputs):
        """Workspace bounds in `summary.json` match `engines_compatibility.json`."""
        sm = outputs["summary.json"]
        ec = outputs["engines_compatibility.json"]
        assert sm["engines_node_workspace_lower"] == ec["engines_node_workspace_lower"]
        assert sm["engines_node_workspace_upper"] == ec["engines_node_workspace_upper"]

    def test_summary_action_counts_sum_to_total_entries(self, outputs):
        """Sum of `action_counts` values equals `total_entries`."""
        sm = outputs["summary.json"]
        assert sum(sm["action_counts"].values()) == sm["total_entries"]

    def test_summary_resolution_kind_counts_sum_to_total_entries(self, outputs):
        """Sum of `resolution_kind_counts` values equals `total_entries`."""
        sm = outputs["summary.json"]
        assert sum(sm["resolution_kind_counts"].values()) == sm["total_entries"]
