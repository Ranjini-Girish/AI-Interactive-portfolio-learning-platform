"""Behavioral tests for the backup-retention-auditor task.

These tests assert the agent's outputs against the documented contract in
``instruction.md``. Hash-locked anti-cheat fixtures are computed independently
from the input data and compared against the agent's emitted JSON files; an
agent cannot pass these tests by writing arbitrary or hand-tweaked output.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("BRA_DATA_DIR", "/app/data"))
AUDIT_DIR = Path(os.environ.get("BRA_AUDIT_DIR", "/app/audit"))

REQUIRED_OUTPUT_FILES = [
    "retention.json",
    "eviction_plan.json",
    "integrity.json",
    "host_summary.json",
    "summary.json",
]

# Canonical SHA-256 of each input file's raw bytes. Verifies the agent did
# not modify any input under /app/data while computing the report.
EXPECTED_INPUT_HASHES = {
    "SPEC.md":                    "9a32819c373867c84f4ae15940596ac083678a654d78ae4e154c4edfeb96119f",
    "pool_state.json":            "e012c58cedd3354988cba22f109711732ebee6b207994263552eb97a6aa00589",
    "retention_policy.json":      "2f4d117bf6b48b153efed280874bf379da80d4ad6ec09cf4e0c1ba11fd616033",
    "host_profiles/alpha.json":   "c02e29597a51619458dc357e528199cb54385bd2ac4af4ff94a8eda4bc6c38d7",
    "host_profiles/beta.json":    "42319c90345314685bfcb1215bb194ad2f18537ebe2ce8886366cce43c0209ed",
    "host_profiles/gamma.json":   "47e249b45bbc4c6db65cf1df249b0d4dbd797e46a491612e6895f2b3670a901d",
    "host_profiles/delta.json":   "55bc8c55d72969e2f4aba0f9a5ed44ead75eafc4b9f31d6e0b938bd3da46f6b2",
    "host_profiles/epsilon.json": "4641cd4ac2a7822de19bf7e2cac74f14edabf94cdda1f5e9be029689c0482641",
    "host_profiles/zeta.json":    "12a9aad85a3ac04f04198fee19775b823bc775c660a1ef26d429d17911d4d032",
    "host_profiles/eta.json":     "b13fb526fa75c77ef43a7edebe1ead6cf0a855694a89e8a9db04c7d13fef2431",
    "host_profiles/theta.json":   "70fc283b71e97b5e2df89031393d980126eabadf15bced7fc070e00bed79a367",
    "incident_log.json":          "683d65f868da637eaf400c09e9c7835643424707e11e018ebb0e88aeea810ad9",
    "snapshots/alpha.json":       "7ac9946acea990dc01a8dbf4d0c52f6152c99a47feb2c3183e14a8dde413979b",
    "snapshots/beta.json":        "66be3139719174d74cd3b1c1f9f1499757e5737a3dda1ca515fbfb475621a40a",
    "snapshots/gamma.json":       "9a8b169d3bd0d4bab36444356519be13050d672d2a83a1ddd37ad210d7960beb",
    "snapshots/delta.json":       "deee138e841c573998d94e330bf40aa3eb7fb32c62abd3bf26f96297c8b03d58",
    "snapshots/epsilon.json":     "3967b205db683059855d3af0b358c7a8104cf64013a1ae6c4270c9c8d6250650",
    "snapshots/zeta.json":        "35ef1bb1f81cc42162ee29172dd6f096782ad46e01ec9c5e3840032ec6d641b0",
    "snapshots/eta.json":         "53838dc9879c2564b94342a5f7fcd3f9051c04377f3525ad46c7eb4bb128fe4e",
    "snapshots/theta.json":       "4a1e0e25a8f926c123d3b0d2013fcf90b4e38d0343def1b9a53fd1d67fb4c8a4",
}

# Canonical SHA-256 of the structurally-canonicalised JSON of every required
# output. The canonicalisation rule is ``json.dumps(obj, sort_keys=True,
# separators=(',', ':'), ensure_ascii=False)`` followed by a single trailing
# newline byte. This locks the *value* of the output independently of the
# agent's chosen on-disk whitespace style.
EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "retention.json":     "842601434a8f1947d631ac84b2b847902ae3a8f3120940088b6982bafb22cc01",
    "eviction_plan.json": "c13f53ea63d8ee9b5abc592f41c2ce392c9e41c88dfc5c8c1ae1e873381a7a4c",
    "integrity.json":     "f0df348373442a70e2d60e6ea8b276dab56a18a2c208096b5adb95cd50ab995c",
    "host_summary.json":  "3cb3e04e4a373777a38d3ee224b623efdeb0f8736ca9a94747c8137bea2b64be",
    "summary.json":       "84f1e7e1d92f8e09ad378e5eaebd1690962107388f65608b4845416ae9e9f1c3",
}

# Field-level canonical hashes for selected list fields. These let us pinpoint
# *which* output is wrong when ``EXPECTED_OUTPUT_CANONICAL_HASHES`` fails.
EXPECTED_FIELD_HASHES = {
    "retention.snapshots":                  "e89bbed814fbddb853d5f56137a4341da2500cbc6ba66087c2a7b4dafcc969cd",
    "eviction_plan.evictions":              "e8d90044f848f33c9be3206f6c2e6cd47de285e0f1afbdc7cf8f3cb29336fe14",
    "eviction_plan.containment_evictions":  "e62d54598b588f46281fd4d6a62d9656a6653e4cc6e97e9f7e4c1f205003bdee",
    "integrity.hosts":                      "0c5030e7fc69272d622bc097646cd539dfe7317e4dd2878dbf654765591f9406",
    "host_summary.hosts":                   "f07eb1aefc2203a1da049ef7ce34713f961330c1b19d75a73b1d6490042328f9",
    "summary.invalid_snapshots_per_host":   "16aba22c3f232910a5fa29106c8f86b8643dea87dfae15b1158492e631392bc7",
}

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


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
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: /app/audit/{name}"
        with open(p, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output /app/audit/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


# ---------------------------------------------------------------------------
# Input integrity
# ---------------------------------------------------------------------------


class TestInputIntegrity:
    """Inputs under /app/data must remain byte-identical to the original
    fixtures throughout agent execution."""

    @pytest.mark.parametrize("rel", list(EXPECTED_INPUT_HASHES.keys()))
    def test_input_file_unchanged(self, rel):
        path = DATA_DIR / rel
        assert path.is_file(), f"required input file missing: {path}"
        with open(path, "rb") as f:
            actual = _sha256_bytes(f.read())
        expected = EXPECTED_INPUT_HASHES[rel]
        assert actual == expected, (
            f"input file /app/data/{rel} was modified during agent execution "
            f"(sha256 expected {expected}, got {actual})"
        )


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------


class TestOutputStructure:
    """The five required outputs must exist with the documented shape and
    use deterministic JSON formatting."""

    def test_audit_directory_exists(self):
        assert AUDIT_DIR.is_dir(), "/app/audit must exist as a directory"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_file_exists(self, name):
        assert (AUDIT_DIR / name).is_file(), f"missing /app/audit/{name}"

    def test_no_extra_files_in_audit_dir(self):
        actual = sorted(p.name for p in AUDIT_DIR.iterdir() if p.is_file())
        assert actual == sorted(REQUIRED_OUTPUT_FILES), (
            f"/app/audit must contain exactly {sorted(REQUIRED_OUTPUT_FILES)}; "
            f"found {actual}"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_ends_with_single_newline(self, loaded_outputs, name):
        b = loaded_outputs[name]["bytes"]
        assert b.endswith(b"\n"), f"{name} must end with a trailing newline"
        assert not b.endswith(b"\n\n"), f"{name} must end with exactly one trailing newline"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_matches_canonical_pretty_form(self, loaded_outputs, name):
        """The on-disk file must equal ``json.dumps(obj, indent=2,
        sort_keys=True, ensure_ascii=False) + '\\n'``. This single check
        enforces three spec requirements simultaneously: exactly two-space
        indentation per nesting level, sorted object keys at every level in
        the on-disk byte stream, and a single trailing newline."""
        obj = loaded_outputs[name]["obj"]
        expected_bytes = (
            json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        actual_bytes = loaded_outputs[name]["bytes"]
        if actual_bytes != expected_bytes:
            min_len = min(len(actual_bytes), len(expected_bytes))
            divergence_at = next(
                (i for i in range(min_len) if actual_bytes[i] != expected_bytes[i]),
                min_len,
            )
            ctx_start = max(0, divergence_at - 40)
            ctx_end = min(len(actual_bytes), divergence_at + 40)
            actual_ctx = actual_bytes[ctx_start:ctx_end].decode("utf-8", errors="replace")
            expected_ctx = expected_bytes[ctx_start:min(len(expected_bytes), divergence_at + 40)].decode("utf-8", errors="replace")
            pytest.fail(
                f"/app/audit/{name} on-disk bytes do not match the required canonical "
                f"pretty form (json.dumps with indent=2, sort_keys=True, ensure_ascii=False, "
                f"plus trailing newline).\n"
                f"  actual length:   {len(actual_bytes)}\n"
                f"  expected length: {len(expected_bytes)}\n"
                f"  first divergence at byte offset {divergence_at}\n"
                f"  actual near divergence:   {actual_ctx!r}\n"
                f"  expected near divergence: {expected_ctx!r}"
            )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_object_keys_sorted_at_every_level_on_disk(self, name):
        """Object keys must be emitted in sorted order at every nesting level
        in the on-disk byte stream itself, not just after a parse-and-resort
        round-trip."""
        path = AUDIT_DIR / name
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        ordered = json.loads(text, object_pairs_hook=collections.OrderedDict)
        violations: list[str] = []

        def walk(node, path_str):
            if isinstance(node, collections.OrderedDict):
                keys = list(node.keys())
                if keys != sorted(keys):
                    violations.append(
                        f"{path_str}: keys not in sorted order; got {keys}, "
                        f"expected {sorted(keys)}"
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


# ---------------------------------------------------------------------------
# Retention semantics
# ---------------------------------------------------------------------------


class TestRetention:
    """retention.json's per-snapshot decisions must match the documented
    rule contract for every valid snapshot."""

    def test_retention_top_level_keys(self, loaded_outputs):
        obj = loaded_outputs["retention.json"]["obj"]
        assert isinstance(obj, dict)
        assert set(obj.keys()) == {"snapshots"}

    def test_retention_entries_have_required_keys(self, loaded_outputs):
        snaps = loaded_outputs["retention.json"]["obj"]["snapshots"]
        assert isinstance(snaps, list)
        required = {"id", "host", "decision", "reason", "matched_rule"}
        for entry in snaps:
            assert isinstance(entry, dict)
            assert set(entry.keys()) == required, f"retention entry has wrong keys: {entry}"
            assert entry["decision"] in {"keep", "evict"}
            assert isinstance(entry["host"], str)
            assert isinstance(entry["id"], str) and entry["id"]
            assert isinstance(entry["reason"], str) and entry["reason"]
            assert entry["matched_rule"] is None or isinstance(entry["matched_rule"], str)

    def test_retention_sorted_by_host_then_id(self, loaded_outputs):
        snaps = loaded_outputs["retention.json"]["obj"]["snapshots"]
        keys = [(e["host"], e["id"]) for e in snaps]
        assert keys == sorted(keys), "retention.snapshots must be sorted by (host, id)"

    def test_retention_excludes_invalid_snapshots(self, loaded_outputs):
        snaps = loaded_outputs["retention.json"]["obj"]["snapshots"]
        ids = {e["id"] for e in snaps}
        # The dataset deliberately includes invalid snapshots that must be
        # silently dropped from every output.
        assert "alpha-INV1" not in ids
        assert "alpha-INV2" not in ids
        assert "beta-FUT" not in ids
        assert "theta-NOHASH" not in ids

    def test_retention_keep_decisions_have_matched_rule(self, loaded_outputs):
        snaps = loaded_outputs["retention.json"]["obj"]["snapshots"]
        for e in snaps:
            if e["decision"] == "keep":
                assert e["matched_rule"] is not None, (
                    f"kept snapshot {e['id']} must declare matched_rule"
                )

    def test_retention_evict_decisions_have_no_matched_rule(self, loaded_outputs):
        snaps = loaded_outputs["retention.json"]["obj"]["snapshots"]
        for e in snaps:
            if e["decision"] == "evict":
                assert e["matched_rule"] is None, (
                    f"evicted snapshot {e['id']} must have matched_rule=null"
                )

    def test_retention_evict_reasons_are_canonical(self, loaded_outputs):
        snaps = loaded_outputs["retention.json"]["obj"]["snapshots"]
        evict_reasons = {e["reason"] for e in snaps if e["decision"] == "evict"}
        assert evict_reasons.issubset(
            {"no_matching_rule", "capacity_overflow", "cascade_overflow", "tamper_containment"}
        )

    def test_retention_keep_reasons_are_canonical(self, loaded_outputs):
        snaps = loaded_outputs["retention.json"]["obj"]["snapshots"]
        keep_reasons = {e["reason"] for e in snaps if e["decision"] == "keep"}
        assert keep_reasons.issubset({"retained_by_rule", "exempt"})

    def test_retention_exempt_host_keeps_everything(self, loaded_outputs):
        # delta is the exempt host with no contained snapshots in the fixture;
        # every valid delta snapshot must be kept with reason="exempt".
        snaps = loaded_outputs["retention.json"]["obj"]["snapshots"]
        delta = [e for e in snaps if e["host"] == "delta"]
        assert delta, "delta host must have at least one valid snapshot in retention.json"
        for e in delta:
            assert e["decision"] == "keep"
            assert e["reason"] == "exempt"
            assert e["matched_rule"] == "exempt"

    def test_cascade_eviction_propagates_to_descendants(self, loaded_outputs):
        # SPEC §"Cascading eviction": a retained incremental snapshot whose
        # transitive ancestor has been capacity-evicted must itself be
        # evicted with reason="cascade_overflow" and matched_rule=null.
        # Cascade-evicted snapshots are NOT listed in eviction_plan.evictions.
        snaps = loaded_outputs["retention.json"]["obj"]["snapshots"]
        eviction_plan = loaded_outputs["eviction_plan.json"]["obj"]
        capacity_ids = {e["id"] for e in eviction_plan["evictions"]}
        cascade_entries = [e for e in snaps if e["reason"] == "cascade_overflow"]

        assert cascade_entries, (
            "fixture must exercise cascading eviction; no entry has "
            "reason='cascade_overflow' (sanity check on the dataset)"
        )
        for e in cascade_entries:
            assert e["decision"] == "evict"
            assert e["matched_rule"] is None
            assert e["id"] not in capacity_ids, (
                f"cascade-evicted {e['id']} must NOT also appear in "
                "eviction_plan.evictions"
            )

        snap_by_host: dict[str, dict] = {}
        for fp in (DATA_DIR / "snapshots").glob("*.json"):
            with open(fp) as f:
                doc = json.load(f)
            host = doc["host"]
            snap_by_host[host] = {s["id"]: s for s in doc["snapshots"]}

        for e in cascade_entries:
            host_snaps = snap_by_host[e["host"]]
            cur = host_snaps[e["id"]]
            assert cur["kind"] == "incremental", (
                f"only incremental snapshots can be cascade-evicted; "
                f"{e['id']} is kind={cur['kind']}"
            )
            found_evicted_ancestor = False
            seen = set()
            while cur["kind"] == "incremental":
                pid = cur.get("parent_id")
                if pid is None or pid in seen:
                    break
                seen.add(pid)
                parent = host_snaps.get(pid)
                if parent is None:
                    break
                if pid in capacity_ids:
                    found_evicted_ancestor = True
                    break
                cur = parent
            assert found_evicted_ancestor, (
                f"cascade-evicted {e['id']} has no capacity-evicted ancestor "
                "in its parent chain"
            )

    def test_temporal_incident_event_rejected(self, loaded_outputs):
        # SPEC §"Incident-log filtering": an event whose day precedes its
        # referenced snapshot's taken_day must be rejected. The fixture
        # contains a tamper event on alpha-005 (taken_day=200) with day=150.
        # This event must NOT contribute to alpha's compromised list.
        integrity = {
            h["host"]: h
            for h in loaded_outputs["integrity.json"]["obj"]["hosts"]
        }
        host_summary = {
            h["host"]: h
            for h in loaded_outputs["host_summary.json"]["obj"]["hosts"]
        }
        assert "alpha-005" not in integrity["alpha"]["compromised"], (
            "alpha-005 was referenced by a temporally-invalid tamper event "
            "(day=150 < taken_day=200) and must be rejected from compromised"
        )
        assert host_summary["alpha"]["integrity_status"] == "ok", (
            "alpha has no accepted incidents and no chain breaks; its "
            "integrity_status must be 'ok'"
        )

    def test_override_sub_priority_last_entry_wins(self, loaded_outputs):
        # SPEC §"Retention rules": when a host's override_rules contains
        # multiple entries of the same kind, only the LAST entry applies.
        # Beta's profile has TWO daily overrides: beta_daily_extra (first,
        # keep_count=14, max_age=30) and beta_daily_strict (second,
        # keep_count=2, max_age=5). Only beta_daily_strict is in beta's
        # effective rule set; beta_daily_extra must NEVER be the matched_rule
        # for any beta snapshot.
        snaps = loaded_outputs["retention.json"]["obj"]["snapshots"]
        beta_kept = [
            e for e in snaps
            if e["host"] == "beta" and e["decision"] == "keep"
        ]
        for e in beta_kept:
            assert e["matched_rule"] != "beta_daily_extra", (
                f"beta snapshot {e['id']} matched the dropped override "
                "'beta_daily_extra'; only the LAST same-kind override "
                "('beta_daily_strict') should be in effect"
            )


# ---------------------------------------------------------------------------
# Tamper containment (pre-retention propagation)
# ---------------------------------------------------------------------------


class TestTamperContainment:
    """SPEC §"Tamper containment": accepted tamper events propagate
    containment to same-host transitive descendants taken within the event's
    containment_window_days."""

    def test_containment_evictions_field_present(self, loaded_outputs):
        obj = loaded_outputs["eviction_plan.json"]["obj"]
        assert "containment_evictions" in obj
        assert isinstance(obj["containment_evictions"], list)

    def test_containment_entries_have_required_keys(self, loaded_outputs):
        entries = loaded_outputs["eviction_plan.json"]["obj"]["containment_evictions"]
        required = {"id", "host", "size_mb"}
        for e in entries:
            assert set(e.keys()) == required, (
                f"containment entry must have exactly {required}; got {set(e.keys())}"
            )
            assert isinstance(e["id"], str) and e["id"]
            assert isinstance(e["host"], str) and e["host"]
            assert isinstance(e["size_mb"], int) and e["size_mb"] >= 0

    def test_containment_sorted_by_host_then_id(self, loaded_outputs):
        entries = loaded_outputs["eviction_plan.json"]["obj"]["containment_evictions"]
        keys = [(e["host"], e["id"]) for e in entries]
        assert keys == sorted(keys), (
            "containment_evictions must be sorted by (host, id) ascending"
        )

    def test_containment_includes_directly_tampered_snapshot(self, loaded_outputs):
        # epsilon-003 is the subject of an accepted tamper event with
        # containment_window_days=100. It must appear in containment_evictions
        # (the event's own subject is always contained, regardless of window).
        entries = loaded_outputs["eviction_plan.json"]["obj"]["containment_evictions"]
        ids = {e["id"] for e in entries}
        assert "epsilon-003" in ids, (
            "epsilon-003 was tampered and must be in containment_evictions"
        )

    def test_containment_propagates_to_descendant_within_window(self, loaded_outputs):
        # epsilon-004 is the immediate child of epsilon-003 with taken_day=240.
        # epsilon-003.taken_day=180 and containment_window_days=100, so
        # 240 - 180 = 60 <= 100 → epsilon-004 must also be contained.
        entries = loaded_outputs["eviction_plan.json"]["obj"]["containment_evictions"]
        ids = {e["id"] for e in entries}
        assert "epsilon-004" in ids, (
            "epsilon-004 (descendant of epsilon-003 within the 100-day window) "
            "must be contained"
        )

    def test_containment_stops_outside_window(self, loaded_outputs):
        # epsilon-005 is a transitive descendant of epsilon-003 with
        # taken_day=320 (320 - 180 = 140 > 100). It must NOT be contained.
        # eta-006 is a descendant of eta-005 (taken_day=320, window=20):
        # 355 - 320 = 35 > 20, so eta-006 must NOT be contained.
        entries = loaded_outputs["eviction_plan.json"]["obj"]["containment_evictions"]
        ids = {e["id"] for e in entries}
        assert "epsilon-005" not in ids, (
            "epsilon-005 is outside epsilon-003's 100-day containment window "
            "(140 > 100) and must NOT be contained"
        )
        assert "eta-006" not in ids, (
            "eta-006 is outside eta-005's 20-day containment window "
            "(35 > 20) and must NOT be contained"
        )

    def test_contained_snapshots_marked_tamper_containment_in_retention(self, loaded_outputs):
        # Every entry of containment_evictions must appear in retention.json
        # with decision="evict", reason="tamper_containment", matched_rule=null.
        retention_by_id = {
            e["id"]: e
            for e in loaded_outputs["retention.json"]["obj"]["snapshots"]
        }
        for c in loaded_outputs["eviction_plan.json"]["obj"]["containment_evictions"]:
            entry = retention_by_id.get(c["id"])
            assert entry is not None, (
                f"contained snapshot {c['id']} missing from retention.json"
            )
            assert entry["decision"] == "evict"
            assert entry["reason"] == "tamper_containment"
            assert entry["matched_rule"] is None

    def test_contained_snapshots_excluded_from_capacity_evictions(self, loaded_outputs):
        # Contained snapshots must not also appear in eviction_plan.evictions
        # (the capacity-driven list). They are removed from the retained set
        # before capacity eviction runs.
        contained_ids = {
            c["id"]
            for c in loaded_outputs["eviction_plan.json"]["obj"]["containment_evictions"]
        }
        evict_ids = {
            e["id"]
            for e in loaded_outputs["eviction_plan.json"]["obj"]["evictions"]
        }
        overlap = contained_ids & evict_ids
        assert not overlap, (
            f"contained snapshots must not appear in capacity evictions; "
            f"found overlap: {sorted(overlap)}"
        )

    def test_summary_total_size_contained_matches_containment_evictions(self, loaded_outputs):
        # summary.total_size_contained_mb is exactly the sum of size_mb over
        # every entry in eviction_plan.containment_evictions.
        entries = loaded_outputs["eviction_plan.json"]["obj"]["containment_evictions"]
        expected = sum(e["size_mb"] for e in entries)
        actual = loaded_outputs["summary.json"]["obj"]["total_size_contained_mb"]
        assert actual == expected, (
            f"summary.total_size_contained_mb={actual} but sum of "
            f"containment_evictions size_mb={expected}"
        )

    def test_compromised_list_still_records_tampered_id(self, loaded_outputs):
        # Per SPEC, the compromised list still lists every tamper-referenced
        # snapshot even after containment evicts them. eta-005 was tampered
        # and contained; it must still appear in eta.compromised.
        hosts = {
            h["host"]: h
            for h in loaded_outputs["integrity.json"]["obj"]["hosts"]
        }
        assert "eta-005" in hosts["eta"]["compromised"], (
            "eta-005 was tampered; it must remain in eta.compromised even "
            "though it was also contained"
        )


# ---------------------------------------------------------------------------
# Eviction plan
# ---------------------------------------------------------------------------


class TestEvictionPlan:
    """eviction_plan.json contains capacity-overflow evictions in the
    documented priority order, plus the separate containment list."""

    def test_top_level_keys(self, loaded_outputs):
        obj = loaded_outputs["eviction_plan.json"]["obj"]
        assert set(obj.keys()) == {
            "capacity_mb",
            "containment_evictions",
            "evictions",
            "final_size_mb",
            "initial_size_mb",
        }

    def test_capacity_mb_matches_pool_state(self, loaded_outputs):
        with open(DATA_DIR / "pool_state.json", "r", encoding="utf-8") as f:
            pool = json.load(f)
        obj = loaded_outputs["eviction_plan.json"]["obj"]
        assert obj["capacity_mb"] == pool["capacity_mb"]

    def test_eviction_entries_have_required_keys(self, loaded_outputs):
        ev = loaded_outputs["eviction_plan.json"]["obj"]["evictions"]
        required = {"id", "host", "pass", "size_mb", "running_size_mb"}
        for e in ev:
            assert set(e.keys()) == required, (
                f"eviction entry must have exactly {required}; got {set(e.keys())}"
            )
            assert isinstance(e["id"], str)
            assert isinstance(e["host"], str)
            assert isinstance(e["size_mb"], int) and e["size_mb"] >= 0
            assert isinstance(e["running_size_mb"], int)
            assert e["pass"] in {"tier_quota", "global_capacity"}

    def test_running_size_mb_decreases_monotonically(self, loaded_outputs):
        ev = loaded_outputs["eviction_plan.json"]["obj"]["evictions"]
        if not ev:
            return
        previous = loaded_outputs["eviction_plan.json"]["obj"]["initial_size_mb"]
        for e in ev:
            assert e["running_size_mb"] == previous - e["size_mb"], (
                "running_size_mb must equal previous_total - this_size"
            )
            previous = e["running_size_mb"]
        assert previous == loaded_outputs["eviction_plan.json"]["obj"]["final_size_mb"]

    def test_eviction_plan_excludes_exempt_hosts(self, loaded_outputs):
        ev = loaded_outputs["eviction_plan.json"]["obj"]["evictions"]
        for e in ev:
            assert e["host"] != "delta", (
                "exempt host delta must never appear in capacity evictions"
            )

    def test_final_size_within_capacity_when_evictions_occurred(self, loaded_outputs):
        obj = loaded_outputs["eviction_plan.json"]["obj"]
        if obj["evictions"]:
            assert obj["final_size_mb"] <= obj["capacity_mb"], (
                "final_size_mb must not exceed capacity after both eviction passes"
            )


class TestTwoPassCapacityEviction:
    """SPEC §"Capacity-driven eviction (two-pass)": Pass 1 (tier_quota)
    removes excess per-tier retained size, then Pass 2 (global_capacity)
    removes any remaining excess against pool_state.capacity_mb."""

    def test_tier_quota_pass_executed(self, loaded_outputs):
        # The fixture's tier_quotas are calibrated so that the bronze-tier
        # retained set exceeds its quota and at least one snapshot is
        # evicted with pass="tier_quota". A submission that skips Pass 1
        # entirely fails this check.
        ev = loaded_outputs["eviction_plan.json"]["obj"]["evictions"]
        tier_quota_entries = [e for e in ev if e["pass"] == "tier_quota"]
        assert tier_quota_entries, (
            "fixture exercises Pass 1; at least one eviction must have "
            "pass='tier_quota'"
        )

    def test_global_capacity_pass_executed(self, loaded_outputs):
        # Global capacity is also exceeded post-Pass-1, so at least one
        # eviction must have pass="global_capacity".
        ev = loaded_outputs["eviction_plan.json"]["obj"]["evictions"]
        gc_entries = [e for e in ev if e["pass"] == "global_capacity"]
        assert gc_entries, (
            "fixture exercises Pass 2; at least one eviction must have "
            "pass='global_capacity'"
        )

    def test_tier_quota_entries_come_before_global_capacity_entries(self, loaded_outputs):
        # SPEC: "evictions lists every capacity-evicted snapshot in the exact
        # order it was evicted: Pass 1's evictions first, then Pass 2's."
        ev = loaded_outputs["eviction_plan.json"]["obj"]["evictions"]
        seen_global = False
        for e in ev:
            if e["pass"] == "global_capacity":
                seen_global = True
            else:
                assert not seen_global, (
                    f"tier_quota entry {e['id']} appears after a "
                    "global_capacity entry; Pass 1 evictions must precede "
                    "all Pass 2 evictions"
                )

    def test_initial_size_equals_summary_before_eviction(self, loaded_outputs):
        ev_obj = loaded_outputs["eviction_plan.json"]["obj"]
        summary = loaded_outputs["summary.json"]["obj"]
        assert summary["total_size_before_eviction_mb"] == ev_obj["initial_size_mb"], (
            "summary.total_size_before_eviction_mb must equal "
            "eviction_plan.initial_size_mb"
        )

    def test_tier_quota_evictions_respect_quota(self, loaded_outputs):
        # After Pass 1 completes, no tier's running retained-size should
        # still exceed its quota (excluding exempt hosts).
        with open(DATA_DIR / "pool_state.json", "r", encoding="utf-8") as f:
            pool = json.load(f)
        tier_quotas = pool["tier_quotas"]

        snap_size = {}
        snap_host = {}
        for fp in (DATA_DIR / "snapshots").glob("*.json"):
            with open(fp) as f:
                doc = json.load(f)
            for s in doc["snapshots"]:
                snap_size[s["id"]] = s.get("size_mb", 0)
                snap_host[s["id"]] = doc["host"]
        profile_tier = {}
        exempt = set()
        for fp in (DATA_DIR / "host_profiles").glob("*.json"):
            with open(fp) as f:
                p = json.load(f)
            profile_tier[p["host"]] = p["tier"]
            if p.get("exempt", False):
                exempt.add(p["host"])

        retention = loaded_outputs["retention.json"]["obj"]["snapshots"]
        ev = loaded_outputs["eviction_plan.json"]["obj"]["evictions"]
        tier_quota_ids = {e["id"] for e in ev if e["pass"] == "tier_quota"}

        retained_after_pass1_by_tier = collections.defaultdict(int)
        for entry in retention:
            sid = entry["id"]
            if entry["reason"] in {"tamper_containment", "no_matching_rule"}:
                continue
            host = entry["host"]
            if host in exempt:
                continue
            if sid in tier_quota_ids:
                continue
            retained_after_pass1_by_tier[profile_tier[host]] += snap_size.get(sid, 0)

        for tier_name, quota in tier_quotas.items():
            assert retained_after_pass1_by_tier[tier_name] <= quota, (
                f"after Pass 1, non-exempt retained size for tier "
                f"{tier_name} ({retained_after_pass1_by_tier[tier_name]} MB) "
                f"still exceeds quota ({quota} MB)"
            )


# ---------------------------------------------------------------------------
# Integrity
# ---------------------------------------------------------------------------


class TestIntegrity:
    """integrity.json must classify chain breaks per the immediate-parent
    rule and cross-reference incident_log for explanation."""

    def test_top_level_keys(self, loaded_outputs):
        obj = loaded_outputs["integrity.json"]["obj"]
        assert set(obj.keys()) == {"hosts"}

    def test_each_host_entry_has_required_keys(self, loaded_outputs):
        hosts = loaded_outputs["integrity.json"]["obj"]["hosts"]
        for h in hosts:
            assert set(h.keys()) == {"host", "chain_breaks", "compromised"}

    def test_hosts_sorted_alphabetically(self, loaded_outputs):
        hosts = loaded_outputs["integrity.json"]["obj"]["hosts"]
        names = [h["host"] for h in hosts]
        assert names == sorted(names)

    def test_chain_break_entries_have_required_keys(self, loaded_outputs):
        for h in loaded_outputs["integrity.json"]["obj"]["hosts"]:
            for cb in h["chain_breaks"]:
                assert set(cb.keys()) == {"id", "parent_id", "status"}
                assert cb["status"] in {"explained_break", "unexpected_break"}

    def test_chain_breaks_sorted_by_id(self, loaded_outputs):
        for h in loaded_outputs["integrity.json"]["obj"]["hosts"]:
            ids = [cb["id"] for cb in h["chain_breaks"]]
            assert ids == sorted(ids), f"chain_breaks for {h['host']} not sorted by id"

    def test_compromised_sorted_by_id(self, loaded_outputs):
        for h in loaded_outputs["integrity.json"]["obj"]["hosts"]:
            assert h["compromised"] == sorted(h["compromised"])

    def test_known_explained_break_classified_correctly(self, loaded_outputs):
        # gamma-005 has parent_id=gamma-004 (which is not a valid snapshot)
        # AND has a chain_break event in incident_log → explained_break.
        hosts = {h["host"]: h for h in loaded_outputs["integrity.json"]["obj"]["hosts"]}
        gamma = hosts["gamma"]
        cb = [e for e in gamma["chain_breaks"] if e["id"] == "gamma-005"]
        assert len(cb) == 1
        assert cb[0]["status"] == "explained_break"
        assert cb[0]["parent_id"] == "gamma-004"

    def test_unexpected_break_classified_correctly(self, loaded_outputs):
        # zeta-007 is an incremental snapshot whose parent_id ("zeta-PHANTOM")
        # does not match any valid snapshot of zeta, AND no incident_log
        # event of kind="chain_break" references zeta-007.
        hosts = {h["host"]: h for h in loaded_outputs["integrity.json"]["obj"]["hosts"]}
        zeta = hosts["zeta"]
        cb = [e for e in zeta["chain_breaks"] if e["id"] == "zeta-007"]
        assert len(cb) == 1, "zeta-007 must appear exactly once in zeta.chain_breaks"
        assert cb[0]["status"] == "unexpected_break"
        assert cb[0]["parent_id"] == "zeta-PHANTOM"

    def test_zeta_chain_break_explained(self, loaded_outputs):
        hosts = {h["host"]: h for h in loaded_outputs["integrity.json"]["obj"]["hosts"]}
        zeta = hosts["zeta"]
        cb = [e for e in zeta["chain_breaks"] if e["id"] == "zeta-004"]
        assert len(cb) == 1
        assert cb[0]["status"] == "explained_break"
        assert cb[0]["parent_id"] == "zeta-MISSING"

    def test_compromised_includes_epsilon_003(self, loaded_outputs):
        hosts = {h["host"]: h for h in loaded_outputs["integrity.json"]["obj"]["hosts"]}
        assert "epsilon-003" in hosts["epsilon"]["compromised"]

    def test_compromised_includes_eta_005(self, loaded_outputs):
        # eta-005 is tampered. Even though containment also evicts it, it
        # must still appear in eta.compromised per SPEC.
        hosts = {h["host"]: h for h in loaded_outputs["integrity.json"]["obj"]["hosts"]}
        assert "eta-005" in hosts["eta"]["compromised"]

    def test_compromised_excludes_phantom_and_unknown(self, loaded_outputs):
        for h in loaded_outputs["integrity.json"]["obj"]["hosts"]:
            for sid in h["compromised"]:
                assert sid != "phantom-001"
                assert sid != "alpha-010"

    def test_chain_breaks_only_reference_immediate_parent(self, loaded_outputs):
        # Spec: only the snapshot's *own* parent_id is checked. Descendants
        # of broken snapshots do not get separate chain_break entries.
        hosts = {h["host"]: h for h in loaded_outputs["integrity.json"]["obj"]["hosts"]}
        zeta_break_ids = {cb["id"] for cb in hosts["zeta"]["chain_breaks"]}
        assert "zeta-005" not in zeta_break_ids
        assert "zeta-006" not in zeta_break_ids


# ---------------------------------------------------------------------------
# Host summary
# ---------------------------------------------------------------------------


class TestHostSummary:
    def test_top_level_keys(self, loaded_outputs):
        obj = loaded_outputs["host_summary.json"]["obj"]
        assert set(obj.keys()) == {"hosts"}

    def test_each_host_has_required_keys(self, loaded_outputs):
        required = {
            "host",
            "tier",
            "exempt",
            "valid_snapshots",
            "kept_count",
            "evicted_count",
            "kept_size_mb",
            "oldest_kept_day",
            "integrity_status",
        }
        for h in loaded_outputs["host_summary.json"]["obj"]["hosts"]:
            assert set(h.keys()) == required

    def test_hosts_sorted_alphabetically(self, loaded_outputs):
        names = [h["host"] for h in loaded_outputs["host_summary.json"]["obj"]["hosts"]]
        assert names == sorted(names)

    def test_kept_plus_evicted_equals_valid(self, loaded_outputs):
        for h in loaded_outputs["host_summary.json"]["obj"]["hosts"]:
            assert h["kept_count"] + h["evicted_count"] == h["valid_snapshots"]

    def test_oldest_kept_day_null_iff_no_kept(self, loaded_outputs):
        for h in loaded_outputs["host_summary.json"]["obj"]["hosts"]:
            if h["kept_count"] == 0:
                assert h["oldest_kept_day"] is None
            else:
                assert isinstance(h["oldest_kept_day"], int)

    def test_integrity_status_canonical_values(self, loaded_outputs):
        for h in loaded_outputs["host_summary.json"]["obj"]["hosts"]:
            assert h["integrity_status"] in {"ok", "chain_issues", "compromised"}

    def test_epsilon_marked_compromised(self, loaded_outputs):
        hosts = {h["host"]: h for h in loaded_outputs["host_summary.json"]["obj"]["hosts"]}
        assert hosts["epsilon"]["integrity_status"] == "compromised"

    def test_eta_marked_compromised(self, loaded_outputs):
        # eta-005 is tampered → eta.integrity_status must be "compromised".
        hosts = {h["host"]: h for h in loaded_outputs["host_summary.json"]["obj"]["hosts"]}
        assert hosts["eta"]["integrity_status"] == "compromised"

    def test_gamma_and_zeta_flag_chain_issues(self, loaded_outputs):
        hosts = {h["host"]: h for h in loaded_outputs["host_summary.json"]["obj"]["hosts"]}
        assert hosts["gamma"]["integrity_status"] == "chain_issues"
        assert hosts["zeta"]["integrity_status"] == "chain_issues"

    def test_clean_hosts_marked_ok(self, loaded_outputs):
        # alpha, beta, delta, theta have no accepted incidents and no
        # chain breaks → integrity_status="ok".
        hosts = {h["host"]: h for h in loaded_outputs["host_summary.json"]["obj"]["hosts"]}
        for name in ("alpha", "beta", "delta", "theta"):
            assert hosts[name]["integrity_status"] == "ok", (
                f"{name} should be integrity_status=ok"
            )

    def test_delta_exempt_keeps_everything(self, loaded_outputs):
        # delta is exempt and has no contained snapshots in the fixture,
        # so all its valid snapshots are kept.
        hosts = {h["host"]: h for h in loaded_outputs["host_summary.json"]["obj"]["hosts"]}
        delta = hosts["delta"]
        assert delta["exempt"] is True
        assert delta["kept_count"] == delta["valid_snapshots"]
        assert delta["evicted_count"] == 0


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_top_level_keys(self, loaded_outputs):
        obj = loaded_outputs["summary.json"]["obj"]
        required = {
            "capacity_mb",
            "current_day",
            "total_valid_snapshots",
            "total_invalid_snapshots",
            "total_size_before_eviction_mb",
            "total_size_after_eviction_mb",
            "total_size_contained_mb",
            "ignored_incident_events",
            "invalid_snapshots_per_host",
        }
        assert set(obj.keys()) == required

    def test_capacity_and_current_day_match_input(self, loaded_outputs):
        with open(DATA_DIR / "pool_state.json", "r", encoding="utf-8") as f:
            pool = json.load(f)
        obj = loaded_outputs["summary.json"]["obj"]
        assert obj["capacity_mb"] == pool["capacity_mb"]
        assert obj["current_day"] == pool["current_day"]

    def test_invalid_snapshot_counts(self, loaded_outputs):
        # Dataset has 4 invalid snapshots: alpha-INV1, alpha-INV2, beta-FUT,
        # theta-NOHASH.
        obj = loaded_outputs["summary.json"]["obj"]
        per_host = obj["invalid_snapshots_per_host"]
        assert per_host.get("alpha", 0) == 2
        assert per_host.get("beta", 0) == 1
        assert per_host.get("theta", 0) == 1
        assert obj["total_invalid_snapshots"] == 4
        for host in ("gamma", "delta", "epsilon", "zeta", "eta"):
            assert host not in per_host, (
                f"{host} has zero invalid snapshots and must be omitted from "
                "summary.invalid_snapshots_per_host"
            )

    def test_ignored_incident_events_count(self, loaded_outputs):
        # incident_log has 8 events. Of those:
        #   - alpha-001 (kind=future_event): kind not allowed → ignored
        #   - phantom-001: snapshot_id unknown → ignored
        #   - alpha-010 (restore_failure): snapshot_id unknown → ignored
        #   - alpha-005 tamper day=150: predates referenced snapshot
        #     (alpha-005.taken_day=200) → temporally rejected
        # The other 4 (gamma-005 chain_break, epsilon-003 tamper,
        # eta-005 tamper, zeta-004 chain_break) are accepted.
        obj = loaded_outputs["summary.json"]["obj"]
        assert obj["ignored_incident_events"] == 4

    def test_total_valid_snapshots_count(self, loaded_outputs):
        obj = loaded_outputs["summary.json"]["obj"]
        # alpha=8, beta=10, gamma=8, delta=5, epsilon=7, zeta=7, eta=7, theta=6
        assert obj["total_valid_snapshots"] == 8 + 10 + 8 + 5 + 7 + 7 + 7 + 6

    def test_size_consistency(self, loaded_outputs):
        # SPEC: total_size_before_eviction_mb equals
        # eviction_plan.initial_size_mb (retained-set total after containment
        # and retention, before capacity-eviction passes).
        # total_size_after_eviction_mb equals the sum of size_mb over all
        # snapshots whose final decision == "keep" in retention.json.
        obj = loaded_outputs["summary.json"]["obj"]
        ev_obj = loaded_outputs["eviction_plan.json"]["obj"]
        ret = loaded_outputs["retention.json"]["obj"]["snapshots"]

        snap_size_by_id = {}
        for fp in (DATA_DIR / "snapshots").glob("*.json"):
            with open(fp) as f:
                doc = json.load(f)
            for s in doc["snapshots"]:
                snap_size_by_id[s["id"]] = s.get("size_mb", 0)
        kept_total = sum(
            snap_size_by_id.get(e["id"], 0)
            for e in ret
            if e["decision"] == "keep"
        )

        assert obj["total_size_before_eviction_mb"] == ev_obj["initial_size_mb"]
        assert obj["total_size_after_eviction_mb"] == kept_total
        assert obj["total_size_after_eviction_mb"] <= ev_obj["final_size_mb"]


# ---------------------------------------------------------------------------
# Hash-locked anti-cheat
# ---------------------------------------------------------------------------


class TestCanonicalHashes:
    """The structural value of every output is locked by SHA-256 over its
    canonical JSON form. An agent cannot pass these by tweaking whitespace
    or by emitting partially-correct results."""

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_canonical_hash(self, loaded_outputs, name):
        expected = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        assert actual == expected, (
            f"canonical SHA-256 of /app/audit/{name} does not match: "
            f"expected {expected}, got {actual}"
        )


class TestFieldHashes:
    """Per-field hashes give a finer-grained signal about which output is
    wrong when the canonical hash test fails."""

    def test_retention_snapshots_field(self, loaded_outputs):
        expected = EXPECTED_FIELD_HASHES["retention.snapshots"]
        actual = _canonical_sha256(loaded_outputs["retention.json"]["obj"]["snapshots"])
        assert actual == expected

    def test_eviction_evictions_field(self, loaded_outputs):
        expected = EXPECTED_FIELD_HASHES["eviction_plan.evictions"]
        actual = _canonical_sha256(loaded_outputs["eviction_plan.json"]["obj"]["evictions"])
        assert actual == expected

    def test_eviction_containment_evictions_field(self, loaded_outputs):
        expected = EXPECTED_FIELD_HASHES["eviction_plan.containment_evictions"]
        actual = _canonical_sha256(
            loaded_outputs["eviction_plan.json"]["obj"]["containment_evictions"]
        )
        assert actual == expected

    def test_integrity_hosts_field(self, loaded_outputs):
        expected = EXPECTED_FIELD_HASHES["integrity.hosts"]
        actual = _canonical_sha256(loaded_outputs["integrity.json"]["obj"]["hosts"])
        assert actual == expected

    def test_host_summary_hosts_field(self, loaded_outputs):
        expected = EXPECTED_FIELD_HASHES["host_summary.hosts"]
        actual = _canonical_sha256(loaded_outputs["host_summary.json"]["obj"]["hosts"])
        assert actual == expected

    def test_summary_invalid_snapshots_per_host_field(self, loaded_outputs):
        expected = EXPECTED_FIELD_HASHES["summary.invalid_snapshots_per_host"]
        actual = _canonical_sha256(
            loaded_outputs["summary.json"]["obj"]["invalid_snapshots_per_host"]
        )
        assert actual == expected
