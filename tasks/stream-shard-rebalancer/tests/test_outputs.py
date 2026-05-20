"""Behavioral tests for the stream-shard-rebalancer task.

The tests verify that the JSON files at ``/app/plan/`` satisfy the contract
in ``instruction.md`` (which delegates the normative grammar / sort rules /
precedence to ``/app/cluster/SPEC.md``). Anti-cheat fixtures are hash-locked
to canonicalised reference output computed independently from the input data
under the same spec; an agent cannot pass these tests by writing arbitrary or
hand-tweaked JSON.

The task is constrained to a Go implementation: the agent must produce a Go
source tree under ``/app/src/`` and a compiled binary at ``/app/bin/rebalancer``
whose execution against ``/app/cluster/`` populates ``/app/plan/``. Tests in
``TestImplementationLanguage`` enforce that constraint by confirming the
deliverable is a native ELF binary with Go toolchain build metadata, by
re-running the agent's binary into a temporary directory, and by comparing its
output against the files left in ``/app/plan/`` byte-for-byte.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

CLUSTER_DIR = Path(os.environ.get("SSR_CLUSTER_DIR", "/app/cluster"))
PLAN_DIR = Path(os.environ.get("SSR_PLAN_DIR", "/app/plan"))
SRC_DIR = Path(os.environ.get("SSR_SRC_DIR", "/app/src"))
BIN_PATH = Path(os.environ.get("SSR_BIN_PATH", "/app/bin/rebalancer"))

REQUIRED_OUTPUT_FILES = [
    "consumer_rebalance.json",
    "lag_report.json",
    "partition_assignment.json",
    "quarantine_status.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md":                                "1beb8b1065c44642599ec1375e98ef6e0493bc7aabc6b5e2fe599ab8847c0505",
    "consumers/cg.audit-archiver.json":       "b8110080a0b774d81e7452f90fd1c399247cb51fe875f4e5152057d9a17487ec",
    "consumers/cg.legacy-importer.json":      "9ccac0dcbbb3222fa52d6e8ce859111f97c68bb6491ab6151f8b6a2e3606ff98",
    "consumers/cg.metrics-aggregator.json":   "9c3f0a61e3a1ae7801967c875c12c9600356dad643601b1647a0886063732fb3",
    "consumers/cg.order-processor.json":      "15732b37aa0d0e131632a4f6e84251d2992b0e3c777f5573c0214f53d1f7fe6b",
    "consumers/cg.payments-billing.json":     "e3d467e98624d7aa90a55850c81598fd121868b5130e4ed5492a60c157a6f338",
    "incidents/incident_log.json":            "06d6fd5abce9564ff06512def5803b1bd9142fb9de20c1a7690ee0aba5711e44",
    "policy/rebalance_policy.json":           "a792af5c83f801d9070edf54e6b840f13c130e9ea0ccebd2225690c1e58a611e",
    "pool_state.json":                        "4ee5279bcc1c1e720b6618eaf9467931422f3c26c077f6896c02e5aa93c5228b",
    "topics/t.audit.archive.json":            "0d2cc1313751c7b388286d997bb5f503d227e36d06464e71326b0e19940f1815",
    "topics/t.audit.trail.json":              "6892bf14dd89616284a8bcfb9e58a5f652c080a7d4dc6204212daab7d7cf242a",
    "topics/t.legacy.dump.json":              "3705e8471fabf2c25e58ca9ec50aed330cc140a4f8fa7e51b38504dbbced2def",
    "topics/t.metrics.fast.json":             "1c385804a0fe68c0abc82ea73fa3648637da52895990e3ca1be922cc37759446",
    "topics/t.metrics.slow.json":             "41d33f190aa4f0f71b6638922658f5db61ac9419d150abc22a56d2b9a729168f",
    "topics/t.orders.events.json":            "b716d97647af03e5c99db1003b8bed914ac131e6fdcb92412005f2ea87dce490",
    "topics/t.payments.events.json":          "5282cdd0e0c4f0b0f61528b575ad532bc3b95b77d662abf27c7bd082ba5e65ee",
    "topics/t.product.updates.json":          "6e354cbff5215d854d78474d408ad11cc08e309e01c2c885d4a86e19993cf831",
    "topics/t.user.events.json":              "eddcf7196e32f28f34ffda0f74d8b5a4a648834d7cc2e9922bfda7a1056dbb9c",
    "topology/azs.json":                      "945e62b48a4471dad7119365376781606e5e7b36954c26563188f3423ef47d53",
    "topology/cluster.json":                  "06ccc069a921d376f012df5b514b494fb4779264fd9564179b5805dee3fccc3e",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "consumer_rebalance.json":    "5767048636fd94e02952528ce66ccea8e4c6b719382d2a3fae69ea09f4bf034c",
    "lag_report.json":            "d8b2526bb181a50d7b4840acbe3a21c86d9915224263f98cd5b0a59d6cf0ddf7",
    "partition_assignment.json":  "00f9d6038107a2e617b7aee45485f449b7e127b445957a1c31c6ecef5a8a6fa5",
    "quarantine_status.json":     "b01481525850bea4363af75ba55f2243e51ccccebbecc07c96951a1dd4459be9",
    "summary.json":               "f8648cbcc962d2adb75dd88e501221fe8377867b24057271464f3e77b5e118b5",
}

EXPECTED_FIELD_HASHES = {
    "partition_assignment.partitions":              "65f5a16f67fe173be050545c9b72468799d8881a29921ce9d6a424bb78ae9d16",
    "consumer_rebalance.groups":                    "2c3a077e7c1eb579d25b2f56063b2428499c59dc059c1dbe612254e6d6d01241",
    "lag_report.groups":                            "5a83ece7d3b7771f898d3fd7f1bfb91bd819e4e8aa1ce2dd4f660e27212c2608",
    "quarantine_status.brokers":                    "a229bf8f913436b7795bf06c8e1f8e84c6601e58b7f82b5ffb18ca9e38a14a64",
    "summary.accepted_incident_events":             "f0b5c2c2211c8d67ed15e75e656c7862d086e9245420892a7de62cd9ec582a06",
    "summary.active_brokers":                       "2e6d31a5983a91251bfae5aefa1c0a19d8ba3cf601d0e8a706b4cfa9661a6b8a",
    "summary.anti_affinity_violations_blocked":     "9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa",
    "summary.brokers_over_threshold":               "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.brokers_total":                        "a1fb50e6c86fae1679ef3351296fd6713411a08cf8dd1790a4fd05fae8688164",
    "summary.capacity_overridden_brokers":          "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.consumer_groups_total":                "f0b5c2c2211c8d67ed15e75e656c7862d086e9245420892a7de62cd9ec582a06",
    "summary.demotions_total":                      "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.frozen_partitions":                    "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.frozen_quarantined_brokers":           "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.groups_with_lag_exceeded":             "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.groups_with_lag_within_target_or_near": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.ignored_incident_events":              "f0b5c2c2211c8d67ed15e75e656c7862d086e9245420892a7de62cd9ec582a06",
    "summary.partitions_total":                     "9961d158a7e0e2f990765971a9e490af826c0743b7d603020f34cc8944319fcb",
    "summary.quarantined_brokers":                  "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.topics_total":                         "2e6d31a5983a91251bfae5aefa1c0a19d8ba3cf601d0e8a706b4cfa9661a6b8a",
}

PLACEMENT_REASON_VALUES = {
    "hash_placement",
    "frozen_during_quarantine",
    "frozen_by_event",
    "demoted_for_backpressure",
}

PARTITION_STATUS_VALUES = {"active", "frozen"}
BROKER_STATUS_VALUES = {"active", "quarantined", "frozen_quarantined", "capacity_overridden"}
LAG_STATUS_VALUES = {"within_target", "near_threshold", "exceeded"}
TIER_VALUES = {"gold", "silver", "bronze"}
TIER_RF = {"gold": 3, "silver": 2, "bronze": 1}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = PLAN_DIR / name
        assert p.is_file(), f"missing required output file: /app/plan/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output /app/plan/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


# ---------------------------------------------------------------------------
# Input integrity
# ---------------------------------------------------------------------------


class TestInputIntegrity:
    """The dataset under /app/cluster/ must remain byte-identical to the
    original fixtures throughout agent execution."""

    @pytest.mark.parametrize("rel", list(EXPECTED_INPUT_HASHES.keys()))
    def test_input_file_unchanged(self, rel):
        """Each ``/app/cluster/`` file's SHA-256 must equal the pinned input
        hash, proving the agent did not mutate any read-only fixture during
        execution."""
        path = CLUSTER_DIR / rel
        assert path.is_file(), f"required input file missing: {path}"
        actual = _sha256_bytes(path.read_bytes())
        expected = EXPECTED_INPUT_HASHES[rel]
        assert actual == expected, (
            f"input file /app/cluster/{rel} was modified during agent execution "
            f"(sha256 expected {expected}, got {actual})"
        )


# ---------------------------------------------------------------------------
# Output structure & encoding
# ---------------------------------------------------------------------------


class TestOutputStructure:
    """The five required outputs must exist with the documented shape and
    use deterministic JSON formatting."""

    def test_plan_directory_exists(self):
        """``/app/plan`` must exist as a directory after the agent runs."""
        assert PLAN_DIR.is_dir(), "/app/plan must exist as a directory"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_file_exists(self, name):
        """Each of the five required output files must exist as a regular
        file under ``/app/plan/``."""
        assert (PLAN_DIR / name).is_file(), f"missing /app/plan/{name}"

    def test_no_extra_files_in_plan_dir(self):
        """``/app/plan/`` must contain exactly the five required output
        files - nothing more, nothing less."""
        actual = sorted(p.name for p in PLAN_DIR.iterdir() if p.is_file())
        assert actual == sorted(REQUIRED_OUTPUT_FILES), (
            f"/app/plan must contain exactly {sorted(REQUIRED_OUTPUT_FILES)}; "
            f"found {actual}"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_ends_with_single_newline(self, loaded_outputs, name):
        """Each output file must end with exactly one trailing ``\\n``
        byte, matching the canonical-encoding requirement in the spec."""
        b = loaded_outputs[name]["bytes"]
        assert b.endswith(b"\n"), f"{name} must end with a trailing newline"
        assert not b.endswith(b"\n\n"), f"{name} must end with exactly one trailing newline"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_matches_canonical_pretty_form(self, loaded_outputs, name):
        """The on-disk file must equal ``json.dumps(obj, indent=2,
        sort_keys=True, ensure_ascii=False) + '\\n'``."""
        obj = loaded_outputs[name]["obj"]
        expected_bytes = (
            json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        actual_bytes = loaded_outputs[name]["bytes"]
        assert actual_bytes == expected_bytes, (
            f"/app/plan/{name} on-disk bytes do not match the required canonical "
            f"pretty form (json.dumps with indent=2, sort_keys=True, "
            f"ensure_ascii=False, plus trailing newline)"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_object_keys_sorted_at_every_level_on_disk(self, name):
        """Re-parses the on-disk file with ``object_pairs_hook=OrderedDict``
        and walks the resulting tree to assert every nested object's keys
        are emitted in sorted order, not just the top level."""
        path = PLAN_DIR / name
        ordered = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=collections.OrderedDict)
        violations: list[str] = []

        def walk(node, path_str):
            if isinstance(node, collections.OrderedDict):
                keys = list(node.keys())
                if keys != sorted(keys):
                    violations.append(
                        f"{path_str}: keys not sorted; got {keys}, expected {sorted(keys)}"
                    )
                for key, value in node.items():
                    walk(value, f"{path_str}.{key}")
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, f"{path_str}[{index}]")

        walk(ordered, name)
        assert not violations, (
            f"object keys must be emitted in sorted order at every level of {name}; "
            f"violations:\n  - " + "\n  - ".join(violations)
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_canonical_hash(self, loaded_outputs, name):
        """The canonical (compact, sort-keyed) SHA-256 of each output
        object must match the reference hash, proving the values match
        the independently-computed expected output byte-for-byte."""
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        expected = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        assert actual == expected, (
            f"/app/plan/{name} canonical SHA-256 mismatch: expected {expected}, got {actual}"
        )


# ---------------------------------------------------------------------------
# partition_assignment.json
# ---------------------------------------------------------------------------


class TestPartitionAssignment:
    """Every partition is placed under the tier eligibility, replication, and
    AZ anti-affinity rules; freezes and demotions are reflected in
    placement_reason and status."""

    def test_top_level_shape(self, loaded_outputs):
        """``partition_assignment.json`` must be ``{"partitions": [...]}``
        with a non-empty list of partition entries."""
        obj = loaded_outputs["partition_assignment.json"]["obj"]
        assert set(obj.keys()) == {"partitions"}
        assert isinstance(obj["partitions"], list)
        assert obj["partitions"], "partition_assignment.partitions must not be empty"

    def test_entry_fields(self, loaded_outputs):
        """Every partition entry must carry exactly the seven documented
        fields with the correct primitive types and enumerated string
        values, and ``replica_brokers`` must itself be sorted."""
        required = {"leader_broker", "partition_id", "placement_reason", "replica_brokers", "status", "tier", "topic_id"}
        for entry in loaded_outputs["partition_assignment.json"]["obj"]["partitions"]:
            assert set(entry.keys()) == required
            assert isinstance(entry["topic_id"], str)
            assert isinstance(entry["partition_id"], int)
            assert isinstance(entry["leader_broker"], str) and entry["leader_broker"]
            assert isinstance(entry["replica_brokers"], list)
            for r in entry["replica_brokers"]:
                assert isinstance(r, str)
            assert entry["replica_brokers"] == sorted(entry["replica_brokers"])
            assert entry["placement_reason"] in PLACEMENT_REASON_VALUES
            assert entry["status"] in PARTITION_STATUS_VALUES
            assert entry["tier"] in TIER_VALUES

    def test_sorted_by_topic_then_partition(self, loaded_outputs):
        """The ``partitions`` array must be sorted lexicographically by
        ``(topic_id, partition_id)`` per the spec's per-field sort order."""
        entries = loaded_outputs["partition_assignment.json"]["obj"]["partitions"]
        keys = [(e["topic_id"], e["partition_id"]) for e in entries]
        assert keys == sorted(keys), "partitions must be sorted by (topic_id, partition_id)"

    def test_replication_factor_per_tier(self, loaded_outputs):
        """Each partition's leader+replica count must equal the tier's
        replication factor: gold=3, silver=2, bronze=1."""
        for entry in loaded_outputs["partition_assignment.json"]["obj"]["partitions"]:
            expected_rf = TIER_RF[entry["tier"]]
            actual_rf = 1 + len(entry["replica_brokers"])
            assert actual_rf == expected_rf, (
                f"{entry['topic_id']}:{entry['partition_id']} tier={entry['tier']} "
                f"expected RF={expected_rf}, got {actual_rf}"
            )

    def test_leader_not_in_replicas(self, loaded_outputs):
        """A broker may only appear once in the leader+replica set for
        any partition - the leader id must not also appear in
        ``replica_brokers``."""
        for entry in loaded_outputs["partition_assignment.json"]["obj"]["partitions"]:
            assert entry["leader_broker"] not in entry["replica_brokers"], (
                f"{entry['topic_id']}:{entry['partition_id']} leader appears in replica_brokers"
            )

    def test_known_partition_count(self, loaded_outputs):
        """The reference fixture defines 28 partitions across all topics;
        the agent must emit assignments for exactly that many."""
        assert len(loaded_outputs["partition_assignment.json"]["obj"]["partitions"]) == 28

    def test_field_canonical_hash(self, loaded_outputs):
        """The full ``partitions`` array must canonicalise to the pinned
        hash, equivalent to a byte-for-byte match of the reference."""
        partitions = loaded_outputs["partition_assignment.json"]["obj"]["partitions"]
        assert _canonical_sha256(partitions) == EXPECTED_FIELD_HASHES["partition_assignment.partitions"]


class TestPlacementReasonCoverage:
    """The canonical fixture exercises every documented placement_reason
    value at least once; the agent must produce all four."""

    def _by_reason(self, loaded_outputs, reason):
        return [
            e
            for e in loaded_outputs["partition_assignment.json"]["obj"]["partitions"]
            if e["placement_reason"] == reason
        ]

    def test_hash_placement_present(self, loaded_outputs):
        """At least one partition must use the default ``hash_placement``
        reason - the path for unfrozen, non-demoted partitions."""
        assert self._by_reason(loaded_outputs, "hash_placement"), (
            "no partitions with placement_reason=hash_placement (the default for unfrozen, non-demoted partitions)"
        )

    def test_frozen_during_quarantine_present(self, loaded_outputs):
        """Exactly one partition (``t.orders.events:2``) must carry
        ``frozen_during_quarantine`` and keep its documented frozen
        leader ``b04`` per the Phase 2 cascade rules."""
        entries = self._by_reason(loaded_outputs, "frozen_during_quarantine")
        assert len(entries) == 1, (
            f"expected exactly one frozen_during_quarantine partition (t.orders.events:2), found {len(entries)}"
        )
        e = entries[0]
        assert e["topic_id"] == "t.orders.events"
        assert e["partition_id"] == 2
        assert e["status"] == "frozen"
        assert e["leader_broker"] == "b04"

    def test_frozen_by_event_present(self, loaded_outputs):
        """Exactly one partition (``t.user.events:0``) must carry
        ``frozen_by_event`` with status ``frozen`` from the explicit
        partition_freeze incident in the input log."""
        entries = self._by_reason(loaded_outputs, "frozen_by_event")
        assert len(entries) == 1, (
            f"expected exactly one frozen_by_event partition (t.user.events:0), found {len(entries)}"
        )
        e = entries[0]
        assert e["topic_id"] == "t.user.events"
        assert e["partition_id"] == 0
        assert e["status"] == "frozen"

    def test_demoted_for_backpressure_present(self, loaded_outputs):
        """At least one partition must be demoted from b05 (the
        capacity_overridden broker) and only non-gold tiers are eligible
        for that demotion."""
        entries = self._by_reason(loaded_outputs, "demoted_for_backpressure")
        assert entries, (
            "expected at least one partition with placement_reason=demoted_for_backpressure "
            "(b05's capacity_override forces non-gold leaders off it)"
        )
        for e in entries:
            assert e["tier"] in {"bronze", "silver"}, (
                f"gold partitions must never be demoted; {e['topic_id']}:{e['partition_id']} is gold"
            )
            assert e["status"] == "active"


class TestQuarantineExclusion:
    """An accepted broker_quarantine event removes the broker from every
    eligible-broker pool; no leader or replica may sit on a quarantined
    broker (the partition_freeze override of t.orders.events:2 is the sole
    documented exception and reaches frozen_during_quarantine via Phase 2)."""

    def test_quarantined_brokers_excluded(self, loaded_outputs):
        """Brokers ``b04`` and ``b08`` are quarantined and must not appear
        as a leader or replica anywhere - the only documented exception is
        ``t.orders.events:2`` where the partition_freeze cascade pins the
        frozen leader on b04."""
        quarantined = {"b04", "b08"}
        for entry in loaded_outputs["partition_assignment.json"]["obj"]["partitions"]:
            if entry["placement_reason"] == "frozen_during_quarantine":
                continue
            assert entry["leader_broker"] not in quarantined, (
                f"non-frozen partition {entry['topic_id']}:{entry['partition_id']} "
                f"has leader on quarantined broker {entry['leader_broker']}"
            )
            for r in entry["replica_brokers"]:
                assert r not in quarantined, (
                    f"partition {entry['topic_id']}:{entry['partition_id']} has replica "
                    f"on quarantined broker {r}"
                )


class TestAntiAffinity:
    """For each partition, replica brokers must occupy distinct AZs (or
    distinct regions when AZs are exhausted); identical AZ+region for two
    replicas of the same partition is a violation."""

    def test_replicas_distinct_az_or_region(self, loaded_outputs):
        """For every partition, the leader+replica brokers must live in
        distinct availability zones; if AZs collide, they must at least
        live in distinct regions (the documented fallback)."""
        cluster = json.loads((CLUSTER_DIR / "topology" / "cluster.json").read_text(encoding="utf-8"))
        broker_by_id = {b["broker_id"]: b for b in cluster["brokers"]}
        for entry in loaded_outputs["partition_assignment.json"]["obj"]["partitions"]:
            all_brokers = [entry["leader_broker"]] + list(entry["replica_brokers"])
            azs = [broker_by_id[bid]["availability_zone"] for bid in all_brokers]
            regions = [broker_by_id[bid]["region"] for bid in all_brokers]
            if len(set(azs)) == len(azs):
                continue
            assert len(set(regions)) == len(regions), (
                f"partition {entry['topic_id']}:{entry['partition_id']} has replicas in "
                f"both the same AZ and the same region: azs={azs}, regions={regions}"
            )


# ---------------------------------------------------------------------------
# consumer_rebalance.json
# ---------------------------------------------------------------------------


class TestConsumerRebalance:
    """The rebalance plan respects subscription matching (literal and
    anchored regex), excludes frozen partitions from member assignments, and
    distributes load via the documented LPT rule."""

    def test_top_level_shape(self, loaded_outputs):
        """``consumer_rebalance.json`` must be ``{"groups": [...]}`` with
        the groups list sorted by ``group_id``."""
        obj = loaded_outputs["consumer_rebalance.json"]["obj"]
        assert set(obj.keys()) == {"groups"}
        groups = obj["groups"]
        group_ids = [g["group_id"] for g in groups]
        assert group_ids == sorted(group_ids)

    def test_group_entry_fields(self, loaded_outputs):
        """Each group entry must expose exactly the four documented keys
        with the correct collection types and a sorted
        ``subscribed_topics`` list."""
        required = {"group_id", "member_assignments", "subscribed_topics", "unassigned_partitions"}
        for g in loaded_outputs["consumer_rebalance.json"]["obj"]["groups"]:
            assert set(g.keys()) == required
            assert isinstance(g["member_assignments"], dict)
            assert g["subscribed_topics"] == sorted(g["subscribed_topics"])
            assert isinstance(g["unassigned_partitions"], list)

    def test_literal_subscription_matches_one_topic(self, loaded_outputs):
        """Groups whose subscription is a literal string must resolve to
        exactly the one matching topic - no regex fallback or broader
        match."""
        groups = {g["group_id"]: g for g in loaded_outputs["consumer_rebalance.json"]["obj"]["groups"]}
        assert groups["cg.order-processor"]["subscribed_topics"] == ["t.orders.events"]
        assert groups["cg.payments-billing"]["subscribed_topics"] == ["t.payments.events"]
        assert groups["cg.legacy-importer"]["subscribed_topics"] == ["t.legacy.dump"]

    def test_regex_subscription_matches_all_anchored(self, loaded_outputs):
        """Groups subscribed by anchored regex must resolve to every
        topic whose id fully matches the pattern, sorted alphabetically."""
        groups = {g["group_id"]: g for g in loaded_outputs["consumer_rebalance.json"]["obj"]["groups"]}
        assert groups["cg.audit-archiver"]["subscribed_topics"] == ["t.audit.archive", "t.audit.trail"]
        assert groups["cg.metrics-aggregator"]["subscribed_topics"] == ["t.metrics.fast", "t.metrics.slow"]

    def test_frozen_partitions_in_unassigned(self, loaded_outputs):
        """The frozen partition ``t.orders.events:2`` must surface in
        ``unassigned_partitions`` of ``cg.order-processor`` (with reason
        ``frozen``) and must never appear in any member's assignments."""
        groups = {g["group_id"]: g for g in loaded_outputs["consumer_rebalance.json"]["obj"]["groups"]}
        unassigned = groups["cg.order-processor"]["unassigned_partitions"]
        assert unassigned == [{"partition_id": 2, "reason": "frozen", "topic_id": "t.orders.events"}]
        for g in loaded_outputs["consumer_rebalance.json"]["obj"]["groups"]:
            assignments = g["member_assignments"]
            for member_id, parts in assignments.items():
                for p in parts:
                    if p["topic_id"] == "t.orders.events" and p["partition_id"] == 2:
                        pytest.fail(
                            f"group {g['group_id']} member {member_id} was assigned the frozen "
                            f"partition t.orders.events:2 (must go to unassigned_partitions)"
                        )

    def test_every_member_appears_in_assignments(self, loaded_outputs):
        """Every member declared in each consumer-group input file must
        appear (even if with an empty list) as a key in the group's
        ``member_assignments`` mapping."""
        cons_dir = CLUSTER_DIR / "consumers"
        for f in sorted(cons_dir.glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            group_id = data["group_id"]
            expected_members = {m["member_id"] for m in data["members"]}
            for g in loaded_outputs["consumer_rebalance.json"]["obj"]["groups"]:
                if g["group_id"] == group_id:
                    assert set(g["member_assignments"].keys()) == expected_members, (
                        f"group {group_id} member_assignments keys mismatch input members"
                    )
                    break
            else:
                pytest.fail(f"group {group_id} missing from consumer_rebalance.groups")

    def test_assigned_partitions_sorted(self, loaded_outputs):
        """Within each member's assignment list, partitions must be
        sorted lexicographically by ``(topic_id, partition_id)``."""
        for g in loaded_outputs["consumer_rebalance.json"]["obj"]["groups"]:
            for member_id, parts in g["member_assignments"].items():
                keys = [(p["topic_id"], p["partition_id"]) for p in parts]
                assert keys == sorted(keys), (
                    f"group {g['group_id']} member {member_id} partitions not sorted by (topic_id, partition_id)"
                )

    def test_field_canonical_hash(self, loaded_outputs):
        """The full ``groups`` array must canonicalise to the pinned
        SHA-256, equivalent to a byte-for-byte reference match."""
        groups = loaded_outputs["consumer_rebalance.json"]["obj"]["groups"]
        assert _canonical_sha256(groups) == EXPECTED_FIELD_HASHES["consumer_rebalance.groups"]


# ---------------------------------------------------------------------------
# lag_report.json
# ---------------------------------------------------------------------------


class TestLagReport:
    """Per-group lag classification covers all three states; exceeding
    members are reported for the groups that pass the target."""

    def test_top_level_shape(self, loaded_outputs):
        """``lag_report.json`` must be ``{"groups": [...]}`` with the
        groups list sorted by ``group_id``."""
        obj = loaded_outputs["lag_report.json"]["obj"]
        assert set(obj.keys()) == {"groups"}
        gids = [g["group_id"] for g in obj["groups"]]
        assert gids == sorted(gids)

    def test_entry_fields(self, loaded_outputs):
        """Each group entry must expose exactly the documented keys with
        correct types: ``lag_status`` is one of three enums, the lag and
        throughput projections are integers, and ``exceeding_members``
        is sorted."""
        required = {"exceeding_members", "group_id", "lag_status", "projected_max_member_lag_messages", "projected_total_throughput_mbps"}
        for g in loaded_outputs["lag_report.json"]["obj"]["groups"]:
            assert set(g.keys()) == required
            assert g["lag_status"] in LAG_STATUS_VALUES
            assert isinstance(g["projected_max_member_lag_messages"], int)
            assert isinstance(g["projected_total_throughput_mbps"], int)
            assert g["exceeding_members"] == sorted(g["exceeding_members"])

    def test_within_target_groups(self, loaded_outputs):
        """The three healthy groups (legacy-importer, metrics-aggregator,
        order-processor) must classify as ``within_target`` with no
        exceeding members."""
        groups = {g["group_id"]: g for g in loaded_outputs["lag_report.json"]["obj"]["groups"]}
        for gid in ("cg.legacy-importer", "cg.metrics-aggregator", "cg.order-processor"):
            assert groups[gid]["lag_status"] == "within_target", (
                f"{gid} expected within_target; got {groups[gid]['lag_status']}"
            )
            assert groups[gid]["exceeding_members"] == []

    def test_near_threshold_group(self, loaded_outputs):
        """``cg.audit-archiver`` straddles the warning band and must
        classify as ``near_threshold`` without any exceeding members."""
        groups = {g["group_id"]: g for g in loaded_outputs["lag_report.json"]["obj"]["groups"]}
        g = groups["cg.audit-archiver"]
        assert g["lag_status"] == "near_threshold"
        assert g["exceeding_members"] == []

    def test_exceeded_group(self, loaded_outputs):
        """``cg.payments-billing`` must classify as ``exceeded``, list
        both members as exceeding, and project a max member lag of at
        least 800 messages."""
        groups = {g["group_id"]: g for g in loaded_outputs["lag_report.json"]["obj"]["groups"]}
        g = groups["cg.payments-billing"]
        assert g["lag_status"] == "exceeded"
        assert g["exceeding_members"] == ["m01-pay", "m02-pay"]
        assert g["projected_max_member_lag_messages"] >= 800

    def test_field_canonical_hash(self, loaded_outputs):
        """The full ``groups`` array must canonicalise to the pinned
        SHA-256 reference hash."""
        groups = loaded_outputs["lag_report.json"]["obj"]["groups"]
        assert _canonical_sha256(groups) == EXPECTED_FIELD_HASHES["lag_report.groups"]


# ---------------------------------------------------------------------------
# quarantine_status.json
# ---------------------------------------------------------------------------


class TestQuarantineStatus:
    """Broker statuses, evacuation/reception counts, and over-threshold flags
    reflect the post-Phase-3 state."""

    def test_top_level_shape(self, loaded_outputs):
        """``quarantine_status.json`` must be ``{"brokers": [...]}`` with
        exactly 12 entries sorted by ``broker_id``."""
        obj = loaded_outputs["quarantine_status.json"]["obj"]
        assert set(obj.keys()) == {"brokers"}
        ids = [b["broker_id"] for b in obj["brokers"]]
        assert ids == sorted(ids)
        assert len(ids) == 12

    def test_entry_fields(self, loaded_outputs):
        """Each broker entry must expose exactly the seven documented
        keys with correct primitive types and an enumerated ``status``
        value."""
        required = {"broker_id", "effective_capacity_mbps", "over_threshold", "partitions_evacuated_count", "partitions_received_count", "post_rebalance_load_mbps", "status"}
        for b in loaded_outputs["quarantine_status.json"]["obj"]["brokers"]:
            assert set(b.keys()) == required
            assert b["status"] in BROKER_STATUS_VALUES
            assert isinstance(b["over_threshold"], bool)
            assert isinstance(b["effective_capacity_mbps"], int)
            assert isinstance(b["post_rebalance_load_mbps"], int)

    def test_quarantine_status_assignment(self, loaded_outputs):
        """The quarantine status of every broker must match the cascade:
        ``b04`` is ``frozen_quarantined``, ``b08`` is ``quarantined``,
        ``b05`` is ``capacity_overridden``, and the rest are ``active``."""
        by_id = {b["broker_id"]: b for b in loaded_outputs["quarantine_status.json"]["obj"]["brokers"]}
        assert by_id["b04"]["status"] == "frozen_quarantined"
        assert by_id["b08"]["status"] == "quarantined"
        assert by_id["b05"]["status"] == "capacity_overridden"
        for bid in ("b01", "b02", "b03", "b06", "b07", "b09", "b10", "b11", "b12"):
            assert by_id[bid]["status"] == "active", (
                f"broker {bid} expected status=active; got {by_id[bid]['status']}"
            )

    def test_capacity_overridden_broker_uses_event_value(self, loaded_outputs):
        """``b05``'s ``effective_capacity_mbps`` must reflect the
        capacity_override event value (52 mbps) and the resulting
        post-rebalance load must trip the ``over_threshold`` flag."""
        by_id = {b["broker_id"]: b for b in loaded_outputs["quarantine_status.json"]["obj"]["brokers"]}
        assert by_id["b05"]["effective_capacity_mbps"] == 52
        assert by_id["b05"]["over_threshold"] is True

    def test_quarantined_brokers_receive_no_leaders(self, loaded_outputs):
        """``b08``, the plain quarantined broker, must receive zero
        partitions and post-rebalance load 0 mbps."""
        by_id = {b["broker_id"]: b for b in loaded_outputs["quarantine_status.json"]["obj"]["brokers"]}
        assert by_id["b08"]["partitions_received_count"] == 0
        assert by_id["b08"]["post_rebalance_load_mbps"] == 0

    def test_frozen_quarantined_keeps_frozen_leader(self, loaded_outputs):
        """``b04`` is frozen_quarantined and must not receive new
        partitions, but it keeps the frozen leader of t.orders.events:2 -
        so its post-rebalance load equals that partition's load (45)."""
        by_id = {b["broker_id"]: b for b in loaded_outputs["quarantine_status.json"]["obj"]["brokers"]}
        assert by_id["b04"]["partitions_received_count"] == 0
        assert by_id["b04"]["post_rebalance_load_mbps"] == 45

    def test_field_canonical_hash(self, loaded_outputs):
        """The full ``brokers`` array must canonicalise to the pinned
        SHA-256 reference hash."""
        brokers = loaded_outputs["quarantine_status.json"]["obj"]["brokers"]
        assert _canonical_sha256(brokers) == EXPECTED_FIELD_HASHES["quarantine_status.brokers"]


# ---------------------------------------------------------------------------
# summary.json
# ---------------------------------------------------------------------------


class TestSummary:
    """Per-key summary counts are pinned by canonical hash for fine-grained
    failure diagnosis."""

    def test_summary_keys_exact(self, loaded_outputs):
        """``summary.json`` must expose exactly the 16 documented keys -
        no extras, no omissions."""
        expected = {
            "accepted_incident_events", "active_brokers", "anti_affinity_violations_blocked",
            "brokers_over_threshold", "brokers_total", "capacity_overridden_brokers",
            "consumer_groups_total", "demotions_total", "frozen_partitions",
            "frozen_quarantined_brokers", "groups_with_lag_exceeded",
            "groups_with_lag_within_target_or_near", "ignored_incident_events",
            "partitions_total", "quarantined_brokers", "topics_total",
        }
        assert set(loaded_outputs["summary.json"]["obj"].keys()) == expected

    def test_summary_values_are_ints(self, loaded_outputs):
        """Every summary metric must be an integer count - no floats,
        strings, or null sentinels."""
        for k, v in loaded_outputs["summary.json"]["obj"].items():
            assert isinstance(v, int), f"summary.{k} must be int, got {type(v).__name__}"

    @pytest.mark.parametrize("key", sorted(k.split(".", 1)[1] for k in EXPECTED_FIELD_HASHES if k.startswith("summary.")))
    def test_summary_key_canonical_hash(self, loaded_outputs, key):
        """Each individual summary key must canonicalise to its pinned
        SHA-256, giving fine-grained per-metric failure diagnosis when
        any single counter is wrong."""
        value = loaded_outputs["summary.json"]["obj"][key]
        actual = _canonical_sha256(value)
        expected = EXPECTED_FIELD_HASHES[f"summary.{key}"]
        assert actual == expected, (
            f"summary.{key}={value!r} canonical SHA-256 mismatch: expected {expected}, got {actual}"
        )


# ---------------------------------------------------------------------------
# Implementation-language enforcement
# ---------------------------------------------------------------------------


class TestImplementationLanguage:
    """The task constrains the agent to a Go reference implementation. The
    Go source tree must live under /app/src/ and the compiled binary at
    /app/bin/rebalancer must reproduce /app/plan/ byte-for-byte when run
    against /app/cluster/. This catches both (a) agents that hand-edit JSON
    and (b) agents that bypass Go in favour of a different language."""

    def test_go_source_present(self):
        """``/app/src/`` must contain at least one ``.go`` file, and at
        least one of those files must declare ``package main`` so the
        rebalancer is buildable as an executable."""
        assert SRC_DIR.is_dir(), f"{SRC_DIR} must exist and contain Go source"
        go_files = list(SRC_DIR.rglob("*.go"))
        assert go_files, f"no .go files found under {SRC_DIR}"
        has_main = False
        for gf in go_files:
            text = gf.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^\s*package\s+main\b", text, re.MULTILINE):
                has_main = True
                break
        assert has_main, f"no Go file under {SRC_DIR} declares 'package main'"

    def test_binary_present(self):
        """``/app/bin/rebalancer`` must exist as a regular executable
        file - the compiled artifact of the Go source under ``/app/src/``."""
        assert BIN_PATH.is_file(), f"{BIN_PATH} must exist (compiled rebalancer binary)"
        assert os.access(BIN_PATH, os.X_OK), f"{BIN_PATH} must be executable"

    def test_binary_is_native_elf_executable(self):
        """``/app/bin/rebalancer`` must be a native compiled ELF executable,
        not a shell/Python wrapper that merely invokes another language."""
        head = BIN_PATH.read_bytes()[:4]
        assert head != b"#!/b" and head != b"#!/u" and head != b"#!/p", (
            f"{BIN_PATH} must not be a script (header={head!r})"
        )
        assert head == b"\x7fELF", (
            f"{BIN_PATH} must be an ELF executable produced by a Go compiler (header={head!r})"
        )

    def test_rebalancer_binary_built_from_go(self):
        """``/app/bin/rebalancer`` must carry Go build metadata from the Go
        toolchain, ruling out a Python/shell pipeline that only writes JSON."""
        go_bin = shutil.which("go")
        if go_bin:
            result = subprocess.run(
                [go_bin, "version", "-m", str(BIN_PATH)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            first_line = (result.stdout or "").splitlines()[0] if result.stdout else ""
            assert result.returncode == 0 and re.search(r"\bgo1\.\d+", first_line), (
                f"`go version -m` did not identify a Go-compiled binary "
                f"(rc={result.returncode}, first_line={first_line!r}, "
                f"stderr={(result.stderr or '')[:300]!r})"
            )
            assert "\tmod\t" in result.stdout or "\tpath\t" in result.stdout, (
                f"`go version -m` did not report embedded module/path build info "
                f"for {BIN_PATH}:\n{result.stdout}"
            )
        else:
            data = BIN_PATH.read_bytes()
            assert (
                b"go.buildinfo" in data
                or b"Go build" in data
                or b"runtime.go" in data
            ), f"{BIN_PATH} does not contain Go build metadata"

    def test_binary_reproduces_plan(self):
        """A fresh execution of ``/app/bin/rebalancer`` against
        ``/app/cluster/`` must reproduce the on-disk ``/app/plan/`` files
        byte-for-byte.

        Anti-cheat: before running the binary, the existing ``/app/plan/``
        directory is moved aside so the binary cannot satisfy the test by
        copying the previously-written files. The rebalancer must compute
        each output from the cluster fixtures via the Go implementation;
        any binary that hard-codes ``/app/plan/`` as its data source (for
        example, a thin wrapper around a Python/shell pre-computation)
        will fail because that path no longer exists during this test.
        After the run completes, the original ``/app/plan/`` is restored
        and the freshly produced outputs are compared to the saved bytes
        AND to the canonical reference hashes (an independent check that
        does not rely on whatever was on disk before)."""
        saved_bytes = {
            name: (PLAN_DIR / name).read_bytes() for name in REQUIRED_OUTPUT_FILES
        }
        plan_backup = PLAN_DIR.parent / (PLAN_DIR.name + ".anti_cheat_backup")
        if plan_backup.exists():
            shutil.rmtree(plan_backup)
        shutil.move(str(PLAN_DIR), str(plan_backup))
        try:
            with tempfile.TemporaryDirectory() as td:
                env = os.environ.copy()
                env["SSR_CLUSTER_DIR"] = str(CLUSTER_DIR)
                env["SSR_PLAN_DIR"] = td
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
                    fresh_path = Path(td) / name
                    assert fresh_path.is_file(), (
                        f"binary did not write {name} to a fresh SSR_PLAN_DIR while "
                        f"/app/plan/ was unavailable; this strongly suggests the binary "
                        f"copies from /app/plan/ rather than computing from /app/cluster/"
                    )
                    fresh = fresh_path.read_bytes()
                    assert fresh == saved_bytes[name], (
                        f"/app/plan/{name} was not produced by /app/bin/rebalancer "
                        f"(a fresh run of the binary against /app/cluster/ - with "
                        f"/app/plan/ moved aside so it cannot be read - disagrees with "
                        f"the on-disk file)"
                    )
                    fresh_obj = json.loads(fresh.decode("utf-8"))
                    expected_hash = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
                    actual_hash = _canonical_sha256(fresh_obj)
                    assert actual_hash == expected_hash, (
                        f"fresh /app/bin/rebalancer output for {name} does not match the "
                        f"reference canonical SHA-256 (expected {expected_hash}, got "
                        f"{actual_hash}); the binary must compute the correct outputs "
                        f"from /app/cluster/ on its own"
                    )
        finally:
            if PLAN_DIR.exists():
                shutil.rmtree(PLAN_DIR)
            shutil.move(str(plan_backup), str(PLAN_DIR))
