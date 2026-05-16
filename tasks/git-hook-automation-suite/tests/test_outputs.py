"""Behavioral tests for the git-hook-automation-suite task.

These tests assert the agent's outputs against the documented contract in
``instruction.md`` and ``/app/repos/SPEC.md``. Hash-locked anti-cheat
fixtures are computed independently from the input data and compared
against the agent's emitted JSON files; an agent cannot pass these tests
by writing arbitrary or hand-tweaked output.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GHA_DATA_DIR", "/app/repos"))
AUDIT_DIR = Path(os.environ.get("GHA_AUDIT_DIR", "/app/audit"))

REQUIRED_OUTPUT_FILES = [
    "repo_compliance.json",
    "hook_install_plan.json",
    "commit_review.json",
    "branch_protection.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md":                                "3e3f3c74c50cc5e73b77b1a3c5c46932af34167ce34421aa229f855c8268c132",
    "baseline.json":                          "1b4cc4efd129b2c2778c278397076786afb1739abb8f40f0b5313eef6a00452a",
    "incident_log.json":                      "1e3b7bc40adf5c0f2fdc363199ac15c81c687c5bc52e381f1fee215c9a6eaf1a",
    "pool_state.json":                        "d1e1e093e9d95e77e31d266e1aa8144191785577eb47fbc7993e57042c7fbb53",
    "repos/api-gateway/profile.json":         "b02120deb1400e0a54b36b4c5387abfd67c1427caeadec3d576c09b3a54cb439",
    "repos/api-gateway/hooks_installed.json": "b82499b028b68a16cee8f3f4f00c47f50e440c6c70d1179aa54f2648d2835aaf",
    "repos/api-gateway/recent_commits.json":  "76d6d3a069914f1fd337f1f07b5f6f534c0e8502fea6f4d1094c02edb4ac1293",
    "repos/auth-svc/profile.json":            "c80ba49e99fd8713c9f8deb445a622e69f0df2c65546d3e9379bd0d4e7e0680c",
    "repos/auth-svc/hooks_installed.json":    "0c61143764ac9d79cb1556d28eecbf705f72052ed9ab90349fd889e13a0ffaa7",
    "repos/auth-svc/recent_commits.json":     "199108f0a40c0ffcf33512a0e8c5b384aca88b04ad1aa3c33774144acf9cb504",
    "repos/billing/profile.json":             "415be3d97d2326acdb3d210cbd210f12ceefe5096e81ac44336067dffc2c5e8a",
    "repos/billing/hooks_installed.json":     "8f055fb10363b17a3982086adab16e16515d44198bff1b4c7ec9f62b58aed0ff",
    "repos/billing/recent_commits.json":      "3163d2a11122e79e7766b200700d55a60d18a9485961c9e0ca617d1a8cc27ba8",
    "repos/data-platform/profile.json":       "577f43092609b037a4ab33b52f0d0facf1b719a1a247a4d0d81a9c5521e4f2d4",
    "repos/data-platform/hooks_installed.json": "3791c09a540e988971ca25f4d3e6ac718735cfd0d376400195d1a321619a348f",
    "repos/data-platform/recent_commits.json": "fcb1626bdb07f588bae390f8a07b08bd92f89f2d8992144d710bd00e9844ad8a",
    "repos/frontend/profile.json":            "2facee75da92eadbf2503081cf31dbd23452cd30bf514e956180581993eed4d6",
    "repos/frontend/hooks_installed.json":    "053b754506d3c9141ae26139c33898e9cd3945c16f08dcc5f60238728e91f701",
    "repos/frontend/recent_commits.json":     "12a3f3dd97833d16678bbe80cf19f454220f593a31a06b046751e9575078c4e2",
    "repos/infra-tools/profile.json":         "f49dfe6e995cea861d33b0761c2382ea0877deba3f9577f4f1eaf4857fe4e5c5",
    "repos/infra-tools/hooks_installed.json": "35ee09ccc526b68bad68faf766bc6b209a6cb15b34acf785c0ce69c0942d2560",
    "repos/infra-tools/recent_commits.json":  "473a868b436488c765123f792eb2b9984ba459b1a92740c785f7332b1fe22b84",
    "repos/legacy-shop/profile.json":         "07a6d6424eb6b5d66a595ca4cffb289db537d08afde4aaa79a6cb4cb958da5e8",
    "repos/legacy-shop/hooks_installed.json": "6304f0e89627a7a803c01e9c8bf404fe237cc666f2e1e7a7c4090a41f9b0c473",
    "repos/legacy-shop/recent_commits.json":  "2765007959712f2b89a2319aa0b43bff02780efaadb209c34ce69212b6aee2bd",
    "repos/mobile-app/profile.json":          "cd05d85aea724c52952e794dd078071aaccca2127b56fef1e8038e266462892a",
    "repos/mobile-app/hooks_installed.json":  "7e5c5841eac5ae165fc6f69f82f0cace997e8b6eabd9792d6ccc632524f974e4",
    "repos/mobile-app/recent_commits.json":   "37dd93f51c7ee010f2da8be976c1319cb6094c5001fc4015392ae2bff4eb3971",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "repo_compliance.json":   "1ffea28c57a1e7b10761338d2a3dc18bcf9701638614bd39ba6c55debc6f6db0",
    "hook_install_plan.json": "943932611fe12f75697eefdf407a6bc0629986c6c875817f9a49842d64ec6c3c",
    "commit_review.json":     "a3d870c301d995fc4797001bbe2d6fff3e0c30faf0faf0a6abf3aeea08e059be",
    "branch_protection.json": "2dbf4a0fe9ce8fb94890139ab1e70e280257720861473983aa0b2aa2fdeae79c",
    "summary.json":           "d80945d793737d0e0e8fadb9aa3a2d0ec3793fa9e87912edc515c66799dc99de",
}

EXPECTED_FIELD_HASHES = {
    "repo_compliance.repos":      "9d14f67902a840c1f6888e94c70c43cb2e6662c002b80ecd0d9607e00e4b1ddf",
    "hook_install_plan.actions":  "8e2dda998db310bc4f35bfacc8d2fd5bff0d145f7989295ce765833608150079",
    "commit_review.commits":      "dcbb619512aa6e4f68911d005f72ff940c6cddc23cabe9702b6354de4c3803e4",
    "branch_protection.entries":  "0512bf61d8c21f3439b5ae7b948e0aa8a4b8cffab356ac5b8b2dfe4e7540e4ee",
    "summary.by_compliance":      "7c20cb289969002f19bfa8d787055b8066991d6bf88efe3346b8125416f5dd86",
    "summary.by_commit_status":   "50ce79584406f4becc8dae4c7b87ef81c00528c74596d650d555616a4eeacd81",
    "summary.compromised_repos":  "fe46fe958c383b37b4ae704e20799b000a376425a942310afc01737130415423",
}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: /app/audit/{name}"
        raw = p.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            pytest.fail(f"output /app/audit/{name} is not valid UTF-8: {e}")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output /app/audit/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": raw}
    return out


# ---------------------------------------------------------------------------
# Input integrity
# ---------------------------------------------------------------------------


class TestInputIntegrity:
    """Inputs must remain byte-identical to the original fixtures."""

    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_unchanged(self, rel, expected):
        """Each input file's SHA-256 must match the locked baseline."""
        p = DATA_DIR / rel
        assert p.is_file(), f"input file missing: {rel}"
        actual = _sha256_bytes(p.read_bytes())
        assert actual == expected, (
            f"input file {rel} was modified by the agent (sha256 {actual} != {expected})"
        )


# ---------------------------------------------------------------------------
# Report structure & whole-output hashes
# ---------------------------------------------------------------------------


class TestReportStructure:
    """Top-level structural and canonical-hash invariants on every output."""

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_required_file_exists(self, name):
        """Each required output file must exist and be a regular file."""
        assert (AUDIT_DIR / name).is_file()

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_canonical_hash(self, name, loaded_outputs):
        """Canonical SHA-256 of each output must match the locked baseline."""
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        expected = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        assert actual == expected, (
            f"{name} canonical hash mismatch: {actual} != {expected}"
        )

    def test_repo_compliance_top_level_shape(self, loaded_outputs):
        """repo_compliance.json must have exactly one top-level key 'repos'."""
        obj = loaded_outputs["repo_compliance.json"]["obj"]
        assert set(obj.keys()) == {"repos"}
        assert isinstance(obj["repos"], list)

    def test_hook_install_plan_top_level_shape(self, loaded_outputs):
        """hook_install_plan.json must have exactly one top-level key 'actions'."""
        obj = loaded_outputs["hook_install_plan.json"]["obj"]
        assert set(obj.keys()) == {"actions"}

    def test_commit_review_top_level_shape(self, loaded_outputs):
        """commit_review.json must have exactly one top-level key 'commits'."""
        obj = loaded_outputs["commit_review.json"]["obj"]
        assert set(obj.keys()) == {"commits"}

    def test_branch_protection_top_level_shape(self, loaded_outputs):
        """branch_protection.json must have exactly one top-level key 'entries'."""
        obj = loaded_outputs["branch_protection.json"]["obj"]
        assert set(obj.keys()) == {"entries"}

    def test_summary_top_level_keys(self, loaded_outputs):
        """summary.json must have exactly the documented top-level keys."""
        obj = loaded_outputs["summary.json"]["obj"]
        expected_keys = {
            "current_day", "policy_version", "total_repos", "total_commits",
            "ignored_incident_events", "by_compliance", "by_commit_status",
            "active_waivers", "compromised_repos",
        }
        assert set(obj.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Byte-level formatting (UTF-8, indent=2, sort_keys, one trailing newline)
# ---------------------------------------------------------------------------


class TestByteFormatting:
    """Each output file's raw on-disk bytes must match the documented
    pretty-printed format. The semantic hash gates above normalise JSON
    before hashing, so they accept any spacing/key order; these tests
    additionally enforce the on-disk encoding and layout that the
    contract requires for byte-identical reproducibility.
    """

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_byte_exact_pretty_printed_format(self, name, loaded_outputs):
        """Raw bytes must equal json.dumps(indent=2, sort_keys=True,
        ensure_ascii=False) UTF-8-encoded plus a single trailing newline.
        """
        obj = loaded_outputs[name]["obj"]
        expected_text = (
            json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )
        expected_bytes = expected_text.encode("utf-8")
        actual_bytes = loaded_outputs[name]["bytes"]
        assert actual_bytes == expected_bytes, (
            f"{name} on-disk bytes do not match the required pretty-printed "
            "(indent=2, sort_keys=True, ensure_ascii=False, single trailing "
            f"newline) UTF-8 format: got {len(actual_bytes)} bytes, "
            f"expected {len(expected_bytes)} bytes"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_exactly_one_trailing_newline(self, name, loaded_outputs):
        """File ends with exactly one LF byte and uses no CRLF anywhere."""
        raw = loaded_outputs[name]["bytes"]
        assert raw.endswith(b"\n"), f"{name} does not end with a newline"
        assert not raw.endswith(b"\n\n"), (
            f"{name} has more than one trailing newline"
        )
        assert b"\r" not in raw, (
            f"{name} contains a carriage return; LF-only line endings required"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_no_utf8_bom(self, name, loaded_outputs):
        """File must not begin with a UTF-8 byte-order mark."""
        raw = loaded_outputs[name]["bytes"]
        assert not raw.startswith(b"\xef\xbb\xbf"), (
            f"{name} starts with a UTF-8 BOM; plain UTF-8 required"
        )


# ---------------------------------------------------------------------------
# Field-level hash gates (helpful for diagnosing a single broken output)
# ---------------------------------------------------------------------------


class TestFieldHashes:
    """Per-field canonical hashes pinpoint which output is wrong."""

    def test_repo_compliance_repos_field(self, loaded_outputs):
        """repo_compliance.repos must canonicalise to the locked hash."""
        v = loaded_outputs["repo_compliance.json"]["obj"]["repos"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["repo_compliance.repos"]

    def test_hook_install_plan_actions_field(self, loaded_outputs):
        """hook_install_plan.actions must canonicalise to the locked hash."""
        v = loaded_outputs["hook_install_plan.json"]["obj"]["actions"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["hook_install_plan.actions"]

    def test_commit_review_commits_field(self, loaded_outputs):
        """commit_review.commits must canonicalise to the locked hash."""
        v = loaded_outputs["commit_review.json"]["obj"]["commits"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["commit_review.commits"]

    def test_branch_protection_entries_field(self, loaded_outputs):
        """branch_protection.entries must canonicalise to the locked hash."""
        v = loaded_outputs["branch_protection.json"]["obj"]["entries"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["branch_protection.entries"]

    def test_summary_by_compliance_field(self, loaded_outputs):
        """summary.by_compliance must canonicalise to the locked hash."""
        v = loaded_outputs["summary.json"]["obj"]["by_compliance"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["summary.by_compliance"]

    def test_summary_by_commit_status_field(self, loaded_outputs):
        """summary.by_commit_status must canonicalise to the locked hash."""
        v = loaded_outputs["summary.json"]["obj"]["by_commit_status"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["summary.by_commit_status"]

    def test_summary_compromised_repos_field(self, loaded_outputs):
        """summary.compromised_repos must canonicalise to the locked hash."""
        v = loaded_outputs["summary.json"]["obj"]["compromised_repos"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["summary.compromised_repos"]


# ---------------------------------------------------------------------------
# Repo-compliance behavioral re-derivation
# ---------------------------------------------------------------------------


class TestRepoCompliance:
    """Behavioral assertions that re-derive expected values from the spec."""

    def test_every_repo_present_with_correct_keys(self, loaded_outputs):
        """Each declared repo must appear once with exactly the contract keys."""
        repos_seen = [e["repo"] for e in loaded_outputs["repo_compliance.json"]["obj"]["repos"]]
        on_disk = sorted(p.name for p in (DATA_DIR / "repos").iterdir() if p.is_dir())
        assert sorted(repos_seen) == on_disk
        assert repos_seen == sorted(set(repos_seen)), "duplicate repo entries"
        expected_keys = {
            "repo", "tier", "compliance_level", "missing_hooks",
            "missing_checks", "active_waivers", "compromise_day",
        }
        for entry in loaded_outputs["repo_compliance.json"]["obj"]["repos"]:
            assert set(entry.keys()) == expected_keys

    def test_repos_sorted_ascending(self, loaded_outputs):
        """repos list must be sorted ascending by the 'repo' field."""
        repos = [e["repo"] for e in loaded_outputs["repo_compliance.json"]["obj"]["repos"]]
        assert repos == sorted(repos)

    def test_compromised_repos_get_quarantine_level(self, loaded_outputs):
        """A repo with at least one accepted compromise event has level=quarantine."""
        with open(DATA_DIR / "incident_log.json", encoding="utf-8") as f:
            log = json.load(f)
        with open(DATA_DIR / "pool_state.json", encoding="utf-8") as f:
            current_day = json.load(f)["current_day"]
        known = {p.name for p in (DATA_DIR / "repos").iterdir() if p.is_dir()}
        compromised = {
            ev["repo"]
            for ev in log["events"]
            if ev.get("kind") == "compromise"
            and ev.get("repo") in known
            and isinstance(ev.get("day"), int)
            and not isinstance(ev.get("day"), bool)
            and ev["day"] <= current_day
        }
        for entry in loaded_outputs["repo_compliance.json"]["obj"]["repos"]:
            if entry["repo"] in compromised:
                assert entry["compliance_level"] == "quarantine"
                assert entry["compromise_day"] is not None
            else:
                assert entry["compromise_day"] is None

    def test_compliance_level_enum(self, loaded_outputs):
        """compliance_level must be one of the three documented strings."""
        allowed = {"compliant", "non_compliant", "quarantine"}
        for e in loaded_outputs["repo_compliance.json"]["obj"]["repos"]:
            assert e["compliance_level"] in allowed

    def test_quarantine_disregards_hooks(self, loaded_outputs):
        """A quarantined repo gets level=quarantine even when otherwise compliant."""
        for e in loaded_outputs["repo_compliance.json"]["obj"]["repos"]:
            if e["repo"] == "auth-svc":
                assert e["compliance_level"] == "quarantine"
                return
        pytest.fail("auth-svc not found in repo_compliance")


# ---------------------------------------------------------------------------
# Hook install plan
# ---------------------------------------------------------------------------


class TestHookInstallPlan:
    """Install plan must reflect missing hooks (waiver-aware) and quarantine."""

    def test_actions_sorted_ascending(self, loaded_outputs):
        """actions must be sorted by (repo, hook) ascending."""
        actions = loaded_outputs["hook_install_plan.json"]["obj"]["actions"]
        keys = [(a["repo"], a["hook"]) for a in actions]
        assert keys == sorted(keys)

    def test_actions_have_exact_keys(self, loaded_outputs):
        """Each action entry must have exactly the four documented keys."""
        for a in loaded_outputs["hook_install_plan.json"]["obj"]["actions"]:
            assert set(a.keys()) == {"repo", "hook", "action", "reason"}

    def test_action_enum(self, loaded_outputs):
        """action must be 'install' or 'force_reinstall'."""
        for a in loaded_outputs["hook_install_plan.json"]["obj"]["actions"]:
            assert a["action"] in {"install", "force_reinstall"}

    def test_reason_enum(self, loaded_outputs):
        """reason must be 'missing_required' or 'compromise_quarantine'."""
        for a in loaded_outputs["hook_install_plan.json"]["obj"]["actions"]:
            assert a["reason"] in {"missing_required", "compromise_quarantine"}

    def test_force_reinstall_only_for_quarantined_repos(self, loaded_outputs):
        """force_reinstall actions only appear for repos at compliance_level=quarantine."""
        quarantined = {
            e["repo"]
            for e in loaded_outputs["repo_compliance.json"]["obj"]["repos"]
            if e["compliance_level"] == "quarantine"
        }
        for a in loaded_outputs["hook_install_plan.json"]["obj"]["actions"]:
            if a["action"] == "force_reinstall":
                assert a["repo"] in quarantined
                assert a["reason"] == "compromise_quarantine"


# ---------------------------------------------------------------------------
# Commit review
# ---------------------------------------------------------------------------


class TestCommitReview:
    """Per-commit status assertions covering every documented status value."""

    def test_commits_sorted(self, loaded_outputs):
        """commits must be sorted by (repo, sha) ascending."""
        commits = loaded_outputs["commit_review.json"]["obj"]["commits"]
        keys = [(c["repo"], c["sha"]) for c in commits]
        assert keys == sorted(keys)

    def test_status_enum(self, loaded_outputs):
        """Every commit status is one of the documented values."""
        allowed = {
            "valid", "type_not_allowed", "length_exceeded", "missing_issue_ref",
            "protected_branch_violation", "needs_review",
        }
        for c in loaded_outputs["commit_review.json"]["obj"]["commits"]:
            assert c["status"] in allowed

    def test_total_commits_match_input(self, loaded_outputs):
        """Total commit count equals the sum of recent_commits.json entries."""
        total_in = 0
        for repo in (DATA_DIR / "repos").iterdir():
            if not repo.is_dir():
                continue
            with open(repo / "recent_commits.json", encoding="utf-8") as f:
                total_in += len(json.load(f).get("commits", []))
        total_out = len(loaded_outputs["commit_review.json"]["obj"]["commits"])
        assert total_out == total_in

    def test_quarantine_propagation_to_commits(self, loaded_outputs):
        """Commits in a quarantined repo on/after the compromise_day are needs_review."""
        rc = {e["repo"]: e for e in loaded_outputs["repo_compliance.json"]["obj"]["repos"]}
        commits_by_repo = collections.defaultdict(list)
        for repo in (DATA_DIR / "repos").iterdir():
            if not repo.is_dir():
                continue
            with open(repo / "recent_commits.json", encoding="utf-8") as f:
                for c in json.load(f).get("commits", []):
                    commits_by_repo[repo.name].append(c)
        out_by_sha = {(c["repo"], c["sha"]): c["status"]
                      for c in loaded_outputs["commit_review.json"]["obj"]["commits"]}
        for repo_name, commits in commits_by_repo.items():
            entry = rc.get(repo_name)
            if entry is None or entry["compliance_level"] != "quarantine":
                continue
            cd = entry["compromise_day"]
            for c in commits:
                if c["day"] >= cd:
                    assert out_by_sha[(repo_name, c["sha"])] == "needs_review"

    def test_known_protected_branch_violation_present(self, loaded_outputs):
        """A wip commit on a protected branch must be flagged appropriately."""
        commits = loaded_outputs["commit_review.json"]["obj"]["commits"]
        api_release = next(c for c in commits if c["repo"] == "api-gateway" and c["sha"] == "d4e5f6a7")
        assert api_release["status"] == "protected_branch_violation"

    def test_known_length_exceeded_present(self, loaded_outputs):
        """A gold-tier commit with a 58-char subject must be flagged length_exceeded."""
        commits = loaded_outputs["commit_review.json"]["obj"]["commits"]
        long_one = next(c for c in commits if c["repo"] == "api-gateway" and c["sha"] == "c3d4e5f6")
        assert long_one["status"] == "length_exceeded"

    def test_known_type_not_allowed_present(self, loaded_outputs):
        """A docs commit on a gold tier (whitelist {feat, fix}) must be type_not_allowed."""
        commits = loaded_outputs["commit_review.json"]["obj"]["commits"]
        docs_one = next(c for c in commits if c["repo"] == "api-gateway" and c["sha"] == "e5f6a7b8")
        assert docs_one["status"] == "type_not_allowed"

    def test_known_missing_issue_ref_present(self, loaded_outputs):
        """A silver-tier commit with no issue_ref must be missing_issue_ref."""
        commits = loaded_outputs["commit_review.json"]["obj"]["commits"]
        no_ref = next(c for c in commits if c["repo"] == "billing" and c["sha"] == "f005beef")
        assert no_ref["status"] == "missing_issue_ref"

    def test_known_valid_commit_present(self, loaded_outputs):
        """A bronze-tier commit with no required-issue-ref must be valid."""
        commits = loaded_outputs["commit_review.json"]["obj"]["commits"]
        ok = next(c for c in commits if c["repo"] == "mobile-app" and c["sha"] == "ma000001")
        assert ok["status"] == "valid"


# ---------------------------------------------------------------------------
# Branch protection
# ---------------------------------------------------------------------------


class TestBranchProtection:
    """Branch protection entries with quarantine / waivered / missing_hook coverage."""

    def test_entries_sorted(self, loaded_outputs):
        """entries must be sorted by (repo, branch) ascending."""
        entries = loaded_outputs["branch_protection.json"]["obj"]["entries"]
        keys = [(e["repo"], e["branch"]) for e in entries]
        assert keys == sorted(keys)

    def test_status_enum(self, loaded_outputs):
        """branch status must be one of the four documented values."""
        allowed = {"compliant", "missing_hook", "waivered", "quarantined"}
        for e in loaded_outputs["branch_protection.json"]["obj"]["entries"]:
            assert e["status"] in allowed

    def test_one_entry_per_repo_branch(self, loaded_outputs):
        """Exactly one entry per (repo, branch) in protected_branches."""
        with open(DATA_DIR / "baseline.json", encoding="utf-8") as f:
            base = json.load(f)
        protected = base["branch_protection"]["protected_branches"]
        repos = sorted(p.name for p in (DATA_DIR / "repos").iterdir() if p.is_dir())
        expected = {(r, b) for r in repos for b in protected}
        actual = {(e["repo"], e["branch"]) for e in loaded_outputs["branch_protection.json"]["obj"]["entries"]}
        assert actual == expected

    def test_quarantined_branch_status(self, loaded_outputs):
        """A quarantined repo's branch entries must all have status=quarantined."""
        quar = {e["repo"]
                for e in loaded_outputs["repo_compliance.json"]["obj"]["repos"]
                if e["compliance_level"] == "quarantine"}
        for e in loaded_outputs["branch_protection.json"]["obj"]["entries"]:
            if e["repo"] in quar:
                assert e["status"] == "quarantined"


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestSummary:
    """Summary aggregates must agree with the individual reports."""

    def test_total_repos(self, loaded_outputs):
        """summary.total_repos equals the number of repos under repos/."""
        on_disk = sum(1 for p in (DATA_DIR / "repos").iterdir() if p.is_dir())
        assert loaded_outputs["summary.json"]["obj"]["total_repos"] == on_disk

    def test_total_commits(self, loaded_outputs):
        """summary.total_commits equals the sum of recent_commits.json lengths."""
        total = 0
        for repo in (DATA_DIR / "repos").iterdir():
            if not repo.is_dir():
                continue
            with open(repo / "recent_commits.json", encoding="utf-8") as f:
                total += len(json.load(f).get("commits", []))
        assert loaded_outputs["summary.json"]["obj"]["total_commits"] == total

    def test_by_compliance_keys_complete(self, loaded_outputs):
        """summary.by_compliance has all three documented keys."""
        d = loaded_outputs["summary.json"]["obj"]["by_compliance"]
        assert set(d.keys()) == {"compliant", "non_compliant", "quarantine"}

    def test_by_commit_status_keys_complete(self, loaded_outputs):
        """summary.by_commit_status has all six documented keys."""
        d = loaded_outputs["summary.json"]["obj"]["by_commit_status"]
        expected = {
            "valid", "type_not_allowed", "length_exceeded", "missing_issue_ref",
            "protected_branch_violation", "needs_review",
        }
        assert set(d.keys()) == expected

    def test_by_compliance_sums_to_total_repos(self, loaded_outputs):
        """summary.by_compliance values sum to total_repos."""
        s = loaded_outputs["summary.json"]["obj"]
        assert sum(s["by_compliance"].values()) == s["total_repos"]

    def test_by_commit_status_sums_to_total_commits(self, loaded_outputs):
        """summary.by_commit_status values sum to total_commits."""
        s = loaded_outputs["summary.json"]["obj"]
        assert sum(s["by_commit_status"].values()) == s["total_commits"]

    def test_compromised_repos_match_quarantine(self, loaded_outputs):
        """summary.compromised_repos matches repo_compliance entries with level=quarantine."""
        quar = sorted(
            e["repo"] for e in loaded_outputs["repo_compliance.json"]["obj"]["repos"]
            if e["compliance_level"] == "quarantine"
        )
        assert loaded_outputs["summary.json"]["obj"]["compromised_repos"] == quar

    def test_active_waivers_count_matches_repo_compliance(self, loaded_outputs):
        """summary.active_waivers equals total active_waivers across all repos."""
        total = sum(
            len(e["active_waivers"])
            for e in loaded_outputs["repo_compliance.json"]["obj"]["repos"]
        )
        assert loaded_outputs["summary.json"]["obj"]["active_waivers"] == total

    def test_current_day_and_policy_version_pass_through(self, loaded_outputs):
        """summary.current_day and summary.policy_version come straight from pool_state.json."""
        with open(DATA_DIR / "pool_state.json", encoding="utf-8") as f:
            ps = json.load(f)
        s = loaded_outputs["summary.json"]["obj"]
        assert s["current_day"] == ps["current_day"]
        assert s["policy_version"] == ps["policy_version"]
