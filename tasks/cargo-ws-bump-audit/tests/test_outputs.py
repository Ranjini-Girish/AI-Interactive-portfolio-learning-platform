"""Behavioral tests for the cargo-workspace-bump-planner task.

These tests assert the agent's outputs against the documented contract in
``/app/workspace/SPEC.md``. Hash-locked anti-cheat fixtures are computed
independently from the input data and compared against the agent's emitted
JSON files; arbitrary or hand-tweaked output cannot pass these tests.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CWB_DATA_DIR", "/app/workspace"))
PLAN_DIR = Path(os.environ.get("CWB_PLAN_DIR", "/app/plan"))
PLANNER_DIR = Path(os.environ.get("CWB_PLANNER_DIR", "/app/planner"))

REQUIRED_OUTPUT_FILES = [
    "bump_plan.json",
    "msrv_compatibility.json",
    "feature_conflict_report.json",
    "advisory_status.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md":                       "1fcef7ea2406bfe83a09e4638de3c601ea248072ab512a8851b4750a142ccfde",
    "advisories.json":               "54cf58def5c5b93150be0e648d95efe5aa11e80124f81b3ad0f6905ad306c85b",
    "current_lock.json":             "2c5c7f9da6b45558fa2327469b0c5e1b96cebb1d88c40c8c9ba7f081564c5043",
    "incident_log.json":             "bddb419f902e64f6a8dfda3db41e7df0dac986b4c85add2f31ef4f3093faf77b",
    "members/api-gateway.json":      "bed7587aa5298ae0666616e588005b6e2291982bc0c4486af968408eabb6f0cf",
    "members/batch-worker.json":     "4015d1e0f6c5a6c10c62e5f20fe0302349ba5279d7729eac1b261e52775d85a5",
    "members/cli-tooling.json":      "1f0f168b0fdd51a6e46ac710927044310e3f9905f9646ee58aa09c73daf5de8b",
    "members/events-bus.json":       "e53982d57a1a63ecfc6de776c71d7692d39ddc023208c9cb06ed55368dd112a4",
    "members/metrics-agent.json":    "07104487a76916d91d18891fdbedb5464006f3f81cec4ad076393de29df28dad",
    "members/storage-engine.json":   "f7e0d97f7fd8e1dcd75ab439fee220ff60481af9e1b1fdedc40adaf9ff5a3aeb",
    "members/ui-server.json":        "590caef5470810a52158541d0f63ab484e1adfb2bb3f4e6f42170fb505057cfc",
    "pool_state.json":               "74c78da6512eb916a840372d2ac9ffb12b2973601268cd01bfb6e8ce8ab2d8d3",
    "registry/arbor-sync.json":      "53a20b48732ec766d107939c2a06a842f9fb269a948d10903ce1dbd1d4a0c5f2",
    "registry/cobalt-rt.json":       "1892c74e2ceb7e6d881300da77de33ebd20fa8e108fae8ee84738b529a3159bc",
    "registry/groove-router.json":   "4ea2c2e7301b5de2f4a1f9ab2de444aef6ebd84ca2df04e06366ce2670ed5b7c",
    "registry/lattice-core.json":    "feb8f6dffd149088b8365ab94e7343fa817d75fdcc1248bc759fa88a1351c827",
    "registry/marble-fs.json":       "bb4b9f02255493efa27189076521422c168d48605d66af5b21b5336d55667589",
    "registry/myriad-pool.json":     "0108b865f160f4edf73621cc67a3d2db1fbf8fb017492ff2ca3fa4a0ba859854",
    "registry/prism-codec.json":     "8708443d7e3ae9241eb703d35745a2948fbee653a8506283efc0de20b108b9f2",
    "registry/quill-runtime.json":   "09acae143d88c98c76f3756ce5a6bc892d9e313f2db51e382c3f16d0ddfdfa2b",
    "registry/synapse-bus.json":     "64f4ef4187d25c521b197161a50bd04d8ba4f4451790c1c8ed3459f252639209",
    "registry/tessera-net.json":     "5acf544b8f885beb074862ec083e9a252d2748ab116b6f0f3e6946210e707599",
    "workspace_manifest.json":       "e1fbee92ae97f0b0e28eca1d639e3149bd0624dd973e1d55f9fb0d8d3083cd1c",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "bump_plan.json":                "19e23a0d989f4db10381632f20519a1f20cea3eeaee993185862aeb147707443",
    "msrv_compatibility.json":       "9629ccd4aa322e691c7450e2a7adb4fde13f30cc2141c655efeda4eeed2beb9a",
    "feature_conflict_report.json":  "ec13e757084e99613391f275c086e72db9a99b763e4c0590347c709d43bca69f",
    "advisory_status.json":          "00cc5262b59eb4c3616483353bc9175ca28da63f7a15ac96dc6917f7ce22dfd2",
    "summary.json":                  "8d0e96a3444714649115e97f83981193ab227c3216534702692169d38bb79a2f",
}

EXPECTED_FIELD_HASHES = {
    "bump_plan.entries":                "6ad0f9f944633b08249fc88ed8af870b51d9d66b72b3a63e357553d59de32ae1",
    "msrv_compatibility.members":       "4d69d352b826bc17a7e1adc3e00601db6c6450b65c7cf27e569d1cfe1fd42101",
    "feature_conflict_report.events":   "fcbe89ad66fd3295259f2117f77e2ef888cc181bc0957fc3de40ebdb176cd6f9",
    "advisory_status.advisories":       "2b9b035fcd6127c132b7ff0be7e05964a8712edd4c9fd635e63da99bcee086e2",
    "summary.action_counts":            "ba590d7fa41c0465c17ee8f7b48fc89d5a57d8e768167788ac54b3489cc29f96",
    "summary.advisory_counts":          "ae40ea300e37a5956452839d877a1b7d95eccbe1d5a6d7e9dbc057eca13aa483",
}


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
    for fn in REQUIRED_OUTPUT_FILES:
        path = PLAN_DIR / fn
        assert path.exists(), f"missing required output: {fn}"
        with open(path, "r", encoding="utf-8") as fh:
            out[fn] = json.load(fh)
    return out


@pytest.fixture(scope="module")
def parsed_inputs():
    data = {}
    data["manifest"] = json.loads(
        (DATA_DIR / "workspace_manifest.json").read_text(encoding="utf-8")
    )
    data["lock"] = json.loads(
        (DATA_DIR / "current_lock.json").read_text(encoding="utf-8")
    )["locks"]
    data["advisories"] = json.loads(
        (DATA_DIR / "advisories.json").read_text(encoding="utf-8")
    )["advisories"]
    data["pool"] = json.loads(
        (DATA_DIR / "pool_state.json").read_text(encoding="utf-8")
    )
    members = {}
    for fp in sorted((DATA_DIR / "members").glob("*.json")):
        m = json.loads(fp.read_text(encoding="utf-8"))
        members[m["name"]] = m
    data["members"] = members
    registry = {}
    for fp in sorted((DATA_DIR / "registry").glob("*.json")):
        r = json.loads(fp.read_text(encoding="utf-8"))
        registry[r["name"]] = r
    data["registry"] = registry
    return data


class TestRustPlannerProject:
    """The agent's deliverable must be a Rust Cargo project at /app/planner/."""

    def test_cargo_manifest_exists(self):
        """A Cargo manifest must exist at the project root."""
        assert (PLANNER_DIR / "Cargo.toml").is_file(), "missing /app/planner/Cargo.toml"

    def test_main_source_exists(self):
        """A Rust source file must exist at src/main.rs."""
        assert (PLANNER_DIR / "src" / "main.rs").is_file(), "missing /app/planner/src/main.rs"

    def test_cargo_manifest_declares_package(self):
        """Cargo.toml must declare a [package] section so cargo can build it."""
        text = (PLANNER_DIR / "Cargo.toml").read_text(encoding="utf-8")
        assert "[package]" in text, "Cargo.toml lacks a [package] section"


class TestInputIntegrity:
    """The agent must not modify any file under the read-only input dataset."""

    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_hash(self, rel, expected):
        """Each input file must hash to its expected canonical SHA-256."""
        path = DATA_DIR / rel
        assert path.exists(), f"missing input file: {rel}"
        got = _sha256_bytes(path.read_bytes())
        assert got == expected, f"input drift detected for {rel}"


class TestReportStructure:
    """Every required output exists, parses, and has the documented schema."""

    @pytest.mark.parametrize("fn", REQUIRED_OUTPUT_FILES)
    def test_required_output_exists(self, fn):
        """Each required file under the plan directory must exist."""
        assert (PLAN_DIR / fn).exists(), f"missing output: {fn}"

    @pytest.mark.parametrize("fn", REQUIRED_OUTPUT_FILES)
    def test_required_output_parses(self, fn):
        """Each required output must parse as JSON."""
        with open(PLAN_DIR / fn, "r", encoding="utf-8") as fh:
            json.load(fh)

    @pytest.mark.parametrize("fn,expected", sorted(EXPECTED_OUTPUT_CANONICAL_HASHES.items()))
    def test_output_canonical_hash(self, fn, expected):
        """The full canonicalised JSON of each output must match its expected hash."""
        with open(PLAN_DIR / fn, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        assert _canonical_sha256(obj) == expected, f"canonical mismatch in {fn}"

    def test_bump_plan_top_level_keys(self, loaded_outputs):
        """bump_plan.json must have exactly the key 'entries'."""
        assert set(loaded_outputs["bump_plan.json"].keys()) == {"entries"}

    def test_msrv_compatibility_top_level_keys(self, loaded_outputs):
        """msrv_compatibility.json must contain exactly workspace_msrv and members."""
        assert set(loaded_outputs["msrv_compatibility.json"].keys()) == {
            "workspace_msrv", "members"
        }

    def test_feature_conflict_top_level_keys(self, loaded_outputs):
        """feature_conflict_report.json must contain exactly events."""
        assert set(loaded_outputs["feature_conflict_report.json"].keys()) == {"events"}

    def test_advisory_status_top_level_keys(self, loaded_outputs):
        """advisory_status.json must contain exactly advisories."""
        assert set(loaded_outputs["advisory_status.json"].keys()) == {"advisories"}

    def test_summary_top_level_keys(self, loaded_outputs):
        """summary.json must declare exactly the documented set of summary keys."""
        expected_keys = {
            "workspace_msrv", "severity_block_threshold", "total_members",
            "total_crates_in_registry", "total_entries", "action_counts",
            "shared_crate_count", "per_member_crate_count", "hard_conflict_count",
            "advisory_counts", "ignored_incident_events",
            "msrv_inconsistent_member_count",
        }
        assert set(loaded_outputs["summary.json"].keys()) == expected_keys


class TestBumpPlan:
    """The bump_plan output is the heart of the contract."""

    def test_field_hash(self, loaded_outputs):
        """bump_plan.entries must hash to its expected canonical SHA-256."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        assert _canonical_sha256(entries) == EXPECTED_FIELD_HASHES["bump_plan.entries"]

    def test_entry_count(self, loaded_outputs):
        """The dataset has 7 members × varying deps; expect 25 entries."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        assert len(entries) == 25

    def test_entries_sorted_by_member_then_crate(self, loaded_outputs):
        """bump_plan.entries must be sorted by (member, crate) ascending."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        keys = [(e["member"], e["crate"]) for e in entries]
        assert keys == sorted(keys)

    def test_entries_have_exact_keys(self, loaded_outputs):
        """Each entry must have exactly the nine documented keys."""
        expected = {"member", "crate", "current_version", "chosen_version",
                    "action", "reason", "feature_loss_set", "sharing", "source"}
        for e in loaded_outputs["bump_plan.json"]["entries"]:
            assert set(e.keys()) == expected, f"unexpected keys in entry {e}"

    def test_source_values_are_documented_enum(self, loaded_outputs):
        """source must be one of the three contract values."""
        allowed = {"planner", "incident_log_force_freeze", "incident_log_forced_bump"}
        for e in loaded_outputs["bump_plan.json"]["entries"]:
            assert e["source"] in allowed

    def test_hold_action_present(self, loaded_outputs):
        """At least one entry must have action 'hold' where chosen == current."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        holds = [e for e in entries if e["action"] == "hold"]
        assert holds, "no entry classified as 'hold'"
        for e in holds:
            assert e["chosen_version"] == e["current_version"]

    def test_bump_action_present(self, loaded_outputs):
        """At least one entry must have action 'bump' where chosen > current."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        bumps = [e for e in entries if e["action"] == "bump"]
        assert bumps, "no entry classified as 'bump'"
        for e in bumps:
            assert e["chosen_version"] is not None and e["chosen_version"] != e["current_version"]

    def test_downgrade_action_present(self, loaded_outputs):
        """At least one entry must have action 'downgrade'."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        assert any(e["action"] == "downgrade" for e in entries)

    def test_freeze_action_present(self, loaded_outputs):
        """At least one entry must have action 'freeze' (force_freeze, no advisory)."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        frozen = [e for e in entries if e["action"] == "freeze"]
        assert frozen
        for e in frozen:
            assert e["source"] == "incident_log_force_freeze"

    def test_freeze_unsafe_action_present(self, loaded_outputs):
        """At least one entry must have action 'freeze_unsafe' (advisory blocks lock)."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        unsafe = [e for e in entries if e["action"] == "freeze_unsafe"]
        assert unsafe
        for e in unsafe:
            assert e["reason"] == "freeze_advisory_conflict"
            assert e["source"] == "incident_log_force_freeze"

    def test_forced_bump_action_present(self, loaded_outputs):
        """At least one entry must have action 'forced_bump' from the incident log."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        fb = [e for e in entries if e["action"] == "forced_bump"]
        assert fb
        for e in fb:
            assert e["source"] == "incident_log_forced_bump"

    def test_block_no_safe_version_present(self, loaded_outputs):
        """At least one entry must have action 'block_no_safe_version' (chosen null)."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        blocked = [e for e in entries if e["action"] == "block_no_safe_version"]
        assert blocked
        for e in blocked:
            assert e["chosen_version"] is None
            assert e["reason"] == "no_eligible_version"
            assert e["feature_loss_set"] == []

    def test_sharing_shared_present(self, loaded_outputs):
        """Workspace deps without per-member forced_bump must carry sharing 'shared'."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        assert any(e["sharing"] == "shared" for e in entries)

    def test_sharing_per_member_present(self, loaded_outputs):
        """Per-member deps must carry sharing 'per_member'."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        assert any(e["sharing"] == "per_member" for e in entries)

    def test_sharing_forced_per_member_present(self, loaded_outputs):
        """A workspace dep split off by a per-member forced_bump must be 'forced_per_member'."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        fpm = [e for e in entries if e["sharing"] == "forced_per_member"]
        assert fpm
        for e in fpm:
            assert e["source"] == "incident_log_forced_bump"

    def test_reason_feature_downgrade_present(self, loaded_outputs):
        """At least one entry must have reason 'feature_downgrade' with non-empty loss set."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        fd = [e for e in entries if e["reason"] == "feature_downgrade"]
        assert fd
        for e in fd:
            assert e["feature_loss_set"], "feature_downgrade reason but empty loss set"

    def test_workspace_shared_entries_have_consistent_chosen(self, loaded_outputs):
        """Within a sharing set, all 'shared' entries for one crate must agree on chosen_version."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        by_crate = {}
        for e in entries:
            if e["sharing"] == "shared":
                by_crate.setdefault(e["crate"], set()).add(e["chosen_version"])
        for crate, versions in by_crate.items():
            assert len(versions) == 1, f"shared entries for {crate} disagree: {versions}"

    def test_per_member_crates_independent(self, loaded_outputs, parsed_inputs):
        """Per-member crates may have different chosen_versions per consuming member."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        by_crate = {}
        for e in entries:
            if e["sharing"] == "per_member":
                by_crate.setdefault(e["crate"], set()).add(e["chosen_version"])
        assert any(len(vs) >= 2 for vs in by_crate.values()), (
            "expected at least one per_member crate to have divergent chosen_versions"
        )

    def test_feature_loss_set_sorted(self, loaded_outputs):
        """Every feature_loss_set must be sorted alphabetically."""
        for e in loaded_outputs["bump_plan.json"]["entries"]:
            assert e["feature_loss_set"] == sorted(e["feature_loss_set"])

    def test_current_version_matches_lock(self, loaded_outputs, parsed_inputs):
        """current_version must equal current_lock.locks[crate] or null if absent."""
        lock = parsed_inputs["lock"]
        for e in loaded_outputs["bump_plan.json"]["entries"]:
            assert e["current_version"] == lock.get(e["crate"])


class TestMsrvCompatibility:
    """Per-member MSRV reporting must reflect the workspace-msrv ceiling."""

    def test_field_hash(self, loaded_outputs):
        """msrv_compatibility.members must hash to its expected canonical SHA-256."""
        members = loaded_outputs["msrv_compatibility.json"]["members"]
        assert _canonical_sha256(members) == EXPECTED_FIELD_HASHES["msrv_compatibility.members"]

    def test_workspace_msrv_matches_manifest(self, loaded_outputs, parsed_inputs):
        """The top-level workspace_msrv must mirror the manifest value."""
        assert (
            loaded_outputs["msrv_compatibility.json"]["workspace_msrv"]
            == parsed_inputs["manifest"]["workspace_msrv"]
        )

    def test_members_sorted_by_name(self, loaded_outputs):
        """Members must be reported in alphabetical order by name."""
        members = loaded_outputs["msrv_compatibility.json"]["members"]
        names = [m["member"] for m in members]
        assert names == sorted(names)

    def test_inconsistent_status_only_when_member_exceeds(self, loaded_outputs, parsed_inputs):
        """A member is 'inconsistent' iff member_msrv > workspace_msrv."""
        wsm = tuple(int(x) for x in parsed_inputs["manifest"]["workspace_msrv"].split("."))
        for m in loaded_outputs["msrv_compatibility.json"]["members"]:
            mm = tuple(int(x) for x in m["member_msrv"].split("."))
            if mm > wsm:
                assert m["status"] == "inconsistent"
            else:
                assert m["status"] == "compatible"

    def test_compatible_exceeded_by_is_zero(self, loaded_outputs):
        """Compatible members must report exceeded_by '0.0.0'."""
        for m in loaded_outputs["msrv_compatibility.json"]["members"]:
            if m["status"] == "compatible":
                assert m["exceeded_by"] == "0.0.0"

    def test_inconsistent_exceeded_by_is_diff(self, loaded_outputs, parsed_inputs):
        """An inconsistent member's exceeded_by equals the componentwise difference."""
        wsm = tuple(int(x) for x in parsed_inputs["manifest"]["workspace_msrv"].split("."))
        for m in loaded_outputs["msrv_compatibility.json"]["members"]:
            if m["status"] == "inconsistent":
                mm = tuple(int(x) for x in m["member_msrv"].split("."))
                diff = tuple(max(0, mm[i] - wsm[i]) for i in range(3))
                assert m["exceeded_by"] == f"{diff[0]}.{diff[1]}.{diff[2]}"

    def test_blocked_versions_count_nonnegative(self, loaded_outputs):
        """msrv_blocked_versions_count must be non-negative."""
        for m in loaded_outputs["msrv_compatibility.json"]["members"]:
            assert m["msrv_blocked_versions_count"] >= 0

    def test_at_least_one_member_blocks_versions(self, loaded_outputs):
        """At least one member's effective ranges include MSRV-blocked candidate versions."""
        members = loaded_outputs["msrv_compatibility.json"]["members"]
        assert any(m["msrv_blocked_versions_count"] > 0 for m in members)

    def test_per_member_msrv_propagation_relaxes_blocked_count(self, loaded_outputs, parsed_inputs):
        """For each inconsistent member, msrv_blocked_versions_count must use the
        per-entry effective MSRV (max(workspace_msrv, member_msrv) for per_member
        entries; workspace_msrv for shared entries). Agents that apply workspace_msrv
        uniformly across an inconsistent member's entries will overcount."""

        def parse(s):
            return tuple(int(x) for x in s.split("."))

        def parse_range(r):
            r = r.strip()
            if r.startswith("="):
                v = parse(r[1:].strip())
                return v, (v[0], v[1], v[2] + 1)
            if r.startswith("^"):
                p = [int(x) for x in r[1:].strip().split(".")]
                x, y = p[0], p[1]
                lo = (x, y, 0)
                hi = (x + 1, 0, 0) if x >= 1 else (0, y + 1, 0)
                return lo, hi
            if r.startswith("~"):
                p = [int(x) for x in r[1:].strip().split(".")]
                x, y = p[0], p[1]
                return (x, y, 0), (x, y + 1, 0)
            cleaned = "".join(c for c in r if not c.isspace())
            lo_s, hi_s = cleaned.split(",")
            return parse(lo_s.removeprefix(">=")), parse(hi_s.removeprefix("<"))

        wsm = parse(parsed_inputs["manifest"]["workspace_msrv"])
        manifest_ws_deps = parsed_inputs["manifest"]["workspace_dependencies"]
        registry = parsed_inputs["registry"]
        members_in = parsed_inputs["members"]
        members_out = {m["member"]: m for m in loaded_outputs["msrv_compatibility.json"]["members"]}

        any_inconsistent = False
        for name, member in members_in.items():
            mm = parse(member["member_msrv"])
            if mm <= wsm:
                continue
            any_inconsistent = True
            blocked = set()
            for crate_name, dep in member["deps"].items():
                if crate_name not in registry:
                    continue
                eff_range_str = manifest_ws_deps[crate_name] if dep["workspace"] else dep["version_range"]
                eff_lo, eff_hi = parse_range(eff_range_str)
                ceiling = wsm if dep["workspace"] else max(wsm, mm)
                for v in registry[crate_name]["versions"]:
                    vv = parse(v["version"])
                    if not (eff_lo <= vv < eff_hi):
                        continue
                    if parse(v["msrv"]) > ceiling:
                        blocked.add((crate_name, v["version"]))
            reported = members_out[name]["msrv_blocked_versions_count"]
            assert reported == len(blocked), (
                f"member {name}: expected msrv_blocked_versions_count={len(blocked)} "
                f"under per-entry effective MSRV, got {reported}"
            )
        assert any_inconsistent, (
            "fixture must include at least one inconsistent member for this rule to engage"
        )


class TestFeatureConflictReport:
    """Hard conflicts are recorded only for entries with truly-required missing features."""

    def test_field_hash(self, loaded_outputs):
        """feature_conflict_report.events must hash to its expected canonical SHA-256."""
        events = loaded_outputs["feature_conflict_report.json"]["events"]
        assert _canonical_sha256(events) == EXPECTED_FIELD_HASHES["feature_conflict_report.events"]

    def test_events_sorted(self, loaded_outputs):
        """Events must be sorted by (member, crate) ascending."""
        events = loaded_outputs["feature_conflict_report.json"]["events"]
        keys = [(e["member"], e["crate"]) for e in events]
        assert keys == sorted(keys)

    def test_each_event_has_expected_keys(self, loaded_outputs):
        """Each event must have exactly the documented keys."""
        expected = {"member", "crate", "lost_features", "hard_conflict", "forced_disable"}
        for e in loaded_outputs["feature_conflict_report.json"]["events"]:
            assert set(e.keys()) == expected

    def test_lost_features_sorted(self, loaded_outputs):
        """lost_features must be alphabetically sorted."""
        for e in loaded_outputs["feature_conflict_report.json"]["events"]:
            assert e["lost_features"] == sorted(e["lost_features"])

    def test_events_correspond_to_nonempty_loss_sets(self, loaded_outputs):
        """Every event must correspond to a bump_plan entry with a non-empty feature_loss_set."""
        events = loaded_outputs["feature_conflict_report.json"]["events"]
        entries = loaded_outputs["bump_plan.json"]["entries"]
        entry_loss = {(e["member"], e["crate"]): e["feature_loss_set"] for e in entries}
        for ev in events:
            key = (ev["member"], ev["crate"])
            assert key in entry_loss
            assert entry_loss[key] == ev["lost_features"]
            assert entry_loss[key]

    def test_hard_conflict_implies_forced_disable(self, loaded_outputs):
        """hard_conflict must imply forced_disable (they are coupled by spec)."""
        for e in loaded_outputs["feature_conflict_report.json"]["events"]:
            assert isinstance(e["hard_conflict"], bool)
            assert isinstance(e["forced_disable"], bool)
            if e["hard_conflict"]:
                assert e["forced_disable"] is True

    def test_no_event_for_zero_loss_set(self, loaded_outputs):
        """No bump_plan entry with empty feature_loss_set may appear as an event."""
        events = loaded_outputs["feature_conflict_report.json"]["events"]
        entries = loaded_outputs["bump_plan.json"]["entries"]
        event_keys = {(e["member"], e["crate"]) for e in events}
        for entry in entries:
            if not entry["feature_loss_set"]:
                assert (entry["member"], entry["crate"]) not in event_keys


class TestAdvisoryStatus:
    """Advisory status spans six distinct verdicts across the fixture."""

    def test_field_hash(self, loaded_outputs):
        """advisory_status.advisories must hash to its expected canonical SHA-256."""
        advs = loaded_outputs["advisory_status.json"]["advisories"]
        assert _canonical_sha256(advs) == EXPECTED_FIELD_HASHES["advisory_status.advisories"]

    def test_advisories_sorted(self, loaded_outputs):
        """Advisories must be sorted by advisory_id ascending."""
        advs = loaded_outputs["advisory_status.json"]["advisories"]
        ids = [a["advisory_id"] for a in advs]
        assert ids == sorted(ids)

    def test_each_advisory_has_expected_keys(self, loaded_outputs):
        """Each advisory must have exactly the seven documented keys."""
        expected = {"advisory_id", "crate", "severity", "status",
                    "mitigation_method", "mitigated_versions", "day_published"}
        for a in loaded_outputs["advisory_status.json"]["advisories"]:
            assert set(a.keys()) == expected

    def test_overridden_status_present(self, loaded_outputs):
        """Some advisory must be 'overridden' (cancelled by an advisory_override event)."""
        advs = loaded_outputs["advisory_status.json"]["advisories"]
        overridden = [a for a in advs if a["status"] == "overridden"]
        assert overridden
        for a in overridden:
            assert a["mitigation_method"] == "override"

    def test_inactive_low_severity_status_present(self, loaded_outputs, parsed_inputs):
        """Some advisory's severity must fall below the block threshold (inactive)."""
        advs = loaded_outputs["advisory_status.json"]["advisories"]
        inactive = [a for a in advs if a["status"] == "inactive_low_severity"]
        assert inactive
        for a in inactive:
            assert a["mitigation_method"] is None

    def test_still_open_frozen_status_present(self, loaded_outputs):
        """Some advisory must remain still_open_frozen because a freeze locked the unsafe version."""
        advs = loaded_outputs["advisory_status.json"]["advisories"]
        sof = [a for a in advs if a["status"] == "still_open_frozen"]
        assert sof
        for a in sof:
            assert a["mitigation_method"] == "frozen"

    def test_mitigated_by_forced_disable_status_present(self, loaded_outputs):
        """Some advisory must be mitigated_by_forced_disable through a hard-conflict feature drop."""
        advs = loaded_outputs["advisory_status.json"]["advisories"]
        mfd = [a for a in advs if a["status"] == "mitigated_by_forced_disable"]
        assert mfd
        for a in mfd:
            assert a["mitigation_method"] == "forced_disable"

    def test_resolved_by_bump_status_present(self, loaded_outputs):
        """Some advisory must be resolved_by_bump (every consumer escaped its range)."""
        advs = loaded_outputs["advisory_status.json"]["advisories"]
        rbb = [a for a in advs if a["status"] == "resolved_by_bump"]
        assert rbb
        for a in rbb:
            assert a["mitigation_method"] == "bump"

    def test_still_open_status_present(self, loaded_outputs):
        """Some advisory must remain still_open because at least one consumer is blocked."""
        advs = loaded_outputs["advisory_status.json"]["advisories"]
        so = [a for a in advs if a["status"] == "still_open"]
        assert so
        for a in so:
            assert a["mitigation_method"] is None

    def test_mitigated_versions_sorted(self, loaded_outputs):
        """mitigated_versions must be sorted ascending."""
        for a in loaded_outputs["advisory_status.json"]["advisories"]:
            assert a["mitigated_versions"] == sorted(a["mitigated_versions"])

    def test_no_null_in_mitigated_versions(self, loaded_outputs):
        """mitigated_versions must exclude null chosen versions."""
        for a in loaded_outputs["advisory_status.json"]["advisories"]:
            assert all(v is not None for v in a["mitigated_versions"])


class TestSummary:
    """The summary block aggregates and cross-checks the other reports."""

    def test_action_counts_field_hash(self, loaded_outputs):
        """summary.action_counts must hash to its expected canonical SHA-256."""
        ac = loaded_outputs["summary.json"]["action_counts"]
        assert _canonical_sha256(ac) == EXPECTED_FIELD_HASHES["summary.action_counts"]

    def test_advisory_counts_field_hash(self, loaded_outputs):
        """summary.advisory_counts must hash to its expected canonical SHA-256."""
        ac = loaded_outputs["summary.json"]["advisory_counts"]
        assert _canonical_sha256(ac) == EXPECTED_FIELD_HASHES["summary.advisory_counts"]

    def test_totals_match_inputs(self, loaded_outputs, parsed_inputs):
        """total_members and total_crates_in_registry must match the input counts."""
        s = loaded_outputs["summary.json"]
        assert s["total_members"] == len(parsed_inputs["members"])
        assert s["total_crates_in_registry"] == len(parsed_inputs["registry"])

    def test_total_entries_equals_bump_plan_length(self, loaded_outputs):
        """total_entries must equal the length of bump_plan.entries."""
        s = loaded_outputs["summary.json"]
        b = loaded_outputs["bump_plan.json"]
        assert s["total_entries"] == len(b["entries"])

    def test_action_counts_sum_equals_total_entries(self, loaded_outputs):
        """The sum of action_counts must equal total_entries."""
        s = loaded_outputs["summary.json"]
        assert sum(s["action_counts"].values()) == s["total_entries"]

    def test_advisory_counts_sum_equals_advisory_total(self, loaded_outputs, parsed_inputs):
        """The sum of advisory_counts must equal the total advisory count."""
        s = loaded_outputs["summary.json"]
        assert sum(s["advisory_counts"].values()) == len(parsed_inputs["advisories"])

    def test_hard_conflict_count_matches_events(self, loaded_outputs):
        """hard_conflict_count must equal the count of hard-conflict events."""
        s = loaded_outputs["summary.json"]
        events = loaded_outputs["feature_conflict_report.json"]["events"]
        expected = sum(1 for e in events if e["hard_conflict"])
        assert s["hard_conflict_count"] == expected

    def test_msrv_inconsistent_count_matches_members(self, loaded_outputs):
        """msrv_inconsistent_member_count must equal the count of inconsistent members."""
        s = loaded_outputs["summary.json"]
        members = loaded_outputs["msrv_compatibility.json"]["members"]
        expected = sum(1 for m in members if m["status"] == "inconsistent")
        assert s["msrv_inconsistent_member_count"] == expected

    def test_shared_and_per_member_crate_counts(self, loaded_outputs):
        """shared_crate_count and per_member_crate_count must reflect bump_plan sharing values."""
        s = loaded_outputs["summary.json"]
        entries = loaded_outputs["bump_plan.json"]["entries"]
        shared = {e["crate"] for e in entries if e["sharing"] == "shared"}
        per_member = {
            e["crate"] for e in entries
            if e["sharing"] in ("per_member", "forced_per_member")
        }
        assert s["shared_crate_count"] == len(shared)
        assert s["per_member_crate_count"] == len(per_member)

    def test_workspace_msrv_passthrough(self, loaded_outputs, parsed_inputs):
        """summary.workspace_msrv must equal manifest.workspace_msrv."""
        assert (
            loaded_outputs["summary.json"]["workspace_msrv"]
            == parsed_inputs["manifest"]["workspace_msrv"]
        )

    def test_severity_block_threshold_passthrough(self, loaded_outputs, parsed_inputs):
        """summary.severity_block_threshold must equal manifest.severity_block_threshold."""
        assert (
            loaded_outputs["summary.json"]["severity_block_threshold"]
            == parsed_inputs["manifest"]["severity_block_threshold"]
        )


class TestCrossCuttingTwist:
    """The cross-cutting twist (force_freeze + advisory + forced_bump + feature cascade)
    must flip values consistently across bump_plan, feature_conflict_report,
    advisory_status, and summary simultaneously."""

    def test_force_freeze_on_workspace_dep_locks_all_consumers(self, loaded_outputs):
        """A force_freeze event on a workspace dep must produce identical chosen_version
        across every consuming member."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        freeze_actions = {"freeze", "freeze_unsafe"}
        per_crate = {}
        for e in entries:
            if e["source"] == "incident_log_force_freeze" and e["action"] in freeze_actions:
                per_crate.setdefault(e["crate"], set()).add(e["chosen_version"])
        assert per_crate, "no force_freeze decisions present"
        for crate, versions in per_crate.items():
            assert len(versions) == 1, f"freeze decision for {crate} disagrees: {versions}"

    def test_forced_bump_splits_workspace_decision(self, loaded_outputs, parsed_inputs):
        """A forced_bump on (member, crate) where crate is a workspace dep must split that
        member off — the rest of the sharing set computes a separate planner version."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        manifest = parsed_inputs["manifest"]
        workspace_crates = set(manifest["workspace_dependencies"].keys())
        for crate in workspace_crates:
            forced = [e for e in entries if e["crate"] == crate and e["sharing"] == "forced_per_member"]
            if not forced:
                continue
            shared = [e for e in entries if e["crate"] == crate and e["sharing"] == "shared"]
            assert shared, f"crate {crate} has forced_per_member entry but no shared entries"
            shared_versions = {e["chosen_version"] for e in shared}
            forced_versions = {e["chosen_version"] for e in forced}
            assert shared_versions != forced_versions, (
                f"forced_per_member for {crate} did not actually split the decision"
            )

    def test_hard_conflict_propagates_to_advisory_status(self, loaded_outputs, parsed_inputs):
        """If a hard-conflict feature loss occurs on a crate that has an active advisory,
        that advisory must reach 'mitigated_by_forced_disable'."""
        events = loaded_outputs["feature_conflict_report.json"]["events"]
        if not any(ev["hard_conflict"] for ev in events):
            pytest.skip("no hard conflicts in fixture")
        advs = loaded_outputs["advisory_status.json"]["advisories"]
        manifest = parsed_inputs["manifest"]
        rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        threshold = rank[manifest["severity_block_threshold"]]
        crates_with_hard = {ev["crate"] for ev in events if ev["hard_conflict"]}
        for a in advs:
            if (
                a["crate"] in crates_with_hard
                and rank[a["severity"]] >= threshold
                and a["status"] != "overridden"
            ):
                if a["status"] == "mitigated_by_forced_disable":
                    break
        else:
            pytest.fail("hard conflict did not propagate to any matching advisory status")

    def test_block_no_safe_version_keeps_advisory_open(self, loaded_outputs):
        """An entry whose advisory-induced eligibility set is empty must produce both
        action=block_no_safe_version AND a still_open advisory on its crate."""
        entries = loaded_outputs["bump_plan.json"]["entries"]
        advs = loaded_outputs["advisory_status.json"]["advisories"]
        blocked_crates = {e["crate"] for e in entries if e["action"] == "block_no_safe_version"}
        assert blocked_crates, "no entries with block_no_safe_version"
        for crate in blocked_crates:
            crate_advs = [a for a in advs if a["crate"] == crate]
            assert any(a["status"] == "still_open" for a in crate_advs), (
                f"crate {crate} has a blocked entry but no still_open advisory"
            )

    def test_summary_counts_match_bump_plan_actions(self, loaded_outputs):
        """summary.action_counts must equal the per-action histogram of bump_plan.entries."""
        s = loaded_outputs["summary.json"]
        entries = loaded_outputs["bump_plan.json"]["entries"]
        actual = {}
        for e in entries:
            actual[e["action"]] = actual.get(e["action"], 0) + 1
        assert dict(s["action_counts"]) == actual
